from typing import Any

import pytest

from fleet_api.core.config import Settings


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_cors_origins_are_parsed_from_environment_style_string() -> None:
    settings = _settings(cors_allowed_origins="http://localhost:3000, http://localhost:8000")

    assert settings.cors_origins == ["http://localhost:3000", "http://localhost:8000"]


def test_production_configuration_fails_closed_for_local_defaults() -> None:
    with pytest.raises(ValueError, match="configured OTP provider"):
        _settings(
            environment="production",
            jwt_signing_key="production-signing-key-that-is-longer-than-32-characters",
        )


def test_allowed_hosts_are_parsed_and_secure_cookies_follow_profile() -> None:
    settings = _settings(allowed_hosts="pilot.example, api.pilot.example", environment="pilot")

    assert settings.allowed_host_values == ["pilot.example", "api.pilot.example"]
    assert settings.secure_cookies is True
