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
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.models.common import UpdatedTimestampModel, UUIDTimestampModel, utc_now
from fleet_api.domain.enums import (
    LocationSnapshotSource,
    LocationSnapshotStatus,
    PayBasis,
    PayrollPeriodStatus,
)


class CompensationProfile(UpdatedTimestampModel):
    __tablename__ = "compensation_profiles"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    membership_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    pay_basis: Mapped[PayBasis] = mapped_column(
        SAEnum(PayBasis, name="pay_basis_enum"), nullable=False
    )
    base_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    standard_duty_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    overtime_rate_per_hour: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_compensation_profiles_company_id"),
        ForeignKeyConstraint(
            ["company_id", "membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_compensation_profiles_company_member",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_compensation_profiles_company_creator",
            ondelete="RESTRICT",
        ),
        CheckConstraint("base_amount >= 0", name="compensation_base_non_negative"),
        CheckConstraint(
            "overtime_rate_per_hour >= 0", name="compensation_overtime_rate_non_negative"
        ),
        CheckConstraint(
            "standard_duty_minutes > 0 AND standard_duty_minutes <= 1440",
            name="compensation_standard_minutes_range",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="compensation_effective_dates_ordered",
        ),
        Index(
            "ix_compensation_profiles_member_effective",
            "company_id",
            "membership_id",
            "effective_from",
        ),
    )


class PayrollPeriod(UpdatedTimestampModel):
    __tablename__ = "payroll_periods"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[PayrollPeriodStatus] = mapped_column(
        SAEnum(PayrollPeriodStatus, name="payroll_period_status_enum"), nullable=False
    )
    created_by: Mapped[UUID] = mapped_column(nullable=False)
    reviewed_by: Mapped[UUID | None] = mapped_column(nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_by: Mapped[UUID | None] = mapped_column(nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_payroll_periods_company_id"),
        UniqueConstraint("company_id", "starts_on", "ends_on", name="uq_payroll_period_dates"),
        ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_payroll_periods_company_creator",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "reviewed_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_payroll_periods_company_reviewer",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "finalized_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_payroll_periods_company_finalizer",
            ondelete="RESTRICT",
        ),
        CheckConstraint("ends_on >= starts_on", name="payroll_period_dates_ordered"),
    )


class PayrollLine(UpdatedTimestampModel):
    __tablename__ = "payroll_lines"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    display_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    pay_basis_snapshot: Mapped[PayBasis] = mapped_column(
        SAEnum(PayBasis, name="pay_basis_enum"), nullable=False
    )
    base_pay: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    duty_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    overtime_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    overtime_rate_per_hour: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    overtime_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    adjustment_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    calculated_gross_pay: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    calculation_state: Mapped[str] = mapped_column(String(40), nullable=False)
    calculation_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_payroll_lines_company_id"),
        UniqueConstraint(
            "company_id", "period_id", "membership_id", name="uq_payroll_lines_period_member"
        ),
        ForeignKeyConstraint(
            ["company_id", "period_id"],
            ["payroll_periods.company_id", "payroll_periods.id"],
            name="fk_payroll_lines_company_period",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_payroll_lines_company_member",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "base_pay >= 0 AND duty_minutes >= 0 AND overtime_minutes >= 0 "
            "AND overtime_rate_per_hour >= 0 AND overtime_amount >= 0",
            name="payroll_line_values_non_negative",
        ),
    )


class PayrollAdjustment(UUIDTimestampModel):
    __tablename__ = "payroll_adjustments"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    line_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[UUID] = mapped_column(nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "line_id"],
            ["payroll_lines.company_id", "payroll_lines.id"],
            name="fk_payroll_adjustments_company_line",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_payroll_adjustments_company_creator",
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount <> 0", name="payroll_adjustment_non_zero"),
        CheckConstraint("length(btrim(reason)) > 0", name="payroll_adjustment_reason_non_empty"),
    )


class AttendanceLocationSetting(UpdatedTimestampModel):
    __tablename__ = "attendance_location_settings"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    site_match_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    asset_proximity_threshold_m: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    gps_freshness_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    max_accuracy_m: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_by: Mapped[UUID] = mapped_column(nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "updated_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_attendance_location_settings_company_updater",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "asset_proximity_threshold_m > 0 AND gps_freshness_seconds > 0 "
            "AND max_accuracy_m > 0 AND retention_days > 0",
            name="attendance_location_settings_positive",
        ),
    )


class AttendanceLocationSnapshot(UUIDTimestampModel):
    __tablename__ = "attendance_location_snapshots"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    membership_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    duty_session_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    assignment_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    asset_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    site_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    operational_event_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    captured_at_device: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at_server: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    accuracy_m: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    source: Mapped[LocationSnapshotSource] = mapped_column(
        SAEnum(LocationSnapshotSource, name="location_snapshot_source_enum"), nullable=False
    )
    status: Mapped[LocationSnapshotStatus] = mapped_column(
        SAEnum(LocationSnapshotStatus, name="location_snapshot_status_enum"), nullable=False
    )
    permission_state: Mapped[str | None] = mapped_column(String(40), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_location_snapshots_company_member",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "duty_session_id"],
            ["duty_sessions.company_id", "duty_sessions.id"],
            name="fk_location_snapshots_company_duty",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "assignment_id"],
            ["assignments.company_id", "assignments.id"],
            name="fk_location_snapshots_company_assignment",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_location_snapshots_company_asset",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "site_id"],
            ["sites.company_id", "sites.id"],
            name="fk_location_snapshots_company_site",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "operational_event_id"],
            ["operational_events.company_id", "operational_events.id"],
            name="fk_location_snapshots_company_event",
            ondelete="SET NULL",
        ),
        CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name="location_snapshot_latitude_range",
        ),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="location_snapshot_longitude_range",
        ),
        CheckConstraint(
            "accuracy_m IS NULL OR accuracy_m >= 0",
            name="location_snapshot_accuracy_non_negative",
        ),
        CheckConstraint(
            "(status = 'AVAILABLE' AND latitude IS NOT NULL AND longitude IS NOT NULL "
            "AND accuracy_m IS NOT NULL) OR status <> 'AVAILABLE'",
            name="location_snapshot_available_coordinates",
        ),
        Index(
            "ix_location_snapshots_member_captured",
            "company_id",
            "membership_id",
            "captured_at_device",
        ),
    )
