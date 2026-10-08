"""Add tenant-scoped maintenance plans, work orders, history, and templates."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_maintenance_v2"
down_revision: str | Sequence[str] | None = "0019_asset_meters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def _create_enum(name: str, values: tuple[str, ...]) -> None:
    quoted = ", ".join(f"'{value}'" for value in values)
    op.execute(
        "DO $$ BEGIN "
        f"CREATE TYPE {name} AS ENUM ({quoted}); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )


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
    task_values = (
        "ENGINE_SERVICE",
        "ENGINE_OIL",
        "ENGINE_OIL_FILTER",
        "AIR_FILTER_CLEAN",
        "AIR_FILTER_REPLACE",
        "FUEL_FILTER",
        "GREASING",
        "TYRE_PRESSURE_CHECK",
        "TYRE_INSPECTION",
        "TYRE_ROTATION",
        "TYRE_REPLACEMENT",
        "HUB_SERVICE",
        "WHEEL_BEARING_INSPECTION",
        "BRAKE_INSPECTION",
        "BRAKE_SERVICE",
        "TRANSMISSION_SERVICE",
        "DIFFERENTIAL_OIL",
        "HYDRAULIC_OIL",
        "HYDRAULIC_FILTER",
        "HYDRAULIC_HOSE_INSPECTION",
        "COOLANT",
        "BATTERY_INSPECTION",
        "BELT_HOSE_INSPECTION",
        "UNDERCARRIAGE_INSPECTION",
        "TRACK_TENSION_CHECK",
        "SWING_BEARING_GREASING",
        "GENERAL_INSPECTION",
        "CUSTOM",
    )
    _create_enum("maintenance_task_code_enum", task_values)
    _create_enum(
        "maintenance_action_type_enum", ("INSPECT", "CLEAN", "LUBRICATE", "SERVICE", "REPLACE")
    )
    _create_enum(
        "maintenance_criterion_basis_enum",
        ("CALENDAR_DAYS", "ODOMETER_KM", "HOUR_METER_HOURS"),
    )
    _create_enum(
        "maintenance_plan_source_enum",
        ("CUSTOM", "SUGGESTED_TEMPLATE", "COPIED_ASSET", "COMPANY_DEFAULT"),
    )
    _create_enum(
        "maintenance_work_order_status_enum",
        ("DRAFT", "SCHEDULED", "IN_PROGRESS", "COMPLETED", "CANCELLED"),
    )
    _create_enum("maintenance_template_source_enum", ("COMPANY_DEFAULT", "OEM", "OTHER"))
    _create_enum("maintenance_template_verification_enum", ("VERIFIED", "UNVERIFIED"))

    uuid = postgresql.UUID(as_uuid=True)
    task_enum = _enum("maintenance_task_code_enum", *task_values)
    action_enum = _enum(
        "maintenance_action_type_enum", "INSPECT", "CLEAN", "LUBRICATE", "SERVICE", "REPLACE"
    )
    criterion_enum = _enum(
        "maintenance_criterion_basis_enum", "CALENDAR_DAYS", "ODOMETER_KM", "HOUR_METER_HOURS"
    )

    op.create_table(
        "maintenance_templates",
        sa.Column("id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column(
            "source_type",
            _enum("maintenance_template_source_enum", "COMPANY_DEFAULT", "OEM", "OTHER"),
            nullable=False,
        ),
        sa.Column("source_reference", sa.String(500), nullable=True),
        sa.Column(
            "verification_status",
            _enum("maintenance_template_verification_enum", "VERIFIED", "UNVERIFIED"),
            nullable=False,
        ),
        sa.Column(
            "asset_type",
            _enum(
                "fleet_asset_type_enum", "TIPPER", "EXCAVATOR", "BACKHOE_LOADER", "ROLLER", "GRADER"
            ),
            nullable=True,
        ),
        sa.Column("manufacturer", sa.String(100), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("model_year_min", sa.Integer(), nullable=True),
        sa.Column("model_year_max", sa.Integer(), nullable=True),
        sa.Column("is_generic", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by_membership_id", uuid, nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["company_id", "created_by_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_templates_company_creator",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "id", name="uq_maintenance_templates_company_id"),
        sa.UniqueConstraint(
            "company_id", "name", "version", name="uq_maintenance_templates_name_version"
        ),
        sa.CheckConstraint(
            "model_year_min IS NULL OR model_year_min BETWEEN 1900 AND 2200",
            name="ck_maintenance_templates_model_year_min_range",
        ),
        sa.CheckConstraint(
            "model_year_max IS NULL OR model_year_max BETWEEN 1900 AND 2200",
            name="ck_maintenance_templates_model_year_max_range",
        ),
        sa.CheckConstraint(
            "model_year_min IS NULL OR model_year_max IS NULL OR model_year_max >= model_year_min",
            name="ck_maintenance_templates_model_year_ordered",
        ),
    )
    op.create_index("ix_maintenance_templates_company_id", "maintenance_templates", ["company_id"])

    op.create_table(
        "maintenance_template_items",
        sa.Column("id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("template_id", uuid, nullable=False),
        sa.Column("task_code", task_enum, nullable=False),
        sa.Column("custom_label", sa.String(200), nullable=True),
        sa.Column("action_type", action_enum, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["company_id", "template_id"],
            ["maintenance_templates.company_id", "maintenance_templates.id"],
            name="fk_maintenance_template_items_company_template",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "id", name="uq_maintenance_template_items_company_id"),
        sa.CheckConstraint(
            "task_code <> 'CUSTOM' OR length(btrim(custom_label)) > 0",
            name="ck_maintenance_template_items_custom_label_required",
        ),
    )
    op.create_index(
        "ix_maintenance_template_items_company_id", "maintenance_template_items", ["company_id"]
    )
    op.create_index(
        "ix_maintenance_template_items_template_id", "maintenance_template_items", ["template_id"]
    )

    op.create_table(
        "maintenance_template_criteria",
        sa.Column("id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("template_item_id", uuid, nullable=False),
        sa.Column("basis", criterion_enum, nullable=False),
        sa.Column("interval_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("warning_value", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["company_id", "template_item_id"],
            ["maintenance_template_items.company_id", "maintenance_template_items.id"],
            name="fk_maintenance_template_criteria_company_item",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "template_item_id", "basis", name="uq_template_criterion_basis"
        ),
        sa.CheckConstraint(
            "interval_value > 0", name="ck_maintenance_template_criteria_interval_positive"
        ),
        sa.CheckConstraint(
            "warning_value >= 0 AND warning_value < interval_value",
            name="ck_maintenance_template_criteria_warning_range",
        ),
    )
    op.create_index(
        "ix_maintenance_template_criteria_company_id",
        "maintenance_template_criteria",
        ["company_id"],
    )
    op.create_index(
        "ix_maintenance_template_criteria_template_item_id",
        "maintenance_template_criteria",
        ["template_item_id"],
    )

    op.create_table(
        "maintenance_plans",
        sa.Column("id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("asset_id", uuid, nullable=False),
        sa.Column(
            "source",
            _enum(
                "maintenance_plan_source_enum",
                "CUSTOM",
                "SUGGESTED_TEMPLATE",
                "COPIED_ASSET",
                "COMPANY_DEFAULT",
            ),
            nullable=False,
        ),
        sa.Column("source_template_id", uuid, nullable=True),
        sa.Column("source_template_version", sa.String(40), nullable=True),
        sa.Column("source_asset_id", uuid, nullable=True),
        sa.Column("created_by_membership_id", uuid, nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_maintenance_plans_company_asset",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "source_template_id"],
            ["maintenance_templates.company_id", "maintenance_templates.id"],
            name="fk_maintenance_plans_company_template",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "source_asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_maintenance_plans_company_source_asset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "created_by_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_plans_company_creator",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "asset_id", name="uq_maintenance_plans_company_asset"),
        sa.UniqueConstraint("company_id", "id", name="uq_maintenance_plans_company_id"),
    )
    op.create_index("ix_maintenance_plans_company_id", "maintenance_plans", ["company_id"])
    op.create_index("ix_maintenance_plans_asset_id", "maintenance_plans", ["asset_id"])

    op.create_table(
        "maintenance_schedules",
        sa.Column("id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("plan_id", uuid, nullable=False),
        sa.Column("asset_id", uuid, nullable=False),
        sa.Column("task_code", task_enum, nullable=False),
        sa.Column("custom_label", sa.String(200), nullable=True),
        sa.Column("action_type", action_enum, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("source_template_item_id", uuid, nullable=True),
        sa.Column("created_by_membership_id", uuid, nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["company_id", "plan_id"],
            ["maintenance_plans.company_id", "maintenance_plans.id"],
            name="fk_maintenance_schedules_company_plan",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_maintenance_schedules_company_asset",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "source_template_item_id"],
            ["maintenance_template_items.company_id", "maintenance_template_items.id"],
            name="fk_maintenance_schedules_company_template_item",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "created_by_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_schedules_company_creator",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "id", name="uq_maintenance_schedules_company_id"),
        sa.CheckConstraint(
            "task_code <> 'CUSTOM' OR length(btrim(custom_label)) > 0",
            name="ck_maintenance_schedules_custom_label_required",
        ),
    )
    op.create_index("ix_maintenance_schedules_company_id", "maintenance_schedules", ["company_id"])
    op.create_index("ix_maintenance_schedules_plan_id", "maintenance_schedules", ["plan_id"])
    op.create_index("ix_maintenance_schedules_asset_id", "maintenance_schedules", ["asset_id"])
    op.create_index(
        "ix_maintenance_schedules_asset_enabled", "maintenance_schedules", ["asset_id", "enabled"]
    )

    op.create_table(
        "maintenance_criteria",
        sa.Column("id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("schedule_id", uuid, nullable=False),
        sa.Column("basis", criterion_enum, nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("interval_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("warning_value", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("baseline_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("baseline_date", sa.Date(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["company_id", "schedule_id"],
            ["maintenance_schedules.company_id", "maintenance_schedules.id"],
            name="fk_maintenance_criteria_company_schedule",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "schedule_id", "basis", name="uq_maintenance_criterion_basis"
        ),
        sa.CheckConstraint("interval_value > 0", name="ck_maintenance_criteria_interval_positive"),
        sa.CheckConstraint(
            "warning_value >= 0 AND warning_value < interval_value",
            name="ck_maintenance_criteria_warning_range",
        ),
        sa.CheckConstraint(
            "(basis = 'CALENDAR_DAYS' AND baseline_value IS NULL) OR "
            "(basis <> 'CALENDAR_DAYS' AND baseline_date IS NULL)",
            name="ck_maintenance_criteria_baseline_matches_basis",
        ),
    )
    op.create_index("ix_maintenance_criteria_company_id", "maintenance_criteria", ["company_id"])
    op.create_index("ix_maintenance_criteria_schedule_id", "maintenance_criteria", ["schedule_id"])

    op.create_table(
        "maintenance_work_orders",
        sa.Column("id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("asset_id", uuid, nullable=False),
        sa.Column("schedule_id", uuid, nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            _enum(
                "maintenance_work_order_status_enum",
                "DRAFT",
                "SCHEDULED",
                "IN_PROGRESS",
                "COMPLETED",
                "CANCELLED",
            ),
            nullable=False,
        ),
        sa.Column("scheduled_for", sa.Date(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("service_date", sa.Date(), nullable=True),
        sa.Column("completion_odometer_km", sa.Numeric(12, 2), nullable=True),
        sa.Column("completion_hour_meter", sa.Numeric(12, 2), nullable=True),
        sa.Column("vendor", sa.String(200), nullable=True),
        sa.Column("parts_cost", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("labor_cost", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("other_cost", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_membership_id", uuid, nullable=False),
        sa.Column("completed_by_membership_id", uuid, nullable=True),
        *_timestamps(),
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
            ["company_id", "created_by_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_work_orders_company_creator",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "completed_by_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_work_orders_company_completer",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "id", name="uq_maintenance_work_orders_company_id"),
        sa.CheckConstraint(
            "parts_cost >= 0 AND labor_cost >= 0 AND other_cost >= 0",
            name="ck_maintenance_work_orders_costs_non_negative",
        ),
    )
    for column in ("company_id", "asset_id", "schedule_id"):
        op.create_index(f"ix_maintenance_work_orders_{column}", "maintenance_work_orders", [column])

    op.create_table(
        "maintenance_records",
        sa.Column("id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("work_order_id", uuid, nullable=False),
        sa.Column("asset_id", uuid, nullable=False),
        sa.Column("schedule_id", uuid, nullable=True),
        sa.Column("task_code", task_enum, nullable=True),
        sa.Column("task_label", sa.String(200), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("odometer_km", sa.Numeric(12, 2), nullable=True),
        sa.Column("hour_meter", sa.Numeric(12, 2), nullable=True),
        sa.Column("vendor", sa.String(200), nullable=True),
        sa.Column("parts_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("labor_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("other_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("actor_membership_id", uuid, nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["company_id", "work_order_id"],
            ["maintenance_work_orders.company_id", "maintenance_work_orders.id"],
            name="fk_maintenance_records_company_work_order",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_maintenance_records_company_asset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "schedule_id"],
            ["maintenance_schedules.company_id", "maintenance_schedules.id"],
            name="fk_maintenance_records_company_schedule",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "actor_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_records_company_actor",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "work_order_id", name="uq_maintenance_records_work_order"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_maintenance_records_company_id"),
        sa.CheckConstraint(
            "parts_cost >= 0 AND labor_cost >= 0 AND other_cost >= 0 AND total_cost >= 0",
            name="ck_maintenance_records_costs_non_negative",
        ),
    )
    for column in ("company_id", "work_order_id", "asset_id", "schedule_id"):
        op.create_index(f"ix_maintenance_records_{column}", "maintenance_records", [column])

    op.create_table(
        "maintenance_attachments",
        sa.Column("id", uuid, nullable=False),
        sa.Column("company_id", uuid, nullable=False),
        sa.Column("record_id", uuid, nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["company_id", "record_id"],
            ["maintenance_records.company_id", "maintenance_records.id"],
            name="fk_maintenance_attachments_company_record",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "id", name="uq_maintenance_attachments_company_id"),
        sa.CheckConstraint("size_bytes > 0", name="ck_maintenance_attachments_size_positive"),
    )
    op.create_index(
        "ix_maintenance_attachments_company_id", "maintenance_attachments", ["company_id"]
    )
    op.create_index(
        "ix_maintenance_attachments_record_id", "maintenance_attachments", ["record_id"]
    )


def downgrade() -> None:
    for table in (
        "maintenance_attachments",
        "maintenance_records",
        "maintenance_work_orders",
        "maintenance_criteria",
        "maintenance_schedules",
        "maintenance_plans",
        "maintenance_template_criteria",
        "maintenance_template_items",
        "maintenance_templates",
    ):
        op.drop_table(table)
    for enum_name in (
        "maintenance_template_verification_enum",
        "maintenance_template_source_enum",
        "maintenance_work_order_status_enum",
        "maintenance_plan_source_enum",
        "maintenance_criterion_basis_enum",
        "maintenance_action_type_enum",
        "maintenance_task_code_enum",
    ):
        op.execute(f"DROP TYPE {enum_name}")
