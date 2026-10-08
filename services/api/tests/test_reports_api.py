from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook  # type: ignore[import-untyped]
from sqlalchemy.orm import Session

from fleet_api.db.models import (
    AssetSiteDeployment,
    Assignment,
    Company,
    CompanyMembership,
    DutySession,
    FleetAsset,
    Site,
    SiteDailyClosureHistory,
    SupervisorSiteAccess,
)
from fleet_api.domain.assets import create_fleet_asset
from fleet_api.domain.assignments import create_assignment
from fleet_api.domain.enums import AssetOwnershipType, FleetAssetType, SiteStatus
from fleet_api.domain.reporting import ReportingService
from test_driver_api import session_for_user
from test_supervisor_api import (
    SupervisorStorage,
    access_token,
    client_for,
    create_driver_client,
    driver_event_payload,
    user_by_name,
    value,
)

pytestmark = pytest.mark.postgres

REPORT_DATE = date(2025, 1, 15)
DAY_START = datetime(2025, 1, 14, 18, tzinfo=UTC)


def add_reporting_assignment(
    db_session: Session,
    records: dict[str, object],
    *,
    site: Site | None = None,
    starts_at: datetime = DAY_START - timedelta(hours=1),
    ends_at: datetime | None = None,
) -> Assignment:
    company = value(records, "company_a", Company)
    assignment = create_assignment(
        db_session,
        company_id=company.id,
        driver_membership_id=value(records, "driver_a", CompanyMembership).id,
        supervisor_membership_id=value(records, "supervisor_a", CompanyMembership).id,
        asset_id=value(records, "tipper_a", FleetAsset).id,
        site_id=(site or value(records, "site_a", Site)).id,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    db_session.add(
        SupervisorSiteAccess(
            company_id=company.id,
            supervisor_membership_id=assignment.supervisor_membership_id,
            site_id=assignment.site_id,
        )
    )
    db_session.flush()
    return assignment


def owner_client(
    db_session: Session,
    records: dict[str, object],
    *,
    storage: SupervisorStorage | None = None,
) -> TestClient:
    owner = user_by_name(db_session, "Owner A")
    return client_for(
        db_session,
        access_token(db_session, owner, value(records, "owner_a", CompanyMembership)),
        storage=storage,
    )


def report_template_id(client: TestClient, name: str) -> str:
    response = client.get("/api/v1/owner/report-templates")
    assert response.status_code == 200, response.text
    return cast(
        str,
        next(item["id"] for item in response.json() if item["name"] == name),
    )


def supervisor_client(db_session: Session, records: dict[str, object]) -> TestClient:
    supervisor = user_by_name(db_session, "Supervisor A")
    return client_for(
        db_session,
        access_token(
            db_session,
            supervisor,
            value(records, "supervisor_a", CompanyMembership),
        ),
    )


def create_event(
    client: TestClient,
    storage: SupervisorStorage,
    event_type: str,
    created_at: datetime,
    **extra: str,
) -> str:
    client_event_uuid = str(uuid4())
    payload_extra = dict(extra)
    if event_type in {"KM_READING", "HMR_READING", "DIESEL"}:
        uploaded = client.post(
            "/api/v1/driver/evidence",
            params={"client_event_uuid": client_event_uuid},
            files={"file": ("evidence.jpg", b"\xff\xd8\xffphase6-evidence", "image/jpeg")},
        )
        assert uploaded.status_code == 200
        payload_extra["object_reference"] = uploaded.json()["object_reference"]
    response = client.post(
        "/api/v1/driver/events",
        json=driver_event_payload(
            event_type,
            client_event_uuid=client_event_uuid,
            created_at=created_at,
            **payload_extra,
        ),
    )
    assert response.status_code == 200, response.text
    return cast(str, response.json()["event_id"])


def create_complete_tipper_day(
    client: TestClient,
    storage: SupervisorStorage,
    *,
    started_at: datetime,
    start_km: str,
    end_km: str,
    litres: str | None,
    installation_identifier: str,
) -> list[str]:
    common = {"installation_identifier": installation_identifier}
    events = [
        create_event(
            client,
            storage,
            "KM_READING",
            started_at,
            reading_type="START_READING",
            reading_value=start_km,
            **common,
        ),
        create_event(
            client,
            storage,
            "TRIP_COMPLETE",
            started_at + timedelta(hours=1),
            **common,
        ),
    ]
    if litres is not None:
        events.append(
            create_event(
                client,
                storage,
                "DIESEL",
                started_at + timedelta(hours=2),
                litres=litres,
                **common,
            )
        )
    events.append(
        create_event(
            client,
            storage,
            "KM_READING",
            started_at + timedelta(hours=3),
            reading_type="END_READING",
            reading_value=end_km,
            **common,
        )
    )
    return events


def verify(
    client: TestClient,
    event_id: str,
    decision: str = "APPROVED",
    reason: str | None = None,
) -> None:
    response = client.post(
        f"/api/v1/supervisor/events/{event_id}/verify",
        json={"decision": decision, "reason": reason},
    )
    assert response.status_code == 200, response.text


def test_owner_dashboard_reconciles_site_tipper_excel_and_roles(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    site = value(tenant_records, "site_a", Site)
    site.name = "=Unsafe Site"
    site.short_name = "=Unsafe Site"
    db_session.flush()
    add_reporting_assignment(db_session, tenant_records)
    storage = SupervisorStorage()
    driver = create_driver_client(db_session, tenant_records, storage)
    event_ids: dict[str, list[str]] = {"approved_trips": [], "pending_trips": []}
    try:
        start = create_event(
            driver,
            storage,
            "KM_READING",
            DAY_START + timedelta(hours=1),
            reading_type="START_READING",
            reading_value="10000.00",
        )
        for index in range(8):
            event_ids["approved_trips"].append(
                create_event(
                    driver,
                    storage,
                    "TRIP_COMPLETE",
                    DAY_START + timedelta(hours=2 + index),
                )
            )
        event_ids["pending_trips"].append(
            create_event(driver, storage, "TRIP_COMPLETE", DAY_START + timedelta(hours=12))
        )
        disputed = create_event(driver, storage, "TRIP_COMPLETE", DAY_START + timedelta(hours=13))
        rejected = create_event(driver, storage, "TRIP_COMPLETE", DAY_START + timedelta(hours=14))
        diesel = create_event(
            driver,
            storage,
            "DIESEL",
            DAY_START + timedelta(hours=15),
            litres="30.000",
        )
        disputed_diesel = create_event(
            driver,
            storage,
            "DIESEL",
            DAY_START + timedelta(hours=16),
            litres="5.000",
        )
        create_event(
            driver,
            storage,
            "DIESEL",
            DAY_START + timedelta(hours=17),
            litres="6.000",
        )
        emergency = create_event(
            driver,
            storage,
            "EMERGENCY",
            DAY_START + timedelta(hours=18),
            category="BREAKDOWN",
            description="Open hydraulic warning",
        )
        end = create_event(
            driver,
            storage,
            "KM_READING",
            DAY_START + timedelta(hours=22),
            reading_type="END_READING",
            reading_value="10120.00",
        )
    finally:
        driver.close()

    supervisor = supervisor_client(db_session, tenant_records)
    try:
        verify(supervisor, start)
        verify(supervisor, end)
        for event_id in event_ids["approved_trips"]:
            verify(supervisor, event_id)
        verify(supervisor, diesel)
        verify(supervisor, disputed, "DISPUTED", "Trip details need review")
        verify(supervisor, disputed_diesel, "DISPUTED", "Diesel receipt needs review")
        verify(supervisor, rejected, "REJECTED", "Rejected by site review")
    finally:
        supervisor.close()

    owner = owner_client(db_session, tenant_records, storage=storage)
    try:
        dashboard = owner.get(
            "/api/v1/reports/dashboard", params={"operational_date": REPORT_DATE.isoformat()}
        )
        assert dashboard.status_code == 200
        dashboard_data = dashboard.json()
        assert dashboard_data["approved_trip_count"] == 8
        assert dashboard_data["pending_trip_count"] == 1
        assert dashboard_data["total_km"] == "120.00"
        assert dashboard_data["verified_diesel_issued"] == "30.000"
        assert dashboard_data["pending_verification_count"] == 2
        assert dashboard_data["unresolved_emergency_count"] == 1
        assert "fuel" not in dashboard.text.lower()

        site_report = owner.get(
            f"/api/v1/reports/sites/{site.id}/daily",
            params={"operational_date": REPORT_DATE.isoformat()},
        )
        assert site_report.status_code == 200
        assert site_report.json()["approved_trip_count"] == dashboard_data["approved_trip_count"]
        tipper_report = owner.get(
            f"/api/v1/reports/tippers/{value(tenant_records, 'tipper_a', FleetAsset).id}/daily",
            params={"operational_date": REPORT_DATE.isoformat()},
        )
        assert tipper_report.status_code == 200
        tipper_data = tipper_report.json()[0]
        assert tipper_data["approved_trip_count"] == 8
        assert tipper_data["disputed_trip_count"] == 1
        assert tipper_data["rejected_trip_count"] == 1
        assert tipper_data["km_per_approved_trip"] == "15.00"
        assert tipper_data["diesel_issued_per_approved_trip"] == "3.750"
        assert tipper_data["recorded_activity_span_seconds"] == 25_200.0
        assert tipper_data["avg_trip_completion_interval_seconds"] == 3_600.0
        assert tipper_data["median_trip_completion_interval_seconds"] == 3_600.0
        assert tipper_data["longest_trip_gap_seconds"] == 3_600.0
        assert tipper_data["pending_diesel_count"] == 1
        assert tipper_data["disputed_diesel_count"] == 1
        assert tipper_data["closure_status"] == "OPEN"
        foreign_site = value(tenant_records, "site_b", Site)
        assert (
            owner.get(
                f"/api/v1/reports/sites/{foreign_site.id}/daily",
                params={"operational_date": REPORT_DATE.isoformat()},
            ).status_code
            == 404
        )
        evidence = owner.get(f"/api/v1/reports/events/{start}/evidence")
        assert evidence.status_code == 200
        assert evidence.content == b"\xff\xd8\xffphase6-evidence"
        assert evidence.headers["content-type"] == "image/jpeg"
        assert evidence.headers["cache-control"] == "private, no-store"
        assert evidence.headers["x-fleet-evidence-event-type"] == "KM_READING"
        assert evidence.headers["x-fleet-evidence-driver"] == "Driver A"
        exceptions = owner.get(
            "/api/v1/reports/exceptions", params={"operational_date": REPORT_DATE.isoformat()}
        )
        assert exceptions.status_code == 200
        exception_codes = {item["code"] for item in exceptions.json()}
        assert {"TRIP_PENDING", "DIESEL_PENDING", "UNRESOLVED_EMERGENCY"} <= exception_codes

        workbook_response = owner.get(
            "/api/v1/reports/daily.xlsx",
            params={
                "operational_date": REPORT_DATE.isoformat(),
                "template_id": report_template_id(owner, "Detailed Operations"),
            },
        )
        assert workbook_response.status_code == 200
        workbook = load_workbook(BytesIO(workbook_response.content), data_only=False)
        assert workbook.sheetnames == [
            "Management Dashboard",
            "Tipper Daily",
            "Machinery Daily",
            "Trip Register",
            "Meter Readings",
            "Diesel Register",
            "Duty Register",
            "Exceptions",
        ]
        assert workbook["Duty Register"]["A4"].value == "Date"
        assert workbook["Tipper Daily"]["B5"].value == "'=Unsafe Site"
        tipper_headers = [cell.value for cell in workbook["Tipper Daily"][4]]
        tipper_values = dict(
            zip(
                tipper_headers,
                next(workbook["Tipper Daily"].iter_rows(min_row=5, values_only=True)),
                strict=True,
            )
        )
        assert tipper_values["Distance KM"] == 120
        assert tipper_values["Approved Trips"] == 8
        assert tipper_values["Diesel L"] == 30
        assert workbook["Management Dashboard"]["A4"].value == "Asset"
        dashboard_headers = [cell.value for cell in workbook["Management Dashboard"][4]]
        dashboard_values = dict(
            zip(
                dashboard_headers,
                next(workbook["Management Dashboard"].iter_rows(min_row=5, values_only=True)),
                strict=True,
            )
        )
        assert dashboard_values["Distance KM"] == 120
        assert dashboard_values["Verified Diesel L"] == 30
        assert workbook["Management Dashboard"].freeze_panes == "A5"
        assert workbook["Management Dashboard"].max_column == 10
        trip_rows = list(workbook["Trip Register"].iter_rows(min_row=5, values_only=True))
        assert len(trip_rows) == 11
        assert (
            sum(1 for row in trip_rows if row[6] == "APPROVED")
            == dashboard_data["approved_trip_count"]
        )
        assert workbook["Tipper Daily"].freeze_panes == "A5"
        assert workbook["Tipper Daily"].auto_filter.ref
        meter_rows = list(workbook["Meter Readings"].iter_rows(min_row=5, values_only=True))
        diesel_rows = list(workbook["Diesel Register"].iter_rows(min_row=5, values_only=True))
        assert any(
            isinstance(row[11], str)
            and row[11].startswith('=HYPERLINK("http://localhost:3000/evidence/')
            and str(start) in row[11]
            and "Open Evidence" in row[11]
            and "Authorization" not in row[11]
            for row in meter_rows
        )
        assert any(
            isinstance(row[8], str)
            and row[8].startswith('=HYPERLINK("http://localhost:3000/evidence/')
            and str(diesel) in row[8]
            and "Open Evidence" in row[8]
            and "object" not in row[8].lower()
            for row in diesel_rows
        )

        simple_response = owner.get(
            f"/api/v1/reports/sites/{site.id}/simple-workbook.xlsx",
            params={
                "from_date": REPORT_DATE.isoformat(),
                "to_date": REPORT_DATE.isoformat(),
            },
        )
        assert simple_response.status_code == 200, simple_response.text
        simple = load_workbook(BytesIO(simple_response.content), data_only=False)
        assert simple.sheetnames == ["SUMMARY", "Alpha One"]
        assert simple["SUMMARY"]["B4"].value == "'=Unsafe Site"
        summary_row = next(simple["SUMMARY"].iter_rows(min_row=9, max_row=9, values_only=True))
        summary_headers = [cell.value for cell in simple["SUMMARY"][8]]
        summary_values = dict(zip(summary_headers, summary_row, strict=True))
        assert summary_values["Approved Trips"] == 8
        assert summary_values["Distance KM"] == 120
        assert summary_values["Diesel Recorded L"] == 30
        assert summary_values["Pending / Exceptions"] == "2 pending / 3 exceptions"
        site_totals = {
            row[0]: row[1]
            for row in simple["SUMMARY"].iter_rows(min_row=13, max_row=22, values_only=True)
        }
        assert site_totals["Pending Items"] == 2
        assert site_totals["Exceptions"] == 3
        simple_header_row = next(
            row[0].row for row in simple["Alpha One"] if row[0].value == "Date"
        )
        simple_headers = [cell.value for cell in simple["Alpha One"][simple_header_row]]
        simple_values = dict(
            zip(
                simple_headers,
                next(
                    simple["Alpha One"].iter_rows(
                        min_row=simple_header_row + 1,
                        max_row=simple_header_row + 1,
                        values_only=True,
                    )
                ),
                strict=True,
            )
        )
        assert simple_values["Distance per Litre Recorded"] == 4
        assert (
            "PENDING_VERIFICATION: DIESEL, TRIP_COMPLETE"
            in simple_values["Pending / Exception Status"]
        )
        assert "DISPUTED: DIESEL, TRIP_COMPLETE" in simple_values["Pending / Exception Status"]
        assert "REJECTED: TRIP_COMPLETE" in simple_values["Pending / Exception Status"]
        assert "UNRESOLVED_EMERGENCY" in simple_values["Pending / Exception Status"]
    finally:
        owner.close()

    supervisor_resolver = supervisor_client(db_session, tenant_records)
    try:
        acknowledged = supervisor_resolver.post(
            f"/api/v1/supervisor/events/{emergency}/emergency/acknowledge"
        )
        assert acknowledged.status_code == 200
        resolved = supervisor_resolver.post(
            f"/api/v1/supervisor/events/{emergency}/emergency/resolve"
        )
        assert resolved.status_code == 200
    finally:
        supervisor_resolver.close()

    owner_after_resolution = owner_client(db_session, tenant_records, storage=storage)
    try:
        resolved_dashboard = owner_after_resolution.get(
            "/api/v1/reports/dashboard", params={"operational_date": REPORT_DATE.isoformat()}
        )
        assert resolved_dashboard.status_code == 200
        assert resolved_dashboard.json()["pending_verification_count"] == 2
        assert resolved_dashboard.json()["unresolved_emergency_count"] == 0
    finally:
        owner_after_resolution.close()

    driver_again = create_driver_client(db_session, tenant_records, storage)
    try:
        assert driver_again.get("/api/v1/reports/dashboard").status_code == 403
    finally:
        driver_again.close()
    supervisor_again = supervisor_client(db_session, tenant_records)
    try:
        assert supervisor_again.get("/api/v1/reports/dashboard").status_code == 403
    finally:
        supervisor_again.close()


def test_simple_site_workbook_preserves_historical_site_and_driver_rows(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    company.reporting_timezone = "UTC"
    company.operational_day_start_minutes = 0
    first_site = value(tenant_records, "site_a", Site)
    first_site.short_name = "Site A Short"
    second_site = Site(
        company_id=company.id,
        name="Second Historical Site",
        short_name="Site B Short",
        code="SITE-B-HISTORY",
        status=SiteStatus.ACTIVE,
    )
    db_session.add(second_site)
    db_session.flush()
    db_session.add(
        SupervisorSiteAccess(
            company_id=company.id,
            supervisor_membership_id=value(tenant_records, "supervisor_a", CompanyMembership).id,
            site_id=second_site.id,
        )
    )
    value(tenant_records, "driver_a", CompanyMembership).display_name = "Historical Driver A"
    value(tenant_records, "driver_a2", CompanyMembership).display_name = "Historical Driver B"

    first_boundary = datetime(2025, 1, 16, tzinfo=UTC)
    second_boundary = datetime(2025, 1, 17, tzinfo=UTC)
    first_assignment = add_reporting_assignment(
        db_session,
        tenant_records,
        starts_at=datetime(2025, 1, 14, tzinfo=UTC),
    )
    storage = SupervisorStorage()
    event_ids: list[str] = []
    first_driver = create_driver_client(db_session, tenant_records, storage)
    try:
        event_ids.extend(
            create_complete_tipper_day(
                first_driver,
                storage,
                started_at=datetime(2025, 1, 15, 8, tzinfo=UTC),
                start_km="100",
                end_km="110",
                litres="5",
                installation_identifier="historical-driver-a",
            )
        )
    finally:
        first_driver.close()

    first_assignment.ends_at = first_boundary
    second_assignment = create_assignment(
        db_session,
        company_id=company.id,
        driver_membership_id=value(tenant_records, "driver_a2", CompanyMembership).id,
        supervisor_membership_id=value(tenant_records, "supervisor_a", CompanyMembership).id,
        asset_id=value(tenant_records, "tipper_a", FleetAsset).id,
        site_id=first_site.id,
        starts_at=first_boundary,
    )
    db_session.flush()
    second_driver = client_for(
        db_session,
        session_for_user(
            db_session,
            user_by_name(db_session, "Driver A2"),
            value(tenant_records, "driver_a2", CompanyMembership),
        ),
        storage=storage,
    )
    try:
        event_ids.extend(
            create_complete_tipper_day(
                second_driver,
                storage,
                started_at=datetime(2025, 1, 16, 8, tzinfo=UTC),
                start_km="110",
                end_km="125",
                litres="6",
                installation_identifier="historical-driver-a2",
            )
        )
    finally:
        second_driver.close()

    second_assignment.ends_at = second_boundary
    first_deployment = db_session.get(
        AssetSiteDeployment, first_assignment.asset_site_deployment_id
    )
    assert first_deployment is not None
    first_deployment.ends_at = second_boundary
    third_assignment = create_assignment(
        db_session,
        company_id=company.id,
        driver_membership_id=value(tenant_records, "driver_a2", CompanyMembership).id,
        supervisor_membership_id=value(tenant_records, "supervisor_a", CompanyMembership).id,
        asset_id=value(tenant_records, "tipper_a", FleetAsset).id,
        site_id=second_site.id,
        starts_at=second_boundary,
    )
    db_session.flush()
    third_driver = client_for(
        db_session,
        session_for_user(
            db_session,
            user_by_name(db_session, "Driver A2"),
            value(tenant_records, "driver_a2", CompanyMembership),
        ),
        storage=storage,
    )
    try:
        event_ids.extend(
            create_complete_tipper_day(
                third_driver,
                storage,
                started_at=datetime(2025, 1, 17, 8, tzinfo=UTC),
                start_km="125",
                end_km="145",
                litres=None,
                installation_identifier="historical-driver-a2",
            )
        )
    finally:
        third_driver.close()
    assert third_assignment.site_id == second_site.id

    supervisor = supervisor_client(db_session, tenant_records)
    try:
        for event_id in event_ids:
            verify(supervisor, event_id)
    finally:
        supervisor.close()

    owner = owner_client(db_session, tenant_records, storage=storage)
    params = {"from_date": "2025-01-15", "to_date": "2025-01-17"}
    try:
        first_response = owner.get(
            f"/api/v1/reports/sites/{first_site.id}/simple-workbook.xlsx",
            params=params,
        )
        assert first_response.status_code == 200, first_response.text
        assert (
            "Site-A-Short-2025-01-15-to-2025-01-17.xlsx"
            in first_response.headers["content-disposition"]
        )
        first_workbook = load_workbook(BytesIO(first_response.content), data_only=False)
        assert first_workbook.sheetnames == ["SUMMARY", "Alpha One"]
        assert first_workbook["SUMMARY"]["B4"].value == "Site A Short"
        first_summary_headers = [cell.value for cell in first_workbook["SUMMARY"][8]]
        first_summary_row = next(
            first_workbook["SUMMARY"].iter_rows(min_row=9, max_row=9, values_only=True)
        )
        first_summary = dict(zip(first_summary_headers, first_summary_row, strict=True))
        assert first_summary["Driver / Operator"] == "Multiple — see daily records"
        assert first_summary["Days Worked"] == 2
        assert first_summary["Approved Trips"] == 2
        assert first_summary["Distance KM"] == 25
        assert first_summary["Diesel Recorded L"] == 11
        first_sheet = first_workbook["Alpha One"]
        assert (
            next(
                row[1]
                for row in first_sheet.iter_rows(min_row=4, max_row=10, values_only=True)
                if row[0] == "Selected Site"
            )
            == "Site A Short"
        )
        assert (
            next(
                row[1]
                for row in first_sheet.iter_rows(min_row=4, max_row=10, values_only=True)
                if row[0] == "Driver / Operator"
            )
            == "Multiple — see daily records"
        )
        first_header_row = next(row[0].row for row in first_sheet if row[0].value == "Date")
        first_headers = [cell.value for cell in first_sheet[first_header_row]]
        first_daily = [
            dict(zip(first_headers, row, strict=True))
            for row in first_sheet.iter_rows(
                min_row=first_header_row + 1,
                max_row=first_header_row + 2,
                values_only=True,
            )
        ]
        assert [item["Date"].date() for item in first_daily] == [
            date(2025, 1, 15),
            date(2025, 1, 16),
        ]
        assert [item["Driver"] for item in first_daily] == [
            "Historical Driver A",
            "Historical Driver B",
        ]
        assert [item["Distance KM"] for item in first_daily] == [10, 15]
        first_period = {
            row[0]: row[1]
            for row in first_sheet.iter_rows(min_row=13, max_row=19, values_only=True)
        }
        assert first_period["Average Trips / Working Day"] == 1
        assert first_period["Average Distance / Working Day"] == 12.5
        assert first_period["Distance per Litre Recorded"] == pytest.approx(25 / 11)

        second_response = owner.get(
            f"/api/v1/reports/sites/{second_site.id}/simple-workbook.xlsx",
            params=params,
        )
        assert second_response.status_code == 200, second_response.text
        second_workbook = load_workbook(BytesIO(second_response.content), data_only=False)
        assert second_workbook.sheetnames == ["SUMMARY", "Alpha One"]
        second_headers = [cell.value for cell in second_workbook["SUMMARY"][8]]
        second_row = next(
            second_workbook["SUMMARY"].iter_rows(min_row=9, max_row=9, values_only=True)
        )
        second_summary = dict(zip(second_headers, second_row, strict=True))
        assert second_summary["Driver / Operator"] == "Historical Driver B"
        assert second_summary["Days Worked"] == 1
        assert second_summary["Approved Trips"] == 1
        assert second_summary["Distance KM"] == 20
        assert second_summary["Diesel Recorded L"] == 0
        second_sheet = second_workbook["Alpha One"]
        second_header_row = next(row[0].row for row in second_sheet if row[0].value == "Date")
        only_second_site_row = next(
            second_sheet.iter_rows(
                min_row=second_header_row + 1,
                max_row=second_header_row + 1,
                values_only=True,
            )
        )
        assert only_second_site_row[0].date() == date(2025, 1, 17)
        assert only_second_site_row[6] == 20
        second_daily_headers = [cell.value for cell in second_sheet[second_header_row]]
        second_daily = dict(zip(second_daily_headers, only_second_site_row, strict=True))
        assert second_daily["Diesel Recorded L"] == 0
        assert second_daily["Distance per Litre Recorded"] == "N/A"
        second_period = {
            row[0]: row[1]
            for row in second_sheet.iter_rows(min_row=13, max_row=19, values_only=True)
        }
        assert second_period["Distance per Litre Recorded"] == "N/A"

        value(tenant_records, "driver_a", CompanyMembership).display_name = "Same Name"
        value(tenant_records, "driver_a2", CompanyMembership).display_name = "Same Name"
        db_session.flush()
        collision_response = owner.get(
            f"/api/v1/reports/sites/{first_site.id}/simple-workbook.xlsx",
            params=params,
        )
        assert collision_response.status_code == 200, collision_response.text
        collision_workbook = load_workbook(BytesIO(collision_response.content), data_only=False)
        collision_headers = [cell.value for cell in collision_workbook["SUMMARY"][8]]
        collision_row = next(
            collision_workbook["SUMMARY"].iter_rows(min_row=9, max_row=9, values_only=True)
        )
        collision_summary = dict(zip(collision_headers, collision_row, strict=True))
        assert collision_summary["Driver / Operator"] == "Multiple — see daily records"
    finally:
        owner.close()


def test_simple_site_workbook_includes_unassigned_assets_and_sanitizes_excel(
    db_session: Session,
    tenant_records: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company = value(tenant_records, "company_a", Company)
    site = value(tenant_records, "site_a", Site)
    site.short_name = "+Unsafe Site Short"
    deployed_at = datetime(2025, 1, 1, tzinfo=UTC)
    repeated_name = "=Very/Long:*?[] Asset\x02 Name That Exceeds Thirty One Characters"
    assets = [
        create_fleet_asset(
            db_session,
            company_id=company.id,
            asset_type=FleetAssetType.ROLLER,
            ownership_type=AssetOwnershipType.OWNED,
            asset_code="SUMMARY-ASSET",
            registration_number=None,
            short_name="SUMMARY",
            manufacturer="@Unsafe Manufacturer\x01",
            model="Model 1",
        ),
        create_fleet_asset(
            db_session,
            company_id=company.id,
            asset_type=FleetAssetType.ROLLER,
            ownership_type=AssetOwnershipType.RENTED,
            asset_code="DUPLICATE-A",
            registration_number=None,
            short_name=repeated_name,
            model="-Unsafe Model",
        ),
        create_fleet_asset(
            db_session,
            company_id=company.id,
            asset_type=FleetAssetType.ROLLER,
            ownership_type=AssetOwnershipType.OWNED,
            asset_code="DUPLICATE-B",
            registration_number=None,
            short_name=repeated_name,
        ),
    ]
    db_session.add_all(
        [
            AssetSiteDeployment(
                company_id=company.id,
                asset_id=asset.id,
                site_id=site.id,
                starts_at=deployed_at,
            )
            for asset in assets
        ]
    )
    foreign_company = value(tenant_records, "company_b", Company)
    foreign_site = value(tenant_records, "site_b", Site)
    foreign_asset = value(tenant_records, "tipper_b", FleetAsset)
    db_session.add(
        AssetSiteDeployment(
            company_id=foreign_company.id,
            asset_id=foreign_asset.id,
            site_id=foreign_site.id,
            starts_at=deployed_at,
        )
    )
    db_session.flush()

    owner = owner_client(db_session, tenant_records)
    params = {"from_date": "2025-01-15", "to_date": "2025-01-15"}
    try:
        response = owner.get(f"/api/v1/reports/sites/{site.id}/simple-workbook.xlsx", params=params)
        assert response.status_code == 200, response.text
        assert (
            "Unsafe-Site-Short-2025-01-15-to-2025-01-15.xlsx"
            in response.headers["content-disposition"]
        )
        workbook = load_workbook(BytesIO(response.content), data_only=False)
        assert workbook.sheetnames[0] == "SUMMARY"
        assert len(workbook.sheetnames) == 1 + len(assets)
        assert len({name.casefold() for name in workbook.sheetnames}) == len(workbook.sheetnames)
        assert all(len(name) <= 31 for name in workbook.sheetnames)
        assert all(not set("[]:*?/\\") & set(name) for name in workbook.sheetnames)
        assert "SUMMARY (2)" in workbook.sheetnames
        assert all(not name.startswith(("=", "+", "-", "@")) for name in workbook.sheetnames)
        duplicate_sheets = [name for name in workbook.sheetnames if name.startswith("_Very_Long")]
        assert len(duplicate_sheets) == 2
        assert duplicate_sheets[1].endswith(" (2)")
        assert workbook["SUMMARY"]["B4"].value == "'+Unsafe Site Short"

        summary_headers = [cell.value for cell in workbook["SUMMARY"][8]]
        summary_rows = [
            dict(zip(summary_headers, row, strict=True))
            for row in workbook["SUMMARY"].iter_rows(
                min_row=9,
                max_row=8 + len(assets),
                values_only=True,
            )
        ]
        assert all(item["Days Worked"] == 0 for item in summary_rows)
        assert all(item["Driver / Operator"] == "N/A" for item in summary_rows)
        assert all(item["Approved Trips"] == "N/A" for item in summary_rows)
        assert all(item["Distance KM"] == "MISSING" for item in summary_rows)
        assert all(item["Machine Hours"] == "MISSING" for item in summary_rows)
        assert {item["Ownership"] for item in summary_rows} == {"OWNED", "RENTED"}
        injected_assets = [item["Asset"] for item in summary_rows if "Very/Long" in item["Asset"]]
        assert len(injected_assets) == 2
        assert all(value.startswith("'=") for value in injected_assets)

        summary_asset_sheet = workbook["SUMMARY (2)"]
        assert summary_asset_sheet["B4"].value == "SUMMARY"
        assert summary_asset_sheet["B8"].value == "'@Unsafe Manufacturer / Model 1"
        assert "'-Unsafe Model" in {workbook[name]["B8"].value for name in workbook.sheetnames[1:]}
        repeated_asset_sheet = workbook[duplicate_sheets[0]]
        period_values = {
            row[0]: row[1]
            for row in repeated_asset_sheet.iter_rows(min_row=13, max_row=24, values_only=True)
            if row[0] is not None
        }
        assert period_values["Working Days"] == 0
        assert period_values["Total Machine Hours"] == "MISSING"
        assert period_values["Diesel Recorded L"] == 0
        assert period_values["Average Machine Hours / Working Day"] == "N/A"
        assert period_values["Litres Recorded / Machine Hour"] == "N/A"
        daily_header_row = next(
            row[0].row for row in repeated_asset_sheet if row[0].value == "Date"
        )
        assert repeated_asset_sheet.max_row == daily_header_row

        all_text = "\n".join(
            str(cell.value)
            for worksheet in workbook.worksheets
            for row in worksheet.iter_rows()
            for cell in row
            if cell.value is not None
        )
        assert "Beta One" not in all_text
        assert "BETA-ONE" not in all_text
        assert "\x01" not in all_text
        assert "\x02" not in all_text

        repeated_response = owner.get(
            f"/api/v1/reports/sites/{site.id}/simple-workbook.xlsx", params=params
        )
        assert repeated_response.status_code == 200, repeated_response.text
        repeated_workbook = load_workbook(BytesIO(repeated_response.content), data_only=False)
        assert repeated_workbook.sheetnames == workbook.sheetnames

        reversed_range = owner.get(
            f"/api/v1/reports/sites/{site.id}/simple-workbook.xlsx",
            params={"from_date": "2025-01-16", "to_date": "2025-01-15"},
        )
        assert reversed_range.status_code == 422

        def empty_site_daily(
            _service: ReportingService,
            _site_id: object,
            requested_date: date,
        ) -> object:
            return SimpleNamespace(
                operational_day=SimpleNamespace(
                    reporting_timezone=company.reporting_timezone,
                    operational_date=requested_date,
                ),
                rows=[],
            )

        monkeypatch.setattr(ReportingService, "site_daily", empty_site_daily)
        boundary_range = owner.get(
            f"/api/v1/reports/sites/{site.id}/simple-workbook.xlsx",
            params={"from_date": "2025-01-01", "to_date": "2026-01-01"},
        )
        assert boundary_range.status_code == 200, boundary_range.text
        assert load_workbook(BytesIO(boundary_range.content)).sheetnames == workbook.sheetnames
        too_long = owner.get(
            f"/api/v1/reports/sites/{site.id}/simple-workbook.xlsx",
            params={"from_date": "2025-01-01", "to_date": "2026-01-02"},
        )
        assert too_long.status_code == 422
        assert "cannot exceed 366 operational days" in too_long.text
        minimum_date = owner.get(
            f"/api/v1/reports/sites/{site.id}/simple-workbook.xlsx",
            params={"from_date": "0001-01-01", "to_date": "0001-01-01"},
        )
        assert minimum_date.status_code == 422
        assert "outside the supported operational date range" in minimum_date.text
        assert (
            owner.get(
                f"/api/v1/reports/sites/{foreign_site.id}/simple-workbook.xlsx",
                params=params,
            ).status_code
            == 404
        )
    finally:
        owner.close()

    supervisor = supervisor_client(db_session, tenant_records)
    try:
        assert (
            supervisor.get(
                f"/api/v1/reports/sites/{site.id}/simple-workbook.xlsx",
                params=params,
            ).status_code
            == 403
        )
    finally:
        supervisor.close()


def test_simple_site_workbook_keeps_same_day_transfers_and_authoritative_session_aggregate(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    company.reporting_timezone = "UTC"
    company.operational_day_start_minutes = 0
    site = value(tenant_records, "site_a", Site)
    transfer_at = datetime(2025, 1, 15, 12, tzinfo=UTC)
    first_assignment = add_reporting_assignment(
        db_session,
        tenant_records,
        starts_at=datetime(2025, 1, 15, tzinfo=UTC),
    )
    storage = SupervisorStorage()
    first_driver = create_driver_client(db_session, tenant_records, storage)
    try:
        first_events = create_complete_tipper_day(
            first_driver,
            storage,
            started_at=datetime(2025, 1, 15, 1, tzinfo=UTC),
            start_km="100",
            end_km="120",
            litres="20",
            installation_identifier="same-day-driver-a",
        )
    finally:
        first_driver.close()

    first_assignment.ends_at = transfer_at
    db_session.flush()
    second_assignment = create_assignment(
        db_session,
        company_id=company.id,
        driver_membership_id=value(tenant_records, "driver_a2", CompanyMembership).id,
        supervisor_membership_id=value(tenant_records, "supervisor_a", CompanyMembership).id,
        asset_id=value(tenant_records, "tipper_a", FleetAsset).id,
        site_id=site.id,
        starts_at=transfer_at,
    )
    emergency_asset = create_fleet_asset(
        db_session,
        company_id=company.id,
        asset_type=FleetAssetType.TIPPER,
        ownership_type=AssetOwnershipType.OWNED,
        asset_code="EMERGENCY-ONLY",
        registration_number=None,
        short_name="Emergency Only",
    )
    create_assignment(
        db_session,
        company_id=company.id,
        driver_membership_id=value(tenant_records, "driver_a", CompanyMembership).id,
        supervisor_membership_id=value(tenant_records, "supervisor_a", CompanyMembership).id,
        asset_id=emergency_asset.id,
        site_id=site.id,
        starts_at=transfer_at,
    )
    db_session.flush()

    second_driver = client_for(
        db_session,
        session_for_user(
            db_session,
            user_by_name(db_session, "Driver A2"),
            value(tenant_records, "driver_a2", CompanyMembership),
        ),
        storage=storage,
    )
    try:
        second_events = [
            create_event(
                second_driver,
                storage,
                "KM_READING",
                datetime(2025, 1, 15, 13, tzinfo=UTC),
                reading_type="START_READING",
                reading_value="120",
                installation_identifier="same-day-driver-b",
            ),
            create_event(
                second_driver,
                storage,
                "TRIP_COMPLETE",
                datetime(2025, 1, 15, 14, tzinfo=UTC),
                installation_identifier="same-day-driver-b",
            ),
            create_event(
                second_driver,
                storage,
                "KM_READING",
                datetime(2025, 1, 15, 15, tzinfo=UTC),
                reading_type="END_READING",
                reading_value="130",
                installation_identifier="same-day-driver-b",
            ),
            create_event(
                second_driver,
                storage,
                "KM_READING",
                datetime(2025, 1, 15, 16, tzinfo=UTC),
                reading_type="START_READING",
                reading_value="130",
                installation_identifier="same-day-driver-b",
            ),
            create_event(
                second_driver,
                storage,
                "DIESEL",
                datetime(2025, 1, 15, 17, tzinfo=UTC),
                litres="20",
                installation_identifier="same-day-driver-b",
            ),
        ]
        disputed_session_end = create_event(
            second_driver,
            storage,
            "KM_READING",
            datetime(2025, 1, 15, 18, tzinfo=UTC),
            reading_type="END_READING",
            reading_value="135",
            installation_identifier="same-day-driver-b",
        )
    finally:
        second_driver.close()

    emergency_driver = create_driver_client(db_session, tenant_records, storage)
    try:
        create_event(
            emergency_driver,
            storage,
            "EMERGENCY",
            datetime(2025, 1, 15, 16, tzinfo=UTC),
            category="BREAKDOWN",
            description="Emergency without operational work",
            installation_identifier="emergency-only-driver",
        )
    finally:
        emergency_driver.close()

    supervisor = supervisor_client(db_session, tenant_records)
    try:
        for event_id in [*first_events, *second_events]:
            verify(supervisor, event_id)
        verify(
            supervisor,
            disputed_session_end,
            "DISPUTED",
            "Second session end meter needs review",
        )
    finally:
        supervisor.close()
    assert (
        db_session.query(DutySession)
        .filter(DutySession.assignment_id == second_assignment.id)
        .count()
        == 2
    )

    owner = owner_client(db_session, tenant_records, storage=storage)
    try:
        response = owner.get(
            f"/api/v1/reports/sites/{site.id}/simple-workbook.xlsx",
            params={"from_date": "2025-01-15", "to_date": "2025-01-15"},
        )
        assert response.status_code == 200, response.text
        workbook = load_workbook(BytesIO(response.content), data_only=False)
        summary_headers = [cell.value for cell in workbook["SUMMARY"][8]]
        summary = {
            row[0]: dict(zip(summary_headers, row, strict=True))
            for row in workbook["SUMMARY"].iter_rows(min_row=9, max_row=10, values_only=True)
        }
        assert summary["Alpha One"]["Driver / Operator"] == ("Multiple — see daily records")
        assert summary["Alpha One"]["Days Worked"] == 1
        assert summary["Alpha One"]["Approved Trips"] == 2
        assert summary["Alpha One"]["Distance KM"] == 30
        assert summary["Alpha One"]["Diesel Recorded L"] == 40
        assert summary["Alpha One"]["Pending / Exceptions"] == "0 pending / 1 exceptions"
        assert summary["Emergency Only"]["Days Worked"] == 0

        tipper_sheet = workbook["Alpha One"]
        header_row = next(row[0].row for row in tipper_sheet if row[0].value == "Date")
        headers = [cell.value for cell in tipper_sheet[header_row]]
        daily_rows = [
            dict(zip(headers, row, strict=True))
            for row in tipper_sheet.iter_rows(
                min_row=header_row + 1,
                max_row=header_row + 2,
                values_only=True,
            )
        ]
        assert len(daily_rows) == 2
        assert {row["Date"].date() for row in daily_rows} == {date(2025, 1, 15)}
        assert daily_rows[0]["Driver"] == "Driver A"
        assert daily_rows[0]["Distance KM"] == 20
        assert daily_rows[1]["Driver"] == "Driver A2"
        assert daily_rows[1]["End KM"] == 130
        assert daily_rows[1]["Distance KM"] == 10
        assert daily_rows[1]["Distance per Litre Recorded"] == pytest.approx(0.5)
        assert "DISPUTED: KM_READING" in daily_rows[1]["Pending / Exception Status"]

        period = {
            row[0]: row[1]
            for row in tipper_sheet.iter_rows(min_row=13, max_row=19, values_only=True)
        }
        assert period["Working Days"] == 1
        assert period["Total Distance KM"] == 30
        assert period["Average Distance / Working Day"] == 30
        assert period["Distance per Litre Recorded"] == pytest.approx(0.75)
        site_totals = {
            row[0]: row[1]
            for row in workbook["SUMMARY"].iter_rows(min_row=14, max_row=23, values_only=True)
        }
        assert site_totals["Total Working Days / asset-days"] == 1
        assert site_totals["Total Distance KM"] == "MISSING"

        emergency_period = {
            row[0]: row[1]
            for row in workbook["Emergency Only"].iter_rows(
                min_row=13, max_row=19, values_only=True
            )
        }
        assert emergency_period["Working Days"] == 0
    finally:
        owner.close()


def test_mixed_tipper_and_machinery_report_is_capability_aware(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    company.reporting_timezone = "Asia/Kolkata"
    site = value(tenant_records, "site_a", Site)
    tipper_assignment = add_reporting_assignment(db_session, tenant_records)
    excavator = create_fleet_asset(
        db_session,
        company_id=company.id,
        asset_type=FleetAssetType.EXCAVATOR,
        ownership_type=AssetOwnershipType.RENTED,
        asset_code="EXC-01",
        registration_number=None,
        short_name="CAT 320",
    )
    machinery_assignment = create_assignment(
        db_session,
        company_id=company.id,
        driver_membership_id=value(tenant_records, "driver_a2", CompanyMembership).id,
        supervisor_membership_id=value(tenant_records, "supervisor_a", CompanyMembership).id,
        asset_id=excavator.id,
        site_id=site.id,
        starts_at=DAY_START - timedelta(hours=1),
    )
    storage = SupervisorStorage()
    tipper_driver = create_driver_client(db_session, tenant_records, storage)
    machinery_driver = client_for(
        db_session,
        session_for_user(
            db_session,
            user_by_name(db_session, "Driver A2"),
            value(tenant_records, "driver_a2", CompanyMembership),
        ),
        storage=storage,
    )
    events: list[str] = []
    try:
        events.append(
            create_event(
                tipper_driver,
                storage,
                "KM_READING",
                DAY_START + timedelta(hours=1),
                reading_type="START_READING",
                reading_value="20000",
            )
        )
        for hour in range(2, 5):
            events.append(
                create_event(
                    tipper_driver,
                    storage,
                    "TRIP_COMPLETE",
                    DAY_START + timedelta(hours=hour),
                )
            )
        events.append(
            create_event(
                tipper_driver,
                storage,
                "KM_READING",
                DAY_START + timedelta(hours=5),
                reading_type="END_READING",
                reading_value="20040",
            )
        )
        events.append(
            create_event(
                tipper_driver,
                storage,
                "KM_READING",
                DAY_START + timedelta(hours=6),
                reading_type="START_READING",
                reading_value="20040",
            )
        )
        for hour in range(7, 10):
            events.append(
                create_event(
                    tipper_driver,
                    storage,
                    "TRIP_COMPLETE",
                    DAY_START + timedelta(hours=hour),
                )
            )
        events.append(
            create_event(
                tipper_driver,
                storage,
                "DIESEL",
                DAY_START + timedelta(hours=10),
                litres="20",
            )
        )
        events.append(
            create_event(
                tipper_driver,
                storage,
                "KM_READING",
                DAY_START + timedelta(hours=11),
                reading_type="END_READING",
                reading_value="20100",
            )
        )
        events.append(
            create_event(
                machinery_driver,
                storage,
                "HMR_READING",
                DAY_START + timedelta(hours=1, minutes=30),
                reading_type="START_READING",
                reading_value="1000",
                installation_identifier="machinery-report-device",
            )
        )
        events.append(
            create_event(
                machinery_driver,
                storage,
                "DIESEL",
                DAY_START + timedelta(hours=3),
                litres="10",
                installation_identifier="machinery-report-device",
            )
        )
        pending_hmr = create_event(
            machinery_driver,
            storage,
            "HMR_READING",
            DAY_START + timedelta(hours=3),
            reading_type="END_READING",
            reading_value="1001.5",
            installation_identifier="machinery-report-device",
        )
    finally:
        tipper_driver.close()
        machinery_driver.close()

    supervisor = supervisor_client(db_session, tenant_records)
    try:
        for event_id in events:
            verify(supervisor, event_id)
    finally:
        supervisor.close()
    assert (
        db_session.query(DutySession)
        .filter(DutySession.assignment_id == tipper_assignment.id)
        .count()
        == 2
    )

    owner = owner_client(db_session, tenant_records, storage=storage)
    try:
        params = {"operational_date": REPORT_DATE.isoformat()}
        dashboard = owner.get("/api/v1/reports/dashboard", params=params)
        assert dashboard.status_code == 200, dashboard.text
        report_rows = {
            item["assignment_id"]: item
            for site_report in dashboard.json()["sites"]
            for item in site_report["tippers"]
        }
        tipper = report_rows[str(tipper_assignment.id)]
        machinery = report_rows[str(machinery_assignment.id)]
        assert tipper["approved_trip_count"] == 6
        assert tipper["distance_km"] == "100.00"
        assert tipper["machine_hours"] is None
        assert tipper["machine_hours_state"] == "NOT_APPLICABLE"
        assert tipper["verified_diesel_issued"] == "20.000"
        assert machinery["approved_trip_count"] is None
        assert machinery["trips_state"] == "NOT_APPLICABLE"
        assert machinery["distance_km"] is None
        assert machinery["distance_state"] == "NOT_APPLICABLE"
        assert machinery["start_hmr"] == "1000.00"
        assert machinery["end_hmr"] == "1001.50"
        assert machinery["machine_hours"] == "1.50"
        assert machinery["machine_hours_state"] == "VALUE"
        assert machinery["verified_diesel_issued"] == "10.000"
        assert machinery["missing_start_reading"] is False
        assert machinery["missing_end_reading"] is False
        assert not {
            "MISSING_START_READING",
            "MISSING_END_READING",
            "MISSING_START_HMR",
            "MISSING_END_HMR",
        } & {item["code"] for item in machinery["exceptions"]}

        workbook_response = owner.get("/api/v1/reports/daily.xlsx", params=params)
        assert workbook_response.status_code == 200, workbook_response.text
        workbook = load_workbook(BytesIO(workbook_response.content), data_only=False)
        dashboard_rows = {
            row[0]: row
            for row in workbook["Management Dashboard"].iter_rows(min_row=5, values_only=True)
        }
        dashboard_headers = [cell.value for cell in workbook["Management Dashboard"][4]]
        dashboard_values = {
            asset: dict(zip(dashboard_headers, row, strict=True))
            for asset, row in dashboard_rows.items()
        }
        assert dashboard_values["ALPHA-ONE"]["Trips"] == 6
        assert dashboard_values["ALPHA-ONE"]["Distance KM"] == 100
        assert dashboard_values["ALPHA-ONE"]["Machine Hours"] == "—"
        assert dashboard_values["ALPHA-ONE"]["Verified Diesel L"] == 20
        assert dashboard_values["EXC-01"]["Trips"] == "—"
        assert dashboard_values["EXC-01"]["Distance KM"] == "—"
        assert dashboard_values["EXC-01"]["Machine Hours"] == 1.5
        assert dashboard_values["EXC-01"]["Verified Diesel L"] == 10
        machinery_row = next(
            row
            for row in workbook["Machinery Daily"].iter_rows(min_row=5, values_only=True)
            if row[0] == "EXC-01"
        )
        machinery_headers = [cell.value for cell in workbook["Machinery Daily"][4]]
        machinery_values = dict(zip(machinery_headers, machinery_row, strict=True))
        assert machinery_values["Asset Type"] == "EXCAVATOR"
        assert machinery_values["Start HMR"] == 1000
        assert machinery_values["End HMR"] == 1001.5
        assert machinery_values["Machine Hours"] == 1.5
        assert machinery_values["Diesel L"] == 10

        detailed_template_id = next(
            item["id"]
            for item in owner.get("/api/v1/owner/report-templates").json()
            if item["name"] == "Detailed Operations"
        )
        detailed_response = owner.get(
            "/api/v1/reports/daily.xlsx",
            params={**params, "template_id": detailed_template_id},
        )
        assert detailed_response.status_code == 200, detailed_response.text
        detailed_workbook = load_workbook(BytesIO(detailed_response.content), data_only=False)
        meter_rows = list(
            detailed_workbook["Meter Readings"].iter_rows(min_row=5, values_only=True)
        )
        assert {row[6] for row in meter_rows} == {"ODOMETER", "HMR"}
        assert {row[9] for row in meter_rows} == {"km", "h"}
        exceptions = list(detailed_workbook["Exceptions"].iter_rows(min_row=5, values_only=True))
        assert not any(row[2] == "EXC-01" and "KM" in f"{row[5]} {row[6]}" for row in exceptions)
        trip_time = next(
            row[5]
            for row in detailed_workbook["Trip Register"].iter_rows(min_row=5, values_only=True)
        )
        assert trip_time.hour == 1  # 20:00 UTC + 05:30 on the next local day.
        assert workbook["Management Dashboard"]["B2"].value == "Asia/Kolkata"

        simple_response = owner.get(
            f"/api/v1/reports/sites/{site.id}/simple-workbook.xlsx",
            params={
                "from_date": REPORT_DATE.isoformat(),
                "to_date": REPORT_DATE.isoformat(),
            },
        )
        assert simple_response.status_code == 200, simple_response.text
        assert (
            "Alpha-Site-2025-01-15-to-2025-01-15.xlsx"
            in simple_response.headers["content-disposition"]
        )
        simple = load_workbook(BytesIO(simple_response.content), data_only=False)
        assert simple.sheetnames == ["SUMMARY", "Alpha One", "CAT 320"]
        summary_headers = [cell.value for cell in simple["SUMMARY"][8]]
        summary_values = {
            row[0]: dict(zip(summary_headers, row, strict=True))
            for row in simple["SUMMARY"].iter_rows(min_row=9, max_row=10, values_only=True)
        }
        assert summary_values["Alpha One"] == {
            "Asset": "Alpha One",
            "Registration": "KA01AB1234",
            "Asset Type": "TIPPER",
            "Ownership": "OWNED",
            "Driver / Operator": "Driver A",
            "Days Worked": 1,
            "Approved Trips": 6,
            "Distance KM": 100,
            "Machine Hours": "N/A",
            "Diesel Recorded L": 20,
            "Pending / Exceptions": "0 pending / 0 exceptions",
        }
        assert summary_values["CAT 320"]["Registration"] == "N/A"
        assert summary_values["CAT 320"]["Ownership"] == "RENTED"
        assert summary_values["CAT 320"]["Approved Trips"] == "N/A"
        assert summary_values["CAT 320"]["Distance KM"] == "N/A"
        assert summary_values["CAT 320"]["Machine Hours"] == 1.5
        assert summary_values["CAT 320"]["Pending / Exceptions"] == ("1 pending / 0 exceptions")
        assert simple["Alpha One"]["B7"].value == "OWNED"
        assert simple["CAT 320"]["B7"].value == "RENTED"
        site_totals = {
            row[0]: row[1]
            for row in simple["SUMMARY"].iter_rows(min_row=14, max_row=23, values_only=True)
        }
        assert site_totals == {
            "Total Assets": 2,
            "Total Tippers": 1,
            "Total Machinery": 1,
            "Total Working Days / asset-days": 2,
            "Total Approved Trips": 6,
            "Total Distance KM": 100,
            "Total Machine Hours": 1.5,
            "Total Diesel Recorded L": 30,
            "Pending Items": 1,
            "Exceptions": 0,
        }

        tipper_period = {
            row[0]: row[1]
            for row in simple["Alpha One"].iter_rows(min_row=13, max_row=19, values_only=True)
        }
        assert tipper_period["Working Days"] == 1
        assert tipper_period["Approved Trips"] == 6
        assert tipper_period["Total Distance KM"] == 100
        assert tipper_period["Average Trips / Working Day"] == 6
        assert tipper_period["Average Distance / Working Day"] == 100
        assert tipper_period["Distance per Litre Recorded"] == 5
        tipper_header_row = next(
            row[0].row for row in simple["Alpha One"] if row[0].value == "Date"
        )
        tipper_headers = [cell.value for cell in simple["Alpha One"][tipper_header_row]]
        assert simple["Alpha One"].max_row == tipper_header_row + 1
        tipper_daily = dict(
            zip(
                tipper_headers,
                next(
                    simple["Alpha One"].iter_rows(
                        min_row=tipper_header_row + 1,
                        max_row=tipper_header_row + 1,
                        values_only=True,
                    )
                ),
                strict=True,
            )
        )
        assert tipper_daily["Distance KM"] == 100
        assert tipper_daily["Approved Trips"] == 6
        assert tipper_daily["Diesel Recorded L"] == 20
        assert tipper_daily["Distance per Litre Recorded"] == 5
        assert tipper_daily["Pending / Exception Status"] == "COMPLETE"
        approved_trips_column = tipper_headers.index("Approved Trips") + 1
        assert (
            simple["Alpha One"].cell(tipper_header_row + 1, approved_trips_column).number_format
            == "0"
        )
        assert tipper_daily["Duty Start"] is not None
        assert tipper_daily["Duty End"] is not None
        assert (tipper_daily["Duty Start"].hour, tipper_daily["Duty Start"].minute) == (
            0,
            30,
        )
        assert (tipper_daily["Duty End"].hour, tipper_daily["Duty End"].minute) == (
            10,
            30,
        )

        machinery_period = {
            row[0]: row[1]
            for row in simple["CAT 320"].iter_rows(min_row=13, max_row=17, values_only=True)
        }
        assert machinery_period["Working Days"] == 1
        assert machinery_period["Total Machine Hours"] == 1.5
        assert machinery_period["Diesel Recorded L"] == 10
        assert machinery_period["Average Machine Hours / Working Day"] == 1.5
        assert machinery_period["Litres Recorded / Machine Hour"] == pytest.approx(10 / 1.5)
        machinery_header_row = next(
            row[0].row for row in simple["CAT 320"] if row[0].value == "Date"
        )
        machinery_headers = [cell.value for cell in simple["CAT 320"][machinery_header_row]]
        assert "Approved Trips" not in machinery_headers
        assert "Distance KM" not in machinery_headers
        machinery_daily = dict(
            zip(
                machinery_headers,
                next(
                    simple["CAT 320"].iter_rows(
                        min_row=machinery_header_row + 1,
                        max_row=machinery_header_row + 1,
                        values_only=True,
                    )
                ),
                strict=True,
            )
        )
        assert machinery_daily["Start HMR"] == 1000
        assert machinery_daily["End HMR"] == 1001.5
        assert machinery_daily["Machine Hours"] == 1.5
        assert machinery_daily["Litres Recorded / Machine Hour"] == pytest.approx(10 / 1.5)
        assert "PENDING_VERIFICATION: HMR_READING" in machinery_daily["Pending / Exception Status"]
        pending_hmr_rows = [
            row
            for row in detailed_workbook["Meter Readings"].iter_rows(min_row=5, values_only=True)
            if row[6] == "HMR" and row[7] == "END"
        ]
        assert len(pending_hmr_rows) == 1
        assert pending_hmr_rows[0][8] == 1001.5
        assert pending_hmr_rows[0][10] == "PENDING_VERIFICATION"
        assert pending_hmr not in events
        assert simple["SUMMARY"].freeze_panes == "A9"
        assert simple["Alpha One"].auto_filter.ref is not None
        assert (simple["Alpha One"].column_dimensions["A"].width or 0) >= 30
        assert simple["Alpha One"]["B16"].number_format == "0.000"
        assert simple["Alpha One"]["B18"].number_format == "0.00"
        assert any(
            "not a direct measurement of actual fuel consumed" in str(cell.value)
            for row in simple["Alpha One"].iter_rows()
            for cell in row
        )

        templates_response = owner.get("/api/v1/owner/report-templates")
        assert templates_response.status_code == 200, templates_response.text
        templates = {item["name"]: item for item in templates_response.json()}
        expected_sheets = {
            "Management Summary": [
                "Management Dashboard",
                "Tipper Daily",
                "Machinery Daily",
                "Exceptions",
            ],
            "Detailed Operations": [
                "Management Dashboard",
                "Tipper Daily",
                "Machinery Daily",
                "Trip Register",
                "Meter Readings",
                "Diesel Register",
                "Duty Register",
                "Exceptions",
            ],
            "Diesel Report": [
                "Management Dashboard",
                "Diesel Register",
                "Exceptions",
            ],
        }
        sample_directory = os.getenv("FLEET_REPORT_SAMPLE_DIR")
        for name, sheet_names in expected_sheets.items():
            export = owner.get(
                "/api/v1/reports/daily.xlsx",
                params={**params, "template_id": templates[name]["id"]},
            )
            assert export.status_code == 200, export.text
            assert name.replace(" ", "-") in export.headers["content-disposition"]
            selected = load_workbook(BytesIO(export.content), data_only=False)
            assert selected.sheetnames == sheet_names
            if sample_directory:
                Path(sample_directory, f"{name.replace(' ', '-')}.xlsx").write_bytes(export.content)

        custom_response = owner.post(
            "/api/v1/owner/report-templates",
            json={
                "name": "Custom Minimal",
                "included_sheets": [
                    "management_dashboard",
                    "tipper_daily",
                    "machinery_daily",
                ],
                "management_dashboard_columns": [
                    "asset",
                    "site",
                    "trips",
                    "distance_km",
                    "machine_hours",
                    "verified_diesel_l",
                ],
                "tipper_daily_columns": [
                    "asset",
                    "site",
                    "approved_trips",
                    "distance_km",
                    "diesel_l",
                ],
                "machinery_daily_columns": [
                    "asset",
                    "site",
                    "machine_hours",
                    "diesel_l",
                ],
            },
        )
        assert custom_response.status_code == 201, custom_response.text
        custom_id = custom_response.json()["id"]
        custom_export = owner.get(
            "/api/v1/reports/daily.xlsx",
            params={**params, "template_id": custom_id},
        )
        assert custom_export.status_code == 200, custom_export.text
        if sample_directory:
            Path(sample_directory, "Custom-Minimal.xlsx").write_bytes(custom_export.content)
        custom_workbook = load_workbook(BytesIO(custom_export.content), data_only=False)
        assert custom_workbook.sheetnames == [
            "Management Dashboard",
            "Tipper Daily",
            "Machinery Daily",
        ]
        assert tuple(cell.value for cell in custom_workbook["Management Dashboard"][4]) == (
            "Asset",
            "Site",
            "Trips",
            "Distance KM",
            "Machine Hours",
            "Verified Diesel L",
        )
        custom_rows = {
            row[0]: row
            for row in custom_workbook["Management Dashboard"].iter_rows(
                min_row=5, values_only=True
            )
        }
        assert custom_rows["ALPHA-ONE"] == (
            "ALPHA-ONE",
            "Alpha Site",
            6,
            100,
            "—",
            20,
        )
        assert custom_rows["EXC-01"] == (
            "EXC-01",
            "Alpha Site",
            "—",
            "—",
            1.5,
            10,
        )

        made_default = owner.post(f"/api/v1/owner/report-templates/{custom_id}/default")
        assert made_default.status_code == 200, made_default.text
        default_export = owner.get("/api/v1/reports/daily.xlsx", params=params)
        assert default_export.status_code == 200, default_export.text
        assert load_workbook(BytesIO(default_export.content)).sheetnames == [
            "Management Dashboard",
            "Tipper Daily",
            "Machinery Daily",
        ]
    finally:
        owner.close()


def test_missing_and_invalid_km_readings_block_closure_with_structured_exceptions(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    site = value(tenant_records, "site_a", Site)
    add_reporting_assignment(db_session, tenant_records)
    storage = SupervisorStorage()
    driver = create_driver_client(db_session, tenant_records, storage)
    try:
        start = create_event(
            driver,
            storage,
            "KM_READING",
            DAY_START + timedelta(hours=1),
            reading_type="START_READING",
            reading_value="100.00",
        )
        absurd_end_uuid = str(uuid4())
        absurd_upload = driver.post(
            "/api/v1/driver/evidence",
            params={"client_event_uuid": absurd_end_uuid},
            files={"file": ("evidence.jpg", b"\xff\xd8\xffphase6-evidence", "image/jpeg")},
        )
        assert absurd_upload.status_code == 200
        absurd_end = driver.post(
            "/api/v1/driver/events",
            json=driver_event_payload(
                "KM_READING",
                client_event_uuid=absurd_end_uuid,
                created_at=DAY_START + timedelta(hours=2),
                reading_type="END_READING",
                reading_value="5676543455.81",
                object_reference=absurd_upload.json()["object_reference"],
            ),
        )
        assert absurd_end.status_code == 422
        assert absurd_end.json()["detail"]["code"] == "ODOMETER_OUT_OF_RANGE"
        invalid_end_uuid = str(uuid4())
        invalid_upload = driver.post(
            "/api/v1/driver/evidence",
            params={"client_event_uuid": invalid_end_uuid},
            files={"file": ("evidence.jpg", b"\xff\xd8\xffphase6-evidence", "image/jpeg")},
        )
        assert invalid_upload.status_code == 200
        invalid_end = driver.post(
            "/api/v1/driver/events",
            json=driver_event_payload(
                "KM_READING",
                client_event_uuid=invalid_end_uuid,
                created_at=DAY_START + timedelta(hours=2),
                reading_type="END_READING",
                reading_value="90.00",
                object_reference=invalid_upload.json()["object_reference"],
            ),
        )
        assert invalid_end.status_code == 422
        assert invalid_end.json()["detail"]["code"] == "INVALID_END_KM"
        diesel = create_event(
            driver,
            storage,
            "DIESEL",
            DAY_START + timedelta(hours=3),
            litres="10",
        )
    finally:
        driver.close()
    supervisor = supervisor_client(db_session, tenant_records)
    try:
        verify(supervisor, start)
        verify(supervisor, diesel)
    finally:
        supervisor.close()
    owner = owner_client(db_session, tenant_records)
    try:
        report = owner.get(
            f"/api/v1/reports/sites/{site.id}/daily",
            params={"operational_date": REPORT_DATE.isoformat()},
        )
        assert report.status_code == 200
        data = report.json()
        assert data["total_km"] is None
        assert "5676543455" not in report.text
        assert "MISSING_END_READING" in {item["code"] for item in data["tippers"][0]["exceptions"]}
        close = owner.post(
            f"/api/v1/reports/sites/{site.id}/closure/close",
            params={"operational_date": REPORT_DATE.isoformat()},
            json={"reason": None},
        )
        assert close.status_code == 409
        assert close.json()["detail"]["code"] == "CLOSURE_BLOCKED"
        assert any(
            blocker["code"] == "MISSING_END_READING"
            for blocker in close.json()["detail"]["blockers"]
        )
        workbook = load_workbook(
            BytesIO(
                owner.get(
                    "/api/v1/reports/daily.xlsx",
                    params={
                        "operational_date": REPORT_DATE.isoformat(),
                        "template_id": report_template_id(owner, "Detailed Operations"),
                    },
                ).content
            ),
            data_only=False,
        )
        meter_rows = list(workbook["Meter Readings"].iter_rows(min_row=5, values_only=True))
        assert all("5676543455" not in str(row) for row in meter_rows)

        simple_response = owner.get(
            f"/api/v1/reports/sites/{site.id}/simple-workbook.xlsx",
            params={
                "from_date": REPORT_DATE.isoformat(),
                "to_date": REPORT_DATE.isoformat(),
            },
        )
        assert simple_response.status_code == 200, simple_response.text
        simple = load_workbook(BytesIO(simple_response.content), data_only=False)
        sheet = simple["Alpha One"]
        header_row = next(row[0].row for row in sheet if row[0].value == "Date")
        headers = [cell.value for cell in sheet[header_row]]
        values = dict(
            zip(
                headers,
                next(
                    sheet.iter_rows(
                        min_row=header_row + 1,
                        max_row=header_row + 1,
                        values_only=True,
                    )
                ),
                strict=True,
            )
        )
        assert values["Start KM"] == 100
        assert values["End KM"] == "MISSING"
        assert values["Distance KM"] == "MISSING"
        assert values["Diesel Recorded L"] == 10
        assert values["Distance per Litre Recorded"] == "MISSING"
        assert "MISSING_END_READING" in values["Pending / Exception Status"]
    finally:
        owner.close()


def test_phase6_smoke_fixture_approves_pending_work_then_closes_day(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    site = value(tenant_records, "site_a", Site)
    add_reporting_assignment(db_session, tenant_records)
    storage = SupervisorStorage()
    driver = create_driver_client(db_session, tenant_records, storage)
    try:
        start = create_event(
            driver,
            storage,
            "KM_READING",
            DAY_START + timedelta(hours=1),
            reading_type="START_READING",
            reading_value="10000.00",
        )
        trips = [
            create_event(driver, storage, "TRIP_COMPLETE", DAY_START + timedelta(hours=2 + index))
            for index in range(9)
        ]
        diesel = create_event(
            driver,
            storage,
            "DIESEL",
            DAY_START + timedelta(hours=19),
            litres="30.000",
        )
        end = create_event(
            driver,
            storage,
            "KM_READING",
            DAY_START + timedelta(hours=20),
            reading_type="END_READING",
            reading_value="10120.00",
        )
    finally:
        driver.close()
    supervisor = supervisor_client(db_session, tenant_records)
    try:
        verify(supervisor, start)
        verify(supervisor, end)
        for trip in trips[:8]:
            verify(supervisor, trip)
        verify(supervisor, diesel)
    finally:
        supervisor.close()

    owner = owner_client(db_session, tenant_records, storage=storage)
    try:
        params = {"operational_date": REPORT_DATE.isoformat()}
        before = owner.get("/api/v1/reports/dashboard", params=params)
        assert before.status_code == 200
        assert before.json()["approved_trip_count"] == 8
        assert before.json()["pending_trip_count"] == 1
        assert before.json()["total_km"] == "120.00"
        assert before.json()["verified_diesel_issued"] == "30.000"
        workbook = load_workbook(
            BytesIO(owner.get("/api/v1/reports/daily.xlsx", params=params).content),
            data_only=False,
        )
        tipper_headers = [cell.value for cell in workbook["Tipper Daily"][4]]
        tipper_values = dict(
            zip(
                tipper_headers,
                next(workbook["Tipper Daily"].iter_rows(min_row=5, values_only=True)),
                strict=True,
            )
        )
        assert tipper_values["Approved Trips"] == 8
        assert tipper_values["Distance KM"] == 120
        blocked = owner.post(
            f"/api/v1/reports/sites/{site.id}/closure/close",
            params=params,
            json={"reason": None},
        )
        assert blocked.status_code == 409
        assert any(item["code"] == "TRIP_PENDING" for item in blocked.json()["detail"]["blockers"])
    finally:
        owner.close()

    supervisor = supervisor_client(db_session, tenant_records)
    try:
        verify(supervisor, trips[8])
    finally:
        supervisor.close()
    owner = owner_client(db_session, tenant_records)
    try:
        ready = owner.get(f"/api/v1/reports/sites/{site.id}/closure", params=params)
        assert ready.status_code == 200
        assert ready.json()["status"] == "READY_TO_CLOSE"
        closed = owner.post(
            f"/api/v1/reports/sites/{site.id}/closure/close",
            params=params,
            json={"reason": "Smoke review complete"},
        )
        assert closed.status_code == 200
        assert closed.json()["status"] == "CLOSED"
        after = owner.get("/api/v1/reports/dashboard", params=params)
        assert after.json()["approved_trip_count"] == 9
        assert after.json()["pending_trip_count"] == 0
    finally:
        owner.close()


def test_timezone_boundary_and_assignment_transfer_are_historical_and_not_double_counted(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    company.reporting_timezone = "Asia/Kolkata"
    company.operational_day_start_minutes = 360
    first_site = value(tenant_records, "site_a", Site)
    second_site = Site(
        company_id=company.id,
        name="Second Site",
        short_name="Second Site",
        code="SECOND",
        status=SiteStatus.ACTIVE,
    )
    db_session.add(second_site)
    first_assignment = add_reporting_assignment(
        db_session,
        tenant_records,
        starts_at=datetime(2025, 1, 14, 5, tzinfo=UTC),
        ends_at=datetime(2025, 1, 15, 5, tzinfo=UTC),
    )
    second_assignment = add_reporting_assignment(
        db_session,
        tenant_records,
        site=second_site,
        starts_at=datetime(2025, 1, 15, 5, tzinfo=UTC),
    )
    assert first_assignment.id != second_assignment.id
    db_session.flush()
    storage = SupervisorStorage()
    driver = create_driver_client(db_session, tenant_records, storage)
    try:
        create_event(
            driver,
            storage,
            "KM_READING",
            datetime(2025, 1, 15, 0, tzinfo=UTC),
            reading_type="START_READING",
            reading_value="100.00",
        )
        first_event = create_event(
            driver, storage, "TRIP_COMPLETE", datetime(2025, 1, 15, 0, 45, tzinfo=UTC)
        )
        create_event(
            driver,
            storage,
            "KM_READING",
            datetime(2025, 1, 15, 4, tzinfo=UTC),
            reading_type="END_READING",
            reading_value="105.00",
        )
        create_event(
            driver,
            storage,
            "KM_READING",
            datetime(2025, 1, 15, 5, 15, tzinfo=UTC),
            reading_type="START_READING",
            reading_value="200.00",
        )
        second_event = create_event(
            driver, storage, "TRIP_COMPLETE", datetime(2025, 1, 15, 5, 30, tzinfo=UTC)
        )
    finally:
        driver.close()
    supervisor = supervisor_client(db_session, tenant_records)
    try:
        verify(supervisor, first_event)
        verify(supervisor, second_event)
    finally:
        supervisor.close()
    owner = owner_client(db_session, tenant_records)
    try:
        dashboard = owner.get(
            "/api/v1/reports/dashboard", params={"operational_date": "2025-01-15"}
        )
        assert dashboard.status_code == 200
        data = dashboard.json()
        assert data["operational_date"] == "2025-01-15"
        assert data["workday_start_minutes"] == 360
        assert data["approved_trip_count"] == 2
        first = owner.get(
            f"/api/v1/reports/sites/{first_site.id}/daily",
            params={"operational_date": "2025-01-15"},
        )
        second = owner.get(
            f"/api/v1/reports/sites/{second_site.id}/daily",
            params={"operational_date": "2025-01-15"},
        )
        assert first.json()["approved_trip_count"] == 1
        assert second.json()["approved_trip_count"] == 1
        assert sum(item["approved_trip_count"] for item in data["sites"]) == 2
    finally:
        owner.close()


def test_closure_success_history_reopen_policy_and_company_settings(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    site = value(tenant_records, "site_a", Site)
    add_reporting_assignment(db_session, tenant_records)
    owner = owner_client(db_session, tenant_records)
    try:
        settings = owner.get("/api/v1/admin/company")
        assert settings.status_code == 200
        updated = owner.patch(
            "/api/v1/admin/company",
            json={"reporting_timezone": "UTC", "operational_day_start_minutes": 60},
        )
        assert updated.status_code == 200
        assert updated.json()["operational_day_start_minutes"] == 60
        invalid = owner.patch("/api/v1/admin/company", json={"reporting_timezone": "Not/AZone"})
        assert invalid.status_code == 422
    finally:
        owner.close()

    storage = SupervisorStorage()
    driver = create_driver_client(db_session, tenant_records, storage)
    try:
        start = create_event(
            driver,
            storage,
            "KM_READING",
            datetime(2025, 1, 15, 2, tzinfo=UTC),
            reading_type="START_READING",
            reading_value="100.00",
        )
        end = create_event(
            driver,
            storage,
            "KM_READING",
            datetime(2025, 1, 15, 20, tzinfo=UTC),
            reading_type="END_READING",
            reading_value="120.00",
        )
    finally:
        driver.close()
    supervisor = supervisor_client(db_session, tenant_records)
    try:
        verify(supervisor, start)
        verify(supervisor, end)
    finally:
        supervisor.close()

    supervisor = supervisor_client(db_session, tenant_records)
    try:
        supervisor_close = supervisor.post(
            f"/api/v1/reports/sites/{site.id}/closure/close",
            params={"operational_date": "2025-01-15"},
            json={"reason": "Supervisor daily review complete"},
        )
        assert supervisor_close.status_code == 200, supervisor_close.text
    finally:
        supervisor.close()

    # The changed settings are tested above; use the same clean day for owner reopen.
    owner = owner_client(db_session, tenant_records)
    try:
        already_closed = owner.post(
            f"/api/v1/reports/sites/{site.id}/closure/close",
            params={"operational_date": "2025-01-15"},
            json={"reason": "Daily review complete"},
        )
        assert already_closed.status_code == 409
        missing_reason = owner.post(
            f"/api/v1/reports/sites/{site.id}/closure/reopen",
            params={"operational_date": "2025-01-15"},
            json={"reason": None},
        )
        assert missing_reason.status_code == 422
        reopened = owner.post(
            f"/api/v1/reports/sites/{site.id}/closure/reopen",
            params={"operational_date": "2025-01-15"},
            json={"reason": "Correction required"},
        )
        assert reopened.status_code == 200
        assert reopened.json()["status"] == "READY_TO_CLOSE"
        history = db_session.query(SiteDailyClosureHistory).all()
        assert [item.status.value for item in history] == ["CLOSED", "REOPENED"]
        assert all(item.reason for item in history)
    finally:
        owner.close()
