from __future__ import annotations

import base64
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_object_storage, get_otp_provider
from fleet_api.auth.providers import FakeOtpProvider
from fleet_api.auth.service import AuthService
from fleet_api.core.config import Settings
from fleet_api.db.models import (
    Assignment,
    Company,
    CompanyMembership,
    Site,
    SupervisorSiteAccess,
    Tipper,
    User,
)
from fleet_api.db.session import get_db as session_get_db
from fleet_api.main import create_app

pytestmark = pytest.mark.postgres


class SupervisorStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put_private(self, *, object_key: str, content: bytes, content_type: str) -> str:
        self.objects[object_key] = (content, content_type)
        return object_key

    def delete_private(self, *, object_key: str) -> None:
        self.objects.pop(object_key, None)

    def read_private(self, *, object_key: str) -> tuple[bytes, str]:
        return self.objects[object_key]


COLORFUL_JPEG_BYTES = base64.b64decode(
    "/9j/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBT/wAARCAAoACgDASIAAhEBAxEB/8QAGQABAAMBAQAAAAAAAAAAAAAAAAcICQYK/8QALRABAAABBRADAAAAAAAAAAAAABEIExdhpAIFCRQVGEVHZWaEhcPE4uMWI0L/xAAZAQACAwEAAAAAAAAAAAAAAAAFCQYHCAr/xAA1EQAAAwQDCw0AAAAAAAAAAAAAAQIDBQYRBBIhBwgTFzdUgaOytNMVIjEyNDVTVYOEodHS/9oADAMBAAIRAxEAPwCugCjA1MTHJ50/w/UTGhyTzp/h+omNVr67e00bJBFd8tlWe/obsxAAEGYxn3Srsu0eJSrsu0eLgA8HElAHl2tb8QNIxvxvn+rY8MXzkE3lpl+dfdkfJuI/mfnJzGK7mEJuuMaltc3XeCxexV7BNa1OVd40GJsvgWLOE7pT0czmLBUdlgaqetKtR2SztXWUc1KM7TPpkVkiEJeMMumOaUuIYhY4altpV11lInUIkJ5qFJSUkpSViSnKZzMzMQ1m67wWL2CZRnnlx4eJ8J+gNxWwhmWsa/sefIB1FgINB8E1rU5V3jQYCAb6PK8+vb7qwFqOTu9np2jABlUHB//Z"
)


def auth_settings() -> Settings:
    return Settings(
        environment="test",
        phone_default_region="IN",
        jwt_signing_key="test-signing-key-that-is-longer-than-32-characters",
        otp_resend_cooldown_seconds=0,
    )


def value[T](records: dict[str, object], key: str, expected_type: type[T]) -> T:
    item = records[key]
    assert isinstance(item, expected_type)
    return item


def user_by_name(db_session: Session, display_name: str) -> User:
    user = db_session.scalar(select(User).where(User.display_name == display_name))
    assert user is not None
    return user


def access_token(db_session: Session, user: User, membership: CompanyMembership) -> str:
    phone_by_name = {
        "Driver A": "+919876543210",
        "Supervisor A": "+919876543212",
        "Supervisor B": "+919876543214",
        "Owner A": "+919876543213",
    }
    user.phone_number = phone_by_name[user.display_name]
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
    return tokens.access_token


