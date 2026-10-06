from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_object_storage, get_otp_provider
from fleet_api.auth.providers import FakeOtpProvider
from fleet_api.auth.service import AuthService
from fleet_api.core.config import Settings
from fleet_api.db.models import (
    Assignment,
    AuditLog,
    Company,
    CompanyMembership,
    Device,
    DutySession,
    EmergencyEvent,
    EvidenceObject,
    FleetAsset,
    HourMeterReading,
    OperationalEvent,
    Site,
    SupervisorSiteAccess,
    User,
)
from fleet_api.db.session import get_db as session_get_db
from fleet_api.domain.assets import create_fleet_asset
from fleet_api.domain.assignments import create_assignment
from fleet_api.domain.enums import (
    AssetOwnershipType,
    FleetAssetStatus,
    FleetAssetType,
    MembershipStatus,
    VerificationStatus,
)
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
        "Driver B": "+919876543214",
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
    tipper: FleetAsset | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
) -> Assignment:
    return create_assignment(
        db_session,
        company_id=value(records, "company_a", Company).id,
        driver_membership_id=value(records, driver_key, CompanyMembership).id,
        supervisor_membership_id=value(records, "supervisor_a", CompanyMembership).id,
        asset_id=(tipper or value(records, "tipper_a", FleetAsset)).id,
        site_id=value(records, "site_a", Site).id,
        starts_at=starts_at or datetime.now(UTC) - timedelta(hours=1),
        ends_at=ends_at,
    )


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


def start_duty(client: TestClient, *, installation_identifier: str = "android-test-device") -> None:
    client_event_uuid = str(uuid4())
    uploaded = client.post(
        "/api/v1/driver/evidence",
        params={"client_event_uuid": client_event_uuid},
        files={"file": ("start.jpg", b"\xff\xd8\xffstart", "image/jpeg")},
    )
    assert uploaded.status_code == 200
    started = client.post(
        "/api/v1/driver/events",
        json={
            "client_event_uuid": client_event_uuid,
            "event_type": "KM_READING",
            "device_created_at": datetime.now(UTC).isoformat(),
            "installation_identifier": installation_identifier,
            "platform": "ANDROID",
            "reading_type": "START_READING",
            "reading_value": "100",
            "object_reference": uploaded.json()["object_reference"],
        },
    )
    assert started.status_code == 200


def submit_km(
    client: TestClient,
    *,
    reading_type: str,
    reading_value: int | str,
    created_at: datetime,
    installation_identifier: str = "duty-test-device",
) -> Response:
    client_event_uuid = str(uuid4())
    uploaded = client.post(
        "/api/v1/driver/evidence",
        params={"client_event_uuid": client_event_uuid},
        files={"file": ("km.jpg", b"\xff\xd8\xffkm", "image/jpeg")},
    )
    assert uploaded.status_code == 200
    response = client.post(
        "/api/v1/driver/events",
        json={
            "client_event_uuid": client_event_uuid,
            "event_type": "KM_READING",
            "device_created_at": created_at.isoformat(),
            "installation_identifier": installation_identifier,
            "platform": "ANDROID",
            "reading_type": reading_type,
            "reading_value": str(reading_value),
            "object_reference": uploaded.json()["object_reference"],
        },
    )
    return response


def submit_hmr(
    client: TestClient,
    *,
    reading_type: str,
    reading_value: str,
    created_at: datetime,
    installation_identifier: str = "machinery-test-device",
) -> Response:
    client_event_uuid = str(uuid4())
    uploaded = client.post(
        "/api/v1/driver/evidence",
        params={"client_event_uuid": client_event_uuid},
        files={"file": ("hmr.jpg", b"\xff\xd8\xffhmr", "image/jpeg")},
    )
    assert uploaded.status_code == 200
    return client.post(
        "/api/v1/driver/events",
        json={
            "client_event_uuid": client_event_uuid,
            "event_type": "HMR_READING",
            "device_created_at": created_at.isoformat(),
            "installation_identifier": installation_identifier,
            "platform": "ANDROID",
            "reading_type": reading_type,
            "reading_value": reading_value,
            "object_reference": uploaded.json()["object_reference"],
        },
    )


