from __future__ import annotations

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
    OperationalEvent,
    Site,
    Tipper,
    User,
)
from fleet_api.db.session import get_db as session_get_db
from fleet_api.domain.enums import TipperStatus
from fleet_api.main import create_app

pytestmark = pytest.mark.postgres


class InMemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_private(self, *, object_key: str, content: bytes, content_type: str) -> str:
        del content_type
        self.objects[object_key] = content
        return object_key

    def delete_private(self, *, object_key: str) -> None:
        self.objects.pop(object_key, None)


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


def session_for_user(
    db_session: Session,
    user: User,
    membership: CompanyMembership,
) -> str:
    phone_by_name = {
        "Driver A": "+919876543210",
        "Driver A2": "+919876543211",
        "Supervisor A": "+919876543212",
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


def driver_app(
    db_session: Session,
    access_token: str,
    *,
    storage: InMemoryStorage | None = None,
) -> TestClient:
    app = create_app(auth_settings())

    def override_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[session_get_db] = override_db
    app.dependency_overrides[get_otp_provider] = lambda: FakeOtpProvider()
    if storage is not None:
        app.dependency_overrides[get_object_storage] = lambda: storage
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {access_token}"})
    return client


def add_assignment(
    db_session: Session,
    records: dict[str, object],
    *,
    driver_key: str = "driver_a",
    tipper: Tipper | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
) -> Assignment:
    assignment = Assignment(
        company_id=value(records, "company_a", Company).id,
        driver_membership_id=value(records, driver_key, CompanyMembership).id,
        supervisor_membership_id=value(records, "supervisor_a", CompanyMembership).id,
        tipper_id=(tipper or value(records, "tipper_a", Tipper)).id,
        site_id=value(records, "site_a", Site).id,
        starts_at=starts_at or datetime.now(UTC) - timedelta(hours=1),
        ends_at=ends_at,
    )
    db_session.add(assignment)
    db_session.flush()
    return assignment


def event_payload(
    client_event_uuid: str,
    *,
    created_at: datetime | None = None,
    platform: str = "ANDROID",
    installation_identifier: str = "android-test-device",
) -> dict[str, str]:
    return {
        "client_event_uuid": client_event_uuid,
        "event_type": "TRIP_COMPLETE",
        "device_created_at": (created_at or datetime.now(UTC)).isoformat(),
        "installation_identifier": installation_identifier,
        "platform": platform,
    }


def test_driver_assignment_role_boundary_and_idempotent_event(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    assignment = add_assignment(db_session, tenant_records)
    driver = user_by_name(db_session, "Driver A")
    driver_membership = value(tenant_records, "driver_a", CompanyMembership)
    driver_token = session_for_user(db_session, driver, driver_membership)
    client = driver_app(db_session, driver_token)
    try:
        current = client.get("/api/v1/driver/assignment/current")
        assert current.status_code == 200
        assert current.json()["assignment_id"] == str(assignment.id)
        assert current.json()["site_name"] == "Alpha Site"

        event_id = str(uuid4())
        accepted = client.post("/api/v1/driver/events", json=event_payload(event_id))
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "accepted"

        replay = client.post("/api/v1/driver/events", json=event_payload(event_id))
        assert replay.status_code == 200
        assert replay.json()["status"] == "already_accepted"
        assert (
            db_session.scalar(
                select(OperationalEvent).where(
                    OperationalEvent.client_event_uuid == event_id,
                )
            )
            is not None
        )
    finally:
        client.close()

    supervisor = user_by_name(db_session, "Supervisor A")
    supervisor_membership = value(tenant_records, "supervisor_a", CompanyMembership)
    supervisor_client = driver_app(
        db_session,
        session_for_user(db_session, supervisor, supervisor_membership),
    )
    try:
        assert supervisor_client.get("/api/v1/driver/assignment/current").status_code == 403
    finally:
        supervisor_client.close()


def test_driver_event_timestamp_and_cross_driver_uuid_are_rejected(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    now = datetime.now(UTC)
    add_assignment(db_session, tenant_records, starts_at=now - timedelta(hours=1))
    second_tipper = Tipper(
        company_id=value(tenant_records, "company_a", Company).id,
        registration_number="KA01XY9999",
        short_name="Alpha Two",
        status=TipperStatus.ACTIVE,
    )
    db_session.add(second_tipper)
    db_session.flush()
    add_assignment(
        db_session,
        tenant_records,
        driver_key="driver_a2",
        tipper=second_tipper,
        starts_at=now - timedelta(hours=1),
    )
    driver_a = user_by_name(db_session, "Driver A")
    driver_a_token = session_for_user(
        db_session,
        driver_a,
        value(tenant_records, "driver_a", CompanyMembership),
    )
    client_a = driver_app(db_session, driver_a_token)
    event_id = str(uuid4())
    try:
        assert (
            client_a.post("/api/v1/driver/events", json=event_payload(event_id)).status_code == 200
        )
        future = client_a.post(
            "/api/v1/driver/events",
            json=event_payload(str(uuid4()), created_at=now + timedelta(minutes=10)),
        )
        assert future.status_code == 422
    finally:
        client_a.close()

    driver_a2 = user_by_name(db_session, "Driver A2")
    client_a2 = driver_app(
        db_session,
        session_for_user(
            db_session,
            driver_a2,
            value(tenant_records, "driver_a2", CompanyMembership),
        ),
    )
    try:
        cross_driver = client_a2.post("/api/v1/driver/events", json=event_payload(event_id))
        assert cross_driver.status_code == 403
    finally:
        client_a2.close()


def test_driver_evidence_is_private_and_required_for_km_event(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    add_assignment(db_session, tenant_records)
    driver = user_by_name(db_session, "Driver A")
    token = session_for_user(
        db_session,
        driver,
        value(tenant_records, "driver_a", CompanyMembership),
    )
    storage = InMemoryStorage()
    client = driver_app(db_session, token, storage=storage)
    client_event_uuid = str(uuid4())
    try:
        invalid = client.post(
            "/api/v1/driver/evidence",
            params={"client_event_uuid": client_event_uuid},
            files={"file": ("evidence.txt", b"not-an-image", "text/plain")},
        )
        assert invalid.status_code == 422

        spoofed = client.post(
            "/api/v1/driver/evidence",
            params={"client_event_uuid": client_event_uuid},
            files={"file": ("evidence.jpg", b"not-an-image", "image/jpeg")},
        )
        assert spoofed.status_code == 422

        uploaded = client.post(
            "/api/v1/driver/evidence",
            params={"client_event_uuid": client_event_uuid},
            files={"file": ("evidence.jpg", b"\xff\xd8\xffimage-bytes", "image/jpeg")},
        )
        assert uploaded.status_code == 200
        object_reference = uploaded.json()["object_reference"]
        assert object_reference in storage.objects
        km = client.post(
            "/api/v1/driver/events",
            json={
                **event_payload(client_event_uuid),
                "event_type": "KM_READING",
                "reading_type": "START_READING",
                "reading_value": "100.25",
                "object_reference": object_reference,
            },
        )
        assert km.status_code == 200
    finally:
        client.close()


def test_driver_device_platform_is_restricted_to_supported_values(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    driver = user_by_name(db_session, "Driver A")
    client = driver_app(
        db_session,
        session_for_user(
            db_session,
            driver,
            value(tenant_records, "driver_a", CompanyMembership),
        ),
    )
    try:
        invalid = client.post(
            "/api/v1/driver/device",
            json={"installation_identifier": "device", "platform": "NOT_A_PLATFORM"},
        )
        assert invalid.status_code == 422
    finally:
        client.close()


def test_driver_qa_registers_web_device_and_submits_real_event(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    add_assignment(db_session, tenant_records)
    driver = user_by_name(db_session, "Driver A")
    client = driver_app(
        db_session,
        session_for_user(
            db_session,
            driver,
            value(tenant_records, "driver_a", CompanyMembership),
        ),
    )
    try:
        device = client.post(
            "/api/v1/driver/device",
            json={"installation_identifier": "qa-web-installation", "platform": "WEB"},
        )
        assert device.status_code == 200
        assert device.json()["platform"] == "WEB"

        event = client.post(
            "/api/v1/driver/events",
            json=event_payload(
                str(uuid4()),
                platform="WEB",
                installation_identifier="qa-web-installation",
            ),
        )
        assert event.status_code == 200
        assert event.json()["status"] == "accepted"
    finally:
        client.close()
