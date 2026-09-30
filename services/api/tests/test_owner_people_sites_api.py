from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_otp_provider
from fleet_api.auth.providers import FakeOtpProvider
from fleet_api.auth.service import AuthService
from fleet_api.core.config import Settings
from fleet_api.db.models import (
    AuditLog,
    CompanyMembership,
    FleetAsset,
    Site,
    User,
)
from fleet_api.db.session import get_db as session_get_db
from fleet_api.domain.assignments import create_assignment
from fleet_api.domain.enums import (
    MembershipRole,
    MembershipStatus,
    SiteStatus,
    UserStatus,
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


def access_token(db: Session, membership: CompanyMembership) -> str:
    user = db.get(User, membership.user_id)
    assert user is not None
    user.phone_number = f"+918{uuid4().int % 1_000_000_000:09d}"
    provider = FakeOtpProvider()
    auth = AuthService(db, settings(), provider)
    challenge = auth.request_otp(phone=user.phone_number)
    pre_session, _ = auth.verify_otp(
        challenge_id=challenge, otp=provider.deliveries[challenge]
    )
    tokens = auth.create_session(
        pre_session_token=pre_session, membership_id=membership.id
    )
    db.commit()
    return tokens.access_token


def owner_client(db: Session, membership: CompanyMembership) -> TestClient:
    app = create_app(settings())

    def override_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[session_get_db] = override_db
    app.dependency_overrides[get_otp_provider] = lambda: FakeOtpProvider()
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {access_token(db, membership)}"
    return client


def test_owner_invites_existing_identity_and_invitee_activates_through_otp(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    owner = value(tenant_records, "owner_a", CompanyMembership)
    existing_user = value(tenant_records, "driver_b", CompanyMembership)
    identity = db_session.get(User, existing_user.user_id)
    assert identity is not None
    original_name = identity.display_name
    identity.phone_number = f"+919{uuid4().int % 1_000_000_000:09d}"
    db_session.flush()
    client = owner_client(db_session, owner)
    try:
        response = client.post(
            "/api/v1/owner/people/invite",
            json={
                "phone": identity.phone_number,
                "display_name": "Alpha Operator",
                "role": "DRIVER",
            },
        )
        assert response.status_code == 201, response.text
        invited_id = response.json()["membership_id"]
        assert response.json()["status"] == "INVITED"
        db_session.refresh(identity)
        assert identity.display_name == original_name

        provider = FakeOtpProvider()
        auth = AuthService(db_session, settings(), provider)
        challenge = auth.request_otp(phone=identity.phone_number)
        pre_session, _ = auth.verify_otp(
            challenge_id=challenge, otp=provider.deliveries[challenge]
        )
        options = auth.list_memberships(pre_session_token=pre_session)
        assert any(str(option[0]) == invited_id for option in options)
        auth.create_session(
            pre_session_token=pre_session,
            membership_id=next(option[0] for option in options if str(option[0]) == invited_id),
        )
        db_session.commit()
        membership = db_session.get(CompanyMembership, invited_id)
        assert membership is not None
        assert membership.status == MembershipStatus.ACTIVE
    finally:
        client.close()


def test_owner_people_crud_duplicate_and_tenant_boundaries(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    client = owner_client(
        db_session, value(tenant_records, "owner_a", CompanyMembership)
    )
    foreign = value(tenant_records, "driver_b", CompanyMembership)
    phone = f"+917{uuid4().int % 1_000_000_000:09d}"
    try:
        created = client.post(
            "/api/v1/owner/people/invite",
            json={"phone": phone, "display_name": "New Driver", "role": "DRIVER"},
        )
        assert created.status_code == 201
        person_id = created.json()["membership_id"]
        assert client.post(
            "/api/v1/owner/people/invite",
            json={
                "phone": phone,
                "display_name": "Duplicate",
                "role": "SUPERVISOR",
            },
        ).status_code == 409
        updated = client.patch(
            f"/api/v1/owner/people/{person_id}",
            json={"display_name": "Edited Driver"},
        )
        assert updated.status_code == 200
        assert updated.json()["display_name"] == "Edited Driver"
        assert client.get(f"/api/v1/owner/people/{foreign.id}").status_code == 404
        inactive = client.post(f"/api/v1/owner/people/{person_id}/deactivate")
        assert inactive.status_code == 200
        assert inactive.json()["status"] == "INACTIVE"
        active = client.post(f"/api/v1/owner/people/{person_id}/reactivate")
        assert active.status_code == 200
        assert active.json()["membership_id"] == person_id
    finally:
        client.close()


def test_owner_site_crud_access_rules_and_audit(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    client = owner_client(
        db_session, value(tenant_records, "owner_a", CompanyMembership)
    )
    supervisor = value(tenant_records, "supervisor_a", CompanyMembership)
    driver = value(tenant_records, "driver_a", CompanyMembership)
    foreign_site = value(tenant_records, "site_b", Site)
    try:
        created = client.post(
            "/api/v1/owner/sites",
            json={
                "name": "Quarry East",
                "code": "qe-1",
                "location_description": "North gate",
                "latitude": "12.971599",
                "longitude": "77.594566",
            },
        )
        assert created.status_code == 201, created.text
        site_id = created.json()["id"]
        assert created.json()["code"] == "QE-1"
        duplicate = client.post(
            "/api/v1/owner/sites", json={"name": "quarry east", "code": "X"}
        )
        assert duplicate.status_code == 409
        assert client.get(f"/api/v1/owner/sites/{foreign_site.id}").status_code == 404
        assert client.post(
            f"/api/v1/owner/sites/{site_id}/supervisors",
            json={"supervisor_membership_id": str(driver.id)},
        ).status_code == 409
        granted = client.post(
            f"/api/v1/owner/sites/{site_id}/supervisors",
            json={"supervisor_membership_id": str(supervisor.id)},
        )
        assert granted.status_code == 200
        assert granted.json()["supervisors"][0]["membership_id"] == str(supervisor.id)
        assert client.post(
            f"/api/v1/owner/sites/{site_id}/supervisors",
            json={"supervisor_membership_id": str(supervisor.id)},
        ).status_code == 409
        revoked = client.delete(
            f"/api/v1/owner/sites/{site_id}/supervisors/{supervisor.id}"
        )
        assert revoked.status_code == 200
        assert revoked.json()["supervisors"] == []
        deactivated = client.post(f"/api/v1/owner/sites/{site_id}/deactivate")
        assert deactivated.status_code == 200
        assert deactivated.json()["status"] == "INACTIVE"
        assert client.post(
            f"/api/v1/owner/sites/{site_id}/supervisors",
            json={"supervisor_membership_id": str(supervisor.id)},
        ).status_code == 409
        assert client.post(f"/api/v1/owner/sites/{site_id}/reactivate").status_code == 200
        actions = set(
            db_session.scalars(
                select(AuditLog.action).where(AuditLog.company_id == supervisor.company_id)
            ).all()
        )
        assert "OWNER_SITE_CREATED" in actions
        assert "OWNER_SUPERVISOR_SITE_GRANTED" in actions
        assert "OWNER_SUPERVISOR_SITE_REVOKED" in actions
    finally:
        client.close()


def test_active_dependencies_block_person_and_site_deactivation(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    owner = value(tenant_records, "owner_a", CompanyMembership)
    driver = value(tenant_records, "driver_a", CompanyMembership)
    supervisor = value(tenant_records, "supervisor_a", CompanyMembership)
    site = value(tenant_records, "site_a", Site)
    create_assignment(
        db_session,
        company_id=owner.company_id,
        driver_membership_id=driver.id,
        supervisor_membership_id=supervisor.id,
        asset_id=value(tenant_records, "tipper_a", FleetAsset).id,
        site_id=site.id,
        starts_at=datetime.now(UTC) - timedelta(minutes=1),
        ends_at=None,
        regular_duty_minutes=600,
    )
    db_session.commit()
    client = owner_client(db_session, owner)
    try:
        assert client.post(f"/api/v1/owner/people/{driver.id}/deactivate").status_code == 409
        assert client.post(f"/api/v1/owner/sites/{site.id}/deactivate").status_code == 409
    finally:
        client.close()


def test_owner_lists_operational_volume_and_non_owner_is_forbidden(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    owner = value(tenant_records, "owner_a", CompanyMembership)
    company_id = owner.company_id
    people: list[object] = []
    for index in range(200):
        user = User(
            phone_number=f"+916{index:09d}",
            display_name=f"Volume Driver {index:03d}",
            status=UserStatus.ACTIVE,
        )
        db_session.add(user)
        db_session.flush()
        people.append(
            CompanyMembership(
                company_id=company_id,
                user_id=user.id,
                display_name=user.display_name,
                role=MembershipRole.DRIVER,
                status=MembershipStatus.ACTIVE,
            )
        )
    db_session.add_all(people)
    db_session.add_all(
        Site(
            company_id=company_id,
            name=f"Volume Site {index:02d}",
            code=f"VS-{index:02d}",
            status=SiteStatus.ACTIVE,
        )
        for index in range(50)
    )
    db_session.commit()
    client = owner_client(db_session, owner)
    forbidden = owner_client(
        db_session, value(tenant_records, "driver_a", CompanyMembership)
    )
    try:
        assert len(client.get("/api/v1/owner/people").json()) >= 203
        assert len(client.get("/api/v1/owner/sites").json()) >= 51
        assert forbidden.get("/api/v1/owner/people").status_code == 403
        assert forbidden.get("/api/v1/owner/sites").status_code == 403
    finally:
        client.close()
        forbidden.close()
