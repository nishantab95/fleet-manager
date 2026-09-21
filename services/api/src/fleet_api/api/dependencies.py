from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from fleet_api.auth.providers import OtpProvider, build_otp_provider
from fleet_api.auth.service import (
    AuthContext,
    AuthService,
    ensure_role,
    ensure_supervisor_site_access,
)
from fleet_api.core.config import Settings
from fleet_api.db.models import CompanyMembership
from fleet_api.db.session import get_db
from fleet_api.domain.admin import AdminService
from fleet_api.domain.enums import MembershipRole
from fleet_api.domain.errors import (
    AuthConfigurationError,
    InvalidTokenError,
    RoleViolationError,
    TenantConsistencyError,
)

bearer_scheme = HTTPBearer(auto_error=False)


def get_app_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_otp_provider(settings: Annotated[Settings, Depends(get_app_settings)]) -> OtpProvider:
    return build_otp_provider(settings)


def get_auth_service(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    otp_provider: Annotated[OtpProvider, Depends(get_otp_provider)],
) -> AuthService:
    request_id = request.headers.get("x-request-id")
    return AuthService(db, settings, otp_provider, request_id=request_id)


def _unauthenticated(detail: str = "authentication required") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "UNAUTHENTICATED", "message": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_session(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthContext:
    if credentials is None:
        raise _unauthenticated()
    try:
        return service.authenticate_access_token(access_token=credentials.credentials)
    except InvalidTokenError as exc:
        raise _unauthenticated("access token is invalid") from exc
    except AuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "AUTH_NOT_CONFIGURED", "message": "authentication is unavailable"},
        ) from exc


def get_current_membership(
    context: Annotated[AuthContext, Depends(get_current_session)],
) -> CompanyMembership:
    return context.membership


def require_role(*allowed_roles: MembershipRole) -> Callable[..., AuthContext]:
    def dependency(
        context: Annotated[AuthContext, Depends(get_current_session)],
    ) -> AuthContext:
        try:
            return ensure_role(context, *allowed_roles)
        except RoleViolationError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "FORBIDDEN", "message": "membership role is not allowed"},
            ) from exc

    return dependency


require_owner_admin = require_role(MembershipRole.OWNER_ADMIN)
require_supervisor = require_role(MembershipRole.SUPERVISOR)
require_driver = require_role(MembershipRole.DRIVER)


def get_admin_service(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    context: Annotated[AuthContext, Depends(require_owner_admin)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AdminService:
    return AdminService(
        db,
        context,
        request_id=request.headers.get("x-request-id"),
        phone_default_region=settings.phone_default_region,
    )


def require_company_context(
    context: Annotated[AuthContext, Depends(get_current_session)],
) -> UUID:
    return context.company.id


def require_supervisor_site_access(
    site_id: UUID,
    context: Annotated[AuthContext, Depends(require_supervisor)],
    db: Annotated[Session, Depends(get_db)],
) -> AuthContext:
    try:
        return ensure_supervisor_site_access(db, context, site_id=site_id)
    except TenantConsistencyError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "site access is not permitted"},
        ) from exc
