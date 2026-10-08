from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import fleet_api.domain.owner_operations as operations_domain
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
    EvidenceObject,
    FleetAsset,
    HourMeterReading,
    KmReading,
    OperationalEvent,
    Site,
    SupervisorSiteAccess,
    User,
)
from fleet_api.db.session import get_db as session_get_db
from fleet_api.domain.assignments import create_assignment
from fleet_api.domain.audit import write_audit_log as real_write_audit_log
from fleet_api.domain.enums import (
    AssetOwnershipType,
    DutySessionStatus,
    FleetAssetStatus,
    FleetAssetType,
    HourMeterReadingType,
    KmReadingType,
    MembershipStatus,
    OperationalEventType,
    SiteStatus,
    VerificationStatus,
)
from fleet_api.domain.errors import ConflictError
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
    pre_session, _ = auth.verify_otp(
        challenge_id=challenge,
        otp=provider.deliveries[challenge],
    )
    token = auth.create_session(
        pre_session_token=pre_session,
        membership_id=membership.id,
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
    code: str,
    *,
    asset_type: FleetAssetType = FleetAssetType.TIPPER,
) -> FleetAsset:
    asset = FleetAsset(
        company_id=company.id,
        asset_type=asset_type,
        ownership_type=AssetOwnershipType.OWNED,
        asset_code=code,
        registration_number=f"REG-{code}",
        short_name=code,
        status=FleetAssetStatus.ACTIVE,
    )
    db.add(asset)
    db.flush()
    return asset


