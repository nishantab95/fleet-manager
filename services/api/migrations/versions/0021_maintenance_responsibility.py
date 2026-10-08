"""Separate maintenance responsibility and add proof/rental boundaries."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_maintenance_responsibility"
down_revision: str | Sequence[str] | None = "0020_maintenance_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_enum(name: str, values: tuple[str, ...]) -> None:
    quoted = ", ".join(f"'{value}'" for value in values)
    op.execute(
        "DO $$ BEGIN "
        f"CREATE TYPE {name} AS ENUM ({quoted}); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )


def _enum(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def _timestamps() -> tuple[sa.Column[sa.DateTime], sa.Column[sa.DateTime]]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    _create_enum(
        "maintenance_responsibility_enum",
        ("OWNER_COMPANY", "RENTER_COMPANY", "SHARED"),
    )
    _create_enum("intercompany_rental_status_enum", ("DRAFT", "ACTIVE", "ENDED", "CANCELLED"))
    _create_enum("maintenance_proof_status_enum", ("PROOF_SUBMITTED", "COMPLETED", "REJECTED"))

    op.add_column(
        "fleet_assets",
        sa.Column(
            "maintenance_responsibility",
            _enum(
                "maintenance_responsibility_enum",
                "OWNER_COMPANY",
                "RENTER_COMPANY",
                "SHARED",
            ),
            server_default=sa.text("'OWNER_COMPANY'"),
            nullable=False,
        ),
    )

    # Migration 0019 deliberately kept legacy Tippers KM-only. Maintenance V2
    # now requires every wheeled Pilot asset to collect both readings. No
    # capability-provenance field exists, so legacy defaults cannot be
    # distinguished from a later explicit edit; this one-time transition makes
    # the physical wheeled classification authoritative going forward.
    op.execute(
        "UPDATE fleet_assets SET supports_odometer_km = true, supports_hour_meter = true "
        "WHERE is_wheeled = true"
    )

    op.create_unique_constraint(
        "uq_evidence_objects_company_id", "evidence_objects", ["company_id", "id"]
    )

    responsibility = _enum(
        "maintenance_responsibility_enum", "OWNER_COMPANY", "RENTER_COMPANY", "SHARED"
    )
    rental_status = _enum(
        "intercompany_rental_status_enum", "DRAFT", "ACTIVE", "ENDED", "CANCELLED"
    )
    proof_status = _enum(
        "maintenance_proof_status_enum", "PROOF_SUBMITTED", "COMPLETED", "REJECTED"
    )

    op.create_table(
        "intercompany_asset_rentals",
        sa.Column("id", uuid, nullable=False),
        sa.Column("asset_owner_company_id", uuid, nullable=False),
        sa.Column("renting_company_id", uuid, nullable=False),
        sa.Column("owner_asset_id", uuid, nullable=False),
        sa.Column("renter_asset_id", uuid, nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", rental_status, nullable=False),
        sa.Column("maintenance_responsibility", responsibility, nullable=False),
        sa.Column(
            "share_odometer_km", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "share_hour_meter", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "share_utilization", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "share_duty_summary", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "share_driver_identity", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("share_diesel", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["asset_owner_company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["renting_company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["asset_owner_company_id", "owner_asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_intercompany_rentals_owner_asset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["renting_company_id", "renter_asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_intercompany_rentals_renter_asset",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "asset_owner_company_id <> renting_company_id",
            name="ck_intercompany_asset_rentals_different_companies",
        ),
        sa.CheckConstraint(
            "ends_at IS NULL OR ends_at > starts_at",
            name="ck_intercompany_asset_rentals_valid_period",
        ),
    )
    for column in (
        "asset_owner_company_id",
        "renting_company_id",
        "owner_asset_id",
        "renter_asset_id",
    ):
        op.create_index(
            f"ix_intercompany_asset_rentals_{column}", "intercompany_asset_rentals", [column]
        )
    op.create_index(
        "ix_intercompany_rentals_active_pair",
        "intercompany_asset_rentals",
        ["asset_owner_company_id", "renting_company_id", "status"],
    )

    op.create_table(
        "maintenance_proof_submissions",
        sa.Column("id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("asset_id", uuid, nullable=False),
        sa.Column("schedule_id", uuid, nullable=False),
        sa.Column("driver_membership_id", uuid, nullable=False),
        sa.Column("assignment_id", uuid, nullable=False),
        sa.Column("site_id", uuid, nullable=False),
        sa.Column("duty_session_id", uuid, nullable=True),
        sa.Column("client_submission_uuid", uuid, nullable=False),
        sa.Column("status", proof_status, nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by_membership_id", uuid, nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_reason", sa.String(500), nullable=True),
        sa.Column("work_order_id", uuid, nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_maintenance_proofs_company_asset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "schedule_id"],
            ["maintenance_schedules.company_id", "maintenance_schedules.id"],
            name="fk_maintenance_proofs_company_schedule",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "driver_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_proofs_company_driver",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "assignment_id"],
            ["assignments.company_id", "assignments.id"],
            name="fk_maintenance_proofs_company_assignment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "site_id"],
            ["sites.company_id", "sites.id"],
            name="fk_maintenance_proofs_company_site",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "duty_session_id"],
            ["duty_sessions.company_id", "duty_sessions.id"],
            name="fk_maintenance_proofs_company_duty",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "reviewed_by_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_proofs_company_reviewer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "work_order_id"],
            ["maintenance_work_orders.company_id", "maintenance_work_orders.id"],
            name="fk_maintenance_proofs_company_work_order",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "driver_membership_id",
            "client_submission_uuid",
            name="uq_maintenance_proofs_driver_submission",
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_maintenance_proofs_company_id"),
    )
    for column in (
        "company_id",
        "asset_id",
        "schedule_id",
        "driver_membership_id",
        "assignment_id",
        "site_id",
        "duty_session_id",
    ):
        op.create_index(
            f"ix_maintenance_proof_submissions_{column}",
            "maintenance_proof_submissions",
            [column],
        )
    op.create_index(
        "ix_maintenance_proofs_site_status",
        "maintenance_proof_submissions",
        ["site_id", "status", "submitted_at"],
    )
    op.create_index(
        "uq_maintenance_proofs_pending_schedule",
        "maintenance_proof_submissions",
        ["company_id", "schedule_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PROOF_SUBMITTED'"),
    )

    op.create_table(
        "maintenance_proof_evidence",
        sa.Column("id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("submission_id", uuid, nullable=False),
        sa.Column("evidence_id", uuid, nullable=False),
        sa.Column("display_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["company_id", "submission_id"],
            ["maintenance_proof_submissions.company_id", "maintenance_proof_submissions.id"],
            name="fk_maintenance_proof_evidence_submission",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "evidence_id"],
            ["evidence_objects.company_id", "evidence_objects.id"],
            name="fk_maintenance_proof_evidence_object",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "submission_id", "evidence_id", name="uq_maintenance_proof_evidence"
        ),
        sa.CheckConstraint(
            "display_order >= 0", name="ck_maintenance_proof_evidence_display_order_non_negative"
        ),
    )
    for column in ("company_id", "submission_id", "evidence_id"):
        op.create_index(
            f"ix_maintenance_proof_evidence_{column}", "maintenance_proof_evidence", [column]
        )


def downgrade() -> None:
    op.drop_table("maintenance_proof_evidence")
    op.drop_table("maintenance_proof_submissions")
    op.drop_table("intercompany_asset_rentals")
    op.drop_constraint("uq_evidence_objects_company_id", "evidence_objects", type_="unique")
    op.drop_column("fleet_assets", "maintenance_responsibility")
    for enum_name in (
        "maintenance_proof_status_enum",
        "intercompany_rental_status_enum",
        "maintenance_responsibility_enum",
    ):
        op.execute(f"DROP TYPE {enum_name}")
