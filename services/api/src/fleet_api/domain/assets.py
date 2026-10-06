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
    supports_trip_complete: bool
    supports_odometer: bool
    supports_hour_meter: bool
    supports_diesel: bool
    supports_emergency: bool
    supports_duty_session: bool


_NO_OPERATIONAL_CAPABILITIES = AssetCapabilities(
    supports_trip_complete=False,
    supports_odometer=False,
    supports_hour_meter=False,
    supports_diesel=False,
    supports_emergency=False,
    supports_duty_session=False,
)

_CAPABILITIES = {
    FleetAssetType.TIPPER: AssetCapabilities(
        supports_trip_complete=True,
        supports_odometer=True,
        supports_hour_meter=False,
        supports_diesel=True,
        supports_emergency=True,
        supports_duty_session=True,
    ),
    **{
        asset_type: AssetCapabilities(
            supports_trip_complete=False,
            supports_odometer=False,
            supports_hour_meter=True,
            supports_diesel=True,
            supports_emergency=True,
            supports_duty_session=True,
        )
        for asset_type in (
            FleetAssetType.EXCAVATOR,
            FleetAssetType.BACKHOE_LOADER,
            FleetAssetType.ROLLER,
            FleetAssetType.GRADER,
        )
    },
}


def capabilities_for(asset_type: FleetAssetType) -> AssetCapabilities:
    """Return the single deterministic capability definition for an asset type."""

    return _CAPABILITIES[asset_type]


def capabilities_for_asset(asset: FleetAsset) -> AssetCapabilities:
    """Return type capabilities with meter support taken from the asset record."""

    defaults = capabilities_for(asset.asset_type)
    # ORM-created legacy objects can transiently have both Python defaults
    # false. Preserve the historical type behavior until an explicit edit.
    supports_odometer = asset.supports_odometer_km
    supports_hour_meter = asset.supports_hour_meter
    if not supports_odometer and not supports_hour_meter:
        supports_odometer = defaults.supports_odometer
        supports_hour_meter = defaults.supports_hour_meter
    return AssetCapabilities(
        supports_trip_complete=defaults.supports_trip_complete,
        supports_odometer=supports_odometer,
        supports_hour_meter=supports_hour_meter,
        supports_diesel=defaults.supports_diesel,
        supports_emergency=defaults.supports_emergency,
        supports_duty_session=defaults.supports_duty_session,
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
    rental_party_name: str | None = None,
    rental_start_date: date | None = None,
    rental_end_date: date | None = None,
    supports_odometer_km: bool | None = None,
    supports_hour_meter: bool | None = None,
) -> FleetAsset:
    if session.get(Company, company_id) is None:
        raise TenantConsistencyError("company does not exist")
    if rental_start_date is not None and rental_end_date is not None:
        if rental_end_date < rental_start_date:
            raise DomainError("rental_end_date must not be before rental_start_date")
    clean_short_name = short_name.strip() if short_name else None
    if short_name is not None and clean_short_name is None:
        raise DomainError("short_name must contain a value when provided")
    asset_id = uuid4()
    default_capabilities = capabilities_for(asset_type)
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
        status=FleetAssetStatus.ACTIVE,
        rental_party_name=rental_party_name.strip() if rental_party_name else None,
        rental_start_date=rental_start_date,
        rental_end_date=rental_end_date,
        supports_odometer_km=(
            default_capabilities.supports_odometer
            if supports_odometer_km is None
            else supports_odometer_km
        ),
        supports_hour_meter=(
            default_capabilities.supports_hour_meter
            if supports_hour_meter is None
            else supports_hour_meter
        ),
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
