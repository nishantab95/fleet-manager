from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from fleet_api.db.models import CompanyMembership, FleetAsset, Site
from fleet_api.domain.enums import MaintenanceBasis, MaintenanceDueStatus
from fleet_api.domain.maintenance import maintenance_due_status
from test_future_foundations_api import authenticated_client, settings, value

pytestmark = pytest.mark.postgres


def test_due_state_keeps_unknown_distinct_from_zero() -> None:
    assert (
        maintenance_due_status(
            basis=MaintenanceBasis.KM,
            next_due_meter=Decimal("100"),
            next_due_date=None,
            current_meter=None,
            as_of=date(2026, 10, 6),
            warning_threshold=Decimal("10"),
        )
        == MaintenanceDueStatus.UNKNOWN
    )
    assert (
        maintenance_due_status(
            basis=MaintenanceBasis.DATE,
            next_due_meter=None,
            next_due_date=date(2026, 10, 6),
            current_meter=None,
            as_of=date(2026, 10, 6),
            warning_threshold=Decimal("10"),
        )
        == MaintenanceDueStatus.DUE
    )


def test_work_order_completion_creates_history_and_resets_schedule(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    client = authenticated_client(
        db_session,
        value(tenant_records, "owner_a", CompanyMembership),
        settings(maintenance_enabled=True),
    )
    asset = value(tenant_records, "tipper_a", FleetAsset)
    try:
        schedule = client.post(
            "/api/v1/owner/maintenance/schedules",
            json={
                "asset_id": str(asset.id),
                "maintenance_type": "ENGINE_OIL",
                "interval_basis": "KM",
                "interval_value": "10000",
                "warning_threshold": "1000",
                "last_service_meter": "50000",
            },
        ).json()
        order = client.post(
            "/api/v1/owner/maintenance/work-orders",
            json={
                "asset_id": str(asset.id),
                "schedule_id": schedule["id"],
                "title": "Engine oil and filters",
                "vendor_name": "Local workshop",
            },
        )
        assert order.status_code == 201, order.text
        completed = client.post(
            f"/api/v1/owner/maintenance/work-orders/{order.json()['id']}/complete",
            json={
                "performed_on": "2026-10-06",
                "meter_value": "55000",
                "labor_cost": "1250.50",
                "parts_cost": "4320.25",
                "other_cost": "0",
            },
        )
        assert completed.status_code == 200, completed.text
        assert completed.json()["work_order"]["status"] == "COMPLETED"
        assert completed.json()["record"]["labor_cost"] == "1250.50"
        refreshed = client.get("/api/v1/owner/maintenance/schedules").json()[0]
        assert refreshed["next_due_meter"] == "65000.00"
        assert len(client.get("/api/v1/owner/maintenance/history").json()) == 1
    finally:
        client.close()


def test_policy_matrix_and_notification_dedupe(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    client = authenticated_client(
        db_session,
        value(tenant_records, "owner_a", CompanyMembership),
        settings(asset_documents_enabled=True, notifications_enabled=True),
    )
    try:
        policy = client.put(
            "/api/v1/owner/asset-documents/policies",
            json={
                "asset_type": "TIPPER",
                "ownership_type": "OWNED",
                "document_type": "INSURANCE",
                "required": True,
                "expiry_warning_days": 30,
            },
        )
        assert policy.status_code == 200, policy.text
        matrix = client.get("/api/v1/owner/asset-documents/compliance").json()
        assert any(
            item["document_type"] == "INSURANCE" and item["status"] == "MISSING" for item in matrix
        )
        first = client.get("/api/v1/owner/notifications").json()
        second = client.get("/api/v1/owner/notifications").json()
        assert len(first) == len(second) == 1
        assert first[0]["category"] == "DOCUMENT_EXPIRY"
        marked = client.patch(
            f"/api/v1/owner/notifications/{first[0]['id']}", json={"state": "READ"}
        )
        assert marked.json()["state"] == "READ"
    finally:
        client.close()


def test_telematics_ingestion_is_idempotent_and_emits_geofence_transition(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    client = authenticated_client(
        db_session,
        value(tenant_records, "owner_a", CompanyMembership),
        settings(telematics_enabled=True),
    )
    asset = value(tenant_records, "tipper_a", FleetAsset)
    site = value(tenant_records, "site_a", Site)
    site.latitude = Decimal("12.971600")
    site.longitude = Decimal("77.594600")
    db_session.commit()
    try:
        mapping = client.post(
            "/api/v1/owner/telematics/mappings",
            json={
                "asset_id": str(asset.id),
                "provider": "SIMULATOR",
                "provider_vehicle_id": "SIM-1",
            },
        ).json()
        geofence = client.put(
            "/api/v1/owner/telematics/geofences",
            json={"site_id": str(site.id), "radius_m": "250"},
        )
        assert geofence.status_code == 200, geofence.text
        payload = {
            "provider_event_id": "position-1",
            "recorded_at": "2026-10-06T10:00:00Z",
            "latitude": "12.971600",
            "longitude": "77.594600",
            "speed_kph": "0",
            "ignition_state": True,
            "odometer_km": "42150.50",
        }
        first = client.post(
            f"/api/v1/owner/telematics/mappings/{mapping['id']}/positions", json=payload
        )
        again = client.post(
            f"/api/v1/owner/telematics/mappings/{mapping['id']}/positions", json=payload
        )
        assert first.json()["transitions"][0]["transition_type"] == "ENTER"
        assert again.json()["duplicate"] is True
        assert len(client.get("/api/v1/owner/telematics/transitions").json()) == 1
    finally:
        client.close()


def test_fuel_csv_import_reports_rows_and_reconciles_missing_driver_data(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    client = authenticated_client(
        db_session,
        value(tenant_records, "owner_a", CompanyMembership),
        settings(fuel_integrations_enabled=True),
    )
    asset = value(tenant_records, "tipper_a", FleetAsset)
    content = (
        "external_transaction_id,occurred_at,litres,asset_identifier,source_type\n"
        f"TX-1,2026-10-06T10:00:00+05:30,50.500,{asset.asset_code},FUEL_CARD\n"
        "TX-2,2026-10-06T11:00:00+05:30,25.000,NO-SUCH-ASSET,FUEL_CARD\n"
    )
    try:
        imported = client.post(
            "/api/v1/owner/fuel/imports",
            data={"source_name": "Test Card"},
            files={"file": ("fuel.csv", content, "text/csv")},
        )
        assert imported.status_code == 201, imported.text
        body = imported.json()
        assert [row["row_status"] for row in body["rows"]] == ["IMPORTED", "UNMAPPED"]
        reconciled = client.post(
            f"/api/v1/owner/fuel/imports/{body['batch']['id']}/reconcile",
            json={"tolerance_litres": "1.000", "time_window_minutes": 720},
        )
        assert reconciled.status_code == 200, reconciled.text
        assert reconciled.json()[0]["status"] == "INSUFFICIENT_DATA"
    finally:
        client.close()
