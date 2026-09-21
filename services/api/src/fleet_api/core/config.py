from functools import lru_cache

from pydantic import Field, model_validator
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
    phone_default_region: str | None = None
    otp_provider: str = "unavailable"
    enable_development_otp: bool = False
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 5
    otp_resend_cooldown_seconds: int = 60
    jwt_signing_key: str | None = Field(default=None, repr=False)
    jwt_issuer: str = "fleet-manager-api"
    jwt_audience: str = "fleet-manager-client"
    access_token_ttl_seconds: int = 600
    pre_session_ttl_seconds: int = 300
    refresh_token_ttl_seconds: int = 2_592_000

    @model_validator(mode="after")
    def validate_auth_configuration(self) -> "Settings":
        if self.otp_ttl_seconds <= 0 or self.otp_max_attempts <= 0:
            raise ValueError("OTP lifetime and attempt limit must be positive")
        if self.otp_resend_cooldown_seconds < 0:
            raise ValueError("OTP resend cooldown cannot be negative")
        if self.access_token_ttl_seconds <= 0 or self.pre_session_ttl_seconds <= 0:
            raise ValueError("token lifetimes must be positive")
        if self.refresh_token_ttl_seconds <= self.access_token_ttl_seconds:
            raise ValueError("refresh token lifetime must exceed access token lifetime")

        if self.environment.lower() in {"production", "prod"}:
            if not self.jwt_signing_key or len(self.jwt_signing_key) < 32:
                raise ValueError("production requires a JWT signing key of at least 32 characters")
            if self.enable_development_otp or self.otp_provider.lower() in {"development", "fake"}:
                raise ValueError("development OTP provider is forbidden in production")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
