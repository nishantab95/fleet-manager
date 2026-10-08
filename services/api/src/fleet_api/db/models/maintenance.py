from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.models.common import UpdatedTimestampModel
from fleet_api.domain.enums import (
    FleetAssetType,
    MaintenanceActionType,
    MaintenanceCriterionBasis,
    MaintenancePlanSource,
    MaintenanceTaskCode,
    MaintenanceTemplateSourceType,
    MaintenanceTemplateVerificationStatus,
    MaintenanceWorkOrderStatus,
)


class MaintenanceTemplate(UpdatedTimestampModel):
    __tablename__ = "maintenance_templates"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    source_type: Mapped[MaintenanceTemplateSourceType] = mapped_column(
        SAEnum(MaintenanceTemplateSourceType, name="maintenance_template_source_enum"),
        nullable=False,
    )
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verification_status: Mapped[MaintenanceTemplateVerificationStatus] = mapped_column(
        SAEnum(
            MaintenanceTemplateVerificationStatus,
            name="maintenance_template_verification_enum",
        ),
        nullable=False,
    )
    asset_type: Mapped[FleetAssetType | None] = mapped_column(
        SAEnum(FleetAssetType, name="fleet_asset_type_enum"), nullable=True
    )
    manufacturer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_year_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_year_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_generic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_by_membership_id: Mapped[UUID] = mapped_column(nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "created_by_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_templates_company_creator",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "id", name="uq_maintenance_templates_company_id"),
        UniqueConstraint(
            "company_id", "name", "version", name="uq_maintenance_templates_name_version"
        ),
        CheckConstraint(
            "model_year_min IS NULL OR model_year_min BETWEEN 1900 AND 2200",
            name="model_year_min_range",
        ),
        CheckConstraint(
            "model_year_max IS NULL OR model_year_max BETWEEN 1900 AND 2200",
            name="model_year_max_range",
        ),
        CheckConstraint(
            "model_year_min IS NULL OR model_year_max IS NULL OR model_year_max >= model_year_min",
            name="model_year_ordered",
        ),
    )


class MaintenanceTemplateItem(UpdatedTimestampModel):
    __tablename__ = "maintenance_template_items"

    company_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    template_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    task_code: Mapped[MaintenanceTaskCode] = mapped_column(
        SAEnum(MaintenanceTaskCode, name="maintenance_task_code_enum"), nullable=False
    )
    custom_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    action_type: Mapped[MaintenanceActionType] = mapped_column(
        SAEnum(MaintenanceActionType, name="maintenance_action_type_enum"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "template_id"],
            ["maintenance_templates.company_id", "maintenance_templates.id"],
            name="fk_maintenance_template_items_company_template",
            ondelete="CASCADE",
        ),
        UniqueConstraint("company_id", "id", name="uq_maintenance_template_items_company_id"),
        CheckConstraint(
            "task_code <> 'CUSTOM' OR length(btrim(custom_label)) > 0",
            name="custom_label_required",
        ),
    )


class MaintenanceTemplateCriterion(UpdatedTimestampModel):
    __tablename__ = "maintenance_template_criteria"

    company_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    template_item_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    basis: Mapped[MaintenanceCriterionBasis] = mapped_column(
        SAEnum(MaintenanceCriterionBasis, name="maintenance_criterion_basis_enum"),
        nullable=False,
    )
    interval_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    warning_value: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=0, server_default=text("0")
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "template_item_id"],
            ["maintenance_template_items.company_id", "maintenance_template_items.id"],
            name="fk_maintenance_template_criteria_company_item",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "company_id", "template_item_id", "basis", name="uq_template_criterion_basis"
        ),
        CheckConstraint("interval_value > 0", name="interval_positive"),
        CheckConstraint(
            "warning_value >= 0 AND warning_value < interval_value",
            name="warning_range",
        ),
    )


class MaintenancePlan(UpdatedTimestampModel):
    __tablename__ = "maintenance_plans"

    company_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    asset_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    source: Mapped[MaintenancePlanSource] = mapped_column(
        SAEnum(MaintenancePlanSource, name="maintenance_plan_source_enum"), nullable=False
    )
    source_template_id: Mapped[UUID | None] = mapped_column(nullable=True)
    source_template_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_asset_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_by_membership_id: Mapped[UUID] = mapped_column(nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_maintenance_plans_company_asset",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "source_template_id"],
            ["maintenance_templates.company_id", "maintenance_templates.id"],
            name="fk_maintenance_plans_company_template",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "source_asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_maintenance_plans_company_source_asset",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "created_by_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_plans_company_creator",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "asset_id", name="uq_maintenance_plans_company_asset"),
        UniqueConstraint("company_id", "id", name="uq_maintenance_plans_company_id"),
    )


