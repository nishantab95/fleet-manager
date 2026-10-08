from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from fleet_api.db.models import AuditLog, Company, ReportTemplate
from fleet_api.domain.report_templates import (
    MACHINERY_COLUMNS,
    MANAGEMENT_COLUMNS,
    SHEET_IDS,
    STANDARD_MACHINERY_COLUMNS,
    STANDARD_MANAGEMENT_COLUMNS,
    STANDARD_TIPPER_COLUMNS,
    TIPPER_COLUMNS,
)
from test_reports_api import owner_client, supervisor_client
from test_supervisor_api import SupervisorStorage, create_driver_client, value

pytestmark = pytest.mark.postgres


def custom_payload(name: str = "Custom Minimal") -> dict[str, object]:
    return {
        "name": name,
        "included_sheets": ["exceptions", "management_dashboard"],
        "management_dashboard_columns": [
            "pending_status",
            "asset",
            "verified_diesel_l",
        ],
        "tipper_daily_columns": ["status", "asset", "approved_trips"],
        "machinery_daily_columns": ["machine_hours", "asset", "status"],
    }


def test_owner_report_template_lifecycle_validation_tenant_scope_and_audit(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    owner = owner_client(db_session, tenant_records)
    try:
        listed = owner.get("/api/v1/owner/report-templates")
        assert listed.status_code == 200, listed.text
        builtins = listed.json()
        assert [item["name"] for item in builtins] == [
            "Simple Site Workbook",
            "Management Summary",
            "Detailed Operations",
            "Diesel Report",
        ]
        assert builtins[0]["builtin_key"] == "simple_site_workbook"
        assert all(item["is_builtin"] for item in builtins)
        assert [item["name"] for item in builtins if item["is_default"]] == ["Management Summary"]
        assert builtins[0]["included_sheets"] == [
            "management_dashboard",
            "tipper_daily",
            "machinery_daily",
        ]
        assert builtins[1]["included_sheets"] == [
            "management_dashboard",
            "tipper_daily",
            "machinery_daily",
            "exceptions",
        ]
        assert builtins[2]["included_sheets"] == list(SHEET_IDS)
        assert builtins[3]["included_sheets"] == [
            "management_dashboard",
            "diesel_register",
            "exceptions",
        ]

        simple_id = builtins[0]["id"]
        assert (
            owner.get("/api/v1/reports/daily.xlsx", params={"template_id": simple_id}).status_code
            == 422
        )
        assert owner.post(f"/api/v1/owner/report-templates/{simple_id}/default").status_code == 409
        assert (
            owner.post(
                f"/api/v1/owner/report-templates/{simple_id}/duplicate",
                json={"name": "Misleading Simple Copy"},
            ).status_code
            == 409
        )

        created = owner.post("/api/v1/owner/report-templates", json=custom_payload())
        assert created.status_code == 201, created.text
        custom = created.json()
        custom_id = custom["id"]
        # Selections are stored in canonical order, regardless of UI order.
        assert custom["included_sheets"] == ["management_dashboard", "exceptions"]
        assert custom["management_dashboard_columns"] == [
            "asset",
            "verified_diesel_l",
            "pending_status",
        ]
        assert custom["tipper_daily_columns"] == [
            "asset",
            "approved_trips",
            "status",
        ]
        assert custom["machinery_daily_columns"] == [
            "asset",
            "machine_hours",
            "status",
        ]

        duplicate_name = owner.post(
            "/api/v1/owner/report-templates", json=custom_payload("custom minimal")
        )
        assert duplicate_name.status_code == 409

        invalid_cases = [
            {**custom_payload("No Sheets"), "included_sheets": []},
            {**custom_payload("No Asset"), "management_dashboard_columns": ["site"]},
            {**custom_payload("Bad Field"), "tipper_daily_columns": ["asset", "bogus"]},
            {
                **custom_payload("Wrong Sheet Field"),
                "tipper_daily_columns": ["asset", "machine_hours"],
            },
            {**custom_payload("Bad Sheet"), "included_sheets": ["not_a_sheet"]},
        ]
        for payload in invalid_cases:
            response = owner.post("/api/v1/owner/report-templates", json=payload)
            assert response.status_code == 422, response.text

        null_update = owner.patch(
            f"/api/v1/owner/report-templates/{custom_id}",
            json={"management_dashboard_columns": None},
        )
        assert null_update.status_code == 422

        builtin_id = builtins[1]["id"]
        assert (
            owner.patch(
                f"/api/v1/owner/report-templates/{builtin_id}",
                json={"name": "Changed"},
            ).status_code
            == 409
        )
        assert owner.delete(f"/api/v1/owner/report-templates/{builtin_id}").status_code == 409

        copied = owner.post(
            f"/api/v1/owner/report-templates/{builtin_id}/duplicate",
            json={"name": "Management Copy"},
        )
        assert copied.status_code == 200, copied.text
        assert copied.json()["is_builtin"] is False

        updated = owner.patch(
            f"/api/v1/owner/report-templates/{custom_id}",
            json={"name": "Daily Brief"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["name"] == "Daily Brief"

        made_default = owner.post(f"/api/v1/owner/report-templates/{custom_id}/default")
        assert made_default.status_code == 200
        assert made_default.json()["is_default"] is True

        reloaded_owner = owner_client(db_session, tenant_records)
        try:
            persisted = reloaded_owner.get("/api/v1/owner/report-templates")
            assert persisted.status_code == 200
            assert [item["name"] for item in persisted.json() if item["is_default"]] == [
                "Daily Brief"
            ]
            assert len([item for item in persisted.json() if item["is_builtin"]]) == 4
        finally:
            reloaded_owner.close()

        # A template UUID belonging to another company is indistinguishable from missing.
        foreign = ReportTemplate(
            id=uuid4(),
            company_id=value(tenant_records, "company_b", Company).id,
            name="Beta Only",
            is_builtin=False,
            is_default=False,
            included_sheets=["management_dashboard"],
            management_dashboard_columns=list(STANDARD_MANAGEMENT_COLUMNS),
            tipper_daily_columns=list(STANDARD_TIPPER_COLUMNS),
            machinery_daily_columns=list(STANDARD_MACHINERY_COLUMNS),
        )
        db_session.add(foreign)
        db_session.flush()
        assert owner.get(f"/api/v1/owner/report-templates/{foreign.id}").status_code == 404
        assert (
            owner.get(
                "/api/v1/reports/daily.xlsx", params={"template_id": str(foreign.id)}
            ).status_code
            == 404
        )

        deleted = owner.delete(f"/api/v1/owner/report-templates/{custom_id}")
        assert deleted.status_code == 204
        after_delete = owner.get("/api/v1/owner/report-templates").json()
        assert [item["name"] for item in after_delete if item["is_default"]] == [
            "Management Summary"
        ]

        audit_actions = set(
            db_session.scalars(
                select(AuditLog.action).where(
                    AuditLog.company_id == value(tenant_records, "company_a", Company).id,
                    AuditLog.entity_type == "REPORT_TEMPLATE",
                )
            )
        )
        assert {
            "REPORT_TEMPLATE_CREATED",
            "REPORT_TEMPLATE_UPDATED",
            "REPORT_TEMPLATE_DEFAULT_SET",
            "REPORT_TEMPLATE_DELETED",
        } <= audit_actions
    finally:
        owner.close()


def test_report_template_routes_are_owner_only(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    supervisor = supervisor_client(db_session, tenant_records)
    try:
        assert supervisor.get("/api/v1/owner/report-templates").status_code == 403
    finally:
        supervisor.close()
    driver = create_driver_client(db_session, tenant_records, SupervisorStorage())
    try:
        assert driver.get("/api/v1/owner/report-templates").status_code == 403
    finally:
        driver.close()


def test_simple_builtin_renames_a_colliding_custom_template_without_overwriting_it(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    custom = ReportTemplate(
        company_id=company.id,
        name="simple site workbook",
        builtin_key=None,
        is_builtin=False,
        is_default=False,
        included_sheets=["management_dashboard"],
        management_dashboard_columns=["asset", "pending_status"],
        tipper_daily_columns=["asset", "status"],
        machinery_daily_columns=["asset", "status"],
    )
    db_session.add(custom)
    db_session.flush()
    custom_id = str(custom.id)

    owner = owner_client(db_session, tenant_records)
    try:
        response = owner.get("/api/v1/owner/report-templates")
        assert response.status_code == 200, response.text
        templates = response.json()
        simple_builtin = next(
            item for item in templates if item["builtin_key"] == "simple_site_workbook"
        )
        renamed_custom = next(item for item in templates if item["id"] == custom_id)
        assert simple_builtin["name"] == "Simple Site Workbook"
        assert renamed_custom["name"] == "simple site workbook (Custom)"
        assert renamed_custom["included_sheets"] == ["management_dashboard"]
        assert renamed_custom["management_dashboard_columns"] == [
            "asset",
            "pending_status",
        ]
        assert (
            db_session.scalar(
                select(AuditLog.action).where(
                    AuditLog.company_id == company.id,
                    AuditLog.entity_id == custom.id,
                    AuditLog.action == "REPORT_TEMPLATE_RENAMED_FOR_BUILTIN",
                )
            )
            == "REPORT_TEMPLATE_RENAMED_FOR_BUILTIN"
        )
    finally:
        owner.close()


def test_template_catalogs_are_stable_and_asset_first() -> None:
    assert MANAGEMENT_COLUMNS[0] == "asset"
    assert TIPPER_COLUMNS[0] == "asset"
    assert MACHINERY_COLUMNS[0] == "asset"
    assert len(SHEET_IDS) == len(set(SHEET_IDS)) == 8
