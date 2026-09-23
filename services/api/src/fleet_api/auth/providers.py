from __future__ import annotations

from dataclasses import dataclass, field
from secrets import randbelow
from typing import Protocol
from uuid import UUID

from fleet_api.core.config import Settings
from fleet_api.domain.errors import AuthConfigurationError, OtpProviderUnavailableError


class OtpProvider(Protocol):
    """Vendor-neutral OTP delivery boundary."""

    def generate(self) -> str:
        """Create the code associated with the next challenge."""

    def deliver(self, *, phone_number: str, otp: str, challenge_id: UUID) -> None:
        """Deliver an OTP without exposing it to the API response or logs."""


def _new_otp() -> str:
    return f"{randbelow(1_000_000):06d}"


class UnavailableOtpProvider:
    def generate(self) -> str:
        return _new_otp()

    def deliver(self, *, phone_number: str, otp: str, challenge_id: UUID) -> None:
        del phone_number, otp, challenge_id
        raise OtpProviderUnavailableError("no OTP provider is configured")


@dataclass
class FakeOtpProvider:
    """Deterministic injected provider for tests; never selected by production config."""

    deliveries: dict[UUID, str] = field(default_factory=dict)

    def generate(self) -> str:
        return _new_otp()

    def deliver(self, *, phone_number: str, otp: str, challenge_id: UUID) -> None:
        del phone_number
        self.deliveries[challenge_id] = otp


@dataclass
class DevelopmentOtpProvider:
    """Explicitly gated local provider with in-memory delivery inspection."""

    deliveries: dict[UUID, str] = field(default_factory=dict)

    def generate(self) -> str:
        return _new_otp()

    def deliver(self, *, phone_number: str, otp: str, challenge_id: UUID) -> None:
        del phone_number
        self.deliveries[challenge_id] = otp


@dataclass
class PilotOtpProvider:
    """Explicit local pilot provider using a gitignored configured code."""

    otp: str
    deliveries: dict[UUID, str] = field(default_factory=dict)

    def generate(self) -> str:
        return self.otp

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
        if not settings.pilot_otp:
            raise AuthConfigurationError("pilot OTP is not configured")
        return PilotOtpProvider(settings.pilot_otp)
    if provider_name == "fake":
        raise AuthConfigurationError("fake OTP provider is test-only")
    raise AuthConfigurationError("configured OTP provider is not available")
