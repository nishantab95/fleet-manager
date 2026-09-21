"""Add OTP challenges and server-side authentication sessions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_authentication"
down_revision: str | Sequence[str] | None = "0002_core_domain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def _create_enum(name: str, values: tuple[str, ...]) -> None:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    op.execute(
        "DO $$ BEGIN "
        f"CREATE TYPE {name} AS ENUM ({quoted_values}); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )


def upgrade() -> None:
    _create_enum(
        "otp_challenge_status_enum",
        ("ACTIVE", "CONSUMED", "EXPIRED", "EXHAUSTED", "CANCELLED"),
    )

    op.create_table(
        "otp_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phone_number", sa.String(length=32), nullable=False),
        sa.Column("otp_hash", sa.String(length=128), nullable=False),
        sa.Column("otp_salt", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            _enum(
                "otp_challenge_status_enum",
                "ACTIVE",
                "CONSUMED",
                "EXPIRED",
                "EXHAUSTED",
                "CANCELLED",
            ),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_allowed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_ip_hash", sa.String(length=64), nullable=True),
        sa.Column("request_user_agent_hash", sa.String(length=64), nullable=True),
        sa.Column("provider_name", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_otp_challenges"),
    )
    op.create_index("ix_otp_challenges_phone_number", "otp_challenges", ["phone_number"])
    op.create_index("ix_otp_challenges_expires_at", "otp_challenges", ["expires_at"])
    op.create_index(
        "ix_otp_challenges_phone_status_created",
        "otp_challenges",
        ["phone_number", "status", "created_at"],
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_refresh_token_hash", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_auth_sessions_user_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_auth_sessions_company_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_auth_sessions_company_membership",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auth_sessions"),
        sa.UniqueConstraint("refresh_token_hash", name="uq_auth_sessions_refresh_token_hash"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_company_id", "auth_sessions", ["company_id"])
    op.create_index("ix_auth_sessions_membership_id", "auth_sessions", ["membership_id"])
    op.create_index("ix_auth_sessions_family_id", "auth_sessions", ["family_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_index(
        "ix_auth_sessions_previous_refresh_token_hash",
        "auth_sessions",
        ["previous_refresh_token_hash"],
    )
    op.create_index(
        "ix_auth_sessions_company_membership", "auth_sessions", ["company_id", "membership_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_company_membership", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_previous_refresh_token_hash", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_family_id", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_membership_id", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_company_id", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_otp_challenges_phone_status_created", table_name="otp_challenges")
    op.drop_index("ix_otp_challenges_expires_at", table_name="otp_challenges")
    op.drop_index("ix_otp_challenges_phone_number", table_name="otp_challenges")
    op.drop_table("otp_challenges")
    op.execute("DROP TYPE IF EXISTS otp_challenge_status_enum")
