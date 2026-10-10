from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast

import firebase_admin  # type: ignore[import-untyped]
from firebase_admin import auth

from fleet_api.auth.phone import normalize_phone
from fleet_api.core.config import Settings
from fleet_api.domain.enums import AuthIdentityProvider
from fleet_api.domain.errors import (
    AuthConfigurationError,
    FirebaseProviderUnavailableError,
    FirebaseTokenError,
    PhoneNormalizationError,
)


@dataclass(frozen=True)
class VerifiedPhoneIdentity:
    provider: AuthIdentityProvider
    subject: str
    normalized_phone: str
    verified_at: datetime


class PhoneIdentityAuthProvider(Protocol):
    """Boundary for a provider that verifies a phone-backed external identity."""

    def verify(self, id_token: str) -> VerifiedPhoneIdentity:
        """Verify a provider token and return only trusted identity claims."""


class UnavailablePhoneIdentityAuthProvider:
    def verify(self, id_token: str) -> VerifiedPhoneIdentity:
        del id_token
        raise AuthConfigurationError("phone identity provider is not configured")


class FirebasePhoneAuthProvider:
    """Firebase Admin adapter isolated from Fleet authorization rules."""

    def __init__(self, settings: Settings) -> None:
        if settings.auth_mode.lower() != "firebase" or not settings.firebase_project_id:
            raise AuthConfigurationError("Firebase phone authentication is not configured")
        self.project_id = settings.firebase_project_id
        self.app_name = settings.firebase_app_name
        self.check_revoked = settings.firebase_check_revoked_tokens
        self._app: firebase_admin.App | None = None

    def _firebase_app(self) -> firebase_admin.App:
        if self._app is not None:
            return self._app
        try:
            app = firebase_admin.get_app(self.app_name)
        except ValueError:
            try:
                app = firebase_admin.initialize_app(
                    options={"projectId": self.project_id},
                    name=self.app_name,
                )
            except (ValueError, OSError) as exc:
                raise FirebaseProviderUnavailableError(
                    "Firebase Admin could not be initialized"
                ) from exc
        if app.project_id != self.project_id:
            raise AuthConfigurationError("Firebase app project does not match configuration")
        self._app = app
        return app

    def verify(self, id_token: str) -> VerifiedPhoneIdentity:
        if not id_token.strip():
            raise FirebaseTokenError("Firebase ID token is missing")
        try:
            decoded = auth.verify_id_token(
                id_token,
                app=self._firebase_app(),
                check_revoked=self.check_revoked,
            )
        except auth.ExpiredIdTokenError as exc:
            raise FirebaseTokenError("Firebase ID token is expired") from exc
        except (auth.InvalidIdTokenError, auth.RevokedIdTokenError, auth.UserDisabledError) as exc:
            raise FirebaseTokenError("Firebase ID token is invalid") from exc
        except auth.CertificateFetchError as exc:
            raise FirebaseProviderUnavailableError(
                "Firebase token verification is temporarily unavailable"
            ) from exc

        subject = decoded.get("sub")
        phone = decoded.get("phone_number")
        firebase_claim = decoded.get("firebase")
        auth_time = decoded.get("auth_time")
        if (
            not isinstance(subject, str)
            or not subject
            or not isinstance(phone, str)
            or not phone
            or not isinstance(firebase_claim, Mapping)
            or firebase_claim.get("sign_in_provider") != "phone"
        ):
            raise FirebaseTokenError("Firebase token is not a phone-auth identity")
        try:
            normalized_phone = normalize_phone(phone)
        except PhoneNormalizationError as exc:
            raise FirebaseTokenError("Firebase token phone number is invalid") from exc
        if isinstance(auth_time, int | float):
            verified_at = datetime.fromtimestamp(auth_time, tz=UTC)
        else:
            verified_at = datetime.now(UTC)
        return VerifiedPhoneIdentity(
            provider=AuthIdentityProvider.FIREBASE_PHONE,
            subject=subject,
            normalized_phone=normalized_phone,
            verified_at=verified_at,
        )


def build_phone_identity_provider(settings: Settings) -> PhoneIdentityAuthProvider:
    if settings.auth_mode.lower() == "firebase":
        return FirebasePhoneAuthProvider(settings)
    return cast(PhoneIdentityAuthProvider, UnavailablePhoneIdentityAuthProvider())