class MaintenanceSchedule(UpdatedTimestampModel):
    __tablename__ = "maintenance_schedules"

    company_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    plan_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    asset_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    task_code: Mapped[MaintenanceTaskCode] = mapped_column(
        SAEnum(MaintenanceTaskCode, name="maintenance_task_code_enum"), nullable=False
    )
    custom_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    action_type: Mapped[MaintenanceActionType] = mapped_column(
        SAEnum(MaintenanceActionType, name="maintenance_action_type_enum"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    source_template_item_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_by_membership_id: Mapped[UUID] = mapped_column(nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "plan_id"],
            ["maintenance_plans.company_id", "maintenance_plans.id"],
            name="fk_maintenance_schedules_company_plan",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_maintenance_schedules_company_asset",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "source_template_item_id"],
            ["maintenance_template_items.company_id", "maintenance_template_items.id"],
            name="fk_maintenance_schedules_company_template_item",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "created_by_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_schedules_company_creator",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "id", name="uq_maintenance_schedules_company_id"),
        CheckConstraint(
            "task_code <> 'CUSTOM' OR length(btrim(custom_label)) > 0",
            name="custom_label_required",
        ),
        Index("ix_maintenance_schedules_asset_enabled", "asset_id", "enabled"),
    )


class MaintenanceCriterion(UpdatedTimestampModel):
    __tablename__ = "maintenance_criteria"

    company_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    schedule_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    basis: Mapped[MaintenanceCriterionBasis] = mapped_column(
        SAEnum(MaintenanceCriterionBasis, name="maintenance_criterion_basis_enum"),
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    interval_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    warning_value: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=0, server_default=text("0")
    )
    baseline_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    baseline_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "schedule_id"],
            ["maintenance_schedules.company_id", "maintenance_schedules.id"],
            name="fk_maintenance_criteria_company_schedule",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "company_id", "schedule_id", "basis", name="uq_maintenance_criterion_basis"
        ),
        CheckConstraint("interval_value > 0", name="interval_positive"),
        CheckConstraint(
            "warning_value >= 0 AND warning_value < interval_value",
            name="warning_range",
        ),
        CheckConstraint(
            "(basis = 'CALENDAR_DAYS' AND baseline_value IS NULL) OR "
            "(basis <> 'CALENDAR_DAYS' AND baseline_date IS NULL)",
            name="baseline_matches_basis",
        ),
    )


class MaintenanceWorkOrder(UpdatedTimestampModel):
    __tablename__ = "maintenance_work_orders"

    company_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    asset_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    schedule_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[MaintenanceWorkOrderStatus] = mapped_column(
        SAEnum(MaintenanceWorkOrderStatus, name="maintenance_work_order_status_enum"),
        nullable=False,
    )
    scheduled_for: Mapped[date | None] = mapped_column(Date, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    service_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completion_odometer_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    completion_hour_meter: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    parts_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=0, server_default=text("0")
    )
    labor_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=0, server_default=text("0")
    )
    other_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=0, server_default=text("0")
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_membership_id: Mapped[UUID] = mapped_column(nullable=False)
    completed_by_membership_id: Mapped[UUID | None] = mapped_column(nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_maintenance_work_orders_company_asset",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "schedule_id"],
            ["maintenance_schedules.company_id", "maintenance_schedules.id"],
            name="fk_maintenance_work_orders_company_schedule",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "created_by_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_work_orders_company_creator",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "completed_by_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_work_orders_company_completer",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "id", name="uq_maintenance_work_orders_company_id"),
        CheckConstraint(
            "parts_cost >= 0 AND labor_cost >= 0 AND other_cost >= 0",
            name="costs_non_negative",
        ),
    )


class MaintenanceRecord(UpdatedTimestampModel):
    __tablename__ = "maintenance_records"

    company_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    work_order_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    asset_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    schedule_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    task_code: Mapped[MaintenanceTaskCode | None] = mapped_column(
        SAEnum(MaintenanceTaskCode, name="maintenance_task_code_enum"), nullable=True
    )
    task_label: Mapped[str] = mapped_column(String(200), nullable=False)
    service_date: Mapped[date] = mapped_column(Date, nullable=False)
    odometer_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    hour_meter: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    parts_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    labor_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    other_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_membership_id: Mapped[UUID] = mapped_column(nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "work_order_id"],
            ["maintenance_work_orders.company_id", "maintenance_work_orders.id"],
            name="fk_maintenance_records_company_work_order",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_maintenance_records_company_asset",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "schedule_id"],
            ["maintenance_schedules.company_id", "maintenance_schedules.id"],
            name="fk_maintenance_records_company_schedule",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "actor_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_records_company_actor",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "work_order_id", name="uq_maintenance_records_work_order"),
        UniqueConstraint("company_id", "id", name="uq_maintenance_records_company_id"),
        CheckConstraint(
            "parts_cost >= 0 AND labor_cost >= 0 AND other_cost >= 0 AND total_cost >= 0",
            name="costs_non_negative",
        ),
    )


class MaintenanceAttachment(UpdatedTimestampModel):
    __tablename__ = "maintenance_attachments"

    company_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    record_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "record_id"],
            ["maintenance_records.company_id", "maintenance_records.id"],
            name="fk_maintenance_attachments_company_record",
            ondelete="CASCADE",
        ),
        UniqueConstraint("company_id", "id", name="uq_maintenance_attachments_company_id"),
        CheckConstraint("size_bytes > 0", name="size_positive"),
    )
