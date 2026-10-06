from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from fleet_api.db.models import (
    Company,
    CompanyMembership,
    DutySession,
    FleetAsset,
    OperationalEvent,
)
from fleet_api.domain.assets import create_fleet_asset
from fleet_api.domain.attendance_location import attendance_location_confidence
from fleet_api.domain.enums import (
    AssetOwnershipType,
    AttendanceConfidence,
    FleetAssetType,
    LocationSnapshotStatus,
)
from fleet_api.domain.workforce import union_interval_minutes
from test_driver_api import add_assignment
from test_future_foundations_api import (
    MemoryObjectStorage,
    authenticated_client,
    settings,
    value,
)

pytestmark = pytest.mark.postgres


def test_interval_union_does_not_double_count_overlap() -> None:
    start = datetime(2026, 10, 6, 8, tzinfo=UTC)
    minutes, overlap = union_interval_minutes(
        [
            (start, start + timedelta(hours=4)),
            (start + timedelta(hours=3), start + timedelta(hours=6)),
        ]
    )
    assert minutes == 360
    assert overlap is True


def test_location_confidence_is_explainable_and_not_payroll_logic() -> None:
    assert (
        attendance_location_confidence(
            status=LocationSnapshotStatus.AVAILABLE,
            site_distance_m=Decimal("10"),
            site_radius_m=Decimal("100"),
            asset_distance_m=Decimal("5"),
            asset_threshold_m=Decimal("50"),
        )
        == AttendanceConfidence.STRONG_MATCH
    )
    assert (
        attendance_location_confidence(
            status=LocationSnapshotStatus.DENIED,
            site_distance_m=None,
            site_radius_m=None,
            asset_distance_m=None,
            asset_threshold_m=Decimal("50"),
        )
        == AttendanceConfidence.UNKNOWN
    )
    assert (
        attendance_location_confidence(
            status=LocationSnapshotStatus.AVAILABLE,
            site_distance_m=Decimal("250"),
            site_radius_m=Decimal("100"),
            asset_distance_m=Decimal("20"),
            asset_threshold_m=Decimal("50"),
        )
        == AttendanceConfidence.ASSET_PROXIMITY_MATCH
    )
    assert (
        attendance_location_confidence(
            status=LocationSnapshotStatus.AVAILABLE,
            site_distance_m=Decimal("250"),
            site_radius_m=Decimal("100"),
            asset_distance_m=Decimal("200"),
            asset_threshold_m=Decimal("50"),
        )
        == AttendanceConfidence.MISMATCH
    )