def add_site(
    db: Session,
    company: Company,
    name: str,
    *,
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


def deploy(db: Session, asset: FleetAsset, site: Site) -> AssetSiteDeployment:
    deployment = AssetSiteDeployment(
        company_id=asset.company_id,
        asset_id=asset.id,
        site_id=site.id,
        starts_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    db.add(deployment)
    db.flush()
    return deployment


def assign(
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
        regular_duty_minutes=600,
    )


def add_active_duty(
    db: Session,
    assignment: Assignment,
    *,
    hour_meter: bool = False,
) -> DutySession:
    started_at = datetime.now(UTC) - timedelta(minutes=2)
    event = OperationalEvent(
        company_id=assignment.company_id,
        assignment_id=assignment.id,
        client_event_uuid=uuid4(),
        device_created_at=started_at,
        event_type=(
            OperationalEventType.HMR_READING if hour_meter else OperationalEventType.KM_READING
        ),
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
        operational_date=date.today(),
        start_event_id=event.id,
        start_km=None if hour_meter else Decimal("10"),
        start_hmr=Decimal("10") if hour_meter else None,
        started_at=started_at,
        configured_regular_duty_minutes=600,
        regular_duty_ends_at=started_at + timedelta(minutes=600),
        status=DutySessionStatus.ACTIVE,
    )
    db.add(duty)
    db.flush()
    event.duty_session_id = duty.id
    db.flush()
    return duty


def add_start_meter_evidence(db: Session, duty: DutySession) -> EvidenceObject:
    event = db.get(OperationalEvent, duty.start_event_id)
    assert event is not None
    event.verification_status = VerificationStatus.APPROVED
    object_key = f"owner-force-close-tests/{uuid4()}.jpg"
    evidence = EvidenceObject(
        company_id=duty.company_id,
        membership_id=duty.driver_membership_id,
        client_event_uuid=event.client_event_uuid,
        object_key=object_key,
        content_type="image/jpeg",
        size_bytes=128,
    )
    db.add(evidence)
    if duty.start_hmr is not None:
        db.add(
            HourMeterReading(
                event_id=event.id,
                reading_type=HourMeterReadingType.START_READING,
                reading_value=duty.start_hmr,
                object_reference=object_key,
            )
        )
    else:
        assert duty.start_km is not None
        db.add(
            KmReading(
                event_id=event.id,
                reading_type=KmReadingType.START_READING,
                reading_value=duty.start_km,
                object_reference=object_key,
            )
        )
    db.flush()
    return evidence


def preview(client: TestClient, payload: dict[str, object]) -> dict[str, object]:
    response = client.post("/api/v1/owner/operations/preview", json=payload)
    assert response.status_code == 200, response.text
    return cast(dict[str, object], response.json())


def execute(
    client: TestClient,
    payload: dict[str, object],
    plan: dict[str, object],
) -> Response:
    return client.post(
        "/api/v1/owner/operations/execute",
        json={**payload, "state_token": plan["state_token"]},
    )


def test_assign_driver_to_undeployed_asset_deploys_and_assigns_atomically(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    site = value(tenant_records, "site_a", Site)
    driver = value(tenant_records, "driver_a", CompanyMembership)
    payload: dict[str, object] = {
        "action": "ASSIGN_DRIVER",
        "asset_id": str(asset.id),
        "driver_membership_id": str(driver.id),
        "site_id": str(site.id),
        "regular_duty_minutes": 600,
    }
    client = client_for(
        db_session,
        value(tenant_records, "owner_a", CompanyMembership),
    )
    try:
        plan = preview(client, payload)
        assert plan["can_execute"] is True
        assert plan["planned_changes"] == [
            "Deploy Alpha One to Alpha Site",
            "Assign Driver A to Alpha One at Alpha Site",
        ]
        response = execute(client, payload, plan)
        assert response.status_code == 200, response.text

        deployment = db_session.scalar(
            select(AssetSiteDeployment).where(
                AssetSiteDeployment.asset_id == asset.id,
                AssetSiteDeployment.ends_at.is_(None),
            )
        )
        assignment = db_session.scalar(
            select(Assignment).where(
                Assignment.asset_id == asset.id,
                Assignment.ends_at.is_(None),
            )
        )
        assert deployment is not None
        assert assignment is not None
        assert assignment.asset_site_deployment_id == deployment.id
        assert assignment.site_id == site.id
        assert assignment.driver_membership_id == driver.id
    finally:
        client.close()


def test_partial_intents_return_server_authoritative_choice_previews(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    driver = value(tenant_records, "driver_a", CompanyMembership)
    site = value(tenant_records, "site_a", Site)
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        deploy_plan = preview(
            client,
            {"action": "DEPLOY_ASSET", "asset_id": str(asset.id)},
        )
        assert deploy_plan["can_execute"] is False
        assert "Choose an active Site" in " ".join(cast(list[str], deploy_plan["blocked_reasons"]))

        driver_plan = preview(
            client,
            {"action": "ASSIGN_DRIVER", "driver_membership_id": str(driver.id)},
        )
        assert driver_plan["can_execute"] is False
        assert "Choose an available asset" in " ".join(
            cast(list[str], driver_plan["blocked_reasons"])
        )

        asset_plan = preview(
            client,
            {"action": "ASSIGN_DRIVER", "asset_id": str(asset.id)},
        )
        assert asset_plan["can_execute"] is False
        assert "Choose a Driver / Operator" in " ".join(
            cast(list[str], asset_plan["blocked_reasons"])
        )

        deploy(db_session, asset, site)
        db_session.commit()
        move_plan = preview(
            client,
            {"action": "MOVE_DEPLOYMENT", "asset_id": str(asset.id)},
        )
        assert move_plan["can_execute"] is False
        assert "Choose a destination Site" in " ".join(
            cast(list[str], move_plan["blocked_reasons"])
        )
    finally:
        client.close()


def test_reassign_driver_ends_old_row_and_creates_site_consistent_history(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    site = value(tenant_records, "site_a", Site)
    deployment = deploy(db_session, asset, site)
    original = assign(db_session, tenant_records, asset, site)
    replacement = value(tenant_records, "driver_a2", CompanyMembership)
    db_session.commit()
    payload: dict[str, object] = {
        "action": "REASSIGN_DRIVER",
        "asset_id": str(asset.id),
        "driver_membership_id": str(replacement.id),
        "regular_duty_minutes": 480,
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        plan = preview(client, payload)
        assert plan["can_execute"] is True
        response = execute(client, payload, plan)
        assert response.status_code == 200, response.text
        db_session.expire_all()
        db_session.refresh(original)
        assert original.ends_at is not None
        current = db_session.scalar(
            select(Assignment).where(
                Assignment.asset_id == asset.id,
                Assignment.ends_at.is_(None),
            )
        )
        assert current is not None
        assert current.id != original.id
        assert current.driver_membership_id == replacement.id
        assert current.site_id == site.id
        assert current.asset_site_deployment_id == deployment.id
        assert current.regular_duty_minutes == 480
    finally:
        client.close()


def test_driver_can_be_reactivated_without_assignment(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    driver = value(tenant_records, "driver_a", CompanyMembership)
    driver.status = MembershipStatus.INACTIVE
    db_session.commit()
    payload: dict[str, object] = {
        "action": "ACTIVATE_PERSON",
        "person_membership_id": str(driver.id),
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        plan = preview(client, payload)
        assert plan["can_execute"] is True
        assert execute(client, payload, plan).status_code == 200
        db_session.expire_all()
        db_session.refresh(driver)
        assert driver.status == MembershipStatus.ACTIVE
        assert (
            db_session.scalar(
                select(func.count(Assignment.id)).where(
                    Assignment.driver_membership_id == driver.id,
                    Assignment.ends_at.is_(None),
                )
            )
            == 0
        )
    finally:
        client.close()


@pytest.mark.parametrize("already_deployed", [True, False])
def test_driver_reactivation_can_assign_deployed_or_deploy_undeployed_asset(
    db_session: Session,
    tenant_records: dict[str, object],
    already_deployed: bool,
) -> None:
    driver = value(tenant_records, "driver_a", CompanyMembership)
    driver.status = MembershipStatus.INACTIVE
    asset = value(tenant_records, "tipper_a", FleetAsset)
    site = value(tenant_records, "site_a", Site)
    if already_deployed:
        deploy(db_session, asset, site)
    db_session.commit()
    payload: dict[str, object] = {
        "action": "ACTIVATE_PERSON",
        "person_membership_id": str(driver.id),
        "asset_id": str(asset.id),
        **({} if already_deployed else {"site_id": str(site.id)}),
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        plan = preview(client, payload)
        assert plan["can_execute"] is True
        assert (
            cast(list[str], plan["planned_changes"]).count(
                "Reactivate Driver A as Driver / Operator"
            )
            == 1
        )
        assert execute(client, payload, plan).status_code == 200
        db_session.expire_all()
        assignment = db_session.scalar(
            select(Assignment).where(
                Assignment.driver_membership_id == driver.id,
                Assignment.ends_at.is_(None),
            )
        )
        deployment = db_session.scalar(
            select(AssetSiteDeployment).where(
                AssetSiteDeployment.asset_id == asset.id,
                AssetSiteDeployment.ends_at.is_(None),
            )
        )
        assert assignment is not None
        assert deployment is not None
        assert assignment.site_id == site.id
        assert assignment.asset_site_deployment_id == deployment.id
    finally:
        client.close()


@pytest.mark.parametrize("assignment_action", ["KEEP", "END"])
def test_move_deployment_reconciles_off_duty_assignment_without_rewriting_history(
    db_session: Session,
    tenant_records: dict[str, object],
    assignment_action: str,
) -> None:
    company = value(tenant_records, "company_a", Company)
    asset = value(tenant_records, "tipper_a", FleetAsset)
    source = value(tenant_records, "site_a", Site)
    target = add_site(db_session, company, f"Move Target {assignment_action}")
    original_deployment = deploy(db_session, asset, source)
    original_assignment = assign(db_session, tenant_records, asset, source)
    db_session.commit()
    payload: dict[str, object] = {
        "action": "MOVE_DEPLOYMENT",
        "asset_id": str(asset.id),
        "target_site_id": str(target.id),
        "assignment_action": assignment_action,
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        plan = preview(client, payload)
        assert plan["can_execute"] is True
        response = execute(client, payload, plan)
        assert response.status_code == 200, response.text
        db_session.expire_all()
        db_session.refresh(original_deployment)
        db_session.refresh(original_assignment)
        assert original_deployment.ends_at is not None
        assert original_assignment.ends_at is not None
        assert original_deployment.site_id == source.id
        assert original_assignment.site_id == source.id

        current_deployment = db_session.scalar(
            select(AssetSiteDeployment).where(
                AssetSiteDeployment.asset_id == asset.id,
                AssetSiteDeployment.ends_at.is_(None),
            )
        )
        current_assignment = db_session.scalar(
            select(Assignment).where(
                Assignment.asset_id == asset.id,
                Assignment.ends_at.is_(None),
            )
        )
        assert current_deployment is not None
        assert current_deployment.site_id == target.id
        if assignment_action == "KEEP":
            assert current_assignment is not None
            assert current_assignment.id != original_assignment.id
            assert current_assignment.site_id == target.id
            assert current_assignment.asset_site_deployment_id == current_deployment.id
        else:
            assert current_assignment is None
    finally:
        client.close()


def test_site_deactivation_resolves_mixed_assets_and_supervisor_access_atomically(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    source = value(tenant_records, "site_a", Site)
    target = add_site(db_session, company, "Destination")
    first = value(tenant_records, "tipper_a", FleetAsset)
    second = add_asset(db_session, company, "SECOND")
    deploy(db_session, first, source)
    deploy(db_session, second, source)
    first_assignment = assign(db_session, tenant_records, first, source)
    supervisor = value(tenant_records, "supervisor_a", CompanyMembership)
    access = SupervisorSiteAccess(
        company_id=company.id,
        supervisor_membership_id=supervisor.id,
        site_id=source.id,
    )
    db_session.add(access)
    db_session.commit()
    payload: dict[str, object] = {
        "action": "DEACTIVATE_SITE",
        "site_id": str(source.id),
        "asset_resolutions": [
            {
                "asset_id": str(first.id),
                "action": "MOVE",
                "target_site_id": str(target.id),
                "assignment_action": "KEEP",
            },
            {"asset_id": str(second.id), "action": "REMOVE"},
        ],
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        plan = preview(client, payload)
        assert plan["can_execute"] is True
        assert len(cast(list[object], plan["dependencies"])) == 3
        response = execute(client, payload, plan)
        assert response.status_code == 200, response.text
        db_session.expire_all()
        db_session.refresh(source)
        db_session.refresh(first_assignment)
        assert source.status == SiteStatus.INACTIVE
        assert first_assignment.ends_at is not None
        assert db_session.get(SupervisorSiteAccess, access.id) is None
        deployments = db_session.scalars(
            select(AssetSiteDeployment).where(
                AssetSiteDeployment.company_id == company.id,
                AssetSiteDeployment.ends_at.is_(None),
            )
        ).all()
        assert [(row.asset_id, row.site_id) for row in deployments] == [(first.id, target.id)]
        replacement = db_session.scalar(
            select(Assignment).where(
                Assignment.asset_id == first.id,
                Assignment.ends_at.is_(None),
            )
        )
        assert replacement is not None
        assert replacement.site_id == target.id
    finally:
        client.close()


def test_site_without_dependencies_deactivates_and_preserves_the_row(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    site = value(tenant_records, "site_a", Site)
    payload: dict[str, object] = {
        "action": "DEACTIVATE_SITE",
        "site_id": str(site.id),
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        plan = preview(client, payload)
        assert plan["can_execute"] is True
        assert cast(list[object], plan["dependencies"]) == []
        assert execute(client, payload, plan).status_code == 200
        db_session.expire_all()
        db_session.refresh(site)
        assert site.status == SiteStatus.INACTIVE
        assert db_session.get(Site, site.id) is not None
    finally:
        client.close()


def test_site_reactivation_can_grant_access_and_deploy_assets_atomically(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    site = value(tenant_records, "site_a", Site)
    site.status = SiteStatus.INACTIVE
    asset = value(tenant_records, "tipper_a", FleetAsset)
    supervisor = value(tenant_records, "supervisor_a", CompanyMembership)
    db_session.commit()
    payload: dict[str, object] = {
        "action": "REACTIVATE_SITE",
        "site_id": str(site.id),
        "selected_supervisor_ids": [str(supervisor.id)],
        "selected_asset_ids": [str(asset.id)],
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        plan = preview(client, payload)
        assert plan["can_execute"] is True
        assert execute(client, payload, plan).status_code == 200
        db_session.expire_all()
        db_session.refresh(site)
        assert site.status == SiteStatus.ACTIVE
        assert db_session.scalar(
            select(AssetSiteDeployment).where(
                AssetSiteDeployment.asset_id == asset.id,
                AssetSiteDeployment.site_id == site.id,
                AssetSiteDeployment.ends_at.is_(None),
            )
        )
        assert db_session.scalar(
            select(SupervisorSiteAccess).where(
                SupervisorSiteAccess.supervisor_membership_id == supervisor.id,
                SupervisorSiteAccess.site_id == site.id,
            )
        )
    finally:
        client.close()


def test_site_deactivation_with_active_duty_is_blocked_without_partial_changes(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    site = value(tenant_records, "site_a", Site)
    deployment = deploy(db_session, asset, site)
    assignment = assign(db_session, tenant_records, asset, site)
    duty = add_active_duty(db_session, assignment)
    db_session.commit()
    payload: dict[str, object] = {
        "action": "DEACTIVATE_SITE",
        "site_id": str(site.id),
        "asset_resolutions": [{"asset_id": str(asset.id), "action": "REMOVE"}],
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        plan = preview(client, payload)
        assert plan["can_execute"] is False
        assert "on duty" in " ".join(cast(list[str], plan["blocked_reasons"])).lower()
        response = execute(client, payload, plan)
        assert response.status_code == 409
        db_session.expire_all()
        db_session.refresh(site)
        db_session.refresh(deployment)
        db_session.refresh(assignment)
        db_session.refresh(duty)
        assert site.status == SiteStatus.ACTIVE
        assert deployment.ends_at is None
        assert assignment.ends_at is None
        assert duty.status == DutySessionStatus.ACTIVE
    finally:
        client.close()


def test_site_deactivation_stale_preview_returns_conflict_and_zero_partial_changes(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    site = value(tenant_records, "site_a", Site)
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    payload: dict[str, object] = {"action": "DEACTIVATE_SITE", "site_id": str(site.id)}
    try:
        plan = preview(client, payload)
        late_asset = add_asset(db_session, company, "LATE")
        deployment = deploy(db_session, late_asset, site)
        db_session.commit()

        response = execute(client, payload, plan)
        assert response.status_code == 409
        assert response.json()["detail"]["message"] == (
            "State changed. Review the operation again."
        )
        db_session.expire_all()
        db_session.refresh(site)
        db_session.refresh(deployment)
        assert site.status == SiteStatus.ACTIVE
        assert deployment.ends_at is None
    finally:
        client.close()


def test_supervisor_activation_site_management_and_deactivation_end_access(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    first = value(tenant_records, "site_a", Site)
    second = add_site(db_session, company, "Second Site")
    supervisor = value(tenant_records, "supervisor_a", CompanyMembership)
    supervisor.status = MembershipStatus.INACTIVE
    db_session.commit()
    activate_payload: dict[str, object] = {
        "action": "ACTIVATE_PERSON",
        "person_membership_id": str(supervisor.id),
        "selected_site_ids": [str(first.id)],
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        plan = preview(client, activate_payload)
        assert plan["can_execute"] is True
        assert execute(client, activate_payload, plan).status_code == 200
        db_session.expire_all()
        db_session.refresh(supervisor)
        assert supervisor.status == MembershipStatus.ACTIVE
        assert (
            db_session.scalar(
                select(func.count(SupervisorSiteAccess.id)).where(
                    SupervisorSiteAccess.supervisor_membership_id == supervisor.id
                )
            )
            == 1
        )

        manage_payload: dict[str, object] = {
            "action": "SET_SUPERVISOR_SITES",
            "person_membership_id": str(supervisor.id),
            "selected_site_ids": [str(first.id), str(second.id)],
        }
        manage_plan = preview(client, manage_payload)
        assert execute(client, manage_payload, manage_plan).status_code == 200
        assert (
            db_session.scalar(
                select(func.count(SupervisorSiteAccess.id)).where(
                    SupervisorSiteAccess.supervisor_membership_id == supervisor.id
                )
            )
            == 2
        )

        deactivate_payload: dict[str, object] = {
            "action": "DEACTIVATE_PERSON",
            "person_membership_id": str(supervisor.id),
        }
        deactivate_plan = preview(client, deactivate_payload)
        assert execute(client, deactivate_payload, deactivate_plan).status_code == 200
        db_session.expire_all()
        db_session.refresh(supervisor)
        assert supervisor.status.value == MembershipStatus.INACTIVE.value
        assert (
            db_session.scalar(
                select(func.count(SupervisorSiteAccess.id)).where(
                    SupervisorSiteAccess.supervisor_membership_id == supervisor.id
                )
            )
            == 0
        )
    finally:
        client.close()


def test_supervisor_can_be_reactivated_without_site_access(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    supervisor = value(tenant_records, "supervisor_a", CompanyMembership)
    supervisor.status = MembershipStatus.INACTIVE
    db_session.commit()
    payload: dict[str, object] = {
        "action": "ACTIVATE_PERSON",
        "person_membership_id": str(supervisor.id),
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        plan = preview(client, payload)
        assert plan["can_execute"] is True
        assert execute(client, payload, plan).status_code == 200
        db_session.expire_all()
        db_session.refresh(supervisor)
        assert supervisor.status == MembershipStatus.ACTIVE
        assert (
            db_session.scalar(
                select(func.count(SupervisorSiteAccess.id)).where(
                    SupervisorSiteAccess.supervisor_membership_id == supervisor.id
                )
            )
            == 0
        )
    finally:
        client.close()


def test_driver_deactivation_ends_off_duty_assignment_and_blocks_active_duty(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    site = value(tenant_records, "site_a", Site)
    off_duty_asset = value(tenant_records, "tipper_a", FleetAsset)
    on_duty_asset = add_asset(db_session, company, "DUTY")
    off_duty_assignment = assign(db_session, tenant_records, off_duty_asset, site)
    on_duty_assignment = assign(
        db_session,
        tenant_records,
        on_duty_asset,
        site,
        driver_key="driver_a2",
    )
    add_active_duty(db_session, on_duty_assignment)
    db_session.commit()
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        driver = value(tenant_records, "driver_a", CompanyMembership)
        payload: dict[str, object] = {
            "action": "DEACTIVATE_PERSON",
            "person_membership_id": str(driver.id),
        }
        plan = preview(client, payload)
        assert plan["can_execute"] is True
        assert execute(client, payload, plan).status_code == 200
        db_session.expire_all()
        db_session.refresh(driver)
        db_session.refresh(off_duty_assignment)
        assert driver.status == MembershipStatus.INACTIVE
        assert off_duty_assignment.ends_at is not None

        duty_driver = value(tenant_records, "driver_a2", CompanyMembership)
        duty_payload: dict[str, object] = {
            "action": "DEACTIVATE_PERSON",
            "person_membership_id": str(duty_driver.id),
        }
        duty_plan = preview(client, duty_payload)
        assert duty_plan["can_execute"] is False
        assert execute(client, duty_payload, duty_plan).status_code == 409
        db_session.expire_all()
        db_session.refresh(duty_driver)
        db_session.refresh(on_duty_assignment)
        assert duty_driver.status == MembershipStatus.ACTIVE
        assert on_duty_assignment.ends_at is None
    finally:
        client.close()


def test_asset_deactivation_cascades_off_duty_relationships_and_preserves_rows(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    site = value(tenant_records, "site_a", Site)
    deployment = deploy(db_session, asset, site)
    assignment = assign(db_session, tenant_records, asset, site)
    db_session.commit()
    payload: dict[str, object] = {
        "action": "DEACTIVATE_ASSET",
        "asset_id": str(asset.id),
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        plan = preview(client, payload)
        assert execute(client, payload, plan).status_code == 200
        db_session.expire_all()
        db_session.refresh(asset)
        db_session.refresh(deployment)
        db_session.refresh(assignment)
        assert asset.status == FleetAssetStatus.INACTIVE
        assert deployment.ends_at is not None
        assert assignment.ends_at is not None
        assert db_session.get(AssetSiteDeployment, deployment.id) is not None
        assert db_session.get(Assignment, assignment.id) is not None
    finally:
        client.close()


def test_operation_is_owner_only_and_tenant_scoped(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    foreign_asset = value(tenant_records, "tipper_b", FleetAsset)
    owner = value(tenant_records, "owner_a", CompanyMembership)
    driver = value(tenant_records, "driver_a", CompanyMembership)
    payload = {"action": "DEACTIVATE_ASSET", "asset_id": str(foreign_asset.id)}
    owner_client = client_for(db_session, owner)
    driver_client = client_for(db_session, driver)
    try:
        missing_response = owner_client.post(
            "/api/v1/owner/operations/preview",
            json=payload,
        )
        assert missing_response.status_code == 404
        assert missing_response.json()["detail"]["code"] == "NOT_FOUND"
        assert (
            driver_client.post(
                "/api/v1/owner/operations/preview",
                json=payload,
            ).status_code
            == 403
        )
    finally:
        owner_client.close()
        driver_client.close()


def test_composite_operation_rolls_back_all_changes_when_audit_fails(
    db_session: Session,
    tenant_records: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    site = value(tenant_records, "site_a", Site)
    deployment = deploy(db_session, asset, site)
    assignment = assign(db_session, tenant_records, asset, site)
    db_session.commit()
    payload: dict[str, object] = {
        "action": "REMOVE_DEPLOYMENT",
        "asset_id": str(asset.id),
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        plan = preview(client, payload)

        def fail_second_audit(*args: object, **kwargs: object) -> AuditLog:
            if kwargs.get("action") == "ASSET_REMOVED_FROM_SITE":
                raise ConflictError("injected audit failure")
            return real_write_audit_log(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(operations_domain, "write_audit_log", fail_second_audit)
        response = execute(client, payload, plan)
        assert response.status_code == 409
        db_session.expire_all()
        db_session.refresh(deployment)
        db_session.refresh(assignment)
        assert deployment.ends_at is None
        assert assignment.ends_at is None
    finally:
        client.close()


def test_reactivate_asset_only_leaves_it_undeployed_and_unassigned(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    asset.status = FleetAssetStatus.INACTIVE
    db_session.commit()
    payload: dict[str, object] = {
        "action": "REACTIVATE_ASSET",
        "asset_id": str(asset.id),
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        plan = preview(client, payload)
        assert plan["can_execute"] is True
        assert plan["allowed_resolutions"] == [
            "REACTIVATE_ONLY",
            "REACTIVATE_AND_DEPLOY",
            "REACTIVATE_DEPLOY_ASSIGN",
        ]
        assert execute(client, payload, plan).status_code == 200
        db_session.expire_all()
        db_session.refresh(asset)
        assert asset.status == FleetAssetStatus.ACTIVE
        assert (
            db_session.scalar(
                select(AssetSiteDeployment).where(
                    AssetSiteDeployment.asset_id == asset.id,
                    AssetSiteDeployment.ends_at.is_(None),
                )
            )
            is None
        )
        assert (
            db_session.scalar(
                select(Assignment).where(
                    Assignment.asset_id == asset.id,
                    Assignment.ends_at.is_(None),
                )
            )
            is None
        )
        assert (
            db_session.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.action == "OWNER_ASSET_REACTIVATED",
                    AuditLog.entity_id == asset.id,
                )
            )
            == 1
        )
    finally:
        client.close()


def test_reactivate_asset_with_site_deploys_without_assigning(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    site = value(tenant_records, "site_a", Site)
    asset.status = FleetAssetStatus.INACTIVE
    db_session.commit()
    payload: dict[str, object] = {
        "action": "REACTIVATE_ASSET",
        "asset_id": str(asset.id),
        "site_id": str(site.id),
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        plan = preview(client, payload)
        assert plan["can_execute"] is True
        assert any(
            item["kind"] == "TARGET_SITE"
            for item in cast(list[dict[str, object]], plan["dependencies"])
        )
        assert execute(client, payload, plan).status_code == 200
        db_session.expire_all()
        db_session.refresh(asset)
        deployment = db_session.scalar(
            select(AssetSiteDeployment).where(
                AssetSiteDeployment.asset_id == asset.id,
                AssetSiteDeployment.ends_at.is_(None),
            )
        )
        assert asset.status == FleetAssetStatus.ACTIVE
        assert deployment is not None
        assert deployment.site_id == site.id
        assert (
            db_session.scalar(
                select(Assignment).where(
                    Assignment.asset_id == asset.id,
                    Assignment.ends_at.is_(None),
                )
            )
            is None
        )
    finally:
        client.close()


def test_reactivate_asset_with_site_and_driver_is_atomic_setup(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    site = value(tenant_records, "site_a", Site)
    driver = value(tenant_records, "driver_a", CompanyMembership)
    asset.status = FleetAssetStatus.INACTIVE
    db_session.commit()
    payload: dict[str, object] = {
        "action": "REACTIVATE_ASSET",
        "asset_id": str(asset.id),
        "site_id": str(site.id),
        "driver_membership_id": str(driver.id),
        "regular_duty_minutes": 540,
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        plan = preview(client, payload)
        assert plan["can_execute"] is True
        driver_item = next(
            item
            for item in cast(list[dict[str, object]], plan["dependencies"])
            if item["kind"] == "DRIVER"
        )
        assert cast(dict[str, object], driver_item["details"])["assignment_state"] == "UNASSIGNED"
        assert execute(client, payload, plan).status_code == 200
        db_session.expire_all()
        db_session.refresh(asset)
        deployment = db_session.scalar(
            select(AssetSiteDeployment).where(
                AssetSiteDeployment.asset_id == asset.id,
                AssetSiteDeployment.ends_at.is_(None),
            )
        )
        assignment = db_session.scalar(
            select(Assignment).where(
                Assignment.asset_id == asset.id,
                Assignment.ends_at.is_(None),
            )
        )
        assert asset.status == FleetAssetStatus.ACTIVE
        assert deployment is not None
        assert assignment is not None
        assert assignment.asset_site_deployment_id == deployment.id
        assert assignment.site_id == site.id
        assert assignment.driver_membership_id == driver.id
        assert assignment.regular_duty_minutes == 540
    finally:
        client.close()


def test_reactivate_asset_requires_site_before_driver_assignment(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    driver = value(tenant_records, "driver_a", CompanyMembership)
    asset.status = FleetAssetStatus.INACTIVE
    db_session.commit()
    payload: dict[str, object] = {
        "action": "REACTIVATE_ASSET",
        "asset_id": str(asset.id),
        "driver_membership_id": str(driver.id),
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        plan = preview(client, payload)
        assert plan["can_execute"] is False
        assert "Choose a Site before assigning a Driver / Operator." in cast(
            list[str], plan["blocked_reasons"]
        )
        response = execute(client, payload, plan)
        assert response.status_code == 409
        db_session.expire_all()
        db_session.refresh(asset)
        assert asset.status == FleetAssetStatus.INACTIVE
    finally:
        client.close()


def test_reactivate_asset_rejects_driver_with_a_current_assignment(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    target_asset = value(tenant_records, "tipper_a", FleetAsset)
    site = value(tenant_records, "site_a", Site)
    driver = value(tenant_records, "driver_a", CompanyMembership)
    busy_asset = add_asset(db_session, company, "BUSY")
    deploy(db_session, busy_asset, site)
    assign(db_session, tenant_records, busy_asset, site)
    target_asset.status = FleetAssetStatus.INACTIVE
    db_session.commit()
    payload: dict[str, object] = {
        "action": "REACTIVATE_ASSET",
        "asset_id": str(target_asset.id),
        "site_id": str(site.id),
        "driver_membership_id": str(driver.id),
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        plan = preview(client, payload)
        assert plan["can_execute"] is False
        assert "Driver / Operator already has a current asset." in cast(
            list[str], plan["blocked_reasons"]
        )
        driver_item = next(
            item
            for item in cast(list[dict[str, object]], plan["dependencies"])
            if item["kind"] == "DRIVER"
        )
        assert cast(dict[str, object], driver_item["details"])["assignment_state"] == "ASSIGNED"
    finally:
        client.close()


def test_reactivate_asset_requires_explicit_inactive_driver_role_reactivation(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    site = value(tenant_records, "site_a", Site)
    driver = value(tenant_records, "driver_a", CompanyMembership)
    asset.status = FleetAssetStatus.INACTIVE
    driver.status = MembershipStatus.INACTIVE
    db_session.commit()
    base_payload: dict[str, object] = {
        "action": "REACTIVATE_ASSET",
        "asset_id": str(asset.id),
        "site_id": str(site.id),
        "driver_membership_id": str(driver.id),
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        blocked_plan = preview(client, base_payload)
        assert blocked_plan["can_execute"] is False
        assert any(
            "Reactivate role as part of this setup" in reason
            for reason in cast(list[str], blocked_plan["blocked_reasons"])
        )

        payload = {**base_payload, "activate_membership": True}
        plan = preview(client, payload)
        assert plan["can_execute"] is True
        assert execute(client, payload, plan).status_code == 200
        db_session.expire_all()
        db_session.refresh(driver)
        assert driver.status == MembershipStatus.ACTIVE
        assignment = db_session.scalar(
            select(Assignment).where(
                Assignment.asset_id == asset.id,
                Assignment.ends_at.is_(None),
            )
        )
        assert assignment is not None
        assert assignment.driver_membership_id == driver.id
    finally:
        client.close()


def test_reactivate_asset_allows_invited_driver_without_silent_activation(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    site = value(tenant_records, "site_a", Site)
    driver = value(tenant_records, "driver_a", CompanyMembership)
    asset.status = FleetAssetStatus.INACTIVE
    driver.status = MembershipStatus.INVITED
    db_session.commit()
    base_payload: dict[str, object] = {
        "action": "REACTIVATE_ASSET",
        "asset_id": str(asset.id),
        "site_id": str(site.id),
        "driver_membership_id": str(driver.id),
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        invalid_activation_plan = preview(
            client,
            {**base_payload, "activate_membership": True},
        )
        assert invalid_activation_plan["can_execute"] is False
        assert "Invited people become active through their first OTP login." in cast(
            list[str], invalid_activation_plan["blocked_reasons"]
        )

        plan = preview(client, base_payload)
        assert plan["can_execute"] is True
        assert execute(client, base_payload, plan).status_code == 200
        db_session.expire_all()
        db_session.refresh(driver)
        assert driver.status == MembershipStatus.INVITED
        assignment = db_session.scalar(
            select(Assignment).where(
                Assignment.asset_id == asset.id,
                Assignment.ends_at.is_(None),
            )
        )
        assert assignment is not None
        assert assignment.driver_membership_id == driver.id
    finally:
        client.close()


def test_reactivate_asset_setup_rolls_back_every_step_when_assignment_audit_fails(
    db_session: Session,
    tenant_records: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    site = value(tenant_records, "site_a", Site)
    driver = value(tenant_records, "driver_a", CompanyMembership)
    asset.status = FleetAssetStatus.INACTIVE
    driver.status = MembershipStatus.INACTIVE
    db_session.commit()
    payload: dict[str, object] = {
        "action": "REACTIVATE_ASSET",
        "asset_id": str(asset.id),
        "site_id": str(site.id),
        "driver_membership_id": str(driver.id),
        "activate_membership": True,
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        plan = preview(client, payload)

        def fail_assignment_audit(*args: object, **kwargs: object) -> AuditLog:
            if kwargs.get("action") == "DRIVER_ASSIGNED_TO_ASSET":
                raise ConflictError("injected assignment audit failure")
            return real_write_audit_log(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(operations_domain, "write_audit_log", fail_assignment_audit)
        response = execute(client, payload, plan)
        assert response.status_code == 409
        db_session.expire_all()
        db_session.refresh(asset)
        db_session.refresh(driver)
        assert asset.status == FleetAssetStatus.INACTIVE
        assert driver.status == MembershipStatus.INACTIVE
        assert (
            db_session.scalar(
                select(AssetSiteDeployment).where(
                    AssetSiteDeployment.asset_id == asset.id,
                    AssetSiteDeployment.ends_at.is_(None),
                )
            )
            is None
        )
        assert (
            db_session.scalar(
                select(Assignment).where(
                    Assignment.asset_id == asset.id,
                    Assignment.ends_at.is_(None),
                )
            )
            is None
        )
    finally:
        client.close()


def test_reactivate_asset_rejects_stale_state_without_partial_changes(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    site = value(tenant_records, "site_a", Site)
    asset.status = FleetAssetStatus.INACTIVE
    db_session.commit()
    payload: dict[str, object] = {
        "action": "REACTIVATE_ASSET",
        "asset_id": str(asset.id),
        "site_id": str(site.id),
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        plan = preview(client, payload)
        site.short_name = "Renamed after preview"
        db_session.commit()
        response = execute(client, payload, plan)
        assert response.status_code == 409
        assert response.json()["detail"]["message"] == (
            "State changed. Review the operation again."
        )
        db_session.expire_all()
        db_session.refresh(asset)
        assert asset.status == FleetAssetStatus.INACTIVE
        assert (
            db_session.scalar(
                select(AssetSiteDeployment).where(
                    AssetSiteDeployment.asset_id == asset.id,
                    AssetSiteDeployment.ends_at.is_(None),
                )
            )
            is None
        )
    finally:
        client.close()


def test_reactivate_asset_is_tenant_scoped_for_asset_site_and_driver(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    foreign_asset = value(tenant_records, "tipper_b", FleetAsset)
    foreign_site = value(tenant_records, "site_b", Site)
    foreign_driver = value(tenant_records, "driver_b", CompanyMembership)
    asset.status = FleetAssetStatus.INACTIVE
    foreign_asset.status = FleetAssetStatus.INACTIVE
    db_session.commit()
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    payloads: list[dict[str, object]] = [
        {
            "action": "REACTIVATE_ASSET",
            "asset_id": str(foreign_asset.id),
        },
        {
            "action": "REACTIVATE_ASSET",
            "asset_id": str(asset.id),
            "site_id": str(foreign_site.id),
        },
        {
            "action": "REACTIVATE_ASSET",
            "asset_id": str(asset.id),
            "site_id": str(value(tenant_records, "site_a", Site).id),
            "driver_membership_id": str(foreign_driver.id),
        },
    ]
    try:
        for payload in payloads:
            response = client.post("/api/v1/owner/operations/preview", json=payload)
            assert response.status_code == 404
            assert response.json()["detail"]["code"] == "NOT_FOUND"
    finally:
        client.close()


def test_reactivate_asset_preserves_history_and_marks_previous_context(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    site = value(tenant_records, "site_a", Site)
    driver = value(tenant_records, "driver_a", CompanyMembership)
    previous_deployment = deploy(db_session, asset, site)
    previous_assignment = assign(db_session, tenant_records, asset, site)
    ended_at = datetime.now(UTC)
    previous_assignment.ends_at = ended_at
    previous_deployment.ends_at = ended_at
    asset.status = FleetAssetStatus.INACTIVE
    db_session.commit()
    payload: dict[str, object] = {
        "action": "REACTIVATE_ASSET",
        "asset_id": str(asset.id),
        "site_id": str(site.id),
        "driver_membership_id": str(driver.id),
    }
    client = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        plan = preview(client, payload)
        current_kinds = {
            item["kind"] for item in cast(list[dict[str, object]], plan["current_state"])
        }
        assert {"ASSET", "PREVIOUS_SITE", "PREVIOUS_DRIVER"} <= current_kinds
        assert execute(client, payload, plan).status_code == 200
        db_session.expire_all()
        db_session.refresh(previous_deployment)
        db_session.refresh(previous_assignment)
        assert previous_deployment.ends_at == ended_at
        assert previous_assignment.ends_at == ended_at
        deployments = db_session.scalars(
            select(AssetSiteDeployment)
            .where(AssetSiteDeployment.asset_id == asset.id)
            .order_by(AssetSiteDeployment.starts_at)
        ).all()
        assignments = db_session.scalars(
            select(Assignment).where(Assignment.asset_id == asset.id).order_by(Assignment.starts_at)
        ).all()
        assert len(deployments) == 2
        assert len(assignments) == 2
        assert deployments[-1].id != previous_deployment.id
        assert assignments[-1].id != previous_assignment.id
        assert deployments[-1].ends_at is None
        assert assignments[-1].ends_at is None
    finally:
        client.close()


@pytest.mark.parametrize(
    ("asset_type", "hour_meter", "expected_exception", "meter_type"),
    [
        (FleetAssetType.TIPPER, False, "MISSING_END_READING", "KM"),
        (FleetAssetType.EXCAVATOR, True, "MISSING_END_HMR", "HMR"),
    ],
)
def test_owner_force_closes_duty_and_deactivates_without_fabricating_end_meter(
    db_session: Session,
    tenant_records: dict[str, object],
    asset_type: FleetAssetType,
    hour_meter: bool,
    expected_exception: str,
    meter_type: str,
) -> None:
    company = value(tenant_records, "company_a", Company)
    site = add_site(db_session, company, f"Recovery {asset_type.value}")
    asset = add_asset(
        db_session,
        company,
        f"FORCE-{asset_type.value}",
        asset_type=asset_type,
    )
    deployment = deploy(db_session, asset, site)
    assignment = assign(db_session, tenant_records, asset, site)
    duty = add_active_duty(db_session, assignment, hour_meter=hour_meter)
    evidence = add_start_meter_evidence(db_session, duty)
    start_event_id = duty.start_event_id
    started_at = duty.started_at
    operational_date = duty.operational_date
    evidence_id = evidence.id
    db_session.commit()

    owner_membership = value(tenant_records, "owner_a", CompanyMembership)
    owner = client_for(db_session, owner_membership)
    owner.headers["X-Request-ID"] = "owner-force-close-test"
    payload: dict[str, object] = {
        "action": "FORCE_CLOSE_DUTY_AND_DEACTIVATE_ASSET",
        "asset_id": str(asset.id),
        "reason": "  Driver cannot safely complete the stuck duty  ",
    }
    try:
        plan = preview(owner, payload)
        assert plan["can_execute"] is True
        assert plan["allowed_resolutions"] == ["FORCE_CLOSE_DUTY_AND_DEACTIVATE"]
        duty_item = next(
            item
            for item in cast(list[dict[str, object]], plan["dependencies"])
            if item["kind"] == "DUTY"
        )
        assert cast(dict[str, object], duty_item["details"])["started_at"] == (
            started_at.isoformat()
        )

        response = execute(owner, payload, plan)
        assert response.status_code == 200, response.text
        db_session.expire_all()

        persisted_duty = db_session.get(DutySession, duty.id)
        persisted_assignment = db_session.get(Assignment, assignment.id)
        persisted_deployment = db_session.get(AssetSiteDeployment, deployment.id)
        persisted_asset = db_session.get(FleetAsset, asset.id)
        assert persisted_duty is not None
        assert persisted_assignment is not None
        assert persisted_deployment is not None
        assert persisted_asset is not None
        assert persisted_duty.status == DutySessionStatus.CLOSED
        assert persisted_duty.ended_at is not None
        assert persisted_duty.end_event_id is None
        assert persisted_duty.end_km is None
        assert persisted_duty.end_hmr is None
        assert persisted_duty.start_event_id == start_event_id
        assert persisted_duty.started_at == started_at
        assert persisted_assignment.ends_at is not None
        assert persisted_deployment.ends_at is not None
        assert persisted_asset.status == FleetAssetStatus.INACTIVE
        assert db_session.get(OperationalEvent, start_event_id) is not None
        assert db_session.get(EvidenceObject, evidence_id) is not None

        audit = db_session.scalar(
            select(AuditLog)
            .where(
                AuditLog.action == "OWNER_DUTY_FORCE_CLOSED_AND_ASSET_DEACTIVATED",
                AuditLog.entity_id == asset.id,
            )
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        )
        assert audit is not None
        assert audit.company_id == company.id
        assert audit.actor_membership_id == owner_membership.id
        assert audit.request_id == "owner-force-close-test"
        assert audit.reason == "Driver cannot safely complete the stuck duty"
        assert audit.old_values is not None
        assert audit.old_values["asset_id"] == str(asset.id)
        assert audit.old_values["duty_session_id"] == str(duty.id)
        assert audit.old_values["driver_membership_id"] == str(assignment.driver_membership_id)
        assert audit.old_values["site_id"] == str(site.id)
        assert audit.old_values["missing_end_meter"] is True
        assert audit.old_values["missing_end_meter_type"] == meter_type
        assert audit.new_values is not None
        assert audit.new_values["end_event_fabricated"] is False
        assert audit.new_values["end_meter_fabricated"] is False
        assert audit.new_values["history_preserved"] is True
        assert set(cast(list[str], audit.new_values["lifecycle_effects"])) == {
            "DUTY_ADMINISTRATIVELY_CLOSED",
            "ASSIGNMENT_ENDED",
            "DEPLOYMENT_ENDED",
            "ASSET_DEACTIVATED",
        }

        report = owner.get(
            f"/api/v1/reports/sites/{site.id}/daily",
            params={"operational_date": operational_date.isoformat()},
        )
        assert report.status_code == 200, report.text
        report_row = next(
            row for row in report.json()["tippers"] if row["tipper_id"] == str(asset.id)
        )
        assert expected_exception in {item["code"] for item in report_row["exceptions"]}
    finally:
        owner.close()

    driver = client_for(
        db_session,
        value(tenant_records, "driver_a", CompanyMembership),
    )
    try:
        assert driver.get("/api/v1/driver/assignment/current").json() is None
        assert driver.get("/api/v1/driver/duty/current").json()["status"] == "NONE"
    finally:
        driver.close()


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_force_close_requires_a_nonblank_reason(
    db_session: Session,
    tenant_records: dict[str, object],
    reason: str | None,
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    payload: dict[str, object] = {
        "action": "FORCE_CLOSE_DUTY_AND_DEACTIVATE_ASSET",
        "asset_id": str(asset.id),
    }
    if reason is not None:
        payload["reason"] = reason
    owner = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        response = owner.post("/api/v1/owner/operations/preview", json=payload)
        assert response.status_code == 422
        assert "reason is required for administrative duty closure" in response.text
        execute_response = owner.post(
            "/api/v1/owner/operations/execute",
            json={**payload, "state_token": "0" * 64},
        )
        assert execute_response.status_code == 422
        assert "reason is required for administrative duty closure" in execute_response.text
    finally:
        owner.close()


def test_force_close_is_owner_only_and_tenant_scoped(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    local_asset = value(tenant_records, "tipper_a", FleetAsset)
    foreign_asset = value(tenant_records, "tipper_b", FleetAsset)
    reason = "Administrative recovery"
    supervisor = client_for(
        db_session,
        value(tenant_records, "supervisor_a", CompanyMembership),
    )
    try:
        forbidden = supervisor.post(
            "/api/v1/owner/operations/preview",
            json={
                "action": "FORCE_CLOSE_DUTY_AND_DEACTIVATE_ASSET",
                "asset_id": str(local_asset.id),
                "reason": reason,
            },
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["detail"]["code"] == "FORBIDDEN"
        forbidden_execute = supervisor.post(
            "/api/v1/owner/operations/execute",
            json={
                "action": "FORCE_CLOSE_DUTY_AND_DEACTIVATE_ASSET",
                "asset_id": str(local_asset.id),
                "reason": reason,
                "state_token": "0" * 64,
            },
        )
        assert forbidden_execute.status_code == 403
    finally:
        supervisor.close()

    owner = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        missing = owner.post(
            "/api/v1/owner/operations/preview",
            json={
                "action": "FORCE_CLOSE_DUTY_AND_DEACTIVATE_ASSET",
                "asset_id": str(foreign_asset.id),
                "reason": reason,
            },
        )
        assert missing.status_code == 404
        assert missing.json()["detail"]["code"] == "NOT_FOUND"
        missing_execute = owner.post(
            "/api/v1/owner/operations/execute",
            json={
                "action": "FORCE_CLOSE_DUTY_AND_DEACTIVATE_ASSET",
                "asset_id": str(foreign_asset.id),
                "reason": reason,
                "state_token": "0" * 64,
            },
        )
        assert missing_execute.status_code == 404
    finally:
        owner.close()


def test_force_close_rejects_a_stale_preview_if_driver_closes_duty_first(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    site = add_site(db_session, company, "Force Close Race")
    asset = add_asset(db_session, company, "FORCE-RACE")
    deployment = deploy(db_session, asset, site)
    assignment = assign(db_session, tenant_records, asset, site)
    duty = add_active_duty(db_session, assignment)
    db_session.commit()
    payload: dict[str, object] = {
        "action": "FORCE_CLOSE_DUTY_AND_DEACTIVATE_ASSET",
        "asset_id": str(asset.id),
        "reason": "Recover stuck duty",
    }
    owner = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    try:
        plan = preview(owner, payload)
        duty.status = DutySessionStatus.CLOSED
        duty.ended_at = datetime.now(UTC)
        duty.final_overtime_minutes = 0
        db_session.commit()

        response = execute(owner, payload, plan)
        assert response.status_code == 409
        assert response.json()["detail"] == {
            "code": "CONFLICT",
            "message": "State changed. Review the operation again.",
        }
        db_session.expire_all()
        persisted_asset = db_session.get(FleetAsset, asset.id)
        persisted_assignment = db_session.get(Assignment, assignment.id)
        persisted_deployment = db_session.get(AssetSiteDeployment, deployment.id)
        assert persisted_asset is not None
        assert persisted_assignment is not None
        assert persisted_deployment is not None
        assert persisted_asset.status == FleetAssetStatus.ACTIVE
        assert persisted_assignment.ends_at is None
        assert persisted_deployment.ends_at is None
    finally:
        owner.close()


def test_force_close_rolls_back_every_effect_if_final_audit_fails(
    db_session: Session,
    tenant_records: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company = value(tenant_records, "company_a", Company)
    site = add_site(db_session, company, "Force Close Rollback")
    asset = add_asset(db_session, company, "FORCE-ROLLBACK")
    deployment = deploy(db_session, asset, site)
    assignment = assign(db_session, tenant_records, asset, site)
    duty = add_active_duty(db_session, assignment)
    db_session.commit()
    payload: dict[str, object] = {
        "action": "FORCE_CLOSE_DUTY_AND_DEACTIVATE_ASSET",
        "asset_id": str(asset.id),
        "reason": "Recover stuck duty",
    }
    owner = client_for(db_session, value(tenant_records, "owner_a", CompanyMembership))
    plan = preview(owner, payload)

    def fail_final_audit(*args: object, **kwargs: object) -> AuditLog:
        if kwargs.get("action") == "OWNER_DUTY_FORCE_CLOSED_AND_ASSET_DEACTIVATED":
            raise ConflictError("forced audit failure")
        return real_write_audit_log(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(operations_domain, "write_audit_log", fail_final_audit)
    try:
        response = execute(owner, payload, plan)
        assert response.status_code == 409
        assert response.json()["detail"]["message"] == "forced audit failure"
        db_session.expire_all()
        persisted_duty = db_session.get(DutySession, duty.id)
        persisted_assignment = db_session.get(Assignment, assignment.id)
        persisted_deployment = db_session.get(AssetSiteDeployment, deployment.id)
        persisted_asset = db_session.get(FleetAsset, asset.id)
        assert persisted_duty is not None
        assert persisted_assignment is not None
        assert persisted_deployment is not None
        assert persisted_asset is not None
        assert persisted_duty.status == DutySessionStatus.ACTIVE
        assert persisted_duty.ended_at is None
        assert persisted_assignment.ends_at is None
        assert persisted_deployment.ends_at is None
        assert persisted_asset.status == FleetAssetStatus.ACTIVE
        assert (
            db_session.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.action == "OWNER_DUTY_FORCE_CLOSED_AND_ASSET_DEACTIVATED",
                    AuditLog.entity_id == asset.id,
                )
            )
            == 0
        )
    finally:
        owner.close()
