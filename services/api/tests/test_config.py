import pytest

from fleet_api.core.config import Settings


def test_cors_origins_are_parsed_from_environment_style_string() -> None:
    settings = Settings(cors_allowed_origins="http://localhost:3000, http://localhost:8000")

    assert settings.cors_origins == ["http://localhost:3000", "http://localhost:8000"]


def test_production_configuration_fails_closed_for_local_defaults() -> None:
    with pytest.raises(ValueError, match="configured OTP provider"):
        Settings(
            environment="production",
            jwt_signing_key="production-signing-key-that-is-longer-than-32-characters",
        )


def test_allowed_hosts_are_parsed_and_secure_cookies_follow_profile() -> None:
    settings = Settings(allowed_hosts="pilot.example, api.pilot.example", environment="pilot")

    assert settings.allowed_host_values == ["pilot.example", "api.pilot.example"]
    assert settings.secure_cookies is True
