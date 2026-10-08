from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fleet_api.db.models import Company, FleetAsset, Site
from fleet_api.domain.enums import (
    AssetOwnershipType,
    FleetAssetStatus,
    FleetAssetType,
    SiteStatus,
)
from fleet_api.domain.errors import DomainError, TenantConsistencyError


@dataclass(frozen=True)
class AssetCapabilities:
    is_wheeled: bool
    supports_trip_complete: bool
    supports_odometer: bool
    supports_hour_meter: bool
    supports_diesel: bool
    supports_emergency: bool
    supports_duty_session: bool


_NO_OPERATIONAL_CAPABILITIES = AssetCapabilities(
    is_wheeled=False,
    supports_trip_complete=False,
    supports_odometer=False,
    supports_hour_meter=False,
    supports_diesel=False,
    supports_emergency=False,
    supports_duty_session=False,
)

_CAPABILITIES = {
    FleetAssetType.TIPPER: AssetCapabilities(
        is_wheeled=True,
        supports_trip_complete=True,
        supports_odometer=True,
        supports_hour_meter=True,
        supports_diesel=True,
        supports_emergency=True,
        supports_duty_session=True,
    ),
    FleetAssetType.EXCAVATOR: AssetCapabilities(False, False, False, True, True, True, True),
    FleetAssetType.BACKHOE_LOADER: AssetCapabilities(True, False, True, True, True, True, True),
    FleetAssetType.ROLLER: AssetCapabilities(True, False, False, True, True, True, True),
    FleetAssetType.GRADER: AssetCapabilities(True, False, True, True, True, True, True),
}


def capabilities_for(asset_type: FleetAssetType) -> AssetCapabilities:
    """Return the single deterministic capability definition for an asset type."""

    return _CAPABILITIES[asset_type]


def capabilities_for_asset(asset: FleetAsset) -> AssetCapabilities:
    """Return workflow capabilities using this individual Asset's meter setup."""

    base = capabilities_for(asset.asset_type)
    return AssetCapabilities(
        is_wheeled=asset.is_wheeled,
        supports_trip_complete=base.supports_trip_complete,
        supports_odometer=asset.supports_odometer_km,
        supports_hour_meter=asset.supports_hour_meter,
        supports_diesel=base.supports_diesel,
        supports_emergency=base.supports_emergency,
        supports_duty_session=base.supports_duty_session,
    )


def normalize_registration_number(value: str) -> str:
    """Normalize road registration values to uppercase without spaces or hyphens."""

    normalized = re.sub(r"[\s-]+", "", value).upper()
    if not normalized:
        raise DomainError("registration_number must contain a value")
    return normalized


def normalize_asset_code(value: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "-", value.strip().upper()).strip("-")
    if not normalized:
        raise DomainError("asset_code must contain a value")
    if len(normalized) > 64:
        raise DomainError("asset_code must be at most 64 characters")
    return normalized


def generated_asset_code(asset_type: FleetAssetType, asset_id: UUID) -> str:
    """Return a stable internal asset code that does not depend on editable labels."""

    return f"{asset_type.value}-{asset_id.hex.upper()}"


def normalize_site_code(value: str) -> str:
    normalized = value.strip().upper()
    if not normalized:
        raise DomainError("site code must contain a value")
    if len(normalized) > 64:
        raise DomainError("site code must be at most 64 characters")
    return normalized


def generated_site_code(site_id: UUID) -> str:
    """Return a stable internal Site code independent of its editable names."""

    return f"SITE-{site_id.hex.upper()}"


def create_site(
    session: Session,
    *,
    company_id: UUID,
    name: str,
    code: str | None = None,
    short_name: str | None = None,
) -> Site:
    if session.get(Company, company_id) is None:
        raise TenantConsistencyError("company does not exist")
    clean_name = name.strip()
    if not clean_name:
        raise DomainError("site name must contain a value")
    clean_short_name = short_name.strip() if short_name else clean_name
    if not clean_short_name:
        raise DomainError("site short_name must contain a value")
    site_id = uuid4()
    site = Site(
        id=site_id,
        company_id=company_id,
        name=clean_name,
        short_name=clean_short_name,
        code=normalize_site_code(code) if code is not None else generated_site_code(site_id),
        status=SiteStatus.ACTIVE,
    )
    session.add(site)
    session.flush()
    return site


