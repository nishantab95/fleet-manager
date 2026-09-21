from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.models.common import UpdatedTimestampModel


class Assignment(UpdatedTimestampModel):
    __tablename__ = "assignments"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    driver_membership_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    supervisor_membership_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    tipper_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    site_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "driver_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_assignments_company_driver_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "supervisor_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_assignments_company_supervisor_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "tipper_id"],
            ["tippers.company_id", "tippers.id"],
            name="fk_assignments_company_tipper",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "site_id"],
            ["sites.company_id", "sites.id"],
            name="fk_assignments_company_site",
            ondelete="RESTRICT",
        ),
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="end_after_start"),
        UniqueConstraint("company_id", "id", name="uq_assignments_company_id"),
        Index("ix_assignments_company_active", "company_id", "starts_at", "ends_at"),
    )
