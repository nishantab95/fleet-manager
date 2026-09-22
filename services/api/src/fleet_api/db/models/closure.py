from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.models.common import UpdatedTimestampModel, UUIDTimestampModel
from fleet_api.domain.enums import SiteClosureStatus


class SiteDailyClosure(UpdatedTimestampModel):
    __tablename__ = "site_daily_closures"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    site_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    operational_date: Mapped[date] = mapped_column(Date, nullable=False)
    reporting_timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    workday_start_minutes: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[SiteClosureStatus] = mapped_column(
        SAEnum(SiteClosureStatus, name="site_closure_status_enum"), nullable=False
    )
    closed_by_membership_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reopened_by_membership_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "site_id"],
            ["sites.company_id", "sites.id"],
            name="fk_closures_company_site",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "closed_by_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_closures_company_closed_by",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "reopened_by_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_closures_company_reopened_by",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "id", name="uq_closures_company_id_id"),
        UniqueConstraint(
            "company_id",
            "site_id",
            "operational_date",
            name="uq_closures_company_site_date",
        ),
        Index("ix_closures_company_date", "company_id", "operational_date"),
        Index("ix_closures_site_date", "site_id", "operational_date"),
    )


class SiteDailyClosureHistory(UUIDTimestampModel):
    __tablename__ = "site_daily_closure_history"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    closure_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    status: Mapped[SiteClosureStatus] = mapped_column(
        SAEnum(SiteClosureStatus, name="site_closure_status_enum"), nullable=False
    )
    changed_by_membership_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "closure_id"],
            ["site_daily_closures.company_id", "site_daily_closures.id"],
            name="fk_closure_history_company_closure",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "changed_by_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_closure_history_company_actor",
            ondelete="RESTRICT",
        ),
        Index("ix_closure_history_closure_time", "closure_id", "created_at"),
    )
