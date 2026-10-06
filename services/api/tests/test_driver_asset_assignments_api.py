from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from fleet_api.db.models import (
    Assignment,
    AuditLog,
    Company,
    CompanyMembership,
    FleetAsset,
    Site,
    SupervisorSiteAccess,
    User,
)
from fleet_api.domain.enums import (
    DutySessionStatus,
    FleetAssetStatus,
    FleetAssetType,
    MembershipRole,
    MembershipStatus,
    SiteStatus,
    UserStatus,
)
from fleet_api.domain.errors import AssignmentNotEffectiveError
from fleet_api.domain.events import create_trip_event
from test_asset_site_deployments_api import (
    add_active_duty,
    add_asset,
    add_site,
    client_for,
    deploy,
    value,
)
from test_driver_api import driver_app, session_for_user, user_by_name

pytestmark = pytest.mark.postgres


def test_owner_assignment_lifecycle_updates_people_driver_and_audit(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    owner = value(tenant_records, "owner_a", CompanyMembership)
    site = value(tenant_records, "site_a", Site)
    asset = value(tenant_records, "tipper_a", FleetAsset)
    driver_a = value(tenant_records, "driver_a", CompanyMembership)
    driver_a2 = value(tenant_records, "driver_a2", CompanyMembership)
    owner_client = client_for(db_session, owner)
    try:
        deployment = deploy(owner_client, asset, site)
        eligible = owner_client.get(f"/api/v1/owner/assets/{asset.id}/eligible-drivers")
        assert eligible.status_code == 200
        assert {row["membership_id"] for row in eligible.json()} >= {
            str(driver_a.id),
            str(driver_a2.id),
        }

        assigned = owner_client.post(
            f"/api/v1/owner/assets/{asset.id}/assignment",
            json={"driver_membership_id": str(driver_a.id)},
        )
        assert assigned.status_code == 201, assigned.text
        assert assigned.json()["asset_site_deployment_id"] == deployment["id"]
        assert assigned.json()["site_id"] == str(site.id)
        assert (
            db_session.scalar(
                select(Assignment.supervisor_membership_id).where(
                    Assignment.id == assigned.json()["assignment_id"]
                )
            )
            is None
        )

        people = owner_client.get("/api/v1/owner/people").json()
        driver_person = next(row for row in people if row["membership_id"] == str(driver_a.id))
        assert driver_person["current_asset_code"] == asset.asset_code
        assert driver_person["current_site_name"] == site.name

        driver_client = driver_app(
            db_session,
            session_for_user(
                db_session,
                user_by_name(db_session, "Driver A"),
                driver_a,
            ),
        )
        try:
            current = driver_client.get("/api/v1/driver/assignment/current")
            assert current.status_code == 200
            assert current.json()["assignment_id"] == assigned.json()["assignment_id"]
        finally:
            driver_client.close()

        reassigned = owner_client.post(
            f"/api/v1/owner/assets/{asset.id}/assignment/reassign",
            json={"driver_membership_id": str(driver_a2.id)},
        )
        assert reassigned.status_code == 200, reassigned.text
        assert reassigned.json()["driver_membership_id"] == str(driver_a2.id)
        history = owner_client.get(f"/api/v1/owner/assets/{asset.id}/assignments")
        assert history.status_code == 200
        assert len(history.json()) == 2
        assert sum(row["ends_at"] is None for row in history.json()) == 1

        unassigned = owner_client.delete(f"/api/v1/owner/assets/{asset.id}/assignment")
        assert unassigned.status_code == 200
        assert unassigned.json()["ends_at"] is not None
        assert owner_client.get(f"/api/v1/owner/assets/{asset.id}/assignment").status_code == 204

        actions = set(
            db_session.scalars(
                select(AuditLog.action).where(AuditLog.company_id == company.id)
            ).all()
        )
        assert {
            "DRIVER_ASSIGNED_TO_ASSET",
            "DRIVER_REASSIGNED_ON_ASSET",
            "DRIVER_UNASSIGNED_FROM_ASSET",
        } <= actions
    finally:
        owner_client.close()


def test_invited_driver_is_eligible_and_assignable_before_first_login(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    owner = value(tenant_records, "owner_a", CompanyMembership)
    site = value(tenant_records, "site_a", Site)
    asset = value(tenant_records, "tipper_a", FleetAsset)
    user = User(
        phone_number=f"+916{uuid4().int % 1_000_000_000:09d}",
        display_name="Invited Operator",
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    db_session.flush()
    invited = CompanyMembership(
        company_id=company.id,
        user_id=user.id,
        display_name="Invited Operator",
        role=MembershipRole.DRIVER,
        status=MembershipStatus.INVITED,
    )
    db_session.add(invited)
    db_session.commit()

    owner_client = client_for(db_session, owner)
    try:
        deploy(owner_client, asset, site)
        eligible = owner_client.get(f"/api/v1/owner/assets/{asset.id}/eligible-drivers")
        assert eligible.status_code == 200
        candidate = next(row for row in eligible.json() if row["membership_id"] == str(invited.id))
        assert candidate == {
            "membership_id": str(invited.id),
            "display_name": "Invited Operator",
            "phone": user.phone_number,
            "status": "INVITED",
        }

        assigned = owner_client.post(
            f"/api/v1/owner/assets/{asset.id}/assignment",
            json={"driver_membership_id": str(invited.id)},
        )
        assert assigned.status_code == 201, assigned.text
        db_session.refresh(invited)
        assert invited.status == MembershipStatus.INVITED
    finally:
        owner_client.close()


def test_supervisor_authorization_multi_supervisor_and_eligibility_guards(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    owner = value(tenant_records, "owner_a", CompanyMembership)
    supervisor = value(tenant_records, "supervisor_a", CompanyMembership)
    driver = value(tenant_records, "driver_a", CompanyMembership)
    site = value(tenant_records, "site_a", Site)
    unauthorized_site = add_site(db_session, company, name="Unauthorized Assignment Site")
    asset = value(tenant_records, "tipper_a", FleetAsset)
    second_asset = add_asset(db_session, company, code="SECOND-TIPPER")
    second_supervisor_user = User(
        phone_number=f"+917{uuid4().int % 1_000_000_000:09d}",
        display_name="Second Site Supervisor",
        status=UserStatus.ACTIVE,
    )
    db_session.add(second_supervisor_user)
    db_session.flush()
    second_supervisor = CompanyMembership(
        company_id=company.id,
        user_id=second_supervisor_user.id,
        display_name="Second Site Supervisor",
        role=MembershipRole.SUPERVISOR,
        status=MembershipStatus.ACTIVE,
    )
    db_session.add(second_supervisor)
    db_session.flush()
    db_session.add_all(
        [
            SupervisorSiteAccess(
                company_id=company.id,
                supervisor_membership_id=supervisor.id,
                site_id=site.id,
            ),
            SupervisorSiteAccess(
                company_id=company.id,
                supervisor_membership_id=second_supervisor.id,
                site_id=site.id,
            ),
        ]
    )
    db_session.commit()
    owner_client = client_for(db_session, owner)
    try:
        deploy(owner_client, asset, site)
        deploy(owner_client, second_asset, site)
    finally:
        owner_client.close()

    supervisor_client = client_for(db_session, supervisor)
    try:
        assigned = supervisor_client.post(
            f"/api/v1/supervisor/sites/{site.id}/assets/{asset.id}/assignment",
            json={"driver_membership_id": str(driver.id)},
        )
        assert assigned.status_code == 201, assigned.text
        eligible = supervisor_client.get(
            f"/api/v1/supervisor/sites/{site.id}/assets/{second_asset.id}/eligible-drivers"
        )
        assert eligible.status_code == 200
        assert str(driver.id) not in {row["membership_id"] for row in eligible.json()}
        assert (
            supervisor_client.get(
                f"/api/v1/supervisor/sites/{unauthorized_site.id}/assets/"
                f"{asset.id}/eligible-drivers"
            ).status_code
            == 403
        )
    finally:
        supervisor_client.close()

    driver_client = driver_app(
        db_session,
        session_for_user(
            db_session,
            user_by_name(db_session, "Driver A"),
            driver,
        ),
    )
    try:
        current = driver_client.get("/api/v1/driver/assignment/current").json()
        assert current["supervisor_name"] is None
        assert current["supervisor_names"] == [
            "Second Site Supervisor",
            "Supervisor A",
        ]
        assert (
            driver_client.post(
                f"/api/v1/owner/assets/{second_asset.id}/assignment",
                json={"driver_membership_id": str(driver.id)},
            ).status_code
            == 403
        )
    finally:
        driver_client.close()

    second_supervisor_client = client_for(db_session, second_supervisor)
    try:
        reassigned = second_supervisor_client.post(
            f"/api/v1/supervisor/sites/{site.id}/assets/{asset.id}/assignment/reassign",
            json={
                "driver_membership_id": str(
                    value(tenant_records, "driver_a2", CompanyMembership).id
                )
            },
        )
        assert reassigned.status_code == 200, reassigned.text
        audit = db_session.scalar(
            select(AuditLog)
            .where(
                AuditLog.company_id == company.id,
                AuditLog.action == "DRIVER_REASSIGNED_ON_ASSET",
            )
            .order_by(AuditLog.created_at.desc())
        )
        assert audit is not None
        assert audit.actor_membership_id == second_supervisor.id
    finally:
        second_supervisor_client.close()


def test_assignment_rejects_ineligible_cross_company_and_conflicting_records(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    owner = value(tenant_records, "owner_a", CompanyMembership)
    site = value(tenant_records, "site_a", Site)
    driver = value(tenant_records, "driver_a", CompanyMembership)
    other_driver = value(tenant_records, "driver_a2", CompanyMembership)
    foreign_driver = value(tenant_records, "driver_b", CompanyMembership)
    undeployed = add_asset(db_session, company, code="UNDEPLOYED-A")
    inactive_asset = add_asset(db_session, company, code="INACTIVE-A")
    machinery = add_asset(
        db_session,
        company,
        code="EXCAVATOR-A",
        asset_type=FleetAssetType.EXCAVATOR,
    )
    inactive_site_asset = add_asset(db_session, company, code="INACTIVE-SITE-A")
    inactive_site = add_site(db_session, company, name="Inactive Assignment Site")
    assigned_asset = add_asset(db_session, company, code="ASSIGNED-A")
    second_asset = add_asset(db_session, company, code="SECOND-A")
    db_session.commit()
    client = client_for(db_session, owner)
    try:
        assert (
            client.post(
                f"/api/v1/owner/assets/{undeployed.id}/assignment",
                json={"driver_membership_id": str(driver.id)},
            ).status_code
            == 409
        )

        deploy(client, inactive_asset, site)
        inactive_asset.status = FleetAssetStatus.INACTIVE
        db_session.commit()
        assert (
            client.post(
                f"/api/v1/owner/assets/{inactive_asset.id}/assignment",
                json={"driver_membership_id": str(driver.id)},
            ).status_code
            == 409
        )

        deploy(client, machinery, site)
        machinery_assignment = client.post(
            f"/api/v1/owner/assets/{machinery.id}/assignment",
            json={"driver_membership_id": str(other_driver.id)},
        )
        assert machinery_assignment.status_code == 201
        assert machinery_assignment.json()["asset_code"] == "EXCAVATOR-A"

        deploy(client, inactive_site_asset, inactive_site)
        inactive_site.status = SiteStatus.INACTIVE
        db_session.commit()
        assert (
            client.post(
                f"/api/v1/owner/assets/{inactive_site_asset.id}/assignment",
                json={"driver_membership_id": str(driver.id)},
            ).status_code
            == 409
        )

        deploy(client, assigned_asset, site)
        driver.status = MembershipStatus.INACTIVE
        db_session.commit()
        assert (
            client.post(
                f"/api/v1/owner/assets/{assigned_asset.id}/assignment",
                json={"driver_membership_id": str(driver.id)},
            ).status_code
            == 409
        )
        driver.status = MembershipStatus.ACTIVE
        db_session.commit()

        assert (
            client.post(
                f"/api/v1/owner/assets/{assigned_asset.id}/assignment",
                json={"driver_membership_id": str(foreign_driver.id)},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/owner/assets/"
                f"{value(tenant_records, 'tipper_b', FleetAsset).id}/assignment",
                json={"driver_membership_id": str(driver.id)},
            ).status_code
            == 404
        )

        assigned = client.post(
            f"/api/v1/owner/assets/{assigned_asset.id}/assignment",
            json={"driver_membership_id": str(driver.id)},
        )
        assert assigned.status_code == 201, assigned.text
        assert (
            client.post(
                f"/api/v1/owner/assets/{assigned_asset.id}/assignment",
                json={"driver_membership_id": str(other_driver.id)},
            ).status_code
            == 409
        )

        deploy(client, second_asset, site)
        assert (
            client.post(
                f"/api/v1/owner/assets/{second_asset.id}/assignment",
                json={"driver_membership_id": str(driver.id)},
            ).status_code
            == 409
        )
    finally:
        client.close()


def test_active_duty_blocks_change_and_closed_assignment_keeps_event_boundary(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    owner = value(tenant_records, "owner_a", CompanyMembership)
    driver = value(tenant_records, "driver_a", CompanyMembership)
    driver_a2 = value(tenant_records, "driver_a2", CompanyMembership)
    site = value(tenant_records, "site_a", Site)
    asset = value(tenant_records, "tipper_a", FleetAsset)
    client = client_for(db_session, owner)
    try:
        deploy(client, asset, site)
        created = client.post(
            f"/api/v1/owner/assets/{asset.id}/assignment",
            json={"driver_membership_id": str(driver.id)},
        )
        assignment = db_session.get(Assignment, created.json()["assignment_id"])
        assert assignment is not None
        duty = add_active_duty(db_session, assignment)
        db_session.commit()
        blocked = client.post(
            f"/api/v1/owner/assets/{asset.id}/assignment/reassign",
            json={"driver_membership_id": str(driver_a2.id)},
        )
        assert blocked.status_code == 409
        assert "end the active duty" in blocked.json()["detail"]["message"]
        blocked_unassign = client.delete(f"/api/v1/owner/assets/{asset.id}/assignment")
        assert blocked_unassign.status_code == 409
        assert "end the active duty" in blocked_unassign.json()["detail"]["message"]
        duty.status = DutySessionStatus.CLOSED
        duty.ended_at = datetime.now(UTC)
        db_session.commit()
        closed = client.delete(f"/api/v1/owner/assets/{asset.id}/assignment")
        assert closed.status_code == 200
        db_session.refresh(assignment)
        assert assignment.ends_at is not None
        before_end = assignment.ends_at - timedelta(microseconds=1)
        create_trip_event(
            db_session,
            company_id=assignment.company_id,
            assignment_id=assignment.id,
            client_event_uuid=uuid4(),
            device_created_at=before_end,
        )
        with pytest.raises(AssignmentNotEffectiveError):
            create_trip_event(
                db_session,
                company_id=assignment.company_id,
                assignment_id=assignment.id,
                client_event_uuid=uuid4(),
                device_created_at=assignment.ends_at,
            )
    finally:
        client.close()
