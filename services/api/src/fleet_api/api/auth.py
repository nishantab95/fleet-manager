from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_auth_service, get_current_session
from fleet_api.api.schemas import (
    MembershipOption,
    MembershipOptionsRequest,
    MembershipOptionsResponse,
    MeResponse,
    OtpRequest,
    OtpRequestResponse,
    OtpVerifyRequest,
    OtpVerifyResponse,
    RefreshRequest,
    SessionRequest,
    TokenResponse,
    WebTokenResponse,
)
from fleet_api.auth.service import AuthContext, AuthService, SessionTokens
from fleet_api.db.session import get_db
from fleet_api.domain.errors import (
    AuthConfigurationError,
    AuthenticationError,
    InvalidOtpError,
    InvalidTokenError,
    MembershipSelectionError,
    OtpProviderUnavailableError,
    OtpRateLimitError,
    PhoneNormalizationError,
    RefreshTokenReuseError,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _error(code: str, message: str, http_status: int) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"code": code, "message": message})


def _token_response(tokens: SessionTokens) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        membership_id=tokens.context.membership.id,
        company_id=tokens.context.company.id,
        role=tokens.context.membership.role,
    )


def _web_token_response(tokens: SessionTokens) -> WebTokenResponse:
    return WebTokenResponse(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        membership_id=tokens.context.membership.id,
        company_id=tokens.context.company.id,
        role=tokens.context.membership.role,
    )


def _set_web_refresh_cookie(
    response: Response,
    tokens: SessionTokens,
    service: AuthService,
) -> None:
    response.set_cookie(
        key="fleet_web_refresh",
        value=tokens.refresh_token,
        max_age=service.settings.refresh_token_ttl_seconds,
        httponly=True,
        secure=service.settings.secure_cookies,
        samesite="lax",
        path="/api/v1/auth",
    )


