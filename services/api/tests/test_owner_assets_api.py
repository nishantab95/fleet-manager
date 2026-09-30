from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_otp_provider
from fleet_api.auth.providers import FakeOtpProvider
from fleet_api.auth.service import AuthService
from fleet_api.core.config import Settings
from fleet_api.db.models import (
    Assignment,
    Company,
    CompanyMembership,
    FleetAsset,
    Site,
    User,
)
from fleet_api.db.session import get_db as session_get_db
from fleet_api.domain.assignments import create_assignment
from fleet_api.domain.enums import FleetAssetStatus
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


def access_token(db_session: Session, membership: CompanyMembership) -> str:
    user = db_session.get(User, membership.user_id)
    assert user is not None
    user.phone_number = f"+919{uuid4().int % 1_000_000_000:09d}"
    db_session.flush()
    provider = FakeOtpProvider()
    auth = AuthService(db_session, settings(), provider)
    challenge_id = auth.request_otp(phone=user.phone_number)
    pre_session, _ = auth.verify_otp(
        challenge_id=challenge_id,
        otp=provider.deliveries[challenge_id],
    )
    tokens = auth.create_session(
        pre_session_token=pre_session,
        membership_id=membership.id,
    )
    db_session.commit()
    return tokens.access_token


def owner_client(db_session: Session, membership: CompanyMembership) -> TestClient:
    app = create_app(settings())

    def override_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[session_get_db] = override_db
    app.dependency_overrides[get_otp_provider] = lambda: FakeOtpProvider()
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {access_token(db_session, membership)}"
    return client


def owned_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "asset_code": "TIPPER-44",
        "asset_type": "TIPPER",
        "ownership_type": "OWNED",
        "registration_number": "ka-04 aa 4444",
        "short_name": "Tipper 44",
        "manufacturer": "Tata",
        "model": "Prima",
    }
    payload.update(overrides)
    return payload


def create_owned(client: TestClient, **overrides: object) -> dict[str, object]:
    response = client.post("/api/v1/owner/assets", json=owned_payload(**overrides))
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json())


