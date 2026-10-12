from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_auth_service, get_current_session
from fleet_api.api.schemas import (
    CompanyActivationRequest,
    CompanyActivationResponse,
    CompanyDeviceAuthResponse,
    CompanyDeviceLoginRequest,
    CompanyPinLoginRequest,
    CompanyPinSessionResponse,
    CompanyPinSetupRequest,
    FirebaseTokenRequest,
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
    WorkspaceSwitchRequest,
)
from fleet_api.auth.service import AuthContext, AuthService, SessionTokens
from fleet_api.db.session import get_db
from fleet_api.domain.enums import MembershipRole
from fleet_api.domain.errors import (
    ActivationCodeError,
    AmbiguousPhoneIdentityError,
    AuthConfigurationError,
    AuthenticationError,
    DeviceAlreadyActivatedError,
    DeviceCredentialError,
    FirebaseProviderUnavailableError,
    FirebaseTokenError,
    FleetIdentityAccessDeniedError,
    IdentityLinkConflictError,
    InvalidOtpError,
    InvalidTokenError,
    MembershipSelectionError,
    OtpProviderUnavailableError,
    OtpRateLimitError,
    PhoneNormalizationError,
    PinAuthenticationError,
    PinLockedError,
    RefreshTokenReuseError,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

UNREGISTERED_PHONE_MESSAGE = (
    "This mobile number is not registered with your company. "
    "Contact your Fleet Manager administrator."
)


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


def _membership_options_response(
    memberships: list[tuple[UUID, UUID, str, MembershipRole]],
) -> MembershipOptionsResponse:
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


@router.post("/firebase/verify", response_model=OtpVerifyResponse)
def verify_firebase_token(
    payload: FirebaseTokenRequest,
    service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> OtpVerifyResponse:
    try:
        pre_session_token, expires_in = service.verify_firebase_identity(id_token=payload.id_token)
        db.commit()
        return OtpVerifyResponse(
            pre_session_token=pre_session_token,
            expires_in=expires_in,
        )
    except FirebaseTokenError as exc:
        db.rollback()
        raise _error(
            "UNAUTHENTICATED",
            "Phone verification is invalid or expired. Please try again.",
            status.HTTP_401_UNAUTHORIZED,
        ) from exc
    except FirebaseProviderUnavailableError as exc:
        db.rollback()
        raise _error(
            "AUTH_PROVIDER_UNAVAILABLE",
            "Phone authentication is temporarily unavailable.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    except AmbiguousPhoneIdentityError as exc:
        db.commit()
        raise _error(
            "ACCOUNT_CONFIGURATION_ERROR",
            str(exc),
            status.HTTP_403_FORBIDDEN,
        ) from exc
    except IdentityLinkConflictError as exc:
        db.commit()
        raise _error(
            "ACCOUNT_LINK_CONFLICT",
            "This phone identity cannot be linked automatically. "
            "Contact your Fleet Manager administrator.",
            status.HTTP_403_FORBIDDEN,
        ) from exc
    except FleetIdentityAccessDeniedError as exc:
        db.commit()
        message = str(exc) or UNREGISTERED_PHONE_MESSAGE
        raise _error("ACCESS_DENIED", message, status.HTTP_403_FORBIDDEN) from exc
    except AuthConfigurationError as exc:
        db.rollback()
        raise _error(
            "AUTH_NOT_CONFIGURED",
            "Phone authentication is temporarily unavailable.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc


@router.post("/company/activate", response_model=CompanyActivationResponse)
def activate_company_device(
    payload: CompanyActivationRequest,
    service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> CompanyActivationResponse:
    try:
        activation = service.begin_company_activation(
            phone=payload.phone,
            activation_code=payload.activation_code,
            installation_identifier=payload.installation_identifier,
        )
        db.commit()
        return CompanyActivationResponse(
            activation_token=activation.device_credential,
            expires_in=activation.expires_in,
        )
    except DeviceAlreadyActivatedError as exc:
        db.rollback()
        raise _error(
            "DEVICE_ALREADY_ACTIVATED",
            str(exc),
            status.HTTP_409_CONFLICT,
        ) from exc
    except (ActivationCodeError, PhoneNormalizationError) as exc:
        # Failed challenge attempts are durable security state.
        db.commit()
        raise _error(
            "ACTIVATION_FAILED",
            "Mobile number or activation code is invalid, expired, or already used.",
            status.HTTP_401_UNAUTHORIZED,
        ) from exc
    except AuthConfigurationError as exc:
        db.rollback()
        raise _error(
            "AUTH_NOT_CONFIGURED",
            "company activation is unavailable",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc


@router.post("/company/set-pin", response_model=CompanyPinSessionResponse)
def set_company_pin(
    payload: CompanyPinSetupRequest,
    service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> CompanyPinSessionResponse:
    try:
        tokens, device_credential = service.complete_company_pin_activation(
            activation_token=payload.activation_token,
            installation_identifier=payload.installation_identifier,
            pin=payload.pin,
        )
        db.commit()
        return CompanyPinSessionResponse(
            **_token_response(tokens).model_dump(),
            device_credential=device_credential,
        )
    except DeviceCredentialError as exc:
        db.rollback()
        raise _error(
            "ACTIVATION_EXPIRED",
            "Activation has expired. Ask an Owner for a new activation code.",
            status.HTTP_401_UNAUTHORIZED,
        ) from exc
    except AuthConfigurationError as exc:
        db.rollback()
        raise _error(
            "AUTH_NOT_CONFIGURED",
            "company PIN authentication is unavailable",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc


@router.post("/company/complete-activation", response_model=CompanyDeviceAuthResponse)
def complete_company_device_activation(
    payload: CompanyPinSetupRequest,
    service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> CompanyDeviceAuthResponse:
    """Build 29 role-neutral activation; Build 28 /set-pin remains supported."""
    try:
        pre_session, expires_in, device_credential = service.complete_company_device_activation(
            activation_token=payload.activation_token,
            installation_identifier=payload.installation_identifier,
            pin=payload.pin,
        )
        db.commit()
        return CompanyDeviceAuthResponse(
            pre_session_token=pre_session,
            expires_in=expires_in,
            device_credential=device_credential,
        )
    except DeviceCredentialError as exc:
        db.rollback()
        raise _error(
            "ACTIVATION_EXPIRED",
            "Activation has expired. Ask an Owner for a new activation code.",
            status.HTTP_401_UNAUTHORIZED,
        ) from exc
    except AuthConfigurationError as exc:
        db.rollback()
        raise _error(
            "AUTH_NOT_CONFIGURED",
            "company device authentication is unavailable",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc


@router.post("/company/device-auth", response_model=OtpVerifyResponse)
def authenticate_company_device(
    payload: CompanyDeviceLoginRequest,
    service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> OtpVerifyResponse:
    """Accept only the Fleet device credential; Android secrets stay local to Android."""
    try:
        pre_session, expires_in = service.authenticate_company_device(
            device_credential=payload.device_credential,
            installation_identifier=payload.installation_identifier,
        )
        db.commit()
        return OtpVerifyResponse(
            pre_session_token=pre_session,
            expires_in=expires_in,
        )
    except DeviceCredentialError as exc:
        db.rollback()
        raise _error(
            "DEVICE_REACTIVATION_REQUIRED",
            "This device must be activated again.",
            status.HTTP_401_UNAUTHORIZED,
        ) from exc
    except AuthConfigurationError as exc:
        db.rollback()
        raise _error(
            "AUTH_NOT_CONFIGURED",
            "company device authentication is unavailable",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc


@router.post("/company/pin-auth", response_model=OtpVerifyResponse)
def authenticate_company_pin(
    payload: CompanyPinLoginRequest,
    service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> OtpVerifyResponse:
    """Build 29 fallback PIN authentication without selecting a workspace."""
    try:
        pre_session, expires_in = service.authenticate_company_pin(
            device_credential=payload.device_credential,
            installation_identifier=payload.installation_identifier,
            pin=payload.pin,
        )
        db.commit()
        return OtpVerifyResponse(
            pre_session_token=pre_session,
            expires_in=expires_in,
        )
    except PinLockedError as exc:
        db.commit()
        raise _error(
            "PIN_LOCKED",
            "Too many incorrect PIN attempts. Try again later.",
            status.HTTP_429_TOO_MANY_REQUESTS,
        ) from exc
    except PinAuthenticationError as exc:
        db.commit()
        raise _error(
            "AUTHENTICATION_FAILED",
            "PIN is incorrect.",
            status.HTTP_401_UNAUTHORIZED,
        ) from exc
    except DeviceCredentialError as exc:
        db.rollback()
        raise _error(
            "DEVICE_REACTIVATION_REQUIRED",
            "This device must be activated again.",
            status.HTTP_401_UNAUTHORIZED,
        ) from exc
    except AuthConfigurationError as exc:
        db.rollback()
        raise _error(
            "AUTH_NOT_CONFIGURED",
            "company PIN authentication is unavailable",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc


@router.post("/company/pin-login", response_model=TokenResponse)
def login_with_company_pin(
    payload: CompanyPinLoginRequest,
    service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> TokenResponse:
    try:
        tokens = service.login_company_pin(
            device_credential=payload.device_credential,
            installation_identifier=payload.installation_identifier,
            pin=payload.pin,
        )
        db.commit()
        return _token_response(tokens)
    except PinLockedError as exc:
        db.commit()
        raise _error(
            "PIN_LOCKED",
            "Too many incorrect PIN attempts. Try again later.",
            status.HTTP_429_TOO_MANY_REQUESTS,
        ) from exc
    except PinAuthenticationError as exc:
        db.commit()
        raise _error(
            "AUTHENTICATION_FAILED",
            "PIN is incorrect.",
            status.HTTP_401_UNAUTHORIZED,
        ) from exc
    except DeviceCredentialError as exc:
        db.rollback()
        raise _error(
            "DEVICE_REACTIVATION_REQUIRED",
            "This device must be activated again.",
            status.HTTP_401_UNAUTHORIZED,
        ) from exc
    except AuthConfigurationError as exc:
        db.rollback()
        raise _error(
            "AUTH_NOT_CONFIGURED",
            "company PIN authentication is unavailable",
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
    return _membership_options_response(memberships)


@router.get("/workspaces", response_model=MembershipOptionsResponse)
def list_current_workspaces(
    context: AuthContext = Depends(get_current_session),
    service: AuthService = Depends(get_auth_service),
) -> MembershipOptionsResponse:
    return _membership_options_response(service.list_session_memberships(context))


@router.post("/workspace", response_model=TokenResponse)
def switch_workspace(
    payload: WorkspaceSwitchRequest,
    context: AuthContext = Depends(get_current_session),
    service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> TokenResponse:
    try:
        tokens = service.switch_workspace(
            context,
            membership_id=payload.membership_id,
        )
        db.commit()
        return _token_response(tokens)
    except MembershipSelectionError as exc:
        db.rollback()
        raise _error(
            "FORBIDDEN",
            "workspace selection is not permitted",
            status.HTTP_403_FORBIDDEN,
        ) from exc


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
