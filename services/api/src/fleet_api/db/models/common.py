from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class UUIDTimestampModel(Base):
    """Small explicit shared base for records with UUID and audit timestamps."""

    __abstract__ = True

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UpdatedTimestampModel(UUIDTimestampModel):
    __abstract__ = True

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
