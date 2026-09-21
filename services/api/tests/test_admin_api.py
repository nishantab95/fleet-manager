from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_otp_provider
from fleet_api.auth.providers import FakeOtpProvider
from fleet_api.auth.service import AuthService
from fleet_api.core.config import Settings
from fleet_api.db.models import CompanyMembership, Site, Tipper, User
from fleet_api.db.session import get_db as session_get_db
from fleet_api.domain.enums import MembershipStatus, SiteStatus, TipperStatus
from fleet_api.main import create_app

pytestmark = pytest.mark.postgres


def value[T](records: dict[str, object], key: str, expected_type: type[T]) -> T:
    item = records[key]
    assert isinstance(item, expected_type)
    return item


def user_by_name(db_session: Session, display_name: str) -> User:
    user = db_session.scalar(select(User).where(User.display_name == display_name))
    assert user is not None
    return user


def auth_settings() -> Settings:
    return Settings(
        environment="test",
        phone_default_region="IN",
        jwt_signing_key="test-signing-key-that-is-longer-than-32-characters",
        otp_resend_cooldown_seconds=0,
    )


def session_for_user(
    db_session: Session,
    user: User,
    membership: CompanyMembership,
) -> tuple[str, FakeOtpProvider]:
    user.phone_number = "+919876543210" if user.display_name == "Owner A" else "+919876543211"
    db_session.flush()
    provider = FakeOtpProvider()
    service = AuthService(db_session, auth_settings(), provider)
    challenge_id = service.request_otp(phone=user.phone_number)
    pre_session, _ = service.verify_otp(
        challenge_id=challenge_id,
        otp=provider.deliveries[challenge_id],
    )
    tokens = service.create_session(pre_session_token=pre_session, membership_id=membership.id)
    db_session.commit()
    return tokens.access_token, provider


def admin_app(db_session: Session, access_token: str) -> TestClient:
    app = create_app(auth_settings())

    def override_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[session_get_db] = override_db
    app.dependency_overrides[get_otp_provider] = lambda: FakeOtpProvider()
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {access_token}"})
    return client


def test_owner_admin_management_is_tenant_scoped_and_uses_domain_rules(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    owner = user_by_name(db_session, "Owner A")
    owner_membership = value(tenant_records, "owner_a", CompanyMembership)
    driver_membership = value(tenant_records, "driver_a", CompanyMembership)
    supervisor_membership = value(tenant_records, "supervisor_a", CompanyMembership)
    site_a = value(tenant_records, "site_a", Site)
    site_b = value(tenant_records, "site_b", Site)
    tipper_a = value(tenant_records, "tipper_a", Tipper)
    access_token, _ = session_for_user(db_session, owner, owner_membership)
    client = admin_app(db_session, access_token)
    try:
        created_site = client.post(
            "/api/v1/admin/sites",
            json={"name": "New Alpha Site", "code": "NEW-A"},
        )
        assert created_site.status_code == 201
        new_site_id = created_site.json()["id"]
        assert (
            client.patch(
                f"/api/v1/admin/sites/{new_site_id}",
                json={"status": "INACTIVE"},
            ).json()["status"]
            == SiteStatus.INACTIVE
        )
        assert client.get(f"/api/v1/admin/sites/{site_b.id}").status_code == 404

        created_tipper = client.post(
            "/api/v1/admin/tippers",
            json={"registration_number": "ka-09 cd 1234", "short_name": "New One"},
        )
        assert created_tipper.status_code == 201
        new_tipper_id = created_tipper.json()["id"]
        assert (
            client.patch(
                f"/api/v1/admin/tippers/{new_tipper_id}",
                json={"status": "INACTIVE"},
            ).json()["status"]
            == TipperStatus.INACTIVE
        )

        created_person = client.post(
            "/api/v1/admin/people",
            json={
                "phone": "+919876543299",
                "display_name": "New Driver",
                "role": "DRIVER",
            },
        )
        assert created_person.status_code == 201
        new_membership_id = created_person.json()["membership_id"]
        updated_person = client.patch(
            f"/api/v1/admin/people/{new_membership_id}",
            json={"status": "INACTIVE"},
        )
        assert updated_person.status_code == 200
        assert updated_person.json()["status"] == MembershipStatus.INACTIVE
        assert (
            client.post(
                "/api/v1/admin/people",
                json={
                    "phone": "+919876543299",
                    "display_name": "Duplicate Driver",
                    "role": "DRIVER",
                },
            ).status_code
            == 409
        )

        granted = client.post(
            "/api/v1/admin/supervisor-site-access",
            json={
                "supervisor_membership_id": str(supervisor_membership.id),
                "site_id": str(site_a.id),
            },
        )
        assert granted.status_code == 201
        access_id = granted.json()["id"]
        assert (
            client.post(
                "/api/v1/admin/supervisor-site-access",
                json={
                    "supervisor_membership_id": str(supervisor_membership.id),
                    "site_id": str(site_a.id),
                },
            ).status_code
            == 409
        )
        assert client.delete(f"/api/v1/admin/supervisor-site-access/{access_id}").status_code == 204

        starts_at = datetime.now(UTC) + timedelta(days=1)
        created_assignment = client.post(
            "/api/v1/admin/assignments",
            json={
                "driver_membership_id": str(driver_membership.id),
                "supervisor_membership_id": str(supervisor_membership.id),
                "tipper_id": str(tipper_a.id),
                "site_id": str(site_a.id),
                "starts_at": starts_at.isoformat(),
            },
        )
        assert created_assignment.status_code == 201
        assignment_id = created_assignment.json()["id"]
        assert client.get("/api/v1/admin/assignments").json()[0]["id"] == assignment_id
        closed = client.post(
            f"/api/v1/admin/assignments/{assignment_id}/close",
            json={"ends_at": (starts_at + timedelta(days=1)).isoformat()},
        )
        assert closed.status_code == 200
        assert closed.json()["ends_at"] is not None
    finally:
        client.close()


def test_admin_routes_reject_non_owner_and_foreign_assignment_inputs(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    supervisor = user_by_name(db_session, "Supervisor A")
    supervisor_membership = value(tenant_records, "supervisor_a", CompanyMembership)
    foreign_tipper = value(tenant_records, "tipper_b", Tipper)
    site_a = value(tenant_records, "site_a", Site)
    access_token, _ = session_for_user(db_session, supervisor, supervisor_membership)
    client = admin_app(db_session, access_token)
    try:
        forbidden = client.get("/api/v1/admin/sites")
        assert forbidden.status_code == 403
        owner = user_by_name(db_session, "Owner A")
        owner_membership = value(tenant_records, "owner_a", CompanyMembership)
        owner_token, _ = session_for_user(db_session, owner, owner_membership)
        client.headers.update({"Authorization": f"Bearer {owner_token}"})
        driver = value(tenant_records, "driver_a", CompanyMembership)
        supervisor_membership = value(tenant_records, "supervisor_a", CompanyMembership)
        response = client.post(
            "/api/v1/admin/assignments",
            json={
                "driver_membership_id": str(driver.id),
                "supervisor_membership_id": str(supervisor_membership.id),
                "tipper_id": str(foreign_tipper.id),
                "site_id": str(site_a.id),
                "starts_at": datetime.now(UTC).isoformat(),
            },
        )
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "NOT_FOUND"
    finally:
        client.close()