@router.post(
    "/otp/request",
    response_model=OtpRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_otp(
    payload: OtpRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> OtpRequestResponse:
    try:
        challenge_id = service.request_otp(
            phone=payload.phone,
            requested_role=payload.requested_role,
            request_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
        return OtpRequestResponse(challenge_id=challenge_id)
    except PhoneNormalizationError as exc:
        db.rollback()
        raise _error(
            "VALIDATION_ERROR",
            "phone number is invalid",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ) from exc
    except OtpProviderUnavailableError as exc:
        db.rollback()
        raise _error(
            "AUTH_PROVIDER_UNAVAILABLE",
            "authentication is temporarily unavailable",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    except OtpRateLimitError as exc:
        db.rollback()
        raise _error(
            "RATE_LIMITED",
            "authentication requests are temporarily limited",
            status.HTTP_429_TOO_MANY_REQUESTS,
        ) from exc
    except AuthConfigurationError as exc:
        db.rollback()
        raise _error(
            "AUTH_NOT_CONFIGURED",
            "authentication is temporarily unavailable",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc


@router.post("/otp/verify", response_model=OtpVerifyResponse)
def verify_otp(
    payload: OtpVerifyRequest,
    service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> OtpVerifyResponse:
    try:
        pre_session_token, expires_in = service.verify_otp(
            challenge_id=payload.challenge_id,
            otp=payload.otp,
        )
        db.commit()
        return OtpVerifyResponse(pre_session_token=pre_session_token, expires_in=expires_in)
    except InvalidOtpError as exc:
        # Failed attempts and exhaustion are security state and must persist.
        db.commit()
        raise _error(
            "AUTHENTICATION_FAILED",
            "OTP is invalid or expired",
            status.HTTP_401_UNAUTHORIZED,
        ) from exc
    except AuthConfigurationError as exc:
        db.rollback()
        raise _error(
            "AUTH_NOT_CONFIGURED",
            "authentication is temporarily unavailable",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc


@router.post("/memberships", response_model=MembershipOptionsResponse)
def list_memberships(
    payload: MembershipOptionsRequest,
    service: AuthService = Depends(get_auth_service),
) -> MembershipOptionsResponse:
    try:
        memberships = service.list_memberships(pre_session_token=payload.pre_session_token)
    except (InvalidTokenError, AuthConfigurationError) as exc:
        raise _error(
            "UNAUTHENTICATED",
            "membership selection context is invalid",
            status.HTTP_401_UNAUTHORIZED,
        ) from exc
    return MembershipOptionsResponse(
        memberships=[
            MembershipOption(
                membership_id=membership_id,
                company_id=company_id,
                company_name=company_name,
                role=role,
            )
            for membership_id, company_id, company_name, role in memberships
        ]
    )


@router.post("/session", response_model=TokenResponse)
def create_session(
    payload: SessionRequest,
    service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> TokenResponse:
    try:
        tokens = service.create_session(
            pre_session_token=payload.pre_session_token,
            membership_id=payload.membership_id,
        )
        db.commit()
        return _token_response(tokens)
    except MembershipSelectionError as exc:
        db.rollback()
        raise _error(
            "FORBIDDEN",
            "membership selection is not permitted",
            status.HTTP_403_FORBIDDEN,
        ) from exc
    except (InvalidTokenError, AuthConfigurationError) as exc:
        db.rollback()
        raise _error(
            "UNAUTHENTICATED",
            "membership selection context is invalid",
            status.HTTP_401_UNAUTHORIZED,
        ) from exc


@router.post("/web-session", response_model=WebTokenResponse)
def create_web_session(
    payload: SessionRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> WebTokenResponse:
    """Create a browser session without exposing the refresh token to JavaScript."""
    try:
        tokens = service.create_session(
            pre_session_token=payload.pre_session_token,
            membership_id=payload.membership_id,
        )
        db.commit()
        _set_web_refresh_cookie(response, tokens, service)
        return _web_token_response(tokens)
    except MembershipSelectionError as exc:
        db.rollback()
        raise _error(
            "FORBIDDEN",
            "membership selection is not permitted",
            status.HTTP_403_FORBIDDEN,
        ) from exc
    except (InvalidTokenError, AuthConfigurationError) as exc:
        db.rollback()
        raise _error(
            "UNAUTHENTICATED",
            "membership selection context is invalid",
            status.HTTP_401_UNAUTHORIZED,
        ) from exc


@router.post("/web-refresh", response_model=WebTokenResponse)
def refresh_web_session(
    response: Response,
    fleet_web_refresh: str | None = Cookie(default=None),
    service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> WebTokenResponse:
    if not fleet_web_refresh:
        raise _error(
            "AUTHENTICATION_FAILED",
            "refresh token is invalid",
            status.HTTP_401_UNAUTHORIZED,
        )
    try:
        tokens = service.refresh(refresh_token=fleet_web_refresh)
        db.commit()
        _set_web_refresh_cookie(response, tokens, service)
        return _web_token_response(tokens)
    except (AuthenticationError, RefreshTokenReuseError, AuthConfigurationError) as exc:
        if isinstance(exc, RefreshTokenReuseError):
            db.commit()
        else:
            db.rollback()
        raise _error(
            "AUTHENTICATION_FAILED",
            "refresh token is invalid",
            status.HTTP_401_UNAUTHORIZED,
        ) from exc


@router.post("/web-logout", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
def web_logout(
    response: Response,
    context: AuthContext | None = Depends(get_current_session),
    service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> None:
    if context is not None:
        service.logout(context)
        db.commit()
    response.delete_cookie("fleet_web_refresh", path="/api/v1/auth")


@router.post("/refresh", response_model=TokenResponse)
def refresh_session(
    payload: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> TokenResponse:
    try:
        tokens = service.refresh(refresh_token=payload.refresh_token)
        db.commit()
        return _token_response(tokens)
    except (AuthenticationError, RefreshTokenReuseError, AuthConfigurationError) as exc:
        # Reuse revocation is persisted by the service before the generic error.
        if isinstance(exc, RefreshTokenReuseError):
            db.commit()
        else:
            db.rollback()
        raise _error(
            "AUTHENTICATION_FAILED",
            "refresh token is invalid",
            status.HTTP_401_UNAUTHORIZED,
        ) from exc


@router.post("/logout", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
def logout(
    context: AuthContext = Depends(get_current_session),
    service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> None:
    service.logout(context)
    db.commit()


@router.get("/me", response_model=MeResponse)
def me(context: AuthContext = Depends(get_current_session)) -> MeResponse:
    return MeResponse(
        user_id=context.user.id,
        display_name=context.user.display_name,
        membership_id=context.membership.id,
        company_id=context.company.id,
        company_name=context.company.name,
        role=context.membership.role,
    )
