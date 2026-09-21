from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.models.common import UUIDTimestampModel, utc_now


class EvidenceObject(UUIDTimestampModel):
    """Private object-storage metadata owned by one driver event upload."""

    __tablename__ = "evidence_objects"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    membership_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    client_event_uuid: Mapped[UUID] = mapped_column(nullable=False)
    object_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_evidence_objects_company_membership",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "company_id",
            "membership_id",
            "client_event_uuid",
            name="uq_evidence_objects_driver_event",
        ),
        Index("ix_evidence_objects_company_event", "company_id", "client_event_uuid"),
    )
