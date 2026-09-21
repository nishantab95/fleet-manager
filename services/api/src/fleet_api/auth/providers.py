from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from fleet_api.core.config import Settings
from fleet_api.domain.errors import AuthConfigurationError, OtpProviderUnavailableError


class OtpProvider(Protocol):
    """Vendor-neutral OTP delivery boundary."""

    def deliver(self, *, phone_number: str, otp: str, challenge_id: UUID) -> None:
        """Deliver an OTP without exposing it to the API response or logs."""


class UnavailableOtpProvider:
    def deliver(self, *, phone_number: str, otp: str, challenge_id: UUID) -> None:
        del phone_number, otp, challenge_id
        raise OtpProviderUnavailableError("no OTP provider is configured")


@dataclass
class FakeOtpProvider:
    """Deterministic injected provider for tests; never selected by production config."""

    deliveries: dict[UUID, str] = field(default_factory=dict)

    def deliver(self, *, phone_number: str, otp: str, challenge_id: UUID) -> None:
        del phone_number
        self.deliveries[challenge_id] = otp


@dataclass
class DevelopmentOtpProvider:
    """Explicitly gated local provider with in-memory delivery inspection."""

    deliveries: dict[UUID, str] = field(default_factory=dict)

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
    if provider_name == "fake":
        raise AuthConfigurationError("fake OTP provider is test-only")
    raise AuthConfigurationError("configured OTP provider is not available")
