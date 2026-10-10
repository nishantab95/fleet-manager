"""Add durable Firebase phone identity links."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_user_auth_identity"
down_revision: str | Sequence[str] | None = "0022_maintenance_starter_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE auth_identity_provider_enum AS ENUM ('FIREBASE_PHONE'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )
    op.create_table(
        "user_auth_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "provider",
            _enum("auth_identity_provider_enum", "FIREBASE_PHONE"),
            nullable=False,
        ),
        sa.Column("provider_subject", sa.String(length=128), nullable=False),
        sa.Column("normalized_phone", sa.String(length=32), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_reason", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_auth_identities_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_auth_identities"),
        sa.UniqueConstraint(
            "provider",
            "provider_subject",
            name="uq_user_auth_identities_provider_subject",
        ),
    )
    op.create_index("ix_user_auth_identities_user_id", "user_auth_identities", ["user_id"])
    op.create_index(
        "ix_user_auth_identities_normalized_phone",
        "user_auth_identities",
        ["normalized_phone"],
    )
    op.create_index(
        "uq_user_auth_identities_active_provider_user",
        "user_auth_identities",
        ["provider", "user_id"],
        unique=True,
        postgresql_where=sa.text("disabled_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_user_auth_identities_active_provider_user",
        table_name="user_auth_identities",
    )
    op.drop_index(
        "ix_user_auth_identities_normalized_phone",
        table_name="user_auth_identities",
    )
    op.drop_index("ix_user_auth_identities_user_id", table_name="user_auth_identities")
    op.drop_table("user_auth_identities")
    op.execute("DROP TYPE IF EXISTS auth_identity_provider_enum")
