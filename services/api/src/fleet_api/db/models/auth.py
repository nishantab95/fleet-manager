from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.models.common import UpdatedTimestampModel
from fleet_api.domain.enums import MembershipRole, OtpChallengeStatus


class OtpChallenge(UpdatedTimestampModel):
    """Short-lived phone challenge; only a one-way OTP representation is stored."""

    __tablename__ = "otp_challenges"

    phone_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
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
