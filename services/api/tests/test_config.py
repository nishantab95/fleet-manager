from typing import Any

import pytest

from fleet_api.core.config import Settings
from fleet_api.main import create_app


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_cors_origins_are_parsed_from_environment_style_string() -> None:
    settings = _settings(cors_allowed_origins="http://localhost:3000, http://localhost:8000")

    assert settings.cors_origins == ["http://localhost:3000", "http://localhost:8000"]


def test_production_configuration_fails_closed_for_local_defaults() -> None:
    with pytest.raises(ValueError, match="Firebase authentication mode"):
        _settings(
            environment="production",
            jwt_signing_key="production-signing-key-that-is-longer-than-32-characters",
        )


def test_staging_configuration_requires_firebase_and_secure_public_boundaries() -> None:
    with pytest.raises(ValueError, match="staging requires Firebase authentication mode"):
        _settings(
            environment="staging",
            jwt_signing_key="staging-signing-key-that-is-longer-than-32-characters",
        )

    settings = _settings(
        environment="staging",
        auth_mode="firebase",
        firebase_project_id="fleet-staging",
        jwt_signing_key="staging-signing-key-that-is-longer-than-32-characters",
        web_public_base_url="https://owner.staging.example",
        cors_allowed_origins="https://owner.staging.example",
        allowed_hosts="api.staging.example",
    )

    assert settings.secure_cookies is True


def test_staging_configuration_rejects_insecure_web_url() -> None:
    with pytest.raises(ValueError, match="staging requires an HTTPS web public base URL"):
        _settings(
            environment="staging",
            auth_mode="firebase",
            firebase_project_id="fleet-staging",
            jwt_signing_key="staging-signing-key-that-is-longer-than-32-characters",
            web_public_base_url="http://owner.staging.example",
            cors_allowed_origins="https://owner.staging.example",
            allowed_hosts="api.staging.example",
        )


def test_allowed_hosts_are_parsed_and_secure_cookies_follow_profile() -> None:
    settings = _settings(allowed_hosts="pilot.example, api.pilot.example", environment="pilot")

    assert settings.allowed_host_values == ["pilot.example", "api.pilot.example"]
    assert settings.secure_cookies is True


def test_odometer_ceiling_defaults_to_realistic_value_and_is_configurable() -> None:
    assert str(_settings().max_odometer_km) == "10000000"
    assert str(_settings(max_odometer_km="2500000.50").max_odometer_km) == "2500000.50"


def test_odometer_ceiling_rejects_non_finite_or_unstorable_values() -> None:
    with pytest.raises(ValueError, match="max_odometer_km"):
        _settings(max_odometer_km="Infinity")
    with pytest.raises(ValueError, match="max_odometer_km"):
        _settings(max_odometer_km="10000000000")


def test_intercompany_rental_skeleton_is_disabled_and_not_routable() -> None:
    settings = _settings()

    assert settings.intercompany_rentals_enabled is False
    assert all(
        "intercompany" not in getattr(route, "path", "").casefold()
        for route in create_app(settings).routes
    )
