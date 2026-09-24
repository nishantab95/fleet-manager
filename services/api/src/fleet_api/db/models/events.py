from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
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

from fleet_api.db.base import Base
from fleet_api.db.models.common import UpdatedTimestampModel, utc_now
from fleet_api.domain.enums import (
    EmergencyCategory,
    EmergencyStatus,
    KmReadingType,
    OperationalEventType,
    VerificationStatus,
)


class OperationalEvent(UpdatedTimestampModel):
    """Common server-side event envelope and global idempotency boundary."""

    __tablename__ = "operational_events"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assignment_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    client_event_uuid: Mapped[UUID] = mapped_column(nullable=False)
    device_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    device_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    server_received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    event_type: Mapped[OperationalEventType] = mapped_column(
        SAEnum(OperationalEventType, name="operational_event_type_enum"), nullable=False
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus, name="verification_status_enum"),
        default=VerificationStatus.PENDING_VERIFICATION,
        nullable=False,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "assignment_id"],
            ["assignments.company_id", "assignments.id"],
            name="fk_events_company_assignment",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "device_id"],
            ["devices.company_id", "devices.id"],
            name="fk_events_company_device",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "client_event_uuid", name="uq_events_company_client_uuid"),
        UniqueConstraint("company_id", "id", name="uq_events_company_id"),
        Index(
            "ix_events_company_verification",
            "company_id",
            "verification_status",
            "server_received_at",
        ),
        Index("ix_events_assignment_time", "assignment_id", "device_created_at"),
    )


class TripEvent(Base):
    __tablename__ = "trip_events"

    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_events.id", ondelete="CASCADE"), primary_key=True
    )


class KmReading(Base):
    __tablename__ = "km_readings"

    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_events.id", ondelete="CASCADE"), primary_key=True
    )
    reading_type: Mapped[KmReadingType] = mapped_column(
        SAEnum(KmReadingType, name="km_reading_type_enum"), nullable=False
    )
    reading_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    object_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        CheckConstraint("reading_value >= 0", name="non_negative"),
        Index("ix_km_readings_type", "reading_type"),
    )


class DieselEvent(Base):
    __tablename__ = "diesel_events"

    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_events.id", ondelete="CASCADE"), primary_key=True
    )
    litres: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    object_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (CheckConstraint("litres > 0", name="positive_litres"),)


class EmergencyEvent(Base):
    __tablename__ = "emergency_events"

    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_events.id", ondelete="CASCADE"), primary_key=True
    )
    category: Mapped[EmergencyCategory | None] = mapped_column(
        SAEnum(EmergencyCategory, name="emergency_category_enum"), nullable=True
    )
    status: Mapped[EmergencyStatus] = mapped_column(
        SAEnum(EmergencyStatus, name="emergency_status_enum"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class EventVerification(UpdatedTimestampModel):
    __tablename__ = "event_verifications"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    changed_by_membership_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus, name="verification_status_enum"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "event_id"],
            ["operational_events.company_id", "operational_events.id"],
            name="fk_verifications_company_event",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "changed_by_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_verifications_company_membership",
            ondelete="RESTRICT",
        ),
        Index("ix_verifications_event_time", "event_id", "created_at"),
    )
