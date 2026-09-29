from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
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
    FleetAssetType.EXCAVATOR: _NO_OPERATIONAL_CAPABILITIES,
    FleetAssetType.BACKHOE_LOADER: _NO_OPERATIONAL_CAPABILITIES,
    FleetAssetType.ROLLER: _NO_OPERATIONAL_CAPABILITIES,
    FleetAssetType.GRADER: _NO_OPERATIONAL_CAPABILITIES,
}


def capabilities_for(asset_type: FleetAssetType) -> AssetCapabilities:
    """Return the single deterministic capability definition for an asset type."""

    return _CAPABILITIES[asset_type]


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


def create_site(
    session: Session,
    *,
    company_id: UUID,
    name: str,
    code: str | None = None,
) -> Site:
    if session.get(Company, company_id) is None:
        raise TenantConsistencyError("company does not exist")
    site = Site(
        company_id=company_id,
        name=name.strip(),
        code=code.strip() if code else None,
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
    asset_code: str,
    registration_number: str | None,
    short_name: str | None,
    manufacturer: str | None = None,
    model: str | None = None,
    rental_party_name: str | None = None,
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
    asset = FleetAsset(
        company_id=company_id,
        asset_type=asset_type,
        ownership_type=ownership_type,
        asset_code=normalize_asset_code(asset_code),
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
    )
    session.add(asset)
    try:
        session.flush()
    except IntegrityError as exc:
        raise DomainError(
            "asset_code or registration_number is already used by this company"
        ) from exc
    return asset


def _tipper_asset_code(
    session: Session,
    *,
    company_id: UUID,
    registration_number: str,
    short_name: str | None,
) -> str:
    registration = normalize_registration_number(registration_number)
    candidates = [
        normalize_asset_code(short_name) if short_name and short_name.strip() else registration,
        registration,
        f"TIPPER-{registration}",
    ]
    for candidate in candidates:
        exists = session.scalar(
            select(FleetAsset.id).where(
                FleetAsset.company_id == company_id,
                FleetAsset.asset_code == candidate,
            )
        )
        if exists is None:
            return candidate
    suffix = 2
    while True:
        candidate = f"TIPPER-{registration}-{suffix}"
        exists = session.scalar(
            select(FleetAsset.id).where(
                FleetAsset.company_id == company_id,
                FleetAsset.asset_code == candidate,
            )
        )
        if exists is None:
            return candidate
        suffix += 1


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
        asset_code=_tipper_asset_code(
            session,
            company_id=company_id,
            registration_number=registration_number,
            short_name=short_name,
        ),
        registration_number=registration_number,
        short_name=short_name,
    )
