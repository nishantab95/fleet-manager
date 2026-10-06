"""Add working maintenance, compliance, notification, telematics, and fuel modules."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_working_future_modules"
down_revision: str | Sequence[str] | None = "0018_future_foundations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> postgresql.ENUM:
    value = postgresql.ENUM(*values, name=name, create_type=False)
    value.create(op.get_bind(), checkfirst=True)
    return value


def _timestamps(*, updated: bool = False) -> list[sa.Column]:
    columns = [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        )
    ]
    if updated:
        columns.append(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            )
        )
    return columns


def upgrade() -> None:
    work_order_status = _enum(
        "maintenance_work_order_status_enum",
        "DRAFT",
        "SCHEDULED",
        "IN_PROGRESS",
        "COMPLETED",
        "CANCELLED",
    )
    notification_state = _enum("notification_state_enum", "UNREAD", "READ", "ACKNOWLEDGED")
    notification_category = _enum(
        "notification_category_enum",
        "EMERGENCY",
        "DIESEL_PENDING",
        "TRIP_PENDING",
        "METER_PENDING",
        "MAINTENANCE_DUE",
        "DOCUMENT_EXPIRY",
        "ASSIGNMENT_CHANGED",
        "SYSTEM",
    )
    transition_type = _enum("geofence_transition_type_enum", "ENTER", "EXIT")
    fuel_source_type = _enum(
        "fuel_source_type_enum",
        "DRIVER_ENTRY",
        "BUNK_DISPENSER",
        "FUEL_CARD",
        "TANK_SENSOR",
        "SUPPLIER",
        "OTHER",
    )
    fuel_row_status = _enum(
        "fuel_import_row_status_enum", "IMPORTED", "DUPLICATE", "INVALID", "UNMAPPED"
    )
    fuel_batch_status = _enum(
        "fuel_import_batch_status_enum",
        "PROCESSING",
        "COMPLETED",
        "COMPLETED_WITH_ERRORS",
    )
    fuel_reconciliation_status = _enum(
        "fuel_reconciliation_status_enum",
        "MATCHED",
        "WITHIN_TOLERANCE",
        "MISMATCH",
        "INSUFFICIENT_DATA",
        "AMBIGUOUS",
    )

    op.add_column("maintenance_schedules", sa.Column("custom_label", sa.String(120)))
    op.add_column("maintenance_schedules", sa.Column("description", sa.Text()))
    op.add_column(
        "maintenance_schedules",
        sa.Column("warning_threshold", sa.Numeric(12, 2), server_default="0", nullable=False),
    )
    op.alter_column("maintenance_schedules", "warning_threshold", server_default=None)
    op.create_check_constraint(
        "maintenance_warning_threshold_range",
        "maintenance_schedules",
        "warning_threshold >= 0 AND warning_threshold <= interval_value",
    )

    op.create_table(
        "maintenance_work_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True)),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", work_order_status, nullable=False),
        sa.Column("vendor_name", sa.String(200)),
        sa.Column("scheduled_for", sa.Date()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("completion_meter", sa.Numeric(12, 2)),
        sa.Column("labor_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("parts_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("other_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        *_timestamps(updated=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "id", name="uq_maintenance_work_orders_company_id"),
        sa.ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_maintenance_work_orders_company_asset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "schedule_id"],
            ["maintenance_schedules.company_id", "maintenance_schedules.id"],
            name="fk_maintenance_work_orders_company_schedule",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_work_orders_company_creator",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "completion_meter IS NULL OR completion_meter >= 0",
            name="maintenance_work_order_meter_non_negative",
        ),
        sa.CheckConstraint(
            "labor_cost >= 0 AND parts_cost >= 0 AND other_cost >= 0",
            name="maintenance_work_order_costs_non_negative",
        ),
    )
    for column in ("company_id", "asset_id", "schedule_id"):
        op.create_index(f"ix_maintenance_work_orders_{column}", "maintenance_work_orders", [column])
    op.create_index(
        "ix_maintenance_work_orders_company_status_scheduled",
        "maintenance_work_orders",
        ["company_id", "status", "scheduled_for"],
    )

    for name, type_ in (
        ("work_order_id", postgresql.UUID(as_uuid=True)),
        ("vendor_name", sa.String(200)),
        ("labor_cost", sa.Numeric(14, 2)),
        ("parts_cost", sa.Numeric(14, 2)),
        ("other_cost", sa.Numeric(14, 2)),
    ):
        kwargs = {"nullable": True}
        if name.endswith("cost"):
            kwargs = {"nullable": False, "server_default": "0"}
        op.add_column("maintenance_records", sa.Column(name, type_, **kwargs))
    for name in ("labor_cost", "parts_cost", "other_cost"):
        op.alter_column("maintenance_records", name, server_default=None)
    op.create_unique_constraint(
        "uq_maintenance_records_work_order_id", "maintenance_records", ["work_order_id"]
    )
    op.create_foreign_key(
        "fk_maintenance_records_company_work_order",
        "maintenance_records",
        "maintenance_work_orders",
        ["company_id", "work_order_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "maintenance_record_costs_non_negative",
        "maintenance_records",
        "labor_cost >= 0 AND parts_cost >= 0 AND other_cost >= 0",
    )

    op.create_table(
        "maintenance_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("work_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_object_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["company_id", "work_order_id"],
            ["maintenance_work_orders.company_id", "maintenance_work_orders.id"],
            name="fk_maintenance_attachments_company_work_order",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "evidence_object_id"],
            ["evidence_objects.company_id", "evidence_objects.id"],
            name="fk_maintenance_attachments_company_evidence",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_attachments_company_creator",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id",
            "evidence_object_id",
            name="uq_maintenance_attachments_company_evidence",
        ),
    )
    op.create_index(
        "ix_maintenance_attachments_company_id", "maintenance_attachments", ["company_id"]
    )
    op.create_index(
        "ix_maintenance_attachments_work_order_id",
        "maintenance_attachments",
        ["work_order_id"],
    )

    op.create_table(
        "asset_document_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "asset_type",
            postgresql.ENUM(name="fleet_asset_type_enum", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "ownership_type",
            postgresql.ENUM(name="asset_ownership_type_enum", create_type=False),
        ),
        sa.Column("document_type", sa.String(64), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("expiry_warning_days", sa.Integer(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "id", name="uq_asset_document_policies_company_id"),
        sa.ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_asset_document_policies_company_creator",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "expiry_warning_days BETWEEN 0 AND 3650",
            name="asset_document_policy_warning_days_range",
        ),
        sa.CheckConstraint(
            "length(btrim(document_type)) BETWEEN 1 AND 64",
            name="asset_document_policy_type_non_empty",
        ),
    )
    op.create_index(
        "ix_asset_document_policies_company_id", "asset_document_policies", ["company_id"]
    )
    op.create_index(
        "uq_asset_document_policies_scope",
        "asset_document_policies",
        ["company_id", "asset_type", "ownership_type", "document_type"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )

    op.create_table(
        "in_app_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("recipient_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", notification_category, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.String(255), nullable=False),
        sa.Column("deep_link", postgresql.JSONB()),
        sa.Column("state", notification_state, nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["company_id", "recipient_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_notifications_company_recipient",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "company_id",
            "recipient_membership_id",
            "dedupe_key",
            name="uq_notifications_recipient_dedupe",
        ),
    )
    op.create_index("ix_in_app_notifications_company_id", "in_app_notifications", ["company_id"])
    op.create_index(
        "ix_in_app_notifications_recipient_membership_id",
        "in_app_notifications",
        ["recipient_membership_id"],
    )
    op.create_index(
        "ix_notifications_recipient_state_created",
        "in_app_notifications",
        ["company_id", "recipient_membership_id", "state", "created_at"],
    )

    op.create_table(
        "telematics_vehicle_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("provider_vehicle_id", sa.String(160), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        *_timestamps(updated=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "id", name="uq_telematics_mappings_company_id"),
        sa.UniqueConstraint(
            "company_id",
            "provider",
            "provider_vehicle_id",
            name="uq_telematics_mappings_provider_vehicle",
        ),
        sa.UniqueConstraint(
            "company_id", "asset_id", "provider", name="uq_telematics_mappings_asset_provider"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_telematics_mappings_company_asset",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_telematics_mappings_company_creator",
            ondelete="RESTRICT",
        ),
    )
    for column in ("company_id", "asset_id"):
        op.create_index(
            f"ix_telematics_vehicle_mappings_{column}",
            "telematics_vehicle_mappings",
            [column],
        )

    op.create_table(
        "site_geofences",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("radius_m", sa.Numeric(10, 2), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        *_timestamps(updated=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "id", name="uq_site_geofences_company_id"),
        sa.UniqueConstraint("company_id", "site_id", name="uq_site_geofences_company_site"),
        sa.ForeignKeyConstraint(
            ["company_id", "site_id"],
            ["sites.company_id", "sites.id"],
            name="fk_site_geofences_company_site",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_site_geofences_company_creator",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "radius_m > 0 AND radius_m <= 100000", name="site_geofence_radius_range"
        ),
    )
    op.create_index("ix_site_geofences_company_id", "site_geofences", ["company_id"])
    op.create_index("ix_site_geofences_site_id", "site_geofences", ["site_id"])

    op.create_table(
        "telematics_positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mapping_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_event_id", sa.String(200), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("speed_kph", sa.Numeric(8, 2)),
        sa.Column("heading", sa.Numeric(6, 2)),
        sa.Column("ignition_state", sa.Boolean()),
        sa.Column("odometer_km", sa.Numeric(12, 2)),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "id", name="uq_telematics_positions_company_id"),
        sa.UniqueConstraint(
            "company_id",
            "mapping_id",
            "provider_event_id",
            name="uq_telematics_positions_provider_event",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "mapping_id"],
            ["telematics_vehicle_mappings.company_id", "telematics_vehicle_mappings.id"],
            name="fk_telematics_positions_company_mapping",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_telematics_positions_company_asset",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "latitude BETWEEN -90 AND 90", name="telematics_position_latitude_range"
        ),
        sa.CheckConstraint(
            "longitude BETWEEN -180 AND 180", name="telematics_position_longitude_range"
        ),
        sa.CheckConstraint(
            "speed_kph IS NULL OR speed_kph >= 0", name="telematics_position_speed_non_negative"
        ),
        sa.CheckConstraint(
            "heading IS NULL OR (heading >= 0 AND heading < 360)",
            name="telematics_position_heading_range",
        ),
        sa.CheckConstraint(
            "odometer_km IS NULL OR odometer_km >= 0",
            name="telematics_position_odometer_non_negative",
        ),
    )
    for column in ("company_id", "mapping_id", "asset_id"):
        op.create_index(f"ix_telematics_positions_{column}", "telematics_positions", [column])
    op.create_index(
        "ix_telematics_positions_company_asset_recorded",
        "telematics_positions",
        ["company_id", "asset_id", "recorded_at"],
    )

    op.create_table(
        "geofence_transitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transition_type", transition_type, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("distance_m", sa.Numeric(12, 2), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_geofence_transitions_company_asset",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "site_id"],
            ["sites.company_id", "sites.id"],
            name="fk_geofence_transitions_company_site",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "position_id"],
            ["telematics_positions.company_id", "telematics_positions.id"],
            name="fk_geofence_transitions_company_position",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "company_id", "position_id", "site_id", name="uq_geofence_transitions_position_site"
        ),
    )
    for column in ("company_id", "asset_id", "site_id", "position_id"):
        op.create_index(f"ix_geofence_transitions_{column}", "geofence_transitions", [column])
    op.create_index(
        "ix_geofence_transitions_company_asset_occurred",
        "geofence_transitions",
        ["company_id", "asset_id", "occurred_at"],
    )

    op.create_table(
        "fuel_import_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("source_name", sa.String(120), nullable=False),
        sa.Column("status", fuel_batch_status, nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("imported_rows", sa.Integer(), nullable=False),
        sa.Column("rejected_rows", sa.Integer(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        *_timestamps(updated=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "id", name="uq_fuel_import_batches_company_id"),
        sa.ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_fuel_import_batches_company_creator",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "total_rows >= 0 AND imported_rows >= 0 AND rejected_rows >= 0",
            name="fuel_import_batch_counts_non_negative",
        ),
    )
    op.create_index("ix_fuel_import_batches_company_id", "fuel_import_batches", ["company_id"])

    op.create_table(
        "external_fuel_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("row_status", fuel_row_status, nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True)),
        sa.Column("asset_identifier", sa.String(160), nullable=False),
        sa.Column("source_type", fuel_source_type, nullable=False),
        sa.Column("source_name", sa.String(120), nullable=False),
        sa.Column("external_transaction_id", sa.String(160), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("litres", sa.Numeric(12, 3)),
        sa.Column("raw_row", postgresql.JSONB(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "id", name="uq_external_fuel_transactions_company_id"),
        sa.UniqueConstraint(
            "company_id", "batch_id", "row_number", name="uq_external_fuel_transactions_batch_row"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "batch_id"],
            ["fuel_import_batches.company_id", "fuel_import_batches.id"],
            name="fk_external_fuel_transactions_company_batch",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_external_fuel_transactions_company_asset",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("row_number > 0", name="external_fuel_transaction_row_positive"),
        sa.CheckConstraint(
            "litres IS NULL OR litres > 0", name="external_fuel_transaction_litres_positive"
        ),
    )
    for column in ("company_id", "batch_id", "asset_id"):
        op.create_index(
            f"ix_external_fuel_transactions_{column}", "external_fuel_transactions", [column]
        )
    op.create_index(
        "uq_external_fuel_transactions_imported_source_external",
        "external_fuel_transactions",
        ["company_id", "source_name", "external_transaction_id"],
        unique=True,
        postgresql_where=sa.text("row_status = 'IMPORTED'::fuel_import_row_status_enum"),
    )

    op.create_table(
        "fuel_reconciliations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operational_event_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", fuel_reconciliation_status, nullable=False),
        sa.Column("tolerance_litres", sa.Numeric(12, 3), nullable=False),
        sa.Column("difference_litres", sa.Numeric(12, 3)),
        sa.Column("manually_resolved", sa.Boolean(), nullable=False),
        sa.Column("resolution_reason", sa.Text()),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True)),
        *_timestamps(updated=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "external_transaction_id", name="uq_fuel_reconciliations_transaction"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "external_transaction_id"],
            ["external_fuel_transactions.company_id", "external_fuel_transactions.id"],
            name="fk_fuel_reconciliations_company_transaction",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "operational_event_id"],
            ["operational_events.company_id", "operational_events.id"],
            name="fk_fuel_reconciliations_company_event",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "resolved_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_fuel_reconciliations_company_resolver",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "tolerance_litres >= 0", name="fuel_reconciliation_tolerance_non_negative"
        ),
        sa.CheckConstraint(
            "difference_litres IS NULL OR difference_litres >= 0",
            name="fuel_reconciliation_difference_non_negative",
        ),
        sa.CheckConstraint(
            "(manually_resolved = false AND resolution_reason IS NULL AND resolved_by IS NULL) OR "
            "(manually_resolved = true AND length(btrim(resolution_reason)) > 0 "
            "AND resolved_by IS NOT NULL)",
            name="fuel_reconciliation_resolution_complete",
        ),
    )
    for column in ("company_id", "external_transaction_id", "operational_event_id"):
        op.create_index(f"ix_fuel_reconciliations_{column}", "fuel_reconciliations", [column])


def downgrade() -> None:
    for table in (
        "fuel_reconciliations",
        "external_fuel_transactions",
        "fuel_import_batches",
        "geofence_transitions",
        "telematics_positions",
        "site_geofences",
        "telematics_vehicle_mappings",
        "in_app_notifications",
        "asset_document_policies",
        "maintenance_attachments",
    ):
        op.drop_table(table)
    op.drop_constraint(
        "maintenance_record_costs_non_negative", "maintenance_records", type_="check"
    )
    op.drop_constraint(
        "fk_maintenance_records_company_work_order", "maintenance_records", type_="foreignkey"
    )
    op.drop_constraint(
        "uq_maintenance_records_work_order_id", "maintenance_records", type_="unique"
    )
    for column in ("other_cost", "parts_cost", "labor_cost", "vendor_name", "work_order_id"):
        op.drop_column("maintenance_records", column)
    op.drop_table("maintenance_work_orders")
    op.drop_constraint(
        "maintenance_warning_threshold_range", "maintenance_schedules", type_="check"
    )
    for column in ("warning_threshold", "description", "custom_label"):
        op.drop_column("maintenance_schedules", column)
    for name in (
        "fuel_reconciliation_status_enum",
        "fuel_import_batch_status_enum",
        "fuel_import_row_status_enum",
        "fuel_source_type_enum",
        "geofence_transition_type_enum",
        "notification_category_enum",
        "notification_state_enum",
        "maintenance_work_order_status_enum",
    ):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
