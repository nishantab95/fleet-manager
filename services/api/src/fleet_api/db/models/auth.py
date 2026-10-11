from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.models.common import UpdatedTimestampModel
from fleet_api.domain.enums import AuthIdentityProvider, MembershipRole, OtpChallengeStatus


class UserAuthIdentity(UpdatedTimestampModel):
    """Durable external identity linkage; Fleet User remains the business identity."""

    __tablename__ = "user_auth_identities"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    provider: Mapped[AuthIdentityProvider] = mapped_column(
        SAEnum(AuthIdentityProvider, name="auth_identity_provider_enum"), nullable=False
    )
    provider_subject: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_phone: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disabled_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_subject",
            name="uq_user_auth_identities_provider_subject",
        ),
        Index(
            "uq_user_auth_identities_active_provider_user",
            "provider",
            "user_id",
            unique=True,
            postgresql_where=text("disabled_at IS NULL"),
        ),
    )


class OtpChallenge(UpdatedTimestampModel):
    """Short-lived phone challenge; only a one-way OTP representation is stored."""

    __tablename__ = "otp_challenges"

    phone_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    membership_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("company_memberships.id", ondelete="CASCADE"), nullable=True, index=True
    )
    purpose: Mapped[str] = mapped_column(
        String(32), nullable=False, default="LOGIN_OTP", server_default="LOGIN_OTP"
    )
    requested_role: Mapped[MembershipRole | None] = mapped_column(
        SAEnum(MembershipRole, name="membership_role_enum"), nullable=True
    )
    otp_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    otp_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[OtpChallengeStatus] = mapped_column(
        SAEnum(OtpChallengeStatus, name="otp_challenge_status_enum"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(nullable=False)
    next_allowed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        Index(
            "ix_otp_challenges_phone_status_created",
            "phone_number",
            "status",
            "created_at",
        ),
    )


class CompanyPinCredential(UpdatedTimestampModel):
    """Membership-bound device activation with no recoverable PIN or device secret."""

    __tablename__ = "company_pin_credentials"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    membership_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    credential_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    installation_id_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    pin_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pin_salt: Mapped[str | None] = mapped_column(String(64), nullable=True)
    setup_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_authenticated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_company_pin_credentials_company_membership",
            ondelete="CASCADE",
        ),
        Index(
            "uq_company_pin_credentials_active_membership",
            "membership_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "uq_company_pin_credentials_active_company_user",
            "company_id",
            "user_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "ix_company_pin_credentials_company_membership",
            "company_id",
            "membership_id",
        ),
    )


class AuthSession(UpdatedTimestampModel):
    """Server-side session state for access-token validation and refresh rotation."""

    __tablename__ = "auth_sessions"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    membership_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    family_id: Mapped[UUID] = mapped_column(nullable=False, default=uuid4, index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    previous_refresh_token_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_auth_sessions_company_membership",
            ondelete="CASCADE",
        ),
        Index("ix_auth_sessions_company_membership", "company_id", "membership_id"),
    )
