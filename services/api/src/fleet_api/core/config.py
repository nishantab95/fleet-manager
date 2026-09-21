from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FLEET_",
        extra="ignore",
        case_sensitive=False,
    )

    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://fleet:fleet@localhost:5432/fleet"
    cors_allowed_origins: str = "http://localhost:3000"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_region: str = "us-east-1"
    s3_bucket: str = "fleet-local"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = Field(default=None, repr=False)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

