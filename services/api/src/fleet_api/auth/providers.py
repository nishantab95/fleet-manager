from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from secrets import randbelow
from typing import Protocol
from uuid import UUID

from fleet_api.core.config import Settings
from fleet_api.domain.enums import MembershipRole
from fleet_api.domain.errors import AuthConfigurationError, OtpProviderUnavailableError


class OtpProvider(Protocol):
    """Vendor-neutral OTP delivery boundary."""

    def generate(self, *, requested_role: MembershipRole | None = None) -> str:
        """Create the code associated with the next challenge."""

    def deliver(self, *, phone_number: str, otp: str, challenge_id: UUID) -> None:
        """Deliver an OTP without exposing it to the API response or logs."""


def _new_otp() -> str:
    return f"{randbelow(1_000_000):06d}"


class UnavailableOtpProvider:
    def generate(self, *, requested_role: MembershipRole | None = None) -> str:
        del requested_role
        return _new_otp()

    def deliver(self, *, phone_number: str, otp: str, challenge_id: UUID) -> None:
        del phone_number, otp, challenge_id
        raise OtpProviderUnavailableError("no OTP provider is configured")


@dataclass
class FakeOtpProvider:
    """Deterministic injected provider for tests; never selected by production config."""

    deliveries: dict[UUID, str] = field(default_factory=dict)

    def generate(self, *, requested_role: MembershipRole | None = None) -> str:
        del requested_role
        return _new_otp()

    def deliver(self, *, phone_number: str, otp: str, challenge_id: UUID) -> None:
        del phone_number
        self.deliveries[challenge_id] = otp


@dataclass
class DevelopmentOtpProvider:
    """Explicitly gated local provider with in-memory delivery inspection."""

    deliveries: dict[UUID, str] = field(default_factory=dict)

    def generate(self, *, requested_role: MembershipRole | None = None) -> str:
        del requested_role
        return _new_otp()

    def deliver(self, *, phone_number: str, otp: str, challenge_id: UUID) -> None:
        del phone_number
        self.deliveries[challenge_id] = otp


@dataclass
class PilotOtpProvider:
    """Explicit local provider with a fixed code for each intended role."""

    otps: Mapping[MembershipRole, str]
    legacy_otp: str | None = None
    deliveries: dict[UUID, str] = field(default_factory=dict)

    def generate(self, *, requested_role: MembershipRole | None = None) -> str:
        if requested_role is None:
            if self.legacy_otp:
                return self.legacy_otp
            raise AuthConfigurationError("pilot OTP requests require an intended role")
        try:
            return self.otps[requested_role]
        except KeyError as exc:
            raise AuthConfigurationError("pilot OTP is not configured for this role") from exc

    def deliver(self, *, phone_number: str, otp: str, challenge_id: UUID) -> None:
        del phone_number
        self.deliveries[challenge_id] = otp


def build_otp_provider(settings: Settings) -> OtpProvider:
    provider_name = settings.otp_provider.lower()
    if provider_name == "unavailable":
        return UnavailableOtpProvider()
    if provider_name == "development":
        if settings.environment.lower() != "development" or not settings.enable_development_otp:
            raise AuthConfigurationError("development OTP provider is not enabled")
        return DevelopmentOtpProvider()
    if provider_name == "pilot":
        if settings.environment.lower() not in {"development", "pilot", "test"}:
            raise AuthConfigurationError("pilot OTP provider is not enabled in this environment")
        role_otps = {
            MembershipRole.DRIVER: settings.pilot_driver_otp or settings.pilot_otp,
            MembershipRole.SUPERVISOR: settings.pilot_supervisor_otp or settings.pilot_otp,
            MembershipRole.OWNER_ADMIN: settings.pilot_owner_otp or settings.pilot_otp,
        }
        if any(not otp for otp in role_otps.values()):
            raise AuthConfigurationError("pilot OTP is not configured for every role")
        return PilotOtpProvider(
            otps={role: otp for role, otp in role_otps.items() if otp is not None},
            legacy_otp=settings.pilot_otp,
        )
    if provider_name == "fake":
        raise AuthConfigurationError("fake OTP provider is test-only")
    raise AuthConfigurationError("configured OTP provider is not available")