def test_machinery_hmr_duty_capabilities_and_continuity(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    excavator = create_fleet_asset(
        db_session,
        company_id=company.id,
        asset_type=FleetAssetType.EXCAVATOR,
        ownership_type=AssetOwnershipType.OWNED,
        asset_code="EXC-HMR-01",
        registration_number=None,
        short_name="CAT 320",
    )
    assignment = add_assignment(db_session, tenant_records, tipper=excavator)
    driver = value(tenant_records, "driver_a", CompanyMembership)
    token = session_for_user(db_session, user_by_name(db_session, "Driver A"), driver)
    client = driver_app(db_session, token, storage=InMemoryStorage())

    current = client.get("/api/v1/driver/assignment/current")
    assert current.status_code == 200
    assert current.json()["asset_type"] == "EXCAVATOR"
    assert current.json()["asset_code"] == "EXC-HMR-01"
    assert current.json()["tipper_registration_number"] is None

    unsupported_trip = client.post(
        "/api/v1/driver/events",
        json=event_payload(str(uuid4()), installation_identifier="machinery-test-device"),
    )
    assert unsupported_trip.status_code == 422
    assert "not supported" in unsupported_trip.json()["detail"]["message"]
    unsupported_km = client.post(
        "/api/v1/driver/events",
        json={
            **event_payload(str(uuid4()), installation_identifier="machinery-test-device"),
            "event_type": "KM_READING",
            "reading_type": "START_READING",
            "reading_value": "10",
        },
    )
    assert unsupported_km.status_code == 422

    started_at = datetime.now(UTC) - timedelta(minutes=10)
    started = submit_hmr(
        client,
        reading_type="START_READING",
        reading_value="3240.50",
        created_at=started_at,
    )
    assert started.status_code == 200
    duty = client.get("/api/v1/driver/duty/current")
    assert duty.status_code == 200
    assert duty.json()["status"] == "ACTIVE"
    assert duty.json()["start_hmr"] == "3240.50"
    assert duty.json()["start_km"] is None

    diesel = client.post(
        "/api/v1/driver/events",
        json={
            **event_payload(
                str(uuid4()),
                created_at=started_at + timedelta(minutes=2),
                installation_identifier="machinery-test-device",
            ),
            "event_type": "DIESEL",
            "litres": "40",
        },
    )
    assert diesel.status_code == 200
    emergency = client.post(
        "/api/v1/driver/events",
        json={
            **event_payload(
                str(uuid4()),
                created_at=started_at + timedelta(minutes=3),
                installation_identifier="machinery-test-device",
            ),
            "event_type": "EMERGENCY",
        },
    )
    assert emergency.status_code == 200

    invalid_end = submit_hmr(
        client,
        reading_type="END_READING",
        reading_value="3239",
        created_at=started_at + timedelta(minutes=4),
    )
    assert invalid_end.status_code == 422
    assert invalid_end.json()["detail"]["code"] == "INVALID_END_HMR"

    ended = submit_hmr(
        client,
        reading_type="END_READING",
        reading_value="3248.00",
        created_at=started_at + timedelta(minutes=5),
    )
    assert ended.status_code == 200
    closed = client.get("/api/v1/driver/duty/current")
    assert closed.json()["status"] == "CLOSED"
    assert closed.json()["end_hmr"] == "3248.00"
    assert closed.json()["machine_hours"] == "7.50"

    owner = value(tenant_records, "owner_a", CompanyMembership)
    owner_token = session_for_user(db_session, user_by_name(db_session, "Owner A"), owner)
    owner_api = driver_app(db_session, owner_token)
    duty_report = owner_api.get("/api/v1/reports/duty")
    assert duty_report.status_code == 200
    machinery_row = next(
        item for item in duty_report.json() if item["assignment_id"] == str(assignment.id)
    )
    assert machinery_row["asset_type"] == "EXCAVATOR"
    assert machinery_row["start_hmr"] == "3240.50"
    assert machinery_row["end_hmr"] == "3248.00"
    assert machinery_row["machine_hours"] == "7.50"
    daily_report = owner_api.get(f"/api/v1/reports/tippers/{excavator.id}/daily")
    assert daily_report.status_code == 200
    daily_row = daily_report.json()[0]
    assert daily_row["asset_type"] == "EXCAVATOR"
    assert daily_row["start_hmr"] == "3240.50"
    assert daily_row["end_hmr"] == "3248.00"
    assert daily_row["machine_hours"] == "7.50"
    assert daily_row["approved_trip_count"] is None
    assert daily_row["distance_km"] is None
    assert daily_row["km_per_approved_trip"] is None
    daily_workbook = owner_api.get("/api/v1/reports/daily.xlsx")
    assert daily_workbook.status_code == 200
    assert daily_workbook.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert daily_workbook.content.startswith(b"PK")

    supervisor = value(tenant_records, "supervisor_a", CompanyMembership)
    site = value(tenant_records, "site_a", Site)
    db_session.add(
        SupervisorSiteAccess(
            company_id=company.id,
            supervisor_membership_id=supervisor.id,
            site_id=site.id,
        )
    )
    db_session.commit()
    supervisor_token = session_for_user(
        db_session, user_by_name(db_session, "Supervisor A"), supervisor
    )
    supervisor_api = driver_app(db_session, supervisor_token)
    event_list = supervisor_api.get(f"/api/v1/supervisor/sites/{site.id}/events")
    assert event_list.status_code == 200
    hmr_events = [event for event in event_list.json() if event["event_type"] == "HMR_READING"]
    assert [event["reading_value"] for event in reversed(hmr_events)] == [
        "3240.50",
        "3248.00",
    ]
    verified = supervisor_api.post(
        f"/api/v1/supervisor/events/{hmr_events[0]['event_id']}/verify",
        json={"decision": "APPROVED"},
    )
    assert verified.status_code == 200
    assert verified.json()["verification_status"] == "APPROVED"

    regressed = submit_hmr(
        client,
        reading_type="START_READING",
        reading_value="3240",
        created_at=started_at + timedelta(minutes=6),
    )
    assert regressed.status_code == 422
    assert regressed.json()["detail"]["code"] == "HOUR_METER_CONTINUITY"
    assert regressed.json()["detail"]["previous_end_hmr"] == "3248.00"

    readings = db_session.scalars(select(HourMeterReading)).all()
    assert [reading.reading_value for reading in readings] == [
        pytest.approx(3240.5),
        pytest.approx(3248.0),
    ]
    session = db_session.scalar(
        select(DutySession).where(DutySession.assignment_id == assignment.id)
    )
    assert session is not None
    assert session.start_hmr is not None and session.end_hmr is not None
    assert session.end_hmr - session.start_hmr == pytest.approx(7.5)


def test_sequential_same_day_sessions_are_distinct_and_reportable(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    started_at = datetime.now(UTC) - timedelta(hours=8)
    assignment = add_assignment(
        db_session,
        tenant_records,
        starts_at=started_at - timedelta(hours=1),
    )
    driver = user_by_name(db_session, "Driver A")
    token = session_for_user(
        db_session,
        driver,
        value(tenant_records, "driver_a", CompanyMembership),
    )
    client = driver_app(db_session, token, storage=InMemoryStorage())
    try:
        first_start = submit_km(
            client,
            reading_type="START_READING",
            reading_value=10000,
            created_at=started_at,
        )
        assert first_start.status_code == 200
        first_trip = client.post(
            "/api/v1/driver/events",
            json=event_payload(str(uuid4()), created_at=started_at + timedelta(hours=1)),
        )
        assert first_trip.status_code == 200
        first_end = submit_km(
            client,
            reading_type="END_READING",
            reading_value=10120,
            created_at=started_at + timedelta(hours=2),
        )
        assert first_end.status_code == 200
        first_state = client.get("/api/v1/driver/duty/current").json()
        assert first_state["status"] == "CLOSED"

        second_start = submit_km(
            client,
            reading_type="START_READING",
            reading_value=10120,
            created_at=started_at + timedelta(hours=3),
        )
        assert second_start.status_code == 200
        second_state = client.get("/api/v1/driver/duty/current").json()
        assert second_state["status"] == "ACTIVE"
        assert second_state["session_id"] != first_state["session_id"]
        second_end = submit_km(
            client,
            reading_type="END_READING",
            reading_value=10150,
            created_at=started_at + timedelta(hours=4),
        )
        assert second_end.status_code == 200

        sessions = list(
            db_session.scalars(
                select(DutySession)
                .where(DutySession.assignment_id == assignment.id)
                .order_by(DutySession.started_at)
            ).all()
        )
        assert len(sessions) == 2
        assert all(item.status.value == "CLOSED" for item in sessions)
        assert sessions[0].operational_date == sessions[1].operational_date
        event_ids = [
            first_start.json()["event_id"],
            first_trip.json()["event_id"],
            first_end.json()["event_id"],
            second_start.json()["event_id"],
            second_end.json()["event_id"],
        ]
        linked = list(
            db_session.scalars(
                select(OperationalEvent).where(OperationalEvent.id.in_(event_ids))
            ).all()
        )
        assert {event.duty_session_id for event in linked} == {item.id for item in sessions}
        assert str(sessions[0].start_event_id) == first_start.json()["event_id"]
        assert str(sessions[0].end_event_id) == first_end.json()["event_id"]
        assert str(sessions[1].start_event_id) == second_start.json()["event_id"]
        assert str(sessions[1].end_event_id) == second_end.json()["event_id"]
    finally:
        client.close()


def test_active_session_is_rejected_and_survives_a_new_client(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    started_at = datetime.now(UTC) - timedelta(hours=3)
    add_assignment(db_session, tenant_records, starts_at=started_at - timedelta(hours=1))
    driver = user_by_name(db_session, "Driver A")
    token = session_for_user(
        db_session,
        driver,
        value(tenant_records, "driver_a", CompanyMembership),
    )
    first_client = driver_app(db_session, token, storage=InMemoryStorage())
    second_client = driver_app(db_session, token, storage=InMemoryStorage())
    try:
        started = submit_km(
            first_client,
            reading_type="START_READING",
            reading_value=100,
            created_at=started_at,
        )
        assert started.status_code == 200
        duplicate = submit_km(
            second_client,
            reading_type="START_READING",
            reading_value=100,
            created_at=started_at + timedelta(minutes=1),
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"]["code"] == "DUTY_ALREADY_STARTED"
        state = second_client.get("/api/v1/driver/duty/current")
        assert state.status_code == 200
        assert state.json()["status"] == "ACTIVE"
        first_state = first_client.get("/api/v1/driver/duty/current")
        assert state.json()["session_id"] == first_state.json()["session_id"]
    finally:
        first_client.close()
        second_client.close()


def test_start_requires_tipper_odometer_continuity(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    started_at = datetime.now(UTC) - timedelta(hours=6)
    add_assignment(db_session, tenant_records, starts_at=started_at - timedelta(hours=1))
    driver = user_by_name(db_session, "Driver A")
    client = driver_app(
        db_session,
        session_for_user(
            db_session,
            driver,
            value(tenant_records, "driver_a", CompanyMembership),
        ),
        storage=InMemoryStorage(),
    )
    try:
        assert (
            submit_km(
                client,
                reading_type="START_READING",
                reading_value=10100,
                created_at=started_at,
            ).status_code
            == 200
        )
        assert (
            submit_km(
                client,
                reading_type="END_READING",
                reading_value=10120,
                created_at=started_at + timedelta(hours=1),
            ).status_code
            == 200
        )
        rejected = submit_km(
            client,
            reading_type="START_READING",
            reading_value=10000,
            created_at=started_at + timedelta(hours=2),
        )
        assert rejected.status_code == 422
        assert rejected.json()["detail"]["code"] == "ODOMETER_CONTINUITY"
        assert rejected.json()["detail"]["previous_end_km"] == "10120.00"
        assert rejected.json()["detail"]["message"] == (
            "START KM cannot be lower than the previous END KM (10120). Please check the odometer."
        )
        accepted = submit_km(
            client,
            reading_type="START_READING",
            reading_value=10125,
            created_at=started_at + timedelta(hours=2, minutes=1),
        )
        assert accepted.status_code == 200
    finally:
        client.close()


@pytest.mark.parametrize("invalid_value", ["-1", "NaN", "Infinity", "5676543455.81"])
def test_invalid_odometer_values_are_structured_and_transaction_safe(
    db_session: Session,
    tenant_records: dict[str, object],
    invalid_value: str,
) -> None:
    started_at = datetime.now(UTC) - timedelta(hours=4)
    add_assignment(db_session, tenant_records, starts_at=started_at - timedelta(hours=1))
    driver = user_by_name(db_session, "Driver A")
    client = driver_app(
        db_session,
        session_for_user(
            db_session,
            driver,
            value(tenant_records, "driver_a", CompanyMembership),
        ),
        storage=InMemoryStorage(),
    )
    try:
        rejected = submit_km(
            client,
            reading_type="START_READING",
            reading_value=invalid_value,
            created_at=started_at,
        )
        assert rejected.status_code == 422, rejected.text
        assert rejected.json()["detail"]["code"] == "ODOMETER_OUT_OF_RANGE"
        assert (
            rejected.json()["detail"]["message"]
            == "KM reading looks invalid. Please check the odometer and enter the correct value."
        )
        assert client.get("/api/v1/driver/duty/current").json()["status"] == "NONE"
        assert db_session.scalars(select(DutySession)).all() == []
        assert db_session.scalars(select(OperationalEvent)).all() == []
    finally:
        client.close()


def test_invalid_end_does_not_close_duty_and_next_session_keeps_continuity(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    started_at = datetime.now(UTC) - timedelta(hours=4)
    assignment = add_assignment(
        db_session, tenant_records, starts_at=started_at - timedelta(hours=1)
    )
    driver = user_by_name(db_session, "Driver A")
    client = driver_app(
        db_session,
        session_for_user(
            db_session,
            driver,
            value(tenant_records, "driver_a", CompanyMembership),
        ),
        storage=InMemoryStorage(),
    )
    try:
        assert (
            submit_km(
                client, reading_type="START_READING", reading_value=10000, created_at=started_at
            ).status_code
            == 200
        )
        invalid_end = submit_km(
            client,
            reading_type="END_READING",
            reading_value="5676543455.81",
            created_at=started_at + timedelta(hours=1),
        )
        assert invalid_end.status_code == 422
        assert invalid_end.json()["detail"]["code"] == "ODOMETER_OUT_OF_RANGE"
        state = client.get("/api/v1/driver/duty/current").json()
        assert state["status"] == "ACTIVE"
        stored_session = db_session.scalar(
            select(DutySession).where(DutySession.assignment_id == assignment.id)
        )
        assert stored_session is not None
        assert stored_session.status.value == "ACTIVE"
        assert stored_session.end_km is None
        assert stored_session.end_event_id is None
        assert db_session.query(OperationalEvent).count() == 1

        assert (
            submit_km(
                client,
                reading_type="END_READING",
                reading_value=10220,
                created_at=started_at + timedelta(hours=2),
            ).status_code
            == 200
        )
        assert (
            submit_km(
                client,
                reading_type="START_READING",
                reading_value=10220,
                created_at=started_at + timedelta(hours=3),
            ).status_code
            == 200
        )
        assert client.get("/api/v1/driver/duty/current").json()["status"] == "ACTIVE"
    finally:
        client.close()


def test_rejected_end_does_not_poison_next_start_continuity(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    started_at = datetime.now(UTC) - timedelta(hours=5)
    add_assignment(db_session, tenant_records, starts_at=started_at - timedelta(hours=1))
    driver = user_by_name(db_session, "Driver A")
    client = driver_app(
        db_session,
        session_for_user(
            db_session,
            driver,
            value(tenant_records, "driver_a", CompanyMembership),
        ),
        storage=InMemoryStorage(),
    )
    try:
        assert (
            submit_km(
                client, reading_type="START_READING", reading_value=10000, created_at=started_at
            ).status_code
            == 200
        )
        ended = submit_km(
            client,
            reading_type="END_READING",
            reading_value=10120,
            created_at=started_at + timedelta(hours=1),
        )
        assert ended.status_code == 200
        end_event = db_session.get(OperationalEvent, ended.json()["event_id"])
        assert end_event is not None
        end_event.verification_status = VerificationStatus.REJECTED
        db_session.flush()
        assert (
            submit_km(
                client,
                reading_type="START_READING",
                reading_value=10000,
                created_at=started_at + timedelta(hours=2),
            ).status_code
            == 200
        )
    finally:
        client.close()


def test_cross_midnight_session_keeps_start_operational_date(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    started_at = datetime(2026, 9, 23, 20, 0, tzinfo=UTC)
    ended_at = datetime(2026, 9, 24, 4, 0, tzinfo=UTC)
    assignment = add_assignment(
        db_session,
        tenant_records,
        starts_at=started_at - timedelta(hours=1),
    )
    driver = user_by_name(db_session, "Driver A")
    client = driver_app(
        db_session,
        session_for_user(
            db_session,
            driver,
            value(tenant_records, "driver_a", CompanyMembership),
        ),
        storage=InMemoryStorage(),
    )
    try:
        assert (
            submit_km(
                client,
                reading_type="START_READING",
                reading_value=100,
                created_at=started_at,
            ).status_code
            == 200
        )
        assert (
            submit_km(
                client,
                reading_type="END_READING",
                reading_value=120,
                created_at=ended_at,
            ).status_code
            == 200
        )
        session = db_session.scalar(
            select(DutySession).where(DutySession.assignment_id == assignment.id)
        )
        assert session is not None
        assert session.ended_at is not None
        assert session.status.value == "CLOSED"
        assert session.operational_date == started_at.astimezone(ZoneInfo("Asia/Kolkata")).date()
        assert session.started_at.date() != session.ended_at.date()
    finally:
        client.close()


def test_overtime_is_calculated_independently_per_session(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    first_start = datetime.now(UTC) - timedelta(hours=25)
    first_end = first_start + timedelta(hours=11)
    second_start = first_end + timedelta(hours=1)
    second_end = second_start + timedelta(hours=10, minutes=15)
    assignment = add_assignment(
        db_session,
        tenant_records,
        starts_at=first_start - timedelta(hours=1),
    )
    driver = user_by_name(db_session, "Driver A")
    client = driver_app(
        db_session,
        session_for_user(
            db_session,
            driver,
            value(tenant_records, "driver_a", CompanyMembership),
        ),
        storage=InMemoryStorage(),
    )
    try:
        assert (
            submit_km(
                client, reading_type="START_READING", reading_value=100, created_at=first_start
            ).status_code
            == 200
        )
        assert (
            submit_km(
                client, reading_type="END_READING", reading_value=120, created_at=first_end
            ).status_code
            == 200
        )
        assert (
            submit_km(
                client, reading_type="START_READING", reading_value=120, created_at=second_start
            ).status_code
            == 200
        )
        assert (
            submit_km(
                client, reading_type="END_READING", reading_value=140, created_at=second_end
            ).status_code
            == 200
        )
        sessions = list(
            db_session.scalars(
                select(DutySession)
                .where(DutySession.assignment_id == assignment.id)
                .order_by(DutySession.started_at)
            ).all()
        )
        assert [item.final_overtime_minutes for item in sessions] == [60, 15]
    finally:
        client.close()


def test_driver_handover_can_start_after_previous_session_closes(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    handover_at = datetime.now(UTC) - timedelta(hours=3)
    first_assignment = add_assignment(
        db_session,
        tenant_records,
        starts_at=handover_at - timedelta(hours=4),
        ends_at=handover_at,
    )
    second_assignment = add_assignment(
        db_session,
        tenant_records,
        driver_key="driver_a2",
        starts_at=handover_at,
    )
    driver_a = user_by_name(db_session, "Driver A")
    client_a = driver_app(
        db_session,
        session_for_user(
            db_session,
            driver_a,
            value(tenant_records, "driver_a", CompanyMembership),
        ),
        storage=InMemoryStorage(),
    )
    driver_a2 = user_by_name(db_session, "Driver A2")
    client_a2 = driver_app(
        db_session,
        session_for_user(
            db_session,
            driver_a2,
            value(tenant_records, "driver_a2", CompanyMembership),
        ),
        storage=InMemoryStorage(),
    )
    try:
        assert (
            submit_km(
                client_a,
                reading_type="START_READING",
                reading_value=100,
                created_at=handover_at - timedelta(hours=2),
            ).status_code
            == 200
        )
        assert (
            submit_km(
                client_a,
                reading_type="END_READING",
                reading_value=120,
                created_at=handover_at - timedelta(minutes=30),
            ).status_code
            == 200
        )
        assert (
            submit_km(
                client_a2,
                reading_type="START_READING",
                reading_value=125,
                created_at=handover_at + timedelta(minutes=1),
                installation_identifier="handover-driver-a2",
            ).status_code
            == 200
        )
        sessions = list(
            db_session.scalars(
                select(DutySession)
                .where(DutySession.asset_id == value(tenant_records, "tipper_a", FleetAsset).id)
                .order_by(DutySession.started_at)
            ).all()
        )
        assert [item.assignment_id for item in sessions] == [
            first_assignment.id,
            second_assignment.id,
        ]
        assert sessions[0].driver_membership_id != sessions[1].driver_membership_id
    finally:
        client_a.close()
        client_a2.close()


def test_driver_assignment_role_boundary_and_idempotent_event(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    assignment = add_assignment(db_session, tenant_records)
    driver = user_by_name(db_session, "Driver A")
    driver_membership = value(tenant_records, "driver_a", CompanyMembership)
    supervisor_membership = value(tenant_records, "supervisor_a", CompanyMembership)
    supervisor_membership.display_name = "Assigned Supervisor"
    db_session.add(
        SupervisorSiteAccess(
            company_id=assignment.company_id,
            supervisor_membership_id=supervisor_membership.id,
            site_id=assignment.site_id,
        )
    )
    db_session.flush()
    driver_token = session_for_user(db_session, driver, driver_membership)
    client = driver_app(db_session, driver_token, storage=InMemoryStorage())
    try:
        current = client.get("/api/v1/driver/assignment/current")
        assert current.status_code == 200
        assert current.json()["assignment_id"] == str(assignment.id)
        assert current.json()["asset_code"] == "ALPHA-ONE"
        assert current.json()["site_name"] == "Alpha Site"
        assert current.json()["supervisor_name"] == "Assigned Supervisor"
        assert current.json()["supervisor_names"] == ["Assigned Supervisor"]

        event_id = str(uuid4())
        start_duty(client)
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
    second_tipper = FleetAsset(
        company_id=value(tenant_records, "company_a", Company).id,
        asset_type=FleetAssetType.TIPPER,
        ownership_type=AssetOwnershipType.OWNED,
        asset_code="ALPHA-TWO",
        registration_number="KA01XY9999",
        short_name="Alpha Two",
        status=FleetAssetStatus.ACTIVE,
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
    client_a = driver_app(db_session, driver_a_token, storage=InMemoryStorage())
    event_id = str(uuid4())
    try:
        start_duty(client_a)
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
        storage=InMemoryStorage(),
    )
    try:
        invalid = client.post(
            "/api/v1/driver/device",
            json={"installation_identifier": "device", "platform": "NOT_A_PLATFORM"},
        )
        assert invalid.status_code == 422
    finally:
        client.close()


def test_clean_driver_handover_is_audited_and_preserves_history(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    add_assignment(db_session, tenant_records)
    driver_a_membership = value(tenant_records, "driver_a", CompanyMembership)
    driver_a = user_by_name(db_session, "Driver A")
    client_a = driver_app(
        db_session,
        session_for_user(db_session, driver_a, driver_a_membership),
        storage=InMemoryStorage(),
    )
    installation = "handover-phone"
    evidence_uuid = str(uuid4())
    event_uuid = str(uuid4())
    try:
        registered = client_a.post(
            "/api/v1/driver/device",
            json={"installation_identifier": installation, "platform": "ANDROID"},
        )
        assert registered.status_code == 200
        device_id = registered.json()["device_id"]
        assert registered.json()["handed_over"] is False
        assert registered.json()["membership_id"] == str(driver_a_membership.id)
        repeated = client_a.post(
            "/api/v1/driver/device",
            json={"installation_identifier": installation, "platform": "ANDROID"},
        )
        assert repeated.status_code == 200
        assert repeated.json()["device_id"] == device_id

        uploaded = client_a.post(
            "/api/v1/driver/evidence",
            params={"client_event_uuid": evidence_uuid},
            files={"file": ("handover.jpg", b"\xff\xd8\xffhandover", "image/jpeg")},
        )
        assert uploaded.status_code == 200
        event = client_a.post(
            "/api/v1/driver/events",
            json={
                **event_payload(event_uuid, installation_identifier=installation),
                "event_type": "EMERGENCY",
            },
        )
        assert event.status_code == 200
    finally:
        client_a.close()

    driver_a2_membership = value(tenant_records, "driver_a2", CompanyMembership)
    driver_a2 = user_by_name(db_session, "Driver A2")
    client_a2 = driver_app(
        db_session,
        session_for_user(db_session, driver_a2, driver_a2_membership),
    )
    try:
        preflight = client_a2.post(
            "/api/v1/driver/device",
            json={"installation_identifier": installation, "platform": "ANDROID"},
        )
        assert preflight.status_code == 409
        assert preflight.json()["detail"] == {
            "code": "DEVICE_HANDOVER_REQUIRED",
            "message": "device handover confirmation is required",
            "current_membership_id": str(driver_a_membership.id),
        }

        missing_local_confirmation = client_a2.post(
            "/api/v1/driver/device",
            json={
                "installation_identifier": installation,
                "platform": "ANDROID",
                "allow_handover": True,
            },
        )
        assert missing_local_confirmation.status_code == 409
        assert missing_local_confirmation.json()["detail"]["code"] == ("DEVICE_HANDOVER_BLOCKED")

        handed_over = client_a2.post(
            "/api/v1/driver/device",
            json={
                "installation_identifier": installation,
                "platform": "ANDROID",
                "allow_handover": True,
                "local_state_clear": True,
            },
        )
        assert handed_over.status_code == 200
        assert handed_over.json()["device_id"] == device_id
        assert handed_over.json()["membership_id"] == str(driver_a2_membership.id)
        assert handed_over.json()["handed_over"] is True

        same_driver = client_a2.post(
            "/api/v1/driver/device",
            json={"installation_identifier": installation, "platform": "ANDROID"},
        )
        assert same_driver.status_code == 200
        assert same_driver.json()["device_id"] == device_id
        assert same_driver.json()["handed_over"] is False
    finally:
        client_a2.close()

    historical_event = db_session.scalar(
        select(OperationalEvent).where(OperationalEvent.client_event_uuid == event_uuid)
    )
    assert historical_event is not None
    historical_assignment = db_session.get(Assignment, historical_event.assignment_id)
    assert historical_assignment is not None
    assert historical_assignment.driver_membership_id == driver_a_membership.id
    assert str(historical_event.device_id) == device_id
    evidence = db_session.scalar(
        select(EvidenceObject).where(EvidenceObject.client_event_uuid == evidence_uuid)
    )
    assert evidence is not None
    assert evidence.membership_id == driver_a_membership.id
    audit = db_session.scalar(
        select(AuditLog).where(
            AuditLog.entity_id == historical_event.device_id,
            AuditLog.action == "DEVICE_DRIVER_HANDOVER",
        )
    )
    assert audit is not None
    assert audit.actor_membership_id == driver_a2_membership.id
    assert audit.old_values == {"membership_id": str(driver_a_membership.id)}
    assert audit.new_values == {"membership_id": str(driver_a2_membership.id)}


def test_active_old_driver_duty_blocks_handover(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    add_assignment(db_session, tenant_records)
    old_membership = value(tenant_records, "driver_a", CompanyMembership)
    client_a = driver_app(
        db_session,
        session_for_user(db_session, user_by_name(db_session, "Driver A"), old_membership),
        storage=InMemoryStorage(),
    )
    installation = "active-duty-phone"
    try:
        start_duty(client_a, installation_identifier=installation)
    finally:
        client_a.close()

    new_membership = value(tenant_records, "driver_a2", CompanyMembership)
    client_a2 = driver_app(
        db_session,
        session_for_user(
            db_session,
            user_by_name(db_session, "Driver A2"),
            new_membership,
        ),
    )
    try:
        blocked = client_a2.post(
            "/api/v1/driver/device",
            json={
                "installation_identifier": installation,
                "platform": "ANDROID",
                "allow_handover": True,
                "local_state_clear": True,
            },
        )
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "DEVICE_HANDOVER_BLOCKED"
    finally:
        client_a2.close()

    device = db_session.scalar(select(Device).where(Device.installation_identifier == installation))
    assert device is not None
    assert device.membership_id == old_membership.id


def test_inactive_old_driver_does_not_lock_clean_phone(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    old_membership = value(tenant_records, "driver_a", CompanyMembership)
    installation = "inactive-driver-phone"
    client_a = driver_app(
        db_session,
        session_for_user(db_session, user_by_name(db_session, "Driver A"), old_membership),
    )
    try:
        assert (
            client_a.post(
                "/api/v1/driver/device",
                json={"installation_identifier": installation, "platform": "ANDROID"},
            ).status_code
            == 200
        )
    finally:
        client_a.close()
    old_membership.status = MembershipStatus.INACTIVE
    db_session.commit()

    new_membership = value(tenant_records, "driver_a2", CompanyMembership)
    client_a2 = driver_app(
        db_session,
        session_for_user(
            db_session,
            user_by_name(db_session, "Driver A2"),
            new_membership,
        ),
    )
    try:
        handed_over = client_a2.post(
            "/api/v1/driver/device",
            json={
                "installation_identifier": installation,
                "platform": "ANDROID",
                "allow_handover": True,
                "local_state_clear": True,
            },
        )
        assert handed_over.status_code == 200
        assert handed_over.json()["handed_over"] is True
    finally:
        client_a2.close()


def test_same_installation_identifier_cannot_claim_cross_company_device(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    installation = "shared-looking-installation"
    company_a = value(tenant_records, "company_a", Company)
    company_b = value(tenant_records, "company_b", Company)
    driver_a_membership = value(tenant_records, "driver_a", CompanyMembership)
    client_a = driver_app(
        db_session,
        session_for_user(
            db_session,
            user_by_name(db_session, "Driver A"),
            driver_a_membership,
        ),
    )
    try:
        device_a = client_a.post(
            "/api/v1/driver/device",
            json={"installation_identifier": installation, "platform": "ANDROID"},
        )
        assert device_a.status_code == 200
    finally:
        client_a.close()

    driver_b_membership = value(tenant_records, "driver_b", CompanyMembership)
    client_b = driver_app(
        db_session,
        session_for_user(
            db_session,
            user_by_name(db_session, "Driver B"),
            driver_b_membership,
        ),
    )
    try:
        device_b = client_b.post(
            "/api/v1/driver/device",
            json={
                "installation_identifier": installation,
                "platform": "ANDROID",
                "allow_handover": True,
                "local_state_clear": True,
            },
        )
        assert device_b.status_code == 200
        assert device_b.json()["device_id"] != device_a.json()["device_id"]
    finally:
        client_b.close()

    devices = list(
        db_session.scalars(
            select(Device).where(Device.installation_identifier == installation)
        ).all()
    )
    assert {(item.company_id, item.membership_id) for item in devices} == {
        (company_a.id, driver_a_membership.id),
        (company_b.id, driver_b_membership.id),
    }


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
        storage=InMemoryStorage(),
    )
    try:
        device = client.post(
            "/api/v1/driver/device",
            json={"installation_identifier": "qa-web-installation", "platform": "WEB"},
        )
        assert device.status_code == 200
        assert device.json()["platform"] == "WEB"

        start_duty(client, installation_identifier="qa-web-installation")
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


def test_one_tap_emergency_needs_no_category_or_evidence_and_deduplicates_rapid_repeat(
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
    timestamp = datetime.now(UTC)
    first_uuid = str(uuid4())
    second_uuid = str(uuid4())
    try:
        first = client.post(
            "/api/v1/driver/events",
            json={**event_payload(first_uuid, created_at=timestamp), "event_type": "EMERGENCY"},
        )
        assert first.status_code == 200
        assert first.json()["status"] == "accepted"

        repeat = client.post(
            "/api/v1/driver/events",
            json={**event_payload(second_uuid, created_at=timestamp), "event_type": "EMERGENCY"},
        )
        assert repeat.status_code == 200
        assert repeat.json()["status"] == "already_accepted"
        assert repeat.json()["event_id"] == first.json()["event_id"]
        emergency = db_session.scalar(
            select(EmergencyEvent).where(EmergencyEvent.event_id == first.json()["event_id"])
        )
        assert emergency is not None
        assert emergency.category is None
        assert emergency.description is None
        assert len(db_session.scalars(select(EmergencyEvent)).all()) == 1
    finally:
        client.close()


def test_duty_session_gates_work_and_calculates_overtime(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    started_at = datetime.now(UTC) - timedelta(hours=11)
    assignment = add_assignment(
        db_session,
        tenant_records,
        starts_at=started_at - timedelta(hours=1),
    )
    driver = user_by_name(db_session, "Driver A")
    client = driver_app(
        db_session,
        session_for_user(db_session, driver, value(tenant_records, "driver_a", CompanyMembership)),
        storage=InMemoryStorage(),
    )
    try:
        blocked_trip = client.post("/api/v1/driver/events", json=event_payload(str(uuid4())))
        assert blocked_trip.status_code == 422
        assert blocked_trip.json()["detail"]["code"] == "DUTY_NOT_STARTED"
        blocked_diesel = client.post(
            "/api/v1/driver/events",
            json={**event_payload(str(uuid4())), "event_type": "DIESEL", "litres": "20"},
        )
        assert blocked_diesel.status_code == 422
        assert blocked_diesel.json()["detail"]["code"] == "DUTY_NOT_STARTED"

        start_uuid = str(uuid4())
        start_upload = client.post(
            "/api/v1/driver/evidence",
            params={"client_event_uuid": start_uuid},
            files={"file": ("start.jpg", b"\xff\xd8\xffstart", "image/jpeg")},
        )
        assert start_upload.status_code == 200
        started = client.post(
            "/api/v1/driver/events",
            json={
                "client_event_uuid": start_uuid,
                "event_type": "KM_READING",
                "device_created_at": started_at.isoformat(),
                "installation_identifier": "duty-test-device",
                "platform": "ANDROID",
                "reading_type": "START_READING",
                "reading_value": "100",
                "object_reference": start_upload.json()["object_reference"],
            },
        )
        assert started.status_code == 200
        state = client.get("/api/v1/driver/duty/current")
        assert state.status_code == 200
        assert state.json()["status"] == "ACTIVE"
        assert "overtime" not in state.text.lower()

        accepted_diesel = client.post(
            "/api/v1/driver/events",
            json={**event_payload(str(uuid4())), "event_type": "DIESEL", "litres": "20"},
        )
        assert accepted_diesel.status_code == 200

        duplicate_start_uuid = str(uuid4())
        duplicate_upload = client.post(
            "/api/v1/driver/evidence",
            params={"client_event_uuid": duplicate_start_uuid},
            files={"file": ("start.jpg", b"\xff\xd8\xffstart", "image/jpeg")},
        )
        assert duplicate_upload.status_code == 200
        duplicate_start = client.post(
            "/api/v1/driver/events",
            json={
                "client_event_uuid": duplicate_start_uuid,
                "event_type": "KM_READING",
                "device_created_at": (started_at + timedelta(minutes=1)).isoformat(),
                "installation_identifier": "duty-test-device",
                "platform": "ANDROID",
                "reading_type": "START_READING",
                "reading_value": "100",
                "object_reference": duplicate_upload.json()["object_reference"],
            },
        )
        assert duplicate_start.status_code == 409
        assert duplicate_start.json()["detail"]["code"] == "DUTY_ALREADY_STARTED"

        end_uuid = str(uuid4())
        end_upload = client.post(
            "/api/v1/driver/evidence",
            params={"client_event_uuid": end_uuid},
            files={"file": ("end.jpg", b"\xff\xd8\xffend", "image/jpeg")},
        )
        assert end_upload.status_code == 200
        ended_at = started_at + timedelta(hours=10, minutes=20)
        ended = client.post(
            "/api/v1/driver/events",
            json={
                "client_event_uuid": end_uuid,
                "event_type": "KM_READING",
                "device_created_at": ended_at.isoformat(),
                "installation_identifier": "duty-test-device",
                "platform": "ANDROID",
                "reading_type": "END_READING",
                "reading_value": "120",
                "object_reference": end_upload.json()["object_reference"],
            },
        )
        assert ended.status_code == 200
        session = db_session.scalar(
            select(DutySession).where(DutySession.assignment_id == assignment.id)
        )
        assert session is not None
        assert session.status.value == "CLOSED"
        assert session.final_overtime_minutes == 20
        assert client.get("/api/v1/driver/duty/current").json()["status"] == "CLOSED"
    finally:
        client.close()
