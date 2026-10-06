from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fleet_api.db.models import Company, CompanyMembership, FleetAsset, Site
from fleet_api.domain.assets import capabilities_for, create_fleet_asset
from fleet_api.domain.assignments import create_assignment
from fleet_api.domain.enums import (
    AssetOwnershipType,
    FleetAssetStatus,
    FleetAssetType,
)
from fleet_api.domain.errors import DomainError

pytestmark = pytest.mark.postgres


def value[T](records: dict[str, object], key: str, expected_type: type[T]) -> T:
    item = records[key]
    assert isinstance(item, expected_type)
    return item


def test_asset_capabilities_are_centralized_and_ownership_independent() -> None:
    tipper = capabilities_for(FleetAssetType.TIPPER)
    assert tipper.supports_trip_complete is True
    assert tipper.supports_odometer is True
    assert tipper.supports_hour_meter is False
    assert tipper.supports_diesel is True
    assert tipper.supports_emergency is True
    assert tipper.supports_duty_session is True

    for asset_type in (
        FleetAssetType.EXCAVATOR,
        FleetAssetType.BACKHOE_LOADER,
        FleetAssetType.ROLLER,
        FleetAssetType.GRADER,
    ):
        machinery = capabilities_for(asset_type)
        assert machinery.supports_trip_complete is False
        assert machinery.supports_odometer is False
        assert machinery.supports_hour_meter is True
        assert machinery.supports_diesel is True
        assert machinery.supports_emergency is True
        assert machinery.supports_duty_session is True


def test_generic_assets_allow_nullable_registration_and_tenant_scoped_codes(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company_a = value(tenant_records, "company_a", Company)
    company_b = value(tenant_records, "company_b", Company)
    excavator_a = create_fleet_asset(
        db_session,
        company_id=company_a.id,
        asset_type=FleetAssetType.EXCAVATOR,
        ownership_type=AssetOwnershipType.OWNED,
        asset_code="exc 04",
        registration_number=None,
        short_name="CAT 320",
        manufacturer="Caterpillar",
        model="320",
    )
    excavator_b = create_fleet_asset(
        db_session,
        company_id=company_b.id,
        asset_type=FleetAssetType.EXCAVATOR,
        ownership_type=AssetOwnershipType.OWNED,
        asset_code="EXC-04",
        registration_number=None,
        short_name="Other tenant excavator",
    )
    second_unregistered = create_fleet_asset(
        db_session,
        company_id=company_a.id,
        asset_type=FleetAssetType.ROLLER,
        ownership_type=AssetOwnershipType.OWNED,
        asset_code="ROLLER-01",
        registration_number=None,
        short_name="Roller 1",
    )

    assert excavator_a.asset_code == "EXC-04"
    assert excavator_a.registration_number is None
    assert excavator_b.asset_code == excavator_a.asset_code
    assert second_unregistered.registration_number is None


def test_asset_uniqueness_and_rental_date_constraints(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    create_fleet_asset(
        db_session,
        company_id=company.id,
        asset_type=FleetAssetType.TIPPER,
        ownership_type=AssetOwnershipType.RENTED,
        asset_code="RENT-04",
        registration_number="KA05-CD-5678",
        short_name="Tipper 22",
        rental_party_name="ABC Transport",
        rental_start_date=date(2026, 1, 1),
    )

    duplicate_code = db_session.begin_nested()
    with pytest.raises(DomainError):
        create_fleet_asset(
            db_session,
            company_id=company.id,
            asset_type=FleetAssetType.GRADER,
            ownership_type=AssetOwnershipType.OWNED,
            asset_code="RENT-04",
            registration_number=None,
            short_name="Grader",
        )
    duplicate_code.rollback()

    duplicate_registration = db_session.begin_nested()
    with pytest.raises(DomainError):
        create_fleet_asset(
            db_session,
            company_id=company.id,
            asset_type=FleetAssetType.TIPPER,
            ownership_type=AssetOwnershipType.OWNED,
            asset_code="OWNED-99",
            registration_number="KA05CD5678",
            short_name="Duplicate registration",
        )
    duplicate_registration.rollback()

    with pytest.raises(DomainError):
        create_fleet_asset(
            db_session,
            company_id=company.id,
            asset_type=FleetAssetType.TIPPER,
            ownership_type=AssetOwnershipType.RENTED,
            asset_code="RENT-DATES",
            registration_number="KA05CD5680",
            short_name="Invalid rental",
            rental_start_date=date(2026, 2, 1),
            rental_end_date=date(2026, 1, 1),
        )

    invalid_code = db_session.begin_nested()
    db_session.add(
        FleetAsset(
            company_id=company.id,
            asset_type=FleetAssetType.EXCAVATOR,
            ownership_type=AssetOwnershipType.OWNED,
            asset_code="",
            registration_number=None,
            short_name="Invalid code",
            status=FleetAssetStatus.ACTIVE,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    invalid_code.rollback()


def test_machinery_asset_can_enter_shared_duty_assignment_workflow(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    excavator = create_fleet_asset(
        db_session,
        company_id=company.id,
        asset_type=FleetAssetType.EXCAVATOR,
        ownership_type=AssetOwnershipType.OWNED,
        asset_code="EXC-NO-WORKFLOW",
        registration_number=None,
        short_name="Excavator",
    )
    assignment = create_assignment(
        db_session,
        company_id=company.id,
        driver_membership_id=value(tenant_records, "driver_a", CompanyMembership).id,
        supervisor_membership_id=value(tenant_records, "supervisor_a", CompanyMembership).id,
        asset_id=excavator.id,
        site_id=value(tenant_records, "site_a", Site).id,
        starts_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert assignment.asset_id == excavator.id
