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
    Integer,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.models.common import UpdatedTimestampModel
from fleet_api.domain.enums import DutySessionStatus


class DutySession(UpdatedTimestampModel):
    """Server-authoritative driver duty interval for one assignment."""

    __tablename__ = "duty_sessions"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assignment_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    driver_membership_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    tipper_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    site_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    operational_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_event_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    start_km: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    configured_regular_duty_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    regular_duty_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_event_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    end_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[DutySessionStatus] = mapped_column(
        SAEnum(DutySessionStatus, name="duty_session_status_enum"),
        nullable=False,
        default=DutySessionStatus.ACTIVE,
    )
    final_overtime_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "assignment_id"],
            ["assignments.company_id", "assignments.id"],
            name="fk_duty_sessions_company_assignment",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "driver_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_duty_sessions_company_driver_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "tipper_id"],
            ["tippers.company_id", "tippers.id"],
            name="fk_duty_sessions_company_tipper",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "site_id"],
            ["sites.company_id", "sites.id"],
            name="fk_duty_sessions_company_site",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "start_event_id"],
            ["operational_events.company_id", "operational_events.id"],
            name="fk_duty_sessions_company_start_event",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "end_event_id"],
            ["operational_events.company_id", "operational_events.id"],
            name="fk_duty_sessions_company_end_event",
            ondelete="RESTRICT",
        ),
        CheckConstraint("start_km >= 0", name="ck_duty_sessions_start_km_non_negative"),
        CheckConstraint(
            "end_km IS NULL OR end_km >= 0", name="ck_duty_sessions_end_km_non_negative"
        ),
        CheckConstraint(
            "configured_regular_duty_minutes > 0",
            name="ck_duty_sessions_regular_duty_positive",
        ),
        CheckConstraint(
            "final_overtime_minutes IS NULL OR final_overtime_minutes >= 0",
            name="ck_duty_sessions_overtime_non_negative",
        ),
        UniqueConstraint("company_id", "id", name="uq_duty_sessions_company_id"),
        Index(
            "ix_duty_sessions_company_driver_date",
            "company_id",
            "driver_membership_id",
            "operational_date",
        ),
        Index(
            "ix_duty_sessions_company_assignment_status",
            "company_id",
            "assignment_id",
            "status",
        ),
    )