def create_fleet_asset(
    session: Session,
    *,
    company_id: UUID,
    asset_type: FleetAssetType,
    ownership_type: AssetOwnershipType,
    asset_code: str | None,
    registration_number: str | None,
    short_name: str | None,
    manufacturer: str | None = None,
    model: str | None = None,
    model_year: int | None = None,
    is_wheeled: bool | None = None,
    supports_odometer_km: bool | None = None,
    supports_hour_meter: bool | None = None,
    chassis_number: str | None = None,
    engine_number: str | None = None,
    rental_party_name: str | None = None,
    rental_owner_phone_primary: str | None = None,
    rental_owner_phone_secondary: str | None = None,
    rental_start_date: date | None = None,
    rental_end_date: date | None = None,
) -> FleetAsset:
    if session.get(Company, company_id) is None:
        raise TenantConsistencyError("company does not exist")
    if rental_start_date is not None and rental_end_date is not None:
        if rental_end_date < rental_start_date:
            raise DomainError("rental_end_date must not be before rental_start_date")
    clean_short_name = short_name.strip() if short_name else None
    if short_name is not None and clean_short_name is None:
        raise DomainError("short_name must contain a value when provided")
    if model_year is not None and not 1900 <= model_year <= 2200:
        raise DomainError("model_year must be between 1900 and 2200")
    defaults = capabilities_for(asset_type)
    configured_wheeled = defaults.is_wheeled if is_wheeled is None else is_wheeled
    configured_odometer = (
        defaults.supports_odometer if supports_odometer_km is None else supports_odometer_km
    )
    configured_hour_meter = (
        defaults.supports_hour_meter if supports_hour_meter is None else supports_hour_meter
    )
    if not configured_odometer and not configured_hour_meter:
        raise DomainError("at least one meter capability must be enabled")
    if configured_odometer and not configured_wheeled:
        raise DomainError("non-wheeled assets cannot use an odometer KM capability")
    asset_id = uuid4()
    asset = FleetAsset(
        id=asset_id,
        company_id=company_id,
        asset_type=asset_type,
        ownership_type=ownership_type,
        asset_code=(
            normalize_asset_code(asset_code)
            if asset_code is not None
            else generated_asset_code(asset_type, asset_id)
        ),
        registration_number=(
            normalize_registration_number(registration_number)
            if registration_number is not None
            else None
        ),
        short_name=clean_short_name,
        manufacturer=manufacturer.strip() if manufacturer else None,
        model=model.strip() if model else None,
        model_year=model_year,
        is_wheeled=configured_wheeled,
        supports_odometer_km=configured_odometer,
        supports_hour_meter=configured_hour_meter,
        chassis_number=chassis_number.strip() if chassis_number else None,
        engine_number=engine_number.strip() if engine_number else None,
        status=FleetAssetStatus.ACTIVE,
        rental_party_name=rental_party_name.strip() if rental_party_name else None,
        rental_owner_phone_primary=rental_owner_phone_primary,
        rental_owner_phone_secondary=rental_owner_phone_secondary,
        rental_start_date=rental_start_date,
        rental_end_date=rental_end_date,
    )
    session.add(asset)
    try:
        session.flush()
    except IntegrityError as exc:
        raise DomainError(
            "asset_code or registration_number is already used by this company"
        ) from exc
    return asset


def create_tipper(
    session: Session,
    *,
    company_id: UUID,
    registration_number: str,
    short_name: str | None = None,
) -> FleetAsset:
    """Compatibility creation path for the existing owned-tipper API."""

    return create_fleet_asset(
        session,
        company_id=company_id,
        asset_type=FleetAssetType.TIPPER,
        ownership_type=AssetOwnershipType.OWNED,
        asset_code=None,
        registration_number=registration_number,
        short_name=short_name,
    )
