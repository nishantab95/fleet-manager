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
    allowed_hosts: str = "*"
    s3_endpoint_url: str = "http://localhost:19000"
    s3_region: str = "us-east-1"
    s3_bucket: str = "fleet-local"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = Field(default=None, repr=False)
    object_storage_provider: str = "unavailable"
    evidence_max_bytes: int = 5_000_000
    evidence_allowed_mime_types: str = "image/jpeg,image/png,image/webp"
    event_future_skew_seconds: int = 300
    phone_default_region: str | None = None
    otp_provider: str = "unavailable"
    enable_development_otp: bool = False
    pilot_otp: str | None = Field(default=None, repr=False)
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 5
    otp_resend_cooldown_seconds: int = 60
    jwt_signing_key: str | None = Field(default=None, repr=False)
    jwt_issuer: str = "fleet-manager-api"
    jwt_audience: str = "fleet-manager-client"
    access_token_ttl_seconds: int = 600
    pre_session_ttl_seconds: int = 300
    refresh_token_ttl_seconds: int = 2_592_000
    pilot_driver_phone: str | None = Field(default=None, repr=False)

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
        if self.evidence_max_bytes <= 0:
            raise ValueError("evidence_max_bytes must be positive")
        if self.event_future_skew_seconds < 0:
            raise ValueError("event_future_skew_seconds cannot be negative")

        environment = self.environment.lower()
        otp_provider = self.otp_provider.lower()
        if self.pilot_otp is not None and (
            len(self.pilot_otp) != 6 or not self.pilot_otp.isdigit()
        ):
            raise ValueError("pilot OTP must be exactly six digits")
        if otp_provider == "pilot" and environment not in {"development", "pilot", "test"}:
            raise ValueError(
                "pilot OTP provider is restricted to local non-production environments"
            )
        if otp_provider == "pilot" and not self.pilot_otp:
            raise ValueError("pilot OTP provider requires FLEET_PILOT_OTP")

        if environment in {"production", "prod"}:
            if not self.jwt_signing_key or len(self.jwt_signing_key) < 32:
                raise ValueError("production requires a JWT signing key of at least 32 characters")
            if self.enable_development_otp or otp_provider in {"development", "fake", "pilot"}:
                raise ValueError("development and pilot OTP providers are forbidden in production")
            if self.pilot_otp:
                raise ValueError("pilot OTP material is forbidden in production")
            if self.otp_provider.lower() == "unavailable":
                raise ValueError("production requires a configured OTP provider")
            if not self.cors_origins or "*" in self.cors_origins:
                raise ValueError("production requires explicit CORS origins")
            if not self.allowed_host_values or "*" in self.allowed_host_values:
                raise ValueError("production requires explicit allowed hosts")
            if self.object_storage_provider.lower() != "s3":
                raise ValueError("production requires private S3-compatible object storage")
            if not self.s3_access_key_id or not self.s3_secret_access_key:
                raise ValueError("production requires object-storage credentials")
            if self.s3_access_key_id.lower() in {"minioadmin", "changeme"}:
                raise ValueError(
                    "production object-storage credentials must not use local defaults"
                )
            if self.s3_secret_access_key.lower() in {"minioadmin", "changeme", "secret123"}:
                raise ValueError(
                    "production object-storage credentials must not use local defaults"
                )
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def allowed_host_values(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    @property
    def secure_cookies(self) -> bool:
        return self.environment.lower() in {"pilot", "production", "prod"}

    @property
    def evidence_mime_types(self) -> set[str]:
        return {
            mime.strip().lower()
            for mime in self.evidence_allowed_mime_types.split(",")
            if mime.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
