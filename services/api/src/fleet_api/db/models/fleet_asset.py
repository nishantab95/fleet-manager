from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.models.common import UpdatedTimestampModel
from fleet_api.domain.enums import AssetOwnershipType, FleetAssetStatus, FleetAssetType


class FleetAsset(UpdatedTimestampModel):
    """Canonical company-owned or rented fleet record.

    Operational workflows remain capability-gated. Phase 1A assigns only
    tippers, while the nullable registration and generic identity fields make
    the record suitable for later construction machinery.
    """

    __tablename__ = "fleet_assets"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_type: Mapped[FleetAssetType] = mapped_column(
        SAEnum(FleetAssetType, name="fleet_asset_type_enum"), nullable=False
    )
    ownership_type: Mapped[AssetOwnershipType] = mapped_column(
        SAEnum(AssetOwnershipType, name="asset_ownership_type_enum"), nullable=False
    )
    asset_code: Mapped[str] = mapped_column(String(64), nullable=False)
    registration_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    short_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[FleetAssetStatus] = mapped_column(
        SAEnum(FleetAssetStatus, name="fleet_asset_status_enum"), nullable=False
    )
    rental_party_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    rental_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    rental_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        UniqueConstraint("company_id", "asset_code", name="uq_fleet_assets_company_asset_code"),
        UniqueConstraint("company_id", "id", name="uq_fleet_assets_company_id"),
        Index(
            "uq_fleet_assets_company_registration",
            "company_id",
            "registration_number",
            unique=True,
            postgresql_where=text("registration_number IS NOT NULL"),
        ),
        CheckConstraint("length(btrim(asset_code)) > 0", name="asset_code_non_empty"),
        CheckConstraint(
            "short_name IS NULL OR length(btrim(short_name)) BETWEEN 1 AND 100",
            name="short_name_length",
        ),
        CheckConstraint(
            "rental_end_date IS NULL OR rental_start_date IS NULL "
            "OR rental_end_date >= rental_start_date",
            name="rental_dates_ordered",
        ),
    )
