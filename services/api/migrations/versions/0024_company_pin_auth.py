"""Add company-managed activation and device PIN credentials."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_company_pin_auth"
down_revision: str | Sequence[str] | None = "0023_user_auth_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "otp_challenges",
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "otp_challenges",
        sa.Column(
            "purpose",
            sa.String(length=32),
            server_default="LOGIN_OTP",
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_otp_challenges_membership_id",
        "otp_challenges",
        "company_memberships",
        ["membership_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_otp_challenges_membership_id",
        "otp_challenges",
        ["membership_id"],
    )

    op.create_table(
        "company_pin_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credential_hash", sa.String(length=64), nullable=False),
        sa.Column("installation_id_hash", sa.String(length=64), nullable=False),
        sa.Column("pin_hash", sa.String(length=128), nullable=True),
        sa.Column("pin_salt", sa.String(length=64), nullable=True),
        sa.Column("setup_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_attempt_count", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_authenticated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_company_pin_credentials_user_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_company_pin_credentials_company_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_company_pin_credentials_company_membership",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_company_pin_credentials"),
        sa.UniqueConstraint("credential_hash", name="uq_company_pin_credentials_credential_hash"),
    )
    op.create_index("ix_company_pin_credentials_user_id", "company_pin_credentials", ["user_id"])
    op.create_index(
        "ix_company_pin_credentials_company_id", "company_pin_credentials", ["company_id"]
    )
    op.create_index(
        "ix_company_pin_credentials_membership_id",
        "company_pin_credentials",
        ["membership_id"],
    )
    op.create_index(
        "ix_company_pin_credentials_company_membership",
        "company_pin_credentials",
        ["company_id", "membership_id"],
    )
    op.create_index(
        "uq_company_pin_credentials_active_membership",
        "company_pin_credentials",
        ["membership_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "uq_company_pin_credentials_active_company_user",
        "company_pin_credentials",
        ["company_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_company_pin_credentials_active_company_user",
        table_name="company_pin_credentials",
    )
    op.drop_index(
        "uq_company_pin_credentials_active_membership",
        table_name="company_pin_credentials",
    )
    op.drop_index(
        "ix_company_pin_credentials_company_membership",
        table_name="company_pin_credentials",
    )
    op.drop_index("ix_company_pin_credentials_membership_id", table_name="company_pin_credentials")
    op.drop_index("ix_company_pin_credentials_company_id", table_name="company_pin_credentials")
    op.drop_index("ix_company_pin_credentials_user_id", table_name="company_pin_credentials")
    op.drop_table("company_pin_credentials")
    op.drop_index("ix_otp_challenges_membership_id", table_name="otp_challenges")
    op.drop_constraint("fk_otp_challenges_membership_id", "otp_challenges", type_="foreignkey")
    op.drop_column("otp_challenges", "purpose")
    op.drop_column("otp_challenges", "membership_id")
