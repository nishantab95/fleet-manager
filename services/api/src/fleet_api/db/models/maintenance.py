from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.models.common import UpdatedTimestampModel, UUIDTimestampModel
from fleet_api.domain.enums import (
    MaintenanceBasis,
    MaintenanceCriterionBasis,
    MaintenanceScheduleStatus,
    MaintenanceWorkOrderStatus,
)


class MaintenanceSchedule(UpdatedTimestampModel):
    """One recurring maintenance rule for one company-scoped Fleet Asset."""

    __tablename__ = "maintenance_schedules"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    maintenance_type: Mapped[str] = mapped_column(String(64), nullable=False)
    custom_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    interval_basis: Mapped[MaintenanceBasis] = mapped_column(
        SAEnum(MaintenanceBasis, name="maintenance_basis_enum"), nullable=False
    )
    interval_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    warning_threshold: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    last_service_meter: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    last_service_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_due_meter: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    next_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[MaintenanceScheduleStatus] = mapped_column(
        SAEnum(MaintenanceScheduleStatus, name="maintenance_schedule_status_enum"),
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_maintenance_schedules_company_id"),
        ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_maintenance_schedules_company_asset",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_schedules_company_creator",
            ondelete="RESTRICT",
        ),
        CheckConstraint("interval_value > 0", name="maintenance_interval_positive"),
        CheckConstraint(
            "warning_threshold >= 0 AND warning_threshold <= interval_value",
            name="maintenance_warning_threshold_range",
        ),
        CheckConstraint(
            "last_service_meter IS NULL OR last_service_meter >= 0",
            name="maintenance_last_meter_non_negative",
        ),
        CheckConstraint(
            "next_due_meter IS NULL OR next_due_meter >= 0",
            name="maintenance_next_meter_non_negative",
        ),
        Index(
            "ix_maintenance_schedules_company_asset_status",
            "company_id",
            "asset_id",
            "status",
        ),
    )


class MaintenanceRecord(UUIDTimestampModel):
    """Append-only evidence that scheduled maintenance was performed."""

    __tablename__ = "maintenance_records"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    schedule_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    work_order_id: Mapped[UUID | None] = mapped_column(nullable=True, unique=True)
    asset_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    performed_on: Mapped[date] = mapped_column(Date, nullable=False)
    meter_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    completion_odometer_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    completion_hour_meter: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    vendor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    labor_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    parts_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    other_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    created_by: Mapped[UUID] = mapped_column(nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "schedule_id"],
            ["maintenance_schedules.company_id", "maintenance_schedules.id"],
            name="fk_maintenance_records_company_schedule",
            ondelete="RESTRICT",
        ),
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
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_records_company_creator",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "meter_value IS NULL OR meter_value >= 0",
            name="maintenance_record_meter_non_negative",
        ),
        CheckConstraint(
            "completion_odometer_km IS NULL OR completion_odometer_km >= 0",
            name="maintenance_record_odometer_non_negative",
        ),
        CheckConstraint(
            "completion_hour_meter IS NULL OR completion_hour_meter >= 0",
            name="maintenance_record_hour_meter_non_negative",
        ),
        CheckConstraint(
            "labor_cost >= 0 AND parts_cost >= 0 AND other_cost >= 0",
            name="maintenance_record_costs_non_negative",
        ),
        Index(
            "ix_maintenance_records_company_schedule_performed",
            "company_id",
            "schedule_id",
            "performed_on",
        ),
    )


class MaintenanceWorkOrder(UpdatedTimestampModel):
    """Mutable maintenance workflow; completion emits one immutable record."""

    __tablename__ = "maintenance_work_orders"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    schedule_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[MaintenanceWorkOrderStatus] = mapped_column(
        SAEnum(MaintenanceWorkOrderStatus, name="maintenance_work_order_status_enum"),
        nullable=False,
    )
    vendor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    scheduled_for: Mapped[date | None] = mapped_column(Date, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completion_meter: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    completion_odometer_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    completion_hour_meter: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    labor_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    parts_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    other_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_maintenance_work_orders_company_id"),
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
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_work_orders_company_creator",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "completion_meter IS NULL OR completion_meter >= 0",
            name="maintenance_work_order_meter_non_negative",
        ),
        CheckConstraint(
            "completion_odometer_km IS NULL OR completion_odometer_km >= 0",
            name="maintenance_work_order_odometer_non_negative",
        ),
        CheckConstraint(
            "completion_hour_meter IS NULL OR completion_hour_meter >= 0",
            name="maintenance_work_order_hour_meter_non_negative",
        ),
        CheckConstraint(
            "labor_cost >= 0 AND parts_cost >= 0 AND other_cost >= 0",
            name="maintenance_work_order_costs_non_negative",
        ),
        Index(
            "ix_maintenance_work_orders_company_status_scheduled",
            "company_id",
            "status",
            "scheduled_for",
        ),
    )


class MaintenanceAttachment(UUIDTimestampModel):
    __tablename__ = "maintenance_attachments"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_order_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    evidence_object_id: Mapped[UUID] = mapped_column(nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[UUID] = mapped_column(nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "work_order_id"],
            ["maintenance_work_orders.company_id", "maintenance_work_orders.id"],
            name="fk_maintenance_attachments_company_work_order",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "evidence_object_id"],
            ["evidence_objects.company_id", "evidence_objects.id"],
            name="fk_maintenance_attachments_company_evidence",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_attachments_company_creator",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "evidence_object_id",
            name="uq_maintenance_attachments_company_evidence",
        ),
    )


class MaintenanceCriterion(UpdatedTimestampModel):
    """One independent trigger; any criterion may make its schedule due."""

    __tablename__ = "maintenance_criteria"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    schedule_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    basis: Mapped[MaintenanceCriterionBasis] = mapped_column(
        SAEnum(MaintenanceCriterionBasis, name="maintenance_criterion_basis_enum"),
        nullable=False,
    )
    interval_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    warning_threshold: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    last_baseline_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    last_baseline_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_due_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    next_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[UUID] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_maintenance_criteria_company_id"),
        UniqueConstraint(
            "company_id",
            "schedule_id",
            "basis",
            name="uq_maintenance_criteria_schedule_basis",
        ),
        ForeignKeyConstraint(
            ["company_id", "schedule_id"],
            ["maintenance_schedules.company_id", "maintenance_schedules.id"],
            name="fk_maintenance_criteria_company_schedule",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_maintenance_criteria_company_creator",
            ondelete="RESTRICT",
        ),
        CheckConstraint("interval_value > 0", name="maintenance_criterion_interval_positive"),
        CheckConstraint(
            "warning_threshold >= 0 AND warning_threshold <= interval_value",
            name="maintenance_criterion_warning_range",
        ),
        CheckConstraint(
            "last_baseline_value IS NULL OR last_baseline_value >= 0",
            name="maintenance_criterion_baseline_non_negative",
        ),
        CheckConstraint(
            "next_due_value IS NULL OR next_due_value >= 0",
            name="maintenance_criterion_due_non_negative",
        ),
    )
