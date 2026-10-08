from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.engine.default import DefaultExecutionContext
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.models.common import UpdatedTimestampModel
from fleet_api.domain.enums import (
    AssetOwnershipType,
    FleetAssetStatus,
    FleetAssetType,
    MaintenanceResponsibility,
)


def _default_supports_odometer(context: DefaultExecutionContext) -> bool:
    asset_type = context.get_current_parameters().get(  # type: ignore[no-untyped-call]
        "asset_type"
    )
    return asset_type in {
        FleetAssetType.TIPPER,
        FleetAssetType.BACKHOE_LOADER,
        FleetAssetType.ROLLER,
        FleetAssetType.GRADER,
        FleetAssetType.TIPPER.value,
        FleetAssetType.BACKHOE_LOADER.value,
        FleetAssetType.ROLLER.value,
        FleetAssetType.GRADER.value,
    }


def _default_is_wheeled(context: DefaultExecutionContext) -> bool:
    asset_type = context.get_current_parameters().get(  # type: ignore[no-untyped-call]
        "asset_type"
    )
    return asset_type in {
        FleetAssetType.TIPPER,
        FleetAssetType.BACKHOE_LOADER,
        FleetAssetType.ROLLER,
        FleetAssetType.GRADER,
        FleetAssetType.TIPPER.value,
        FleetAssetType.BACKHOE_LOADER.value,
        FleetAssetType.ROLLER.value,
        FleetAssetType.GRADER.value,
    }


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
    maintenance_responsibility: Mapped[MaintenanceResponsibility] = mapped_column(
        SAEnum(MaintenanceResponsibility, name="maintenance_responsibility_enum"),
        nullable=False,
        default=MaintenanceResponsibility.OWNER_COMPANY,
        server_default=text("'OWNER_COMPANY'"),
    )
    asset_code: Mapped[str] = mapped_column(String(64), nullable=False)
    registration_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    short_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_wheeled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=_default_is_wheeled,
        server_default=text("false"),
    )
    supports_odometer_km: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=_default_supports_odometer,
        server_default=text("false"),
    )
    supports_hour_meter: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    chassis_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    engine_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[FleetAssetStatus] = mapped_column(
        SAEnum(FleetAssetStatus, name="fleet_asset_status_enum"), nullable=False
    )
    rental_party_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    rental_owner_phone_primary: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rental_owner_phone_secondary: Mapped[str | None] = mapped_column(String(32), nullable=True)
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
        CheckConstraint(
            "model_year IS NULL OR model_year BETWEEN 1900 AND 2200",
            name="model_year_range",
        ),
        CheckConstraint(
            "supports_odometer_km OR supports_hour_meter",
            name="at_least_one_meter",
        ),
        CheckConstraint(
            "is_wheeled OR NOT supports_odometer_km",
            name="non_wheeled_without_odometer",
        ),
    )
