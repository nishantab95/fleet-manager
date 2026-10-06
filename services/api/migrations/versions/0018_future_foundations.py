"""Add dormant maintenance and asset-document foundations."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_future_foundations"
down_revision: str | Sequence[str] | None = "0017_internal_ids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    basis = postgresql.ENUM("KM", "HMR", "DATE", name="maintenance_basis_enum", create_type=False)
    schedule_status = postgresql.ENUM(
        "ACTIVE",
        "INACTIVE",
        name="maintenance_schedule_status_enum",
        create_type=False,
    )
    basis.create(op.get_bind(), checkfirst=True)
    schedule_status.create(op.get_bind(), checkfirst=True)

    op.create_unique_constraint(
        "uq_evidence_objects_company_id",
        "evidence_objects",
        ["company_id", "id"],
    )

    op.create_table(
        "maintenance_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("maintenance_type", sa.String(64), nullable=False),
        sa.Column("interval_basis", basis, nullable=False),
        sa.Column("interval_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("last_service_meter", sa.Numeric(12, 2), nullable=True),
        sa.Column("last_service_date", sa.Date(), nullable=True),
        sa.Column("next_due_meter", sa.Numeric(12, 2), nullable=True),
        sa.Column("next_due_date", sa.Date(), nullable=True),
        sa.Column("status", schedule_status, nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "id",
            name="uq_maintenance_schedules_company_id",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_maintenance_schedules_company_asset",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_schedules_company_creator",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "interval_value > 0",
            name="maintenance_interval_positive",
        ),
        sa.CheckConstraint(
            "last_service_meter IS NULL OR last_service_meter >= 0",
            name="maintenance_last_meter_non_negative",
        ),
        sa.CheckConstraint(
            "next_due_meter IS NULL OR next_due_meter >= 0",
            name="maintenance_next_meter_non_negative",
        ),
    )
    op.create_index(
        "ix_maintenance_schedules_company_id",
        "maintenance_schedules",
        ["company_id"],
    )
    op.create_index(
        "ix_maintenance_schedules_asset_id",
        "maintenance_schedules",
        ["asset_id"],
    )
    op.create_index(
        "ix_maintenance_schedules_company_asset_status",
        "maintenance_schedules",
        ["company_id", "asset_id", "status"],
    )

    op.create_table(
        "maintenance_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("performed_on", sa.Date(), nullable=False),
        sa.Column("meter_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["company_id", "schedule_id"],
            ["maintenance_schedules.company_id", "maintenance_schedules.id"],
            name="fk_maintenance_records_company_schedule",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_maintenance_records_company_asset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_records_company_creator",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "meter_value IS NULL OR meter_value >= 0",
            name="maintenance_record_meter_non_negative",
        ),
    )
    for column in ("company_id", "schedule_id", "asset_id"):
        op.create_index(
            f"ix_maintenance_records_{column}",
            "maintenance_records",
            [column],
        )
    op.create_index(
        "ix_maintenance_records_company_schedule_performed",
        "maintenance_records",
        ["company_id", "schedule_id", "performed_on"],
    )

    op.create_table(
        "asset_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_type", sa.String(64), nullable=False),
        sa.Column("expiry_warning_days", sa.Integer(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "id", name="uq_asset_documents_company_id"),
        sa.UniqueConstraint(
            "company_id",
            "asset_id",
            "document_type",
            name="uq_asset_documents_company_asset_type",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_asset_documents_company_asset",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_asset_documents_company_creator",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "expiry_warning_days BETWEEN 0 AND 3650",
            name="asset_document_warning_days_range",
        ),
        sa.CheckConstraint(
            "length(btrim(document_type)) BETWEEN 1 AND 64",
            name="asset_document_type_non_empty",
        ),
    )
    op.create_index("ix_asset_documents_company_id", "asset_documents", ["company_id"])
    op.create_index("ix_asset_documents_asset_id", "asset_documents", ["asset_id"])
    op.create_index(
        "ix_asset_documents_company_asset",
        "asset_documents",
        ["company_id", "asset_id"],
    )

    op.create_table(
        "asset_document_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("document_number", sa.String(120), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("issuer", sa.String(200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("evidence_object_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["company_id", "document_id"],
            ["asset_documents.company_id", "asset_documents.id"],
            name="fk_asset_document_revisions_company_document",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "evidence_object_id"],
            ["evidence_objects.company_id", "evidence_objects.id"],
            name="fk_asset_document_revisions_company_evidence",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_asset_document_revisions_company_creator",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id",
            "document_id",
            "revision_number",
            name="uq_asset_document_revisions_company_document_version",
        ),
        sa.UniqueConstraint(
            "company_id",
            "evidence_object_id",
            name="uq_asset_document_revisions_company_evidence",
        ),
        sa.CheckConstraint(
            "revision_number > 0",
            name="asset_document_revision_positive",
        ),
        sa.CheckConstraint(
            "expiry_date IS NULL OR issue_date IS NULL OR expiry_date >= issue_date",
            name="asset_document_revision_dates_ordered",
        ),
    )
    op.create_index(
        "ix_asset_document_revisions_company_id",
        "asset_document_revisions",
        ["company_id"],
    )
    op.create_index(
        "ix_asset_document_revisions_document_id",
        "asset_document_revisions",
        ["document_id"],
    )
    op.create_index(
        "ix_asset_document_revisions_company_document_created",
        "asset_document_revisions",
        ["company_id", "document_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("asset_document_revisions")
    op.drop_table("asset_documents")
    op.drop_table("maintenance_records")
    op.drop_table("maintenance_schedules")
    op.drop_constraint(
        "uq_evidence_objects_company_id",
        "evidence_objects",
        type_="unique",
    )
    postgresql.ENUM("ACTIVE", "INACTIVE", name="maintenance_schedule_status_enum").drop(
        op.get_bind(), checkfirst=True
    )
    postgresql.ENUM("KM", "HMR", "DATE", name="maintenance_basis_enum").drop(
        op.get_bind(), checkfirst=True
    )