def test_owner_lists_assets_with_filters_and_active_assignment(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    company = value(tenant_records, "company_a", Company)
    asset = value(tenant_records, "tipper_a", FleetAsset)
    driver = value(tenant_records, "driver_a", CompanyMembership)
    supervisor = value(tenant_records, "supervisor_a", CompanyMembership)
    site = value(tenant_records, "site_a", Site)
    create_assignment(
        db_session,
        company_id=company.id,
        driver_membership_id=driver.id,
        supervisor_membership_id=supervisor.id,
        asset_id=asset.id,
        site_id=site.id,
        starts_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db_session.commit()
    client = owner_client(
        db_session, value(tenant_records, "owner_a", CompanyMembership)
    )
    try:
        response = client.get(
            "/api/v1/owner/assets",
            params={
                "status": "ACTIVE",
                "ownership_type": "OWNED",
                "asset_type": "TIPPER",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body] == [str(asset.id)]
        assert body[0]["asset_code"] == "ALPHA-ONE"
        assert body[0]["has_active_assignment"] is True
        assert body[0]["active_assignment"]["site_name"] == "Alpha Site"
        assert body[0]["active_assignment"]["driver_name"] == "Driver A"
    finally:
        client.close()


def test_owner_creates_owned_tipper(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    client = owner_client(
        db_session, value(tenant_records, "owner_a", CompanyMembership)
    )
    try:
        asset = create_owned(client)
        assert asset["asset_code"] == "TIPPER-44"
        assert asset["registration_number"] == "KA04AA4444"
        assert asset["ownership_type"] == "OWNED"
        assert asset["rental_party_name"] is None
    finally:
        client.close()


@pytest.mark.parametrize(
    "asset_type",
    ["EXCAVATOR", "BACKHOE_LOADER", "ROLLER", "GRADER"],
)
def test_owner_creates_machinery_without_registration(
    db_session: Session,
    tenant_records: dict[str, object],
    asset_type: str,
) -> None:
    client = owner_client(
        db_session, value(tenant_records, "owner_a", CompanyMembership)
    )
    try:
        response = client.post(
            "/api/v1/owner/assets",
            json=owned_payload(
                asset_code=f"{asset_type}-01",
                asset_type=asset_type,
                registration_number=None,
                short_name=f"{asset_type} machine",
            ),
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["asset_type"] == asset_type
        assert body["registration_number"] is None
    finally:
        client.close()


def test_owner_creates_rented_tipper(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    client = owner_client(
        db_session, value(tenant_records, "owner_a", CompanyMembership)
    )
    try:
        response = client.post(
            "/api/v1/owner/assets",
            json=owned_payload(
                ownership_type="RENTED",
                rental_party_name="ABC Transport",
                rental_start_date="2026-09-01",
                rental_end_date="2026-12-31",
            ),
        )
        assert response.status_code == 201, response.text
        assert response.json()["rental_party_name"] == "ABC Transport"
        missing_party = client.post(
            "/api/v1/owner/assets",
            json=owned_payload(
                asset_code="TIPPER-45",
                registration_number="KA04AA4445",
                ownership_type="RENTED",
            ),
        )
        assert missing_party.status_code == 422
    finally:
        client.close()


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"asset_code": "alpha-one"}, "asset code"),
        ({"registration_number": "ka-01 ab 1234"}, "registration number"),
    ],
)
def test_owner_rejects_duplicate_company_identity(
    db_session: Session,
    tenant_records: dict[str, object],
    override: dict[str, object],
    message: str,
) -> None:
    client = owner_client(
        db_session, value(tenant_records, "owner_a", CompanyMembership)
    )
    try:
        response = client.post("/api/v1/owner/assets", json=owned_payload(**override))
        assert response.status_code == 409
        assert message in response.json()["detail"]["message"].lower()
    finally:
        client.close()


def test_owner_rejects_testown02_case_duplicate_without_creating_asset(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    client = owner_client(
        db_session, value(tenant_records, "owner_a", CompanyMembership)
    )
    try:
        existing = create_owned(
            client,
            asset_code="EXISTING-OWN-02",
            registration_number="TESTOWN02",
            short_name="Existing owned tipper",
        )
        before_ids = {item["id"] for item in client.get("/api/v1/owner/assets").json()}

        response = client.post(
            "/api/v1/owner/assets",
            json=owned_payload(
                asset_code="newcode99",
                registration_number="testown02",
                short_name="owned tipper two",
            ),
        )

        assert response.status_code == 409
        assert response.json()["detail"]["message"] == (
            "registration number is already used by this company"
        )
        after_ids = {item["id"] for item in client.get("/api/v1/owner/assets").json()}
        assert after_ids == before_ids
        assert str(existing["id"]) in after_ids
    finally:
        client.close()


def test_owner_edits_asset_without_recreating_it_or_history(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    assignment = create_assignment(
        db_session,
        company_id=asset.company_id,
        driver_membership_id=value(
            tenant_records, "driver_a", CompanyMembership
        ).id,
        supervisor_membership_id=value(
            tenant_records, "supervisor_a", CompanyMembership
        ).id,
        asset_id=asset.id,
        site_id=value(tenant_records, "site_a", Site).id,
        starts_at=datetime.now(UTC) - timedelta(days=2),
        ends_at=datetime.now(UTC) - timedelta(days=1),
    )
    asset_id = asset.id
    assignment_id = assignment.id
    db_session.commit()
    client = owner_client(
        db_session, value(tenant_records, "owner_a", CompanyMembership)
    )
    try:
        response = client.patch(
            f"/api/v1/owner/assets/{asset_id}",
            json={
                "asset_code": "ALPHA-RENAMED",
                "registration_number": "KA01AB9999",
                "short_name": "Renamed Tipper",
                "manufacturer": "Ashok Leyland",
                "model": "AVTR",
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["id"] == str(asset_id)
        assert response.json()["registration_number"] == "KA01AB9999"
        db_session.expire_all()
        preserved = db_session.get(Assignment, assignment_id)
        assert preserved is not None
        assert preserved.asset_id == asset_id
    finally:
        client.close()


def test_owner_changes_owned_to_rented_and_requires_party(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    client = owner_client(
        db_session, value(tenant_records, "owner_a", CompanyMembership)
    )
    try:
        missing = client.patch(
            f"/api/v1/owner/assets/{asset.id}",
            json={"ownership_type": "RENTED"},
        )
        assert missing.status_code == 422
        response = client.patch(
            f"/api/v1/owner/assets/{asset.id}",
            json={
                "ownership_type": "RENTED",
                "rental_party_name": "Rental Partner",
                "rental_start_date": "2026-09-01",
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["ownership_type"] == "RENTED"
        assert response.json()["rental_party_name"] == "Rental Partner"
    finally:
        client.close()


def test_owner_changes_rented_to_owned_and_clears_rental_fields(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    client = owner_client(
        db_session, value(tenant_records, "owner_a", CompanyMembership)
    )
    try:
        rented = client.post(
            "/api/v1/owner/assets",
            json=owned_payload(
                ownership_type="RENTED",
                rental_party_name="Rental Partner",
                rental_start_date="2026-09-01",
                rental_end_date="2026-12-01",
            ),
        ).json()
        response = client.patch(
            f"/api/v1/owner/assets/{rented['id']}",
            json={"ownership_type": "OWNED"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["ownership_type"] == "OWNED"
        assert body["rental_party_name"] is None
        assert body["rental_start_date"] is None
        assert body["rental_end_date"] is None
    finally:
        client.close()


def test_owner_deactivates_and_reactivates_unassigned_asset(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    client = owner_client(
        db_session, value(tenant_records, "owner_a", CompanyMembership)
    )
    try:
        asset = create_owned(client)
        deactivate = client.post(
            f"/api/v1/owner/assets/{asset['id']}/deactivate"
        )
        assert deactivate.status_code == 200
        assert deactivate.json()["status"] == FleetAssetStatus.INACTIVE
        reactivate = client.post(
            f"/api/v1/owner/assets/{asset['id']}/reactivate"
        )
        assert reactivate.status_code == 200
        assert reactivate.json()["status"] == FleetAssetStatus.ACTIVE
    finally:
        client.close()


def test_owner_cannot_deactivate_effectively_assigned_asset(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    create_assignment(
        db_session,
        company_id=asset.company_id,
        driver_membership_id=value(
            tenant_records, "driver_a", CompanyMembership
        ).id,
        supervisor_membership_id=value(
            tenant_records, "supervisor_a", CompanyMembership
        ).id,
        asset_id=asset.id,
        site_id=value(tenant_records, "site_a", Site).id,
        starts_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db_session.commit()
    client = owner_client(
        db_session, value(tenant_records, "owner_a", CompanyMembership)
    )
    try:
        response = client.post(f"/api/v1/owner/assets/{asset.id}/deactivate")
        assert response.status_code == 409
        assert response.json()["detail"]["message"] == (
            "Asset cannot be deactivated while it has an active assignment."
        )
        db_session.refresh(asset)
        assert asset.status == FleetAssetStatus.ACTIVE
    finally:
        client.close()


@pytest.mark.parametrize("membership_key", ["driver_a", "supervisor_a"])
def test_driver_and_supervisor_cannot_call_owner_asset_api(
    db_session: Session,
    tenant_records: dict[str, object],
    membership_key: str,
) -> None:
    client = owner_client(
        db_session, value(tenant_records, membership_key, CompanyMembership)
    )
    try:
        assert client.get("/api/v1/owner/assets").status_code == 403
        assert client.post("/api/v1/owner/assets", json=owned_payload()).status_code == 403
    finally:
        client.close()


def test_owner_cannot_read_edit_or_deactivate_foreign_asset(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    foreign = value(tenant_records, "tipper_b", FleetAsset)
    client = owner_client(
        db_session, value(tenant_records, "owner_a", CompanyMembership)
    )
    try:
        assert client.get(f"/api/v1/owner/assets/{foreign.id}").status_code == 404
        assert (
            client.patch(
                f"/api/v1/owner/assets/{foreign.id}",
                json={"short_name": "Forbidden"},
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/v1/owner/assets/{foreign.id}/deactivate"
            ).status_code
            == 404
        )
    finally:
        client.close()


def test_owned_creation_rejects_stale_rental_values(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    client = owner_client(
        db_session, value(tenant_records, "owner_a", CompanyMembership)
    )
    try:
        response = client.post(
            "/api/v1/owner/assets",
            json=owned_payload(rental_party_name="Should not persist"),
        )
        assert response.status_code == 422
        assert "cannot contain rental details" in response.json()["detail"][
            "message"
        ].lower()
    finally:
        client.close()