def client_for(
    db_session: Session,
    token: str,
    *,
    storage: SupervisorStorage | None = None,
) -> TestClient:
    app = create_app(auth_settings())

    def override_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[session_get_db] = override_db
    app.dependency_overrides[get_otp_provider] = lambda: FakeOtpProvider()
    if storage is not None:
        app.dependency_overrides[get_object_storage] = lambda: storage
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def add_assignment(db_session: Session, records: dict[str, object]) -> Assignment:
    assignment = Assignment(
        company_id=value(records, "company_a", Company).id,
        driver_membership_id=value(records, "driver_a", CompanyMembership).id,
        supervisor_membership_id=value(records, "supervisor_a", CompanyMembership).id,
        tipper_id=value(records, "tipper_a", Tipper).id,
        site_id=value(records, "site_a", Site).id,
        starts_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db_session.add(assignment)
    db_session.add(
        SupervisorSiteAccess(
            company_id=assignment.company_id,
            supervisor_membership_id=assignment.supervisor_membership_id,
            site_id=assignment.site_id,
        )
    )
    db_session.flush()
    return assignment


def driver_event_payload(
    event_type: str,
    *,
    client_event_uuid: str | None = None,
    created_at: datetime | None = None,
    **extra: str,
) -> dict[str, str]:
    return {
        "client_event_uuid": client_event_uuid or str(uuid4()),
        "event_type": event_type,
        "device_created_at": (created_at or datetime.now(UTC)).isoformat(),
        "installation_identifier": "supervisor-test-driver-device",
        "platform": "ANDROID",
        **extra,
    }


def create_driver_client(
    db_session: Session,
    records: dict[str, object],
    storage: SupervisorStorage,
) -> TestClient:
    driver = user_by_name(db_session, "Driver A")
    token = access_token(
        db_session,
        driver,
        value(records, "driver_a", CompanyMembership),
    )
    return client_for(db_session, token, storage=storage)


def test_supervisor_only_sees_permitted_site_and_verification_is_auditable(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    assignment = add_assignment(db_session, tenant_records)
    storage = SupervisorStorage()
    driver_client = create_driver_client(db_session, tenant_records, storage)
    try:
        created = driver_client.post(
            "/api/v1/driver/events",
            json=driver_event_payload("TRIP_COMPLETE"),
        )
        assert created.status_code == 200
        event_id = created.json()["event_id"]
    finally:
        driver_client.close()

    supervisor = user_by_name(db_session, "Supervisor A")
    supervisor_client = client_for(
        db_session,
        access_token(
            db_session,
            supervisor,
            value(tenant_records, "supervisor_a", CompanyMembership),
        ),
    )
    site = value(tenant_records, "site_a", Site)
    try:
        sites = supervisor_client.get("/api/v1/supervisor/sites")
        assert sites.status_code == 200
        assert sites.json()[0]["id"] == str(site.id)
        events = supervisor_client.get(f"/api/v1/supervisor/sites/{site.id}/events")
        assert events.status_code == 200
        assert events.json()[0]["event_id"] == event_id
        assert events.json()[0]["driver_name"] == "Driver A"

        approved = supervisor_client.post(
            f"/api/v1/supervisor/events/{event_id}/verify",
            json={"decision": "APPROVED", "expected_status": "PENDING_VERIFICATION"},
        )
        assert approved.status_code == 200
        assert approved.json()["verification_status"] == "APPROVED"
        assert approved.json()["verification_history"][-1]["actor_name"] == "Supervisor A"

        stale = supervisor_client.post(
            f"/api/v1/supervisor/events/{event_id}/verify",
            json={
                "decision": "DISPUTED",
                "reason": "Stale decision",
                "expected_status": "PENDING_VERIFICATION",
            },
        )
        assert stale.status_code == 409

        reject_without_reason = supervisor_client.post(
            f"/api/v1/supervisor/events/{event_id}/verify",
            json={"decision": "REJECTED"},
        )
        assert reject_without_reason.status_code == 422
    finally:
        supervisor_client.close()

    assert assignment.site_id == site.id


def test_supervisor_batch_preserves_each_event_and_driver_is_denied(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    add_assignment(db_session, tenant_records)
    storage = SupervisorStorage()
    driver_client = create_driver_client(db_session, tenant_records, storage)
    event_ids: list[str] = []
    try:
        for _ in range(2):
            response = driver_client.post(
                "/api/v1/driver/events",
                json=driver_event_payload("TRIP_COMPLETE"),
            )
            assert response.status_code == 200
            event_ids.append(response.json()["event_id"])
    finally:
        driver_client.close()

    supervisor = user_by_name(db_session, "Supervisor A")
    supervisor_client = client_for(
        db_session,
        access_token(
            db_session,
            supervisor,
            value(tenant_records, "supervisor_a", CompanyMembership),
        ),
    )
    try:
        batch = supervisor_client.post(
            "/api/v1/supervisor/events/verify-batch",
            json={"event_ids": event_ids, "decision": "APPROVED"},
        )
        assert batch.status_code == 200
        assert {item["event_id"] for item in batch.json()["events"]} == set(event_ids)
        assert all(len(item["verification_history"]) == 1 for item in batch.json()["events"])
    finally:
        supervisor_client.close()

    driver = user_by_name(db_session, "Driver A")
    driver_client = client_for(
        db_session,
        access_token(
            db_session,
            driver,
            value(tenant_records, "driver_a", CompanyMembership),
        ),
    )
    try:
        assert driver_client.get("/api/v1/supervisor/sites").status_code == 403
    finally:
        driver_client.close()


def test_unauthorized_site_and_cross_company_supervisor_are_denied(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    supervisor = user_by_name(db_session, "Supervisor A")
    client = client_for(
        db_session,
        access_token(
            db_session,
            supervisor,
            value(tenant_records, "supervisor_a", CompanyMembership),
        ),
    )
    foreign_site = value(tenant_records, "site_b", Site)
    try:
        response = client.get(f"/api/v1/supervisor/sites/{foreign_site.id}/events")
        assert response.status_code == 403
    finally:
        client.close()

    foreign_supervisor = user_by_name(db_session, "Supervisor B")
    foreign_client = client_for(
        db_session,
        access_token(
            db_session,
            foreign_supervisor,
            value(tenant_records, "supervisor_b", CompanyMembership),
        ),
    )
    site_a = value(tenant_records, "site_a", Site)
    try:
        response = foreign_client.get(f"/api/v1/supervisor/sites/{site_a.id}/events")
        assert response.status_code == 403
    finally:
        foreign_client.close()

    owner = user_by_name(db_session, "Owner A")
    owner_client = client_for(
        db_session,
        access_token(
            db_session,
            owner,
            value(tenant_records, "owner_a", CompanyMembership),
        ),
    )
    try:
        assert owner_client.get("/api/v1/supervisor/sites").status_code == 403
    finally:
        owner_client.close()


def test_km_evidence_is_available_only_to_authorized_supervisor_and_completeness_flags_missing_end(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    add_assignment(db_session, tenant_records)
    storage = SupervisorStorage()
    driver_client = create_driver_client(db_session, tenant_records, storage)
    km_event_id = str(uuid4())
    diesel_event_id = str(uuid4())
    try:
        uploaded = driver_client.post(
            "/api/v1/driver/evidence",
            params={"client_event_uuid": km_event_id},
            files={"file": ("meter.jpg", b"\xff\xd8\xffmeter-photo", "image/jpeg")},
        )
        assert uploaded.status_code == 200
        event = driver_client.post(
            "/api/v1/driver/events",
            json=driver_event_payload(
                "KM_READING",
                client_event_uuid=km_event_id,
                reading_type="START_READING",
                reading_value="100.00",
                object_reference=uploaded.json()["object_reference"],
            ),
        )
        assert event.status_code == 200
        km_event_id = event.json()["event_id"]
        diesel_uploaded = driver_client.post(
            "/api/v1/driver/evidence",
            params={"client_event_uuid": diesel_event_id},
            files={"file": ("diesel.jpg", b"\xff\xd8\xffdiesel-photo", "image/jpeg")},
        )
        assert diesel_uploaded.status_code == 200
        diesel = driver_client.post(
            "/api/v1/driver/events",
            json=driver_event_payload(
                "DIESEL",
                client_event_uuid=diesel_event_id,
                litres="12.50",
                object_reference=diesel_uploaded.json()["object_reference"],
            ),
        )
        assert diesel.status_code == 200
        diesel_event_id = diesel.json()["event_id"]
        emergency = driver_client.post(
            "/api/v1/driver/events",
            json=driver_event_payload(
                "EMERGENCY",
                category="BREAKDOWN",
                description="Hydraulic warning",
            ),
        )
        assert emergency.status_code == 200
        emergency_event_id = emergency.json()["event_id"]
    finally:
        driver_client.close()

    supervisor = user_by_name(db_session, "Supervisor A")
    supervisor_client = client_for(
        db_session,
        access_token(
            db_session,
            supervisor,
            value(tenant_records, "supervisor_a", CompanyMembership),
        ),
        storage=storage,
    )
    site = value(tenant_records, "site_a", Site)
    try:
        events = supervisor_client.get(f"/api/v1/supervisor/sites/{site.id}/events")
        assert events.status_code == 200
        event_by_type = {item["event_type"]: item for item in events.json()}
        assert event_by_type["KM_READING"]["evidence_available"] is True
        assert event_by_type["DIESEL"]["litres"] == "12.500"
        evidence = supervisor_client.get(f"/api/v1/supervisor/events/{km_event_id}/evidence")
        assert evidence.status_code == 200
        assert evidence.content == b"\xff\xd8\xffmeter-photo"
        assert evidence.headers["content-type"] == "image/jpeg"
        assert evidence.headers["cache-control"] == "private, no-store"
        assert evidence.headers["x-fleet-evidence-event-type"] == "KM_READING"
        assert evidence.headers["x-fleet-evidence-driver"] == "Driver A"
        assert evidence.headers["x-fleet-evidence-tipper"] == "KA01AB1234"
        diesel_evidence = supervisor_client.get(
            f"/api/v1/supervisor/events/{diesel_event_id}/evidence"
        )
        assert diesel_evidence.status_code == 200
        assert diesel_evidence.content == b"\xff\xd8\xffdiesel-photo"
        assert diesel_evidence.headers["content-type"] == "image/jpeg"

        approved_km = supervisor_client.post(
            f"/api/v1/supervisor/events/{km_event_id}/verify",
            json={"decision": "APPROVED"},
        )
        assert approved_km.status_code == 200
        approved_diesel = supervisor_client.post(
            f"/api/v1/supervisor/events/{diesel_event_id}/verify",
            json={"decision": "APPROVED"},
        )
        assert approved_diesel.status_code == 200
        assert approved_diesel.json()["verification_status"] == "APPROVED"

        emergency = supervisor_client.get(f"/api/v1/supervisor/sites/{site.id}/events").json()
        emergency_item = next(item for item in emergency if item["event_id"] == emergency_event_id)
        assert emergency_item["emergency_status"] == "OPEN"
        acknowledged = supervisor_client.post(
            f"/api/v1/supervisor/events/{emergency_event_id}/emergency/acknowledge",
        )
        assert acknowledged.status_code == 200
        assert acknowledged.json()["emergency_status"] == "ACKNOWLEDGED"

        completeness = supervisor_client.get(
            f"/api/v1/supervisor/sites/{site.id}/completeness",
            params={"review_date": datetime.now(UTC).date().isoformat()},
        )
        assert completeness.status_code == 200
        assert completeness.json()[0]["has_start_reading"] is True
        assert completeness.json()[0]["has_end_reading"] is False
        assert completeness.json()[0]["unresolved_emergency"] is True

        resolved = supervisor_client.post(
            f"/api/v1/supervisor/events/{emergency_event_id}/emergency/resolve",
        )
        assert resolved.status_code == 200
        assert resolved.json()["emergency_status"] == "RESOLVED"

        resolved_completeness = supervisor_client.get(
            f"/api/v1/supervisor/sites/{site.id}/completeness",
            params={"review_date": datetime.now(UTC).date().isoformat()},
        )
        assert resolved_completeness.status_code == 200
        assert resolved_completeness.json()[0]["unresolved_emergency"] is False
    finally:
        supervisor_client.close()

    driver_again = create_driver_client(db_session, tenant_records, storage)
    try:
        assert (
            driver_again.get(f"/api/v1/supervisor/events/{km_event_id}/evidence").status_code == 403
        )
        assert driver_again.get(f"/api/v1/supervisor/events/{uuid4()}/evidence").status_code == 403
    finally:
        driver_again.close()


def test_colorful_jpeg_bytes_survive_upload_storage_and_authorized_response(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    add_assignment(db_session, tenant_records)
    storage = SupervisorStorage()
    driver_client = create_driver_client(db_session, tenant_records, storage)
    client_event_uuid = str(uuid4())
    try:
        uploaded = driver_client.post(
            "/api/v1/driver/evidence",
            params={"client_event_uuid": client_event_uuid},
            files={"file": ("colorful.jpg", COLORFUL_JPEG_BYTES, "image/jpeg")},
        )
        assert uploaded.status_code == 200
        object_reference = uploaded.json()["object_reference"]
        assert storage.objects[object_reference] == (COLORFUL_JPEG_BYTES, "image/jpeg")

        created = driver_client.post(
            "/api/v1/driver/events",
            json=driver_event_payload(
                "KM_READING",
                client_event_uuid=client_event_uuid,
                reading_type="START_READING",
                reading_value="10000.00",
                object_reference=object_reference,
            ),
        )
        assert created.status_code == 200
        event_id = created.json()["event_id"]
    finally:
        driver_client.close()

    supervisor = user_by_name(db_session, "Supervisor A")
    supervisor_client = client_for(
        db_session,
        access_token(
            db_session,
            supervisor,
            value(tenant_records, "supervisor_a", CompanyMembership),
        ),
        storage=storage,
    )
    try:
        response = supervisor_client.get(f"/api/v1/supervisor/events/{event_id}/evidence")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert int(response.headers["content-length"]) == len(COLORFUL_JPEG_BYTES)
        assert response.content == COLORFUL_JPEG_BYTES
    finally:
        supervisor_client.close()


def test_completeness_surfaces_odometer_regression(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    add_assignment(db_session, tenant_records)
    storage = SupervisorStorage()
    driver_client = create_driver_client(db_session, tenant_records, storage)
    try:
        for reading_type, reading_value in (("START_READING", "100.00"), ("END_READING", "90.00")):
            client_event_uuid = str(uuid4())
            uploaded = driver_client.post(
                "/api/v1/driver/evidence",
                params={"client_event_uuid": client_event_uuid},
                files={"file": ("meter.jpg", b"\xff\xd8\xffmeter-photo", "image/jpeg")},
            )
            assert uploaded.status_code == 200
            response = driver_client.post(
                "/api/v1/driver/events",
                json=driver_event_payload(
                    "KM_READING",
                    client_event_uuid=client_event_uuid,
                    reading_type=reading_type,
                    reading_value=reading_value,
                    object_reference=uploaded.json()["object_reference"],
                ),
            )
            assert response.status_code == 200
    finally:
        driver_client.close()

    supervisor = user_by_name(db_session, "Supervisor A")
    supervisor_client = client_for(
        db_session,
        access_token(
            db_session,
            supervisor,
            value(tenant_records, "supervisor_a", CompanyMembership),
        ),
        storage=storage,
    )
    site = value(tenant_records, "site_a", Site)
    try:
        completeness = supervisor_client.get(
            f"/api/v1/supervisor/sites/{site.id}/completeness",
            params={"review_date": datetime.now(UTC).date().isoformat()},
        )
        assert completeness.status_code == 200
        assert completeness.json()[0]["odometer_regression"] is True
        assert completeness.json()[0]["start_reading_value"] == "100.00"
        assert completeness.json()[0]["end_reading_value"] == "90.00"
    finally:
        supervisor_client.close()
