from __future__ import annotations

from uuid import UUID

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.models.common import UpdatedTimestampModel
from fleet_api.domain.enums import DevicePlatform, DeviceStatus


class Device(UpdatedTimestampModel):
    __tablename__ = "devices"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    membership_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    installation_identifier: Mapped[str] = mapped_column(String(200), nullable=False)
    platform: Mapped[DevicePlatform] = mapped_column(
        SAEnum(DevicePlatform, name="device_platform_enum"), nullable=False
    )
    status: Mapped[DeviceStatus] = mapped_column(
        SAEnum(DeviceStatus, name="device_status_enum"), nullable=False
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_devices_company_membership",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id", "installation_identifier", name="uq_devices_company_installation"
        ),
        UniqueConstraint("company_id", "id", name="uq_devices_company_id"),
    )