def test_dual_meter_capture_is_atomic_idempotent_and_keeps_meter_time_separate(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    asset = value(tenant_records, "tipper_a", FleetAsset)
    asset.supports_odometer_km = True
    asset.supports_hour_meter = True
    started_at = datetime.now(UTC) - timedelta(hours=10, minutes=30)
    assignment = add_assignment(
        db_session,
        tenant_records,
        starts_at=started_at - timedelta(hours=1),
    )
    assignment.regular_duty_minutes = 480
    db_session.commit()
    storage = MemoryObjectStorage()
    client = authenticated_client(
        db_session,
        value(tenant_records, "driver_a", CompanyMembership),
        settings(multi_meter_enabled=True),
        storage,
    )

    def evidence(client_event_uuid: str, name: str) -> str:
        uploaded = client.post(
            "/api/v1/driver/evidence",
            params={"client_event_uuid": client_event_uuid},
            files={"file": (name, b"\xff\xd8\xffmeter", "image/jpeg")},
        )
        assert uploaded.status_code == 200, uploaded.text
        return uploaded.json()["object_reference"]

    try:
        start_group = str(uuid4())
        start_km_uuid, start_hmr_uuid = str(uuid4()), str(uuid4())
        start_payload = {
            "capture_group_uuid": start_group,
            "reading_type": "START_READING",
            "device_created_at": started_at.isoformat(),
            "installation_identifier": "dual-meter-device",
            "platform": "ANDROID",
            "km_client_event_uuid": start_km_uuid,
            "odometer_km": "12500",
            "km_object_reference": evidence(start_km_uuid, "start-km.jpg"),
            "hmr_client_event_uuid": start_hmr_uuid,
            "hour_meter_hours": "3000.0",
            "hmr_object_reference": evidence(start_hmr_uuid, "start-hmr.jpg"),
        }
        started = client.post("/api/v1/driver/meter-captures", json=start_payload)
        assert started.status_code == 200, started.text
        assert started.json()["status"] == "accepted"
        assert len(started.json()["event_ids"]) == 2
        repeated = client.post("/api/v1/driver/meter-captures", json=start_payload)
        assert repeated.status_code == 200
        assert repeated.json()["status"] == "already_accepted"
        assert repeated.json()["event_ids"] == started.json()["event_ids"]

        failed_group = str(uuid4())
        failed_km_uuid, failed_hmr_uuid = str(uuid4()), str(uuid4())
        before = len(db_session.scalars(select(OperationalEvent)).all())
        rejected = client.post(
            "/api/v1/driver/meter-captures",
            json={
                "capture_group_uuid": failed_group,
                "reading_type": "END_READING",
                "device_created_at": datetime.now(UTC).isoformat(),
                "installation_identifier": "dual-meter-device",
                "platform": "ANDROID",
                "km_client_event_uuid": failed_km_uuid,
                "odometer_km": "12560",
                "km_object_reference": evidence(failed_km_uuid, "failed-km.jpg"),
                "hmr_client_event_uuid": failed_hmr_uuid,
                "hour_meter_hours": "3008.5",
                "hmr_object_reference": "missing-private-object",
            },
        )
        assert rejected.status_code == 422
        assert len(db_session.scalars(select(OperationalEvent)).all()) == before

        end_group = str(uuid4())
        end_km_uuid, end_hmr_uuid = str(uuid4()), str(uuid4())
        ended = client.post(
            "/api/v1/driver/meter-captures",
            json={
                "capture_group_uuid": end_group,
                "reading_type": "END_READING",
                "device_created_at": datetime.now(UTC).isoformat(),
                "installation_identifier": "dual-meter-device",
                "platform": "ANDROID",
                "km_client_event_uuid": end_km_uuid,
                "odometer_km": "12560",
                "km_object_reference": evidence(end_km_uuid, "end-km.jpg"),
                "hmr_client_event_uuid": end_hmr_uuid,
                "hour_meter_hours": "3008.5",
                "hmr_object_reference": evidence(end_hmr_uuid, "end-hmr.jpg"),
            },
        )
        assert ended.status_code == 200, ended.text
        duty = db_session.scalar(
            select(DutySession).where(DutySession.assignment_id == assignment.id)
        )
        assert duty is not None
        assert duty.end_km - duty.start_km == Decimal("60.00")
        assert duty.end_hmr - duty.start_hmr == Decimal("8.50")
        assert duty.final_overtime_minutes == 150
        events = db_session.scalars(
            select(OperationalEvent).where(
                OperationalEvent.capture_group_uuid.in_([start_group, end_group])
            )
        ).all()
        assert len(events) == 4
        assert {str(item.capture_group_uuid) for item in events} == {
            start_group,
            end_group,
        }
    finally:
        client.close()


def test_multi_trigger_maintenance_and_meter_capabilities(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    client = authenticated_client(
        db_session,
        value(tenant_records, "owner_a", CompanyMembership),
        settings(maintenance_enabled=True, multi_meter_enabled=True),
    )
    asset = value(tenant_records, "tipper_a", FleetAsset)
    try:
        updated = client.patch(
            f"/api/v1/owner/assets/{asset.id}",
            json={"supports_odometer_km": True, "supports_hour_meter": True},
        )
        assert updated.status_code == 200, updated.text
        schedule = client.post(
            "/api/v1/owner/maintenance/schedules",
            json={
                "asset_id": str(asset.id),
                "maintenance_type": "ENGINE_OIL",
                "interval_basis": "KM",
                "interval_value": "1000",
                "last_service_meter": "10000",
            },
        )
        assert schedule.status_code == 201, schedule.text
        criterion = client.post(
            f"/api/v1/owner/maintenance/schedules/{schedule.json()['id']}/criteria",
            json={
                "basis": "HOUR_METER_HOURS",
                "interval_value": "100",
                "last_baseline_value": "500",
            },
        )
        assert criterion.status_code == 201, criterion.text
        completed = client.post(
            f"/api/v1/owner/maintenance/schedules/{schedule.json()['id']}/records",
            json={
                "performed_on": "2026-10-06",
                "odometer_km": "10500",
                "hour_meter_hours": "550",
            },
        )
        assert completed.status_code == 201, completed.text
        refreshed = client.get("/api/v1/owner/maintenance/schedules").json()[0]
        assert len(refreshed["criteria"]) == 2
        assert {row["next_due_value"] for row in refreshed["criteria"]} == {
            "11500.00",
            "650.00",
        }
    finally:
        client.close()


def test_telematics_accepts_every_current_fleet_asset_type(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    company = value(tenant_records, "company_a", Company)
    assets = [value(tenant_records, "tipper_a", FleetAsset)]
    for index, asset_type in enumerate(
        (
            FleetAssetType.EXCAVATOR,
            FleetAssetType.BACKHOE_LOADER,
            FleetAssetType.ROLLER,
            FleetAssetType.GRADER,
        ),
        start=1,
    ):
        assets.append(
            create_fleet_asset(
                db_session,
                company_id=company.id,
                asset_type=asset_type,
                ownership_type=AssetOwnershipType.OWNED,
                asset_code=f"TELEMETRY-{index}",
                registration_number=None,
                short_name=f"Telemetry {asset_type.value}",
            )
        )
    db_session.commit()
    client = authenticated_client(
        db_session,
        value(tenant_records, "owner_a", CompanyMembership),
        settings(telematics_enabled=True),
    )
    try:
        for index, asset in enumerate(assets):
            mapping = client.post(
                "/api/v1/owner/telematics/mappings",
                json={
                    "asset_id": str(asset.id),
                    "provider": "MACHINERY_TEST",
                    "provider_vehicle_id": f"asset-{index}",
                },
            )
            assert mapping.status_code == 201, mapping.text
            position = client.post(
                f"/api/v1/owner/telematics/mappings/{mapping.json()['id']}/positions",
                json={
                    "provider_event_id": f"event-{index}",
                    "recorded_at": datetime.now(UTC).isoformat(),
                    "latitude": "12.971600",
                    "longitude": "77.594600",
                    "speed_kph": "0",
                    "ignition_state": True,
                    "engine_hours": str(3000 + index),
                    "battery_voltage": "24.6",
                },
            )
            assert position.status_code == 200, position.text
            assert position.json()["position"]["engine_hours"] == f"{3000 + index}.00"
            assert Decimal(position.json()["position"]["battery_voltage"]) == Decimal("24.6")
            assert position.json()["discrepancies"][0]["status"] == "INSUFFICIENT_DATA"
    finally:
        client.close()


def test_monthly_payroll_is_decimal_prorated_and_finalized_is_immutable(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    client = authenticated_client(
        db_session,
        value(tenant_records, "owner_a", CompanyMembership),
        settings(payroll_enabled=True),
    )
    driver = value(tenant_records, "driver_a", CompanyMembership)
    try:
        profile = client.post(
            "/api/v1/owner/workforce/compensation",
            json={
                "membership_id": str(driver.id),
                "pay_basis": "MONTHLY",
                "base_amount": "25000",
                "effective_from": "2026-10-01",
                "standard_duty_minutes": 600,
                "overtime_rate_per_hour": "100",
            },
        )
        assert profile.status_code == 201, profile.text
        period = client.post(
            "/api/v1/owner/workforce/payroll-periods",
            json={"starts_on": "2026-10-01", "ends_on": "2026-10-31"},
        )
        assert period.status_code == 201, period.text
        period_id = period.json()["id"]
        lines = client.get(f"/api/v1/owner/workforce/payroll-periods/{period_id}/lines").json()
        assert lines[0]["base_pay"] == "25000.00"
        reviewed = client.patch(
            f"/api/v1/owner/workforce/payroll-periods/{period_id}/status",
            json={"status": "REVIEWED"},
        )
        assert reviewed.status_code == 200
        finalized = client.patch(
            f"/api/v1/owner/workforce/payroll-periods/{period_id}/status",
            json={"status": "FINALIZED"},
        )
        assert finalized.status_code == 200
        adjustment = client.post(
            f"/api/v1/owner/workforce/payroll-lines/{lines[0]['id']}/adjustments",
            json={"amount": "100", "reason": "late approved allowance"},
        )
        assert adjustment.status_code == 409
    finally:
        client.close()


def test_location_capture_requires_flag_role_and_duty(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    driver = value(tenant_records, "driver_a", CompanyMembership)
    disabled = authenticated_client(db_session, driver, settings())
    try:
        payload = {
            "source": "DUTY_START",
            "status": "UNAVAILABLE",
            "captured_at_device": "2026-10-06T10:00:00Z",
            "permission_state": "not-requested",
        }
        assert (
            disabled.post("/api/v1/driver/attendance-location/snapshots", json=payload).status_code
            == 404
        )
    finally:
        disabled.close()
    enabled = authenticated_client(db_session, driver, settings(attendance_location_enabled=True))
    try:
        response = enabled.post(
            "/api/v1/driver/attendance-location/snapshots",
            json={
                "source": "METER_SUBMISSION",
                "status": "DENIED",
                "captured_at_device": "2026-10-06T10:00:00Z",
                "permission_state": "denied",
            },
        )
        assert response.status_code == 422
        assert "active duty" in response.json()["detail"]["message"]
    finally:
        enabled.close()
