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
    with pytest.raises(ValueError, match="company PIN authentication mode"):
        _settings(
            environment="production",
            jwt_signing_key="production-signing-key-that-is-longer-than-32-characters",
        )


def test_staging_configuration_requires_secure_auth_and_public_boundaries() -> None:
    with pytest.raises(ValueError, match="company PIN authentication mode"):
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


def test_company_pin_mode_accepts_protected_profile_without_firebase_and_rejects_pilot_codes() -> (
    None
):
    settings = _settings(
        environment="staging",
        auth_mode="company_pin",
        jwt_signing_key="staging-signing-key-that-is-longer-than-32-characters",
        web_public_base_url="https://owner.staging.example",
        cors_allowed_origins="https://owner.staging.example",
        allowed_hosts="api.staging.example",
    )
    assert settings.firebase_project_id is None

    with pytest.raises(ValueError, match="forbidden in company PIN auth mode"):
        _settings(auth_mode="company_pin", pilot_otp="123456")


def test_database_pool_limits_are_bounded_and_validated() -> None:
    configured = _settings(
        database_pool_size=5,
        database_max_overflow=2,
        database_pool_timeout_seconds=10,
    )
    assert configured.database_pool_size + configured.database_max_overflow == 7

    with pytest.raises(ValueError, match="database_pool_size"):
        _settings(database_pool_size=0)
    with pytest.raises(ValueError, match="database_max_overflow"):
        _settings(database_max_overflow=-1)
    with pytest.raises(ValueError, match="database_pool_timeout_seconds"):
        _settings(database_pool_timeout_seconds=0)


def test_rate_limit_settings_reject_invalid_bounds() -> None:
    with pytest.raises(ValueError, match="rate_limit_requests_per_minute"):
        _settings(rate_limit_requests_per_minute=-1)
    with pytest.raises(ValueError, match="auth_rate_limit_requests_per_minute"):
        _settings(auth_rate_limit_requests_per_minute=-1)
    with pytest.raises(ValueError, match="rate_limit_max_clients"):
        _settings(rate_limit_max_clients=0)


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
