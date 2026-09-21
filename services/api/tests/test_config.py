from fleet_api.core.config import Settings


def test_cors_origins_are_parsed_from_environment_style_string() -> None:
    settings = Settings(cors_allowed_origins="http://localhost:3000, http://localhost:8000")

    assert settings.cors_origins == ["http://localhost:3000", "http://localhost:8000"]
