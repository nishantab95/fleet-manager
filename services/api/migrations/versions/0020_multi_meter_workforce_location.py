"""Add per-asset meters, multi-trigger maintenance, payroll, and attendance location."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_multi_meter_workforce"
down_revision: str | Sequence[str] | None = "0019_working_future_modules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> postgresql.ENUM:
    value = postgresql.ENUM(*values, name=name, create_type=False)
    value.create(op.get_bind(), checkfirst=True)
    return value


def _timestamps(*, updated: bool = False) -> list[sa.Column]:
    result = [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        )
    ]
    if updated:
        result.append(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            )
        )
    return result


def upgrade() -> None:
    criterion_basis = _enum(
        "maintenance_criterion_basis_enum",
        "ODOMETER_KM",
        "HOUR_METER_HOURS",
        "CALENDAR_TIME",
    )
    meter_discrepancy_status = _enum(
        "meter_discrepancy_status_enum",
        "WITHIN_TOLERANCE",
        "MISMATCH",
        "INSUFFICIENT_DATA",
    )
    pay_basis = _enum("pay_basis_enum", "MONTHLY", "DAILY", "HOURLY")
    payroll_status = _enum("payroll_period_status_enum", "DRAFT", "REVIEWED", "FINALIZED")
    location_source = _enum(
        "location_snapshot_source_enum",
        "DUTY_START",
        "DUTY_END",
        "METER_SUBMISSION",
        "DIESEL_SUBMISSION",
        "TRIP_COMPLETE",
        "EMERGENCY",
    )
    location_status = _enum(
        "location_snapshot_status_enum",
        "AVAILABLE",
        "UNAVAILABLE",
        "DENIED",
        "LOW_ACCURACY",
    )

    op.add_column(
        "fleet_assets",
        sa.Column("supports_odometer_km", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "fleet_assets",
        sa.Column("supports_hour_meter", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.execute(
        "UPDATE fleet_assets SET supports_odometer_km = (asset_type = 'TIPPER'), "
        "supports_hour_meter = (asset_type <> 'TIPPER')"
    )
    op.alter_column("fleet_assets", "supports_odometer_km", server_default=None)
    op.alter_column("fleet_assets", "supports_hour_meter", server_default=None)

    op.add_column(
        "operational_events", sa.Column("capture_group_uuid", postgresql.UUID(as_uuid=True))
    )
    op.create_index(
        "ix_operational_events_capture_group_uuid",
        "operational_events",
        ["capture_group_uuid"],
    )
    op.create_index(
        "ix_events_company_capture_group",
        "operational_events",
        ["company_id", "capture_group_uuid"],
    )

    op.drop_constraint("ck_duty_sessions_one_start_meter", "duty_sessions", type_="check")
    op.drop_constraint("ck_duty_sessions_one_end_meter", "duty_sessions", type_="check")
    op.drop_constraint("ck_duty_sessions_meter_type_consistent", "duty_sessions", type_="check")
    op.create_check_constraint(
        "ck_duty_sessions_at_least_one_start_meter",
        "duty_sessions",
        "start_km IS NOT NULL OR start_hmr IS NOT NULL",
    )

    for table in ("maintenance_records", "maintenance_work_orders"):
        op.add_column(table, sa.Column("completion_odometer_km", sa.Numeric(12, 2)))
        op.add_column(table, sa.Column("completion_hour_meter", sa.Numeric(12, 2)))
        op.create_check_constraint(
            f"{table.removesuffix('s')}_odometer_non_negative",
            table,
            "completion_odometer_km IS NULL OR completion_odometer_km >= 0",
        )
        op.create_check_constraint(
            f"{table.removesuffix('s')}_hour_meter_non_negative",
            table,
            "completion_hour_meter IS NULL OR completion_hour_meter >= 0",
        )

    op.create_table(
        "maintenance_criteria",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("basis", criterion_basis, nullable=False),
        sa.Column("interval_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("warning_threshold", sa.Numeric(12, 2), nullable=False),
        sa.Column("last_baseline_value", sa.Numeric(12, 2)),
        sa.Column("last_baseline_date", sa.Date()),
        sa.Column("next_due_value", sa.Numeric(12, 2)),
        sa.Column("next_due_date", sa.Date()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        *_timestamps(updated=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "id", name="uq_maintenance_criteria_company_id"),
        sa.UniqueConstraint(
            "company_id",
            "schedule_id",
            "basis",
            name="uq_maintenance_criteria_schedule_basis",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "schedule_id"],
            ["maintenance_schedules.company_id", "maintenance_schedules.id"],
            name="fk_maintenance_criteria_company_schedule",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_criteria_company_creator",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("interval_value > 0", name="maintenance_criterion_interval_positive"),
        sa.CheckConstraint(
            "warning_threshold >= 0 AND warning_threshold <= interval_value",
            name="maintenance_criterion_warning_range",
        ),
        sa.CheckConstraint(
            "last_baseline_value IS NULL OR last_baseline_value >= 0",
            name="maintenance_criterion_baseline_non_negative",
        ),
        sa.CheckConstraint(
            "next_due_value IS NULL OR next_due_value >= 0",
            name="maintenance_criterion_due_non_negative",
        ),
    )
    op.create_index("ix_maintenance_criteria_company_id", "maintenance_criteria", ["company_id"])
    op.create_index("ix_maintenance_criteria_schedule_id", "maintenance_criteria", ["schedule_id"])
    op.execute(
        "INSERT INTO maintenance_criteria "
        "(id, company_id, schedule_id, basis, interval_value, warning_threshold, "
        "last_baseline_value, last_baseline_date, next_due_value, next_due_date, created_by, "
        "created_at, updated_at) "
        "SELECT gen_random_uuid(), company_id, id, "
        "CASE interval_basis::text WHEN 'KM' THEN 'ODOMETER_KM'::maintenance_criterion_basis_enum "
        "WHEN 'HMR' THEN 'HOUR_METER_HOURS'::maintenance_criterion_basis_enum "
        "ELSE 'CALENDAR_TIME'::maintenance_criterion_basis_enum END, "
        "interval_value, warning_threshold, last_service_meter, last_service_date, "
        "next_due_meter, next_due_date, created_by, created_at, updated_at "
        "FROM maintenance_schedules"
    )

    op.add_column("telematics_positions", sa.Column("engine_hours", sa.Numeric(12, 2)))
    op.add_column("telematics_positions", sa.Column("battery_voltage", sa.Numeric(8, 3)))
    op.create_check_constraint(
        "telematics_position_engine_hours_non_negative",
        "telematics_positions",
        "engine_hours IS NULL OR engine_hours >= 0",
    )
    op.create_check_constraint(
        "telematics_position_voltage_non_negative",
        "telematics_positions",
        "battery_voltage IS NULL OR battery_voltage >= 0",
    )
    op.create_table(
        "telematics_meter_discrepancies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manual_event_id", postgresql.UUID(as_uuid=True)),
        sa.Column("meter_type", sa.String(40), nullable=False),
        sa.Column("telemetry_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("manual_value", sa.Numeric(12, 2)),
        sa.Column("tolerance", sa.Numeric(12, 2), nullable=False),
        sa.Column("difference", sa.Numeric(12, 2)),
        sa.Column("status", meter_discrepancy_status, nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_telematics_discrepancies_company_asset",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "position_id"],
            ["telematics_positions.company_id", "telematics_positions.id"],
            name="fk_telematics_discrepancies_company_position",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "manual_event_id"],
            ["operational_events.company_id", "operational_events.id"],
            name="fk_telematics_discrepancies_company_event",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "company_id",
            "position_id",
            "meter_type",
            name="uq_telematics_discrepancies_position_meter",
        ),
        sa.CheckConstraint(
            "telemetry_value >= 0 AND tolerance >= 0",
            name="telematics_discrepancy_values_non_negative",
        ),
    )
    for column in ("company_id", "asset_id", "position_id", "manual_event_id"):
        op.create_index(
            f"ix_telematics_meter_discrepancies_{column}",
            "telematics_meter_discrepancies",
            [column],
        )

    op.create_table(
        "compensation_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pay_basis", pay_basis, nullable=False),
        sa.Column("base_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("standard_duty_minutes", sa.Integer(), nullable=False),
        sa.Column("overtime_rate_per_hour", sa.Numeric(14, 2), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        *_timestamps(updated=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "id", name="uq_compensation_profiles_company_id"),
        sa.ForeignKeyConstraint(
            ["company_id", "membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_compensation_profiles_company_member",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_compensation_profiles_company_creator",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("base_amount >= 0", name="compensation_base_non_negative"),
        sa.CheckConstraint(
            "overtime_rate_per_hour >= 0", name="compensation_overtime_rate_non_negative"
        ),
        sa.CheckConstraint(
            "standard_duty_minutes > 0 AND standard_duty_minutes <= 1440",
            name="compensation_standard_minutes_range",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="compensation_effective_dates_ordered",
        ),
    )
    op.create_index("ix_compensation_profiles_company_id", "compensation_profiles", ["company_id"])
    op.create_index(
        "ix_compensation_profiles_membership_id", "compensation_profiles", ["membership_id"]
    )
    op.create_index(
        "ix_compensation_profiles_member_effective",
        "compensation_profiles",
        ["company_id", "membership_id", "effective_from"],
    )

    op.create_table(
        "payroll_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("status", payroll_status, nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("finalized_by", postgresql.UUID(as_uuid=True)),
        sa.Column("finalized_at", sa.DateTime(timezone=True)),
        *_timestamps(updated=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "id", name="uq_payroll_periods_company_id"),
        sa.UniqueConstraint("company_id", "starts_on", "ends_on", name="uq_payroll_period_dates"),
        sa.ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_payroll_periods_company_creator",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "reviewed_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_payroll_periods_company_reviewer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "finalized_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_payroll_periods_company_finalizer",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("ends_on >= starts_on", name="payroll_period_dates_ordered"),
    )
    op.create_index("ix_payroll_periods_company_id", "payroll_periods", ["company_id"])

    op.create_table(
        "payroll_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name_snapshot", sa.String(200), nullable=False),
        sa.Column("pay_basis_snapshot", pay_basis, nullable=False),
        sa.Column("base_pay", sa.Numeric(14, 2), nullable=False),
        sa.Column("duty_minutes", sa.Integer(), nullable=False),
        sa.Column("overtime_minutes", sa.Integer(), nullable=False),
        sa.Column("overtime_rate_per_hour", sa.Numeric(14, 2), nullable=False),
        sa.Column("overtime_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("adjustment_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("calculated_gross_pay", sa.Numeric(14, 2), nullable=False),
        sa.Column("calculation_state", sa.String(40), nullable=False),
        sa.Column("calculation_snapshot", postgresql.JSONB(), nullable=False),
        *_timestamps(updated=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "id", name="uq_payroll_lines_company_id"),
        sa.UniqueConstraint(
            "company_id", "period_id", "membership_id", name="uq_payroll_lines_period_member"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "period_id"],
            ["payroll_periods.company_id", "payroll_periods.id"],
            name="fk_payroll_lines_company_period",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_payroll_lines_company_member",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "base_pay >= 0 AND duty_minutes >= 0 AND overtime_minutes >= 0 "
            "AND overtime_rate_per_hour >= 0 AND overtime_amount >= 0",
            name="payroll_line_values_non_negative",
        ),
    )
    for column in ("company_id", "period_id", "membership_id"):
        op.create_index(f"ix_payroll_lines_{column}", "payroll_lines", [column])

    op.create_table(
        "payroll_adjustments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["company_id", "line_id"],
            ["payroll_lines.company_id", "payroll_lines.id"],
            name="fk_payroll_adjustments_company_line",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_payroll_adjustments_company_creator",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("amount <> 0", name="payroll_adjustment_non_zero"),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="payroll_adjustment_reason_non_empty"),
    )
    op.create_index("ix_payroll_adjustments_company_id", "payroll_adjustments", ["company_id"])
    op.create_index("ix_payroll_adjustments_line_id", "payroll_adjustments", ["line_id"])

    op.create_table(
        "attendance_location_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("site_match_required", sa.Boolean(), nullable=False),
        sa.Column("asset_proximity_threshold_m", sa.Numeric(10, 2), nullable=False),
        sa.Column("gps_freshness_seconds", sa.Integer(), nullable=False),
        sa.Column("max_accuracy_m", sa.Numeric(10, 2), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=False),
        *_timestamps(updated=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id"),
        sa.ForeignKeyConstraint(
            ["company_id", "updated_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_attendance_location_settings_company_updater",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "asset_proximity_threshold_m > 0 AND gps_freshness_seconds > 0 "
            "AND max_accuracy_m > 0 AND retention_days > 0",
            name="attendance_location_settings_positive",
        ),
    )

    op.create_table(
        "attendance_location_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("duty_session_id", postgresql.UUID(as_uuid=True)),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operational_event_id", postgresql.UUID(as_uuid=True)),
        sa.Column("captured_at_device", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at_server",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("latitude", sa.Numeric(9, 6)),
        sa.Column("longitude", sa.Numeric(9, 6)),
        sa.Column("accuracy_m", sa.Numeric(10, 2)),
        sa.Column("source", location_source, nullable=False),
        sa.Column("status", location_status, nullable=False),
        sa.Column("permission_state", sa.String(40)),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["company_id", "membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_location_snapshots_company_member",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "duty_session_id"],
            ["duty_sessions.company_id", "duty_sessions.id"],
            name="fk_location_snapshots_company_duty",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "assignment_id"],
            ["assignments.company_id", "assignments.id"],
            name="fk_location_snapshots_company_assignment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_location_snapshots_company_asset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "site_id"],
            ["sites.company_id", "sites.id"],
            name="fk_location_snapshots_company_site",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "operational_event_id"],
            ["operational_events.company_id", "operational_events.id"],
            name="fk_location_snapshots_company_event",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name="location_snapshot_latitude_range",
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="location_snapshot_longitude_range",
        ),
        sa.CheckConstraint(
            "accuracy_m IS NULL OR accuracy_m >= 0",
            name="location_snapshot_accuracy_non_negative",
        ),
        sa.CheckConstraint(
            "(status = 'AVAILABLE' AND latitude IS NOT NULL AND longitude IS NOT NULL "
            "AND accuracy_m IS NOT NULL) OR status <> 'AVAILABLE'",
            name="location_snapshot_available_coordinates",
        ),
    )
    for column in (
        "company_id",
        "membership_id",
        "duty_session_id",
        "assignment_id",
        "asset_id",
        "site_id",
        "operational_event_id",
    ):
        op.create_index(
            f"ix_attendance_location_snapshots_{column}",
            "attendance_location_snapshots",
            [column],
        )
    op.create_index(
        "ix_location_snapshots_member_captured",
        "attendance_location_snapshots",
        ["company_id", "membership_id", "captured_at_device"],
    )


def downgrade() -> None:
    for table in (
        "attendance_location_snapshots",
        "attendance_location_settings",
        "payroll_adjustments",
        "payroll_lines",
        "payroll_periods",
        "compensation_profiles",
        "telematics_meter_discrepancies",
    ):
        op.drop_table(table)
    op.drop_constraint(
        "telematics_position_voltage_non_negative", "telematics_positions", type_="check"
    )
    op.drop_constraint(
        "telematics_position_engine_hours_non_negative",
        "telematics_positions",
        type_="check",
    )
    op.drop_column("telematics_positions", "battery_voltage")
    op.drop_column("telematics_positions", "engine_hours")
    op.drop_table("maintenance_criteria")
    for table in ("maintenance_work_orders", "maintenance_records"):
        op.drop_constraint(
            f"{table.removesuffix('s')}_hour_meter_non_negative", table, type_="check"
        )
        op.drop_constraint(f"{table.removesuffix('s')}_odometer_non_negative", table, type_="check")
        op.drop_column(table, "completion_hour_meter")
        op.drop_column(table, "completion_odometer_km")
    op.drop_constraint("ck_duty_sessions_at_least_one_start_meter", "duty_sessions", type_="check")
    op.create_check_constraint(
        "ck_duty_sessions_one_start_meter",
        "duty_sessions",
        "(start_km IS NOT NULL AND start_hmr IS NULL) OR "
        "(start_km IS NULL AND start_hmr IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_duty_sessions_one_end_meter",
        "duty_sessions",
        "NOT (end_km IS NOT NULL AND end_hmr IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_duty_sessions_meter_type_consistent",
        "duty_sessions",
        "(start_km IS NULL OR end_hmr IS NULL) AND (start_hmr IS NULL OR end_km IS NULL)",
    )
    op.drop_index("ix_events_company_capture_group", table_name="operational_events")
    op.drop_index("ix_operational_events_capture_group_uuid", table_name="operational_events")
    op.drop_column("operational_events", "capture_group_uuid")
    op.drop_column("fleet_assets", "supports_hour_meter")
    op.drop_column("fleet_assets", "supports_odometer_km")
    for name in (
        "location_snapshot_status_enum",
        "location_snapshot_source_enum",
        "payroll_period_status_enum",
        "pay_basis_enum",
        "meter_discrepancy_status_enum",
        "maintenance_criterion_basis_enum",
    ):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
