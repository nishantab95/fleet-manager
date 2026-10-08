from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.models.common import UpdatedTimestampModel
from fleet_api.domain.enums import InterCompanyRentalStatus, MaintenanceResponsibility


class InterCompanyAssetRental(UpdatedTimestampModel):
    """Dormant agreement boundary for a future explicitly shared rental Asset.

    No route or query service exposes these rows in the current Pilot. Enabling
    future sharing must remain agreement-scoped and feature-gated.
    """

    __tablename__ = "intercompany_asset_rentals"

    asset_owner_company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    renting_company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    owner_asset_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    renter_asset_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[InterCompanyRentalStatus] = mapped_column(
        SAEnum(InterCompanyRentalStatus, name="intercompany_rental_status_enum"), nullable=False
    )
    maintenance_responsibility: Mapped[MaintenanceResponsibility] = mapped_column(
        SAEnum(MaintenanceResponsibility, name="maintenance_responsibility_enum"), nullable=False
    )
    share_odometer_km: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    share_hour_meter: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    share_utilization: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    share_duty_summary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    share_driver_identity: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    share_diesel: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["asset_owner_company_id", "owner_asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_intercompany_rentals_owner_asset",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["renting_company_id", "renter_asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_intercompany_rentals_renter_asset",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "asset_owner_company_id <> renting_company_id",
            name="different_companies",
        ),
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="valid_period"),
        Index(
            "ix_intercompany_rentals_active_pair",
            "asset_owner_company_id",
            "renting_company_id",
            "status",
        ),
    )
