from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from secrets import token_urlsafe
from typing import Any, cast
from uuid import UUID, uuid4

import jwt
from jwt import PyJWTError

from fleet_api.core.config import Settings
from fleet_api.domain.errors import AuthConfigurationError, InvalidTokenError


@dataclass(frozen=True)
class PreSessionClaims:
    user_id: UUID | None


@dataclass(frozen=True)
class AccessClaims:
    user_id: UUID
    membership_id: UUID
    company_id: UUID
    session_id: UUID
    role: str


def _signing_key(settings: Settings) -> str:
    if not settings.jwt_signing_key or len(settings.jwt_signing_key) < 32:
        raise AuthConfigurationError("JWT signing is not configured securely")
    return settings.jwt_signing_key


def _decode(token: str, settings: Settings) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            _signing_key(settings),
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["aud", "exp", "iat", "iss", "jti", "kind", "sub"]},
        )
    except (PyJWTError, AuthConfigurationError) as exc:
        raise InvalidTokenError("token is invalid") from exc
    return cast(dict[str, Any], payload)


def issue_pre_session(settings: Settings, *, user_id: UUID | None, now: datetime) -> str:
    subject = str(user_id or uuid4())
    payload: dict[str, Any] = {
        "aud": settings.jwt_audience,
        "exp": now + timedelta(seconds=settings.pre_session_ttl_seconds),
        "iat": now,
        "iss": settings.jwt_issuer,
        "jti": str(uuid4()),
        "kind": "membership_selection",
        "sub": subject,
    }
    if user_id is not None:
        payload["uid"] = str(user_id)
    return jwt.encode(payload, _signing_key(settings), algorithm="HS256")


def decode_pre_session(token: str, settings: Settings) -> PreSessionClaims:
    payload = _decode(token, settings)
    if payload.get("kind") != "membership_selection":
        raise InvalidTokenError("token is not a membership-selection context")
    raw_user_id = payload.get("uid")
    if raw_user_id is None:
        return PreSessionClaims(user_id=None)
    try:
        return PreSessionClaims(user_id=UUID(str(raw_user_id)))
    except ValueError as exc:
        raise InvalidTokenError("token identity is invalid") from exc


def issue_access_token(
    settings: Settings,
    *,
    user_id: UUID,
    membership_id: UUID,
    company_id: UUID,
    session_id: UUID,
    role: str,
    now: datetime,
) -> str:
    payload: dict[str, Any] = {
        "aud": settings.jwt_audience,
        "cid": str(company_id),
        "exp": now + timedelta(seconds=settings.access_token_ttl_seconds),
        "iat": now,
        "iss": settings.jwt_issuer,
        "jti": str(uuid4()),
        "kind": "access",
        "mid": str(membership_id),
        "role": role,
        "sid": str(session_id),
        "sub": str(user_id),
    }
    return jwt.encode(payload, _signing_key(settings), algorithm="HS256")


def decode_access_token(token: str, settings: Settings) -> AccessClaims:
    payload = _decode(token, settings)
    if payload.get("kind") != "access":
        raise InvalidTokenError("token is not an access token")
    try:
        return AccessClaims(
            user_id=UUID(str(payload["sub"])),
            membership_id=UUID(str(payload["mid"])),
            company_id=UUID(str(payload["cid"])),
            session_id=UUID(str(payload["sid"])),
            role=str(payload["role"]),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidTokenError("token claims are invalid") from exc


def generate_refresh_token() -> str:
    return token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    import hashlib

    return hashlib.sha256(token.encode("utf-8")).hexdigest()
