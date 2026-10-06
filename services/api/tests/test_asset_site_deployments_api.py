from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_otp_provider
from fleet_api.auth.providers import FakeOtpProvider
from fleet_api.auth.service import AuthService
from fleet_api.core.config import Settings
from fleet_api.db.models import (
    AssetSiteDeployment,
    Assignment,
    AuditLog,
    Company,
    CompanyMembership,
    DutySession,
    FleetAsset,
    OperationalEvent,
    Site,
    SupervisorSiteAccess,
    User,
)
from fleet_api.db.session import get_db as session_get_db
from fleet_api.domain.assignments import create_assignment
from fleet_api.domain.enums import (
    AssetOwnershipType,
    DutySessionStatus,
    FleetAssetStatus,
    FleetAssetType,
    OperationalEventType,
    SiteStatus,
    VerificationStatus,
)
from fleet_api.main import create_app

pytestmark = pytest.mark.postgres


def value[T](records: dict[str, object], key: str, expected_type: type[T]) -> T:
    item = records[key]
    assert isinstance(item, expected_type)
    return item


def settings() -> Settings:
    return Settings(
        environment="test",
        phone_default_region="IN",
        jwt_signing_key="test-signing-key-that-is-longer-than-32-characters",
        otp_resend_cooldown_seconds=0,
    )


def client_for(db: Session, membership: CompanyMembership) -> TestClient:
    user = db.get(User, membership.user_id)
    assert user is not None
    user.phone_number = f"+919{uuid4().int % 1_000_000_000:09d}"
    provider = FakeOtpProvider()
    auth = AuthService(db, settings(), provider)
    challenge = auth.request_otp(phone=user.phone_number)
    pre_session, _ = auth.verify_otp(challenge_id=challenge, otp=provider.deliveries[challenge])
    token = auth.create_session(
        pre_session_token=pre_session, membership_id=membership.id
    ).access_token
    db.commit()
    app = create_app(settings())

    def override_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[session_get_db] = override_db
    app.dependency_overrides[get_otp_provider] = lambda: FakeOtpProvider()
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def add_asset(
    db: Session,
    company: Company,
    *,
    code: str,
    ownership: AssetOwnershipType = AssetOwnershipType.OWNED,
    asset_type: FleetAssetType = FleetAssetType.TIPPER,
    status: FleetAssetStatus = FleetAssetStatus.ACTIVE,
) -> FleetAsset:
    asset = FleetAsset(
        company_id=company.id,
        asset_type=asset_type,
        ownership_type=ownership,
        asset_code=code,
        registration_number=f"REG-{code}" if asset_type == FleetAssetType.TIPPER else None,
        short_name=code.title(),
        status=status,
        rental_party_name="Rental Co" if ownership == AssetOwnershipType.RENTED else None,
        rental_start_date=date(2026, 9, 1) if ownership == AssetOwnershipType.RENTED else None,
    )
    db.add(asset)
    db.flush()
    return asset


def add_site(
    db: Session,
    company: Company,
    *,
    name: str,
    status: SiteStatus = SiteStatus.ACTIVE,
) -> Site:
    site = Site(
        company_id=company.id,
        name=name,
        short_name=name,
        code=name.upper().replace(" ", "-")[:64],
        status=status,
    )
    db.add(site)
    db.flush()
    return site


def deploy(client: TestClient, asset: FleetAsset, site: Site) -> dict[str, object]:
    response = client.post(
        f"/api/v1/owner/assets/{asset.id}/deployment",
        json={"site_id": str(site.id)},
    )
    assert response.status_code == 200, response.text
    return cast(dict[str, object], response.json())


def active_assignment(
    db: Session,
    records: dict[str, object],
    asset: FleetAsset,
    site: Site,
    *,
    driver_key: str = "driver_a",
) -> Assignment:
    return create_assignment(
        db,
        company_id=asset.company_id,
        driver_membership_id=value(records, driver_key, CompanyMembership).id,
        supervisor_membership_id=value(records, "supervisor_a", CompanyMembership).id,
        asset_id=asset.id,
        site_id=site.id,
        starts_at=datetime.now(UTC) - timedelta(minutes=5),
    )


def add_active_duty(db: Session, assignment: Assignment) -> DutySession:
    started_at = datetime.now(UTC) - timedelta(minutes=2)
    event = OperationalEvent(
        company_id=assignment.company_id,
        assignment_id=assignment.id,
        client_event_uuid=uuid4(),
        device_created_at=started_at,
        event_type=OperationalEventType.KM_READING,
        verification_status=VerificationStatus.PENDING_VERIFICATION,
    )
    db.add(event)
    db.flush()
    duty = DutySession(
        company_id=assignment.company_id,
        assignment_id=assignment.id,
        driver_membership_id=assignment.driver_membership_id,
        asset_id=assignment.asset_id,
        site_id=assignment.site_id,
        operational_date=started_at.date(),
        start_event_id=event.id,
        start_km=Decimal("100"),
        started_at=started_at,
        configured_regular_duty_minutes=600,
        regular_duty_ends_at=started_at + timedelta(minutes=600),
        status=DutySessionStatus.ACTIVE,
    )
    db.add(duty)
    db.flush()
    return duty


