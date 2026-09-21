"""Persist private evidence-object metadata for driver event uploads."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_evidence_objects"
down_revision: str | Sequence[str] | None = "0003_authentication"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence_objects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_event_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name="fk_evidence_objects_company", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_evidence_objects_company_membership",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_objects"),
        sa.UniqueConstraint("object_key", name="uq_evidence_objects_object_key"),
        sa.UniqueConstraint(
            "company_id",
            "membership_id",
            "client_event_uuid",
            name="uq_evidence_objects_driver_event",
        ),
    )
    op.create_index("ix_evidence_objects_company_id", "evidence_objects", ["company_id"])
    op.create_index("ix_evidence_objects_membership_id", "evidence_objects", ["membership_id"])
    op.create_index(
        "ix_evidence_objects_company_event",
        "evidence_objects",
        ["company_id", "client_event_uuid"],
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_objects_company_event", table_name="evidence_objects")
    op.drop_index("ix_evidence_objects_membership_id", table_name="evidence_objects")
    op.drop_index("ix_evidence_objects_company_id", table_name="evidence_objects")
    op.drop_table("evidence_objects")