def test_owner_deploys_owned_rented_and_generic_unassigned_assets(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    company = value(tenant_records, "company_a", Company)
    site = value(tenant_records, "site_a", Site)
    site.short_name = "Alpha Operations"
    assets = [
        add_asset(db_session, company, code="OWN-T02"),
        add_asset(
            db_session,
            company,
            code="RENT-T03",
            ownership=AssetOwnershipType.RENTED,
        ),
        add_asset(
            db_session,
            company,
            code="EXC-01",
            asset_type=FleetAssetType.EXCAVATOR,
        ),
    ]
    db_session.commit()
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        for asset in assets:
            body = deploy(client, asset, site)
            assert body["asset_id"] == str(asset.id)
            assert body["site_id"] == str(site.id)
        listed = client.get(f"/api/v1/owner/sites/{site.id}/assets")
        assert listed.status_code == 200
        by_code = {item["asset_code"]: item for item in listed.json()}
        assert {asset.asset_code for asset in assets} <= set(by_code)
        assert by_code["OWN-T02"]["driver_name"] is None
        assert by_code["OWN-T02"]["current_deployment"]["site_name"] == "Alpha Operations"
        assert by_code["RENT-T03"]["ownership_type"] == "RENTED"
        assert by_code["EXC-01"]["asset_type"] == "EXCAVATOR"
    finally:
        client.close()


def test_move_remove_preserve_history_one_current_and_audit(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    first_site = value(tenant_records, "site_a", Site)
    second_site = add_site(
        db_session, value(tenant_records, "company_a", Company), name="Second Site"
    )
    db_session.commit()
    owner = value(tenant_records, "owner_a", CompanyMembership)
    client = client_for(db_session, owner)
    try:
        first = deploy(client, asset, first_site)
        duplicate = client.post(
            f"/api/v1/owner/assets/{asset.id}/deployment",
            json={"site_id": str(first_site.id)},
        )
        assert duplicate.status_code == 409
        second = deploy(client, asset, second_site)
        history = client.get(f"/api/v1/owner/assets/{asset.id}/deployments").json()
        assert len(history) == 2
        assert history[0]["id"] == second["id"]
        assert history[0]["ends_at"] is None
        assert history[1]["id"] == first["id"]
        assert history[1]["ends_at"] is not None
        assert (
            db_session.scalar(
                select(func.count(AssetSiteDeployment.id)).where(
                    AssetSiteDeployment.asset_id == asset.id,
                    AssetSiteDeployment.ends_at.is_(None),
                )
            )
            == 1
        )

        removed = client.delete(f"/api/v1/owner/assets/{asset.id}/deployment")
        assert removed.status_code == 200
        assert removed.json()["ends_at"] is not None
        assert client.get(f"/api/v1/owner/assets/{asset.id}/deployment").status_code == 204
        assert (
            db_session.scalar(
                select(func.count(AssetSiteDeployment.id)).where(
                    AssetSiteDeployment.asset_id == asset.id,
                    AssetSiteDeployment.ends_at.is_(None),
                )
            )
            == 0
        )
        actions = set(
            db_session.scalars(
                select(AuditLog.action).where(
                    AuditLog.company_id == asset.company_id,
                    AuditLog.entity_id == asset.id,
                )
            ).all()
        )
        assert {
            "ASSET_DEPLOYED_TO_SITE",
            "ASSET_MOVED_SITE",
            "ASSET_REMOVED_FROM_SITE",
        } <= actions
    finally:
        client.close()


def test_deployment_rejects_inactive_and_cross_company_records(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    company = value(tenant_records, "company_a", Company)
    active_asset = value(tenant_records, "tipper_a", FleetAsset)
    active_site = value(tenant_records, "site_a", Site)
    inactive_asset = add_asset(
        db_session,
        company,
        code="INACTIVE-A",
        status=FleetAssetStatus.INACTIVE,
    )
    inactive_site = add_site(db_session, company, name="Inactive Site", status=SiteStatus.INACTIVE)
    assignment_site = add_site(db_session, company, name="Assignment Site")
    mismatch_site = add_site(db_session, company, name="Mismatch Site")
    mismatch_asset = add_asset(db_session, company, code="MISMATCH-A")
    create_assignment(
        db_session,
        company_id=company.id,
        driver_membership_id=value(tenant_records, "driver_a", CompanyMembership).id,
        supervisor_membership_id=value(tenant_records, "supervisor_a", CompanyMembership).id,
        asset_id=mismatch_asset.id,
        site_id=assignment_site.id,
        starts_at=datetime.now(UTC) - timedelta(minutes=5),
        regular_duty_minutes=600,
    )
    foreign_asset = value(tenant_records, "tipper_b", FleetAsset)
    foreign_site = value(tenant_records, "site_b", Site)
    db_session.commit()
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        assert (
            client.post(
                f"/api/v1/owner/assets/{inactive_asset.id}/deployment",
                json={"site_id": str(active_site.id)},
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"/api/v1/owner/assets/{active_asset.id}/deployment",
                json={"site_id": str(inactive_site.id)},
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"/api/v1/owner/assets/{foreign_asset.id}/deployment",
                json={"site_id": str(active_site.id)},
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/v1/owner/assets/{active_asset.id}/deployment",
                json={"site_id": str(foreign_site.id)},
            ).status_code
            == 404
        )
        mismatch = client.post(
            f"/api/v1/owner/assets/{mismatch_asset.id}/deployment",
            json={"site_id": str(mismatch_site.id)},
        )
        assert mismatch.status_code == 409
        assert "actively assigned" in mismatch.json()["detail"]["message"]
    finally:
        client.close()


def test_move_and_remove_reject_active_assignment_and_duty(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    company = value(tenant_records, "company_a", Company)
    site = value(tenant_records, "site_a", Site)
    other_site = add_site(db_session, company, name="Move Target")
    assigned_asset = value(tenant_records, "tipper_a", FleetAsset)
    duty_asset = add_asset(db_session, company, code="DUTY-A")
    db_session.commit()
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        deploy(client, assigned_asset, site)
        active_assignment(db_session, tenant_records, assigned_asset, site)
        db_session.commit()
        moved = client.post(
            f"/api/v1/owner/assets/{assigned_asset.id}/deployment",
            json={"site_id": str(other_site.id)},
        )
        assert moved.status_code == 409
        assert "Driver is actively assigned" in moved.json()["detail"]["message"]
        removed = client.delete(f"/api/v1/owner/assets/{assigned_asset.id}/deployment")
        assert removed.status_code == 409

        deploy(client, duty_asset, site)
        assignment = active_assignment(
            db_session,
            tenant_records,
            duty_asset,
            site,
            driver_key="driver_a2",
        )
        add_active_duty(db_session, assignment)
        db_session.commit()
        duty_move = client.post(
            f"/api/v1/owner/assets/{duty_asset.id}/deployment",
            json={"site_id": str(other_site.id)},
        )
        assert duty_move.status_code == 409
        assert "active duty" in duty_move.json()["detail"]["message"]
    finally:
        client.close()


def test_site_and_asset_deactivation_require_explicit_removal(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    site = value(tenant_records, "site_a", Site)
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        deploy(client, asset, site)
        site_response = client.post(f"/api/v1/owner/sites/{site.id}/deactivate")
        assert site_response.status_code == 409
        assert site_response.json()["detail"]["message"] == (
            "Site cannot be deactivated while assets are deployed."
        )
        asset_response = client.post(f"/api/v1/owner/assets/{asset.id}/deactivate")
        assert asset_response.status_code == 409
        assert asset_response.json()["detail"]["message"] == (
            "Asset must be removed from its Site before deactivation."
        )
    finally:
        client.close()


def test_supervisor_site_assets_are_authorized_and_include_unassigned(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    company = value(tenant_records, "company_a", Company)
    site = value(tenant_records, "site_a", Site)
    other_site = add_site(db_session, company, name="Unauthorized Site")
    assigned = value(tenant_records, "tipper_a", FleetAsset)
    unassigned = add_asset(db_session, company, code="UNASSIGNED-A")
    supervisor = value(tenant_records, "supervisor_a", CompanyMembership)
    db_session.add(
        SupervisorSiteAccess(
            company_id=company.id,
            supervisor_membership_id=supervisor.id,
            site_id=site.id,
        )
    )
    db_session.commit()
    owner_client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        deploy(owner_client, assigned, site)
        deploy(owner_client, unassigned, site)
        active_assignment(db_session, tenant_records, assigned, site)
        db_session.commit()
    finally:
        owner_client.close()

    supervisor_client = client_for(db_session, supervisor)
    driver_client = client_for(db_session, value(tenant_records, "driver_a", CompanyMembership))
    try:
        visible = supervisor_client.get(f"/api/v1/supervisor/sites/{site.id}/assets")
        assert visible.status_code == 200
        by_code = {item["asset_code"]: item for item in visible.json()}
        assert by_code[assigned.asset_code]["driver_name"] == "Driver A"
        assert by_code[unassigned.asset_code]["driver_name"] is None
        assert (
            supervisor_client.get(f"/api/v1/supervisor/sites/{other_site.id}/assets").status_code
            == 403
        )
        assert (
            driver_client.post(
                f"/api/v1/owner/assets/{unassigned.id}/deployment",
                json={"site_id": str(other_site.id)},
            ).status_code
            == 403
        )
    finally:
        supervisor_client.close()
        driver_client.close()
