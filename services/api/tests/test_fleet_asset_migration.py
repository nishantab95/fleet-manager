from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from fleet_api.auth.service import AuthContext
from fleet_api.db.models import AuthSession, Company, CompanyMembership, User
from fleet_api.domain.reporting import ReportingService

pytestmark = pytest.mark.postgres

COMPANY_ID = UUID("10000000-0000-0000-0000-000000000001")
ASSET_ID = UUID("10000000-0000-0000-0000-000000000002")
SITE_ID = UUID("10000000-0000-0000-0000-000000000003")
ASSIGNMENT_ID = UUID("10000000-0000-0000-0000-000000000004")
DUTY_ID = UUID("10000000-0000-0000-0000-000000000005")
DRIVER_USER_ID = UUID("10000000-0000-0000-0000-000000000006")
SUPERVISOR_USER_ID = UUID("10000000-0000-0000-0000-000000000007")
OWNER_USER_ID = UUID("10000000-0000-0000-0000-000000000008")
DRIVER_MEMBERSHIP_ID = UUID("10000000-0000-0000-0000-000000000009")
SUPERVISOR_MEMBERSHIP_ID = UUID("10000000-0000-0000-0000-00000000000a")
OWNER_MEMBERSHIP_ID = UUID("10000000-0000-0000-0000-00000000000b")
DEVICE_ID = UUID("10000000-0000-0000-0000-00000000000c")
START_EVENT_ID = UUID("10000000-0000-0000-0000-00000000000d")
END_EVENT_ID = UUID("10000000-0000-0000-0000-00000000000e")
TRIP_EVENT_ID = UUID("10000000-0000-0000-0000-00000000000f")
DIESEL_EVENT_ID = UUID("10000000-0000-0000-0000-000000000010")
EVIDENCE_ID = UUID("10000000-0000-0000-0000-000000000011")


def _alembic_config(engine: Engine) -> Config:
    api_root = Path(__file__).parents[1]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "migrations"))
    config.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False))
    return config


def _insert_legacy_graph(connection: Connection) -> None:
    started_at = datetime(2026, 1, 15, 3, 30, tzinfo=UTC)
    ended_at = started_at + timedelta(hours=10)
    connection.execute(
        text(
            "INSERT INTO companies "
            "(id, name, status, reporting_timezone, operational_day_start_minutes) "
            "VALUES (:id, 'Migration Company', 'ACTIVE', 'Asia/Kolkata', 0)"
        ),
        {"id": COMPANY_ID},
    )
    users = (
        (DRIVER_USER_ID, "+919100000001", "Migration Driver"),
        (SUPERVISOR_USER_ID, "+919100000002", "Migration Supervisor"),
        (OWNER_USER_ID, "+919100000003", "Migration Owner"),
    )
    for user_id, phone, name in users:
        connection.execute(
            text(
                "INSERT INTO users (id, phone_number, display_name, status) "
                "VALUES (:id, :phone, :name, 'ACTIVE')"
            ),
            {"id": user_id, "phone": phone, "name": name},
        )
    memberships = (
        (DRIVER_MEMBERSHIP_ID, DRIVER_USER_ID, "DRIVER", "Migration Driver"),
        (
            SUPERVISOR_MEMBERSHIP_ID,
            SUPERVISOR_USER_ID,
            "SUPERVISOR",
            "Migration Supervisor",
        ),
        (OWNER_MEMBERSHIP_ID, OWNER_USER_ID, "OWNER_ADMIN", "Migration Owner"),
    )
    for membership_id, user_id, role, display_name in memberships:
        connection.execute(
            text(
                "INSERT INTO company_memberships "
                "(id, company_id, user_id, role, status, display_name) "
                "VALUES (:id, :company_id, :user_id, :role, 'ACTIVE', :display_name)"
            ),
            {
                "id": membership_id,
                "company_id": COMPANY_ID,
                "user_id": user_id,
                "role": role,
                "display_name": display_name,
            },
        )
    connection.execute(
        text(
            "INSERT INTO sites (id, company_id, name, code, status) "
            "VALUES (:id, :company_id, 'Migration Site', 'MIG', 'ACTIVE')"
        ),
        {"id": SITE_ID, "company_id": COMPANY_ID},
    )
    connection.execute(
        text(
            "INSERT INTO tippers "
            "(id, company_id, registration_number, short_name, status) "
            "VALUES (:id, :company_id, 'KA01AB1234', 'Tipper 12', 'ACTIVE')"
        ),
        {"id": ASSET_ID, "company_id": COMPANY_ID},
    )
    connection.execute(
        text(
            "INSERT INTO assignments "
            "(id, company_id, driver_membership_id, supervisor_membership_id, "
            "tipper_id, site_id, starts_at, regular_duty_minutes) "
            "VALUES (:id, :company_id, :driver_id, :supervisor_id, :tipper_id, "
            ":site_id, :starts_at, 600)"
        ),
        {
            "id": ASSIGNMENT_ID,
            "company_id": COMPANY_ID,
            "driver_id": DRIVER_MEMBERSHIP_ID,
            "supervisor_id": SUPERVISOR_MEMBERSHIP_ID,
            "tipper_id": ASSET_ID,
            "site_id": SITE_ID,
            "starts_at": started_at - timedelta(hours=1),
        },
    )
    connection.execute(
        text(
            "INSERT INTO devices "
            "(id, company_id, membership_id, installation_identifier, platform, status) "
            "VALUES (:id, :company_id, :membership_id, 'migration-device', 'ANDROID', 'ACTIVE')"
        ),
        {"id": DEVICE_ID, "company_id": COMPANY_ID, "membership_id": DRIVER_MEMBERSHIP_ID},
    )

    events = (
        (START_EVENT_ID, UUID("20000000-0000-0000-0000-000000000001"), "KM_READING", started_at),
        (
            TRIP_EVENT_ID,
            UUID("20000000-0000-0000-0000-000000000002"),
            "TRIP_COMPLETE",
            started_at + timedelta(hours=2),
        ),
        (
            DIESEL_EVENT_ID,
            UUID("20000000-0000-0000-0000-000000000003"),
            "DIESEL",
            started_at + timedelta(hours=4),
        ),
        (END_EVENT_ID, UUID("20000000-0000-0000-0000-000000000004"), "KM_READING", ended_at),
    )
    for event_id, client_id, event_type, created_at in events:
        connection.execute(
            text(
                "INSERT INTO operational_events "
                "(id, company_id, assignment_id, duty_session_id, client_event_uuid, "
                "device_id, device_created_at, event_type, verification_status) "
                "VALUES (:id, :company_id, :assignment_id, NULL, :client_id, :device_id, "
                ":created_at, :event_type, 'APPROVED')"
            ),
            {
                "id": event_id,
                "company_id": COMPANY_ID,
                "assignment_id": ASSIGNMENT_ID,
                "client_id": client_id,
                "device_id": DEVICE_ID,
                "created_at": created_at,
                "event_type": event_type,
            },
        )
    connection.execute(
        text(
            "INSERT INTO km_readings (event_id, reading_type, reading_value, object_reference) "
            "VALUES (:start_id, 'START_READING', 1000, 'migration/start.jpg'), "
            "(:end_id, 'END_READING', 1010, 'migration/end.jpg')"
        ),
        {"start_id": START_EVENT_ID, "end_id": END_EVENT_ID},
    )
    connection.execute(
        text("INSERT INTO trip_events (event_id) VALUES (:event_id)"),
        {"event_id": TRIP_EVENT_ID},
    )
    connection.execute(
        text("INSERT INTO diesel_events (event_id, litres) VALUES (:event_id, 50)"),
        {"event_id": DIESEL_EVENT_ID},
    )
    connection.execute(
        text(
            "INSERT INTO duty_sessions "
            "(id, company_id, assignment_id, driver_membership_id, tipper_id, site_id, "
            "operational_date, start_event_id, start_km, started_at, "
            "configured_regular_duty_minutes, regular_duty_ends_at, end_event_id, end_km, "
            "ended_at, status, final_overtime_minutes) "
            "VALUES (:id, :company_id, :assignment_id, :driver_id, :tipper_id, :site_id, "
            ":operational_date, :start_event_id, 1000, :started_at, 600, :regular_end, "
            ":end_event_id, 1010, :ended_at, 'CLOSED', 0)"
        ),
        {
            "id": DUTY_ID,
            "company_id": COMPANY_ID,
            "assignment_id": ASSIGNMENT_ID,
            "driver_id": DRIVER_MEMBERSHIP_ID,
            "tipper_id": ASSET_ID,
            "site_id": SITE_ID,
            "operational_date": date(2026, 1, 15),
            "start_event_id": START_EVENT_ID,
            "started_at": started_at,
            "regular_end": started_at + timedelta(hours=10),
            "end_event_id": END_EVENT_ID,
            "ended_at": ended_at,
        },
    )
    connection.execute(
        text(
            "UPDATE operational_events SET duty_session_id = :duty_id "
            "WHERE company_id = :company_id"
        ),
        {"duty_id": DUTY_ID, "company_id": COMPANY_ID},
    )
    for index, (event_id, _client_id, _event_type, _created_at) in enumerate(events, start=1):
        connection.execute(
            text(
                "INSERT INTO event_verifications "
                "(id, company_id, event_id, changed_by_membership_id, status, reason) "
                "VALUES (:id, :company_id, :event_id, :actor_id, 'APPROVED', 'migration')"
            ),
            {
                "id": UUID(f"30000000-0000-0000-0000-{index:012d}"),
                "company_id": COMPANY_ID,
                "event_id": event_id,
                "actor_id": SUPERVISOR_MEMBERSHIP_ID,
            },
        )
    connection.execute(
        text(
            "INSERT INTO evidence_objects "
            "(id, company_id, membership_id, client_event_uuid, object_key, content_type, "
            "size_bytes) VALUES (:id, :company_id, :membership_id, :client_id, "
            "'migration/start.jpg', 'image/jpeg', 100)"
        ),
        {
            "id": EVIDENCE_ID,
            "company_id": COMPANY_ID,
            "membership_id": DRIVER_MEMBERSHIP_ID,
            "client_id": events[0][1],
        },
    )


def _cleanup_migrated_graph(engine: Engine) -> None:
    with engine.begin() as connection:
        table_exists = connection.scalar(text("SELECT to_regclass('public.fleet_assets')"))
        if table_exists is None:
            return
        params = {"company_id": COMPANY_ID}
        connection.execute(
            text(
                "UPDATE operational_events SET duty_session_id = NULL "
                "WHERE company_id = :company_id"
            ),
            params,
        )
        for statement in (
            "DELETE FROM duty_sessions WHERE company_id = :company_id",
            "DELETE FROM event_verifications WHERE company_id = :company_id",
            "DELETE FROM trip_events WHERE event_id IN "
            "(SELECT id FROM operational_events WHERE company_id = :company_id)",
            "DELETE FROM km_readings WHERE event_id IN "
            "(SELECT id FROM operational_events WHERE company_id = :company_id)",
            "DELETE FROM diesel_events WHERE event_id IN "
            "(SELECT id FROM operational_events WHERE company_id = :company_id)",
            "DELETE FROM emergency_events WHERE event_id IN "
            "(SELECT id FROM operational_events WHERE company_id = :company_id)",
            "DELETE FROM evidence_objects WHERE company_id = :company_id",
            "DELETE FROM operational_events WHERE company_id = :company_id",
            "DELETE FROM assignments WHERE company_id = :company_id",
            "DELETE FROM asset_site_deployments WHERE company_id = :company_id",
            "DELETE FROM devices WHERE company_id = :company_id",
            "DELETE FROM company_memberships WHERE company_id = :company_id",
            "DELETE FROM fleet_assets WHERE company_id = :company_id",
            "DELETE FROM sites WHERE company_id = :company_id",
            "DELETE FROM users WHERE id IN "
            "('10000000-0000-0000-0000-000000000006', "
            "'10000000-0000-0000-0000-000000000007', "
            "'10000000-0000-0000-0000-000000000008')",
            "DELETE FROM companies WHERE id = :company_id",
        ):
            connection.execute(text(statement), params)


def test_0011_migrates_complete_tipper_history_and_reporting(
    postgres_engine: Engine,
) -> None:
    config = _alembic_config(postgres_engine)
    command.downgrade(config, "0010_event_duty_session")
    try:
        with postgres_engine.begin() as connection:
            _insert_legacy_graph(connection)
            legacy_counts = {
                "events": connection.scalar(
                    text("SELECT count(*) FROM operational_events WHERE company_id = :company_id"),
                    {"company_id": COMPANY_ID},
                ),
                "verifications": connection.scalar(
                    text("SELECT count(*) FROM event_verifications WHERE company_id = :company_id"),
                    {"company_id": COMPANY_ID},
                ),
                "evidence": connection.scalar(
                    text("SELECT count(*) FROM evidence_objects WHERE company_id = :company_id"),
                    {"company_id": COMPANY_ID},
                ),
            }

        command.upgrade(config, "head")

        with postgres_engine.connect() as connection:
            asset = (
                connection.execute(
                    text(
                        "SELECT id, asset_code, asset_type, ownership_type, registration_number, "
                        "status FROM fleet_assets WHERE id = :id"
                    ),
                    {"id": ASSET_ID},
                )
                .mappings()
                .one()
            )
            assert dict(asset) == {
                "id": ASSET_ID,
                "asset_code": "TIPPER-12",
                "asset_type": "TIPPER",
                "ownership_type": "OWNED",
                "registration_number": "KA01AB1234",
                "status": "ACTIVE",
            }
            assert (
                connection.scalar(
                    text("SELECT asset_id FROM assignments WHERE id = :id"),
                    {"id": ASSIGNMENT_ID},
                )
                == ASSET_ID
            )
            assert (
                connection.scalar(
                    text("SELECT asset_id FROM duty_sessions WHERE id = :id"),
                    {"id": DUTY_ID},
                )
                == ASSET_ID
            )
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM operational_events WHERE company_id = :company_id"),
                    {"company_id": COMPANY_ID},
                )
                == legacy_counts["events"]
            )
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM event_verifications WHERE company_id = :company_id"),
                    {"company_id": COMPANY_ID},
                )
                == legacy_counts["verifications"]
            )
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM evidence_objects WHERE company_id = :company_id"),
                    {"company_id": COMPANY_ID},
                )
                == legacy_counts["evidence"]
            )

        with Session(postgres_engine) as session:
            company = session.get(Company, COMPANY_ID)
            owner = session.get(CompanyMembership, OWNER_MEMBERSHIP_ID)
            owner_user = session.get(User, OWNER_USER_ID)
            assert company is not None and owner is not None and owner_user is not None
            context = AuthContext(
                auth_session=cast(AuthSession, object()),
                user=owner_user,
                membership=owner,
                company=company,
            )
            report = ReportingService(session, context).site_daily(SITE_ID, date(2026, 1, 15))
            assert report.assigned_assets_count == 1
            assert len(report.rows) == 1
            row = report.rows[0]
            assert row.asset.id == ASSET_ID
            assert row.asset.asset_code == "TIPPER-12"
            assert row.approved_trip_count == 1
            assert row.start_km == Decimal("1000.00")
            assert row.end_km == Decimal("1010.00")
            assert row.distance_km == Decimal("10.00")
            assert row.verified_diesel_issued == Decimal("50.000")
            assert len(row.events) == 4
            assert all(event.verification_history for event in row.events)
    finally:
        command.upgrade(config, "head")
        _cleanup_migrated_graph(postgres_engine)


def test_0012_preserves_people_sites_and_accepts_invited_status(
    postgres_engine: Engine,
) -> None:
    config = _alembic_config(postgres_engine)
    company_id = UUID("40000000-0000-0000-0000-000000000001")
    user_id = UUID("40000000-0000-0000-0000-000000000002")
    membership_id = UUID("40000000-0000-0000-0000-000000000003")
    site_id = UUID("40000000-0000-0000-0000-000000000004")
    command.downgrade(config, "0011_fleet_assets")
    try:
        with postgres_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO companies (id, name, status, reporting_timezone, "
                    "operational_day_start_minutes) VALUES "
                    "(:id, 'People Sites Migration', 'ACTIVE', 'Asia/Kolkata', 0)"
                ),
                {"id": company_id},
            )
            connection.execute(
                text(
                    "INSERT INTO users (id, phone_number, display_name, status) "
                    "VALUES (:id, '+919100000099', 'Preserved Supervisor', 'ACTIVE')"
                ),
                {"id": user_id},
            )
            connection.execute(
                text(
                    "INSERT INTO company_memberships "
                    "(id, company_id, user_id, role, status, display_name) VALUES "
                    "(:id, :company_id, :user_id, 'SUPERVISOR', 'ACTIVE', "
                    "'Preserved Supervisor')"
                ),
                {
                    "id": membership_id,
                    "company_id": company_id,
                    "user_id": user_id,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO sites (id, company_id, name, code, status) VALUES "
                    "(:id, :company_id, 'Preserved Site', 'KEEP', 'ACTIVE')"
                ),
                {"id": site_id, "company_id": company_id},
            )

        command.upgrade(config, "head")

        with postgres_engine.begin() as connection:
            site = (
                connection.execute(
                    text(
                        "SELECT id, name, code, location_description, latitude, longitude "
                        "FROM sites WHERE id = :id"
                    ),
                    {"id": site_id},
                )
                .mappings()
                .one()
            )
            assert site["id"] == site_id
            assert site["name"] == "Preserved Site"
            assert site["code"] == "KEEP"
            assert site["location_description"] is None
            assert site["latitude"] is None
            assert site["longitude"] is None
            connection.execute(
                text("UPDATE company_memberships SET status = 'INVITED' WHERE id = :id"),
                {"id": membership_id},
            )
            assert (
                connection.scalar(
                    text("SELECT status::text FROM company_memberships WHERE id = :id"),
                    {"id": membership_id},
                )
                == "INVITED"
            )
    finally:
        command.upgrade(config, "head")
        with postgres_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM sites WHERE company_id = :company_id"),
                {"company_id": company_id},
            )
            connection.execute(
                text("DELETE FROM company_memberships WHERE company_id = :company_id"),
                {"company_id": company_id},
            )
            connection.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
            connection.execute(text("DELETE FROM companies WHERE id = :id"), {"id": company_id})


def test_0013_backfills_assignment_history_as_asset_site_deployments(
    postgres_engine: Engine,
) -> None:
    config = _alembic_config(postgres_engine)
    company_id = UUID("50000000-0000-0000-0000-000000000001")
    asset_id = UUID("50000000-0000-0000-0000-000000000002")
    first_site_id = UUID("50000000-0000-0000-0000-000000000003")
    current_site_id = UUID("50000000-0000-0000-0000-000000000004")
    driver_user_id = UUID("50000000-0000-0000-0000-000000000005")
    supervisor_user_id = UUID("50000000-0000-0000-0000-000000000006")
    driver_id = UUID("50000000-0000-0000-0000-000000000007")
    supervisor_id = UUID("50000000-0000-0000-0000-000000000008")
    boundary = datetime(2026, 9, 1, tzinfo=UTC)
    command.downgrade(config, "0012_owner_people_sites")
    try:
        with postgres_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO companies (id, name, status, reporting_timezone, "
                    "operational_day_start_minutes) VALUES "
                    "(:id, 'Deployment Migration', 'ACTIVE', 'Asia/Kolkata', 0)"
                ),
                {"id": company_id},
            )
            connection.execute(
                text(
                    "INSERT INTO users (id, phone_number, display_name, status) VALUES "
                    "(:driver_user, '+919100000091', 'Migration Driver', 'ACTIVE'), "
                    "(:supervisor_user, '+919100000092', 'Migration Supervisor', 'ACTIVE')"
                ),
                {
                    "driver_user": driver_user_id,
                    "supervisor_user": supervisor_user_id,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO company_memberships "
                    "(id, company_id, user_id, role, status, display_name) VALUES "
                    "(:driver, :company, :driver_user, 'DRIVER', 'ACTIVE', "
                    "'Migration Driver'), "
                    "(:supervisor, :company, :supervisor_user, 'SUPERVISOR', "
                    "'ACTIVE', 'Migration Supervisor')"
                ),
                {
                    "driver": driver_id,
                    "supervisor": supervisor_id,
                    "company": company_id,
                    "driver_user": driver_user_id,
                    "supervisor_user": supervisor_user_id,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO sites (id, company_id, name, code, status) VALUES "
                    "(:first, :company, 'Old Site', 'OLD', 'ACTIVE'), "
                    "(:current, :company, 'Pilot Site', 'PILOT', 'ACTIVE')"
                ),
                {
                    "first": first_site_id,
                    "current": current_site_id,
                    "company": company_id,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO fleet_assets "
                    "(id, company_id, asset_type, ownership_type, asset_code, "
                    "registration_number, short_name, status) VALUES "
                    "(:asset, :company, 'TIPPER', 'OWNED', 'TIPPER-12', "
                    "'PILOT12', 'Tipper 12', 'ACTIVE')"
                ),
                {"asset": asset_id, "company": company_id},
            )
            for assignment_id, site_id, starts_at, ends_at in (
                (uuid4(), first_site_id, boundary - timedelta(days=30), boundary),
                (uuid4(), current_site_id, boundary, None),
            ):
                connection.execute(
                    text(
                        "INSERT INTO assignments "
                        "(id, company_id, driver_membership_id, "
                        "supervisor_membership_id, asset_id, site_id, starts_at, "
                        "ends_at, regular_duty_minutes) VALUES "
                        "(:id, :company, :driver, :supervisor, :asset, :site, "
                        ":starts_at, :ends_at, 600)"
                    ),
                    {
                        "id": assignment_id,
                        "company": company_id,
                        "driver": driver_id,
                        "supervisor": supervisor_id,
                        "asset": asset_id,
                        "site": site_id,
                        "starts_at": starts_at,
                        "ends_at": ends_at,
                    },
                )

        command.upgrade(config, "head")

        with postgres_engine.begin() as connection:
            deployments = (
                connection.execute(
                    text(
                        "SELECT asset_id, site_id, starts_at, ends_at "
                        "FROM asset_site_deployments WHERE company_id = :company "
                        "ORDER BY starts_at"
                    ),
                    {"company": company_id},
                )
                .mappings()
                .all()
            )
            assert len(deployments) == 2
            assert deployments[0]["site_id"] == first_site_id
            assert deployments[0]["ends_at"] == boundary
            assert deployments[1]["asset_id"] == asset_id
            assert deployments[1]["site_id"] == current_site_id
            assert deployments[1]["ends_at"] is None
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM asset_site_deployments "
                        "WHERE company_id = :company AND asset_id = :asset "
                        "AND ends_at IS NULL"
                    ),
                    {"company": company_id, "asset": asset_id},
                )
                == 1
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM assignments "
                        "WHERE company_id = :company AND asset_id = :asset"
                    ),
                    {"company": company_id, "asset": asset_id},
                )
                == 2
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM assignments AS a JOIN "
                        "asset_site_deployments AS d ON "
                        "d.company_id = a.company_id AND "
                        "d.id = a.asset_site_deployment_id AND "
                        "d.asset_id = a.asset_id AND d.site_id = a.site_id "
                        "WHERE a.company_id = :company AND a.asset_id = :asset"
                    ),
                    {"company": company_id, "asset": asset_id},
                )
                == 2
            )
    finally:
        command.upgrade(config, "head")
        with postgres_engine.begin() as connection:
            params = {"company": company_id}
            connection.execute(text("DELETE FROM assignments WHERE company_id = :company"), params)
            connection.execute(
                text("DELETE FROM asset_site_deployments WHERE company_id = :company"),
                params,
            )
            connection.execute(text("DELETE FROM fleet_assets WHERE company_id = :company"), params)
            connection.execute(text("DELETE FROM sites WHERE company_id = :company"), params)
            connection.execute(
                text("DELETE FROM company_memberships WHERE company_id = :company"),
                params,
            )
            connection.execute(
                text("DELETE FROM users WHERE id IN (:driver_user, :supervisor_user)"),
                {
                    "driver_user": driver_user_id,
                    "supervisor_user": supervisor_user_id,
                },
            )
            connection.execute(text("DELETE FROM companies WHERE id = :company"), params)


def test_0016_seeds_exact_builtin_report_templates_for_existing_company(
    postgres_engine: Engine,
) -> None:
    config = _alembic_config(postgres_engine)
    company_id = UUID("60000000-0000-0000-0000-000000000001")
    command.downgrade(config, "0015_machinery_hmr")
    try:
        with postgres_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO companies (id, name, status, reporting_timezone, "
                    "operational_day_start_minutes) VALUES "
                    "(:id, 'Template Migration', 'ACTIVE', 'Asia/Kolkata', 0)"
                ),
                {"id": company_id},
            )

        command.upgrade(config, "head")

        with postgres_engine.connect() as connection:
            templates = (
                connection.execute(
                    text(
                        "SELECT name, builtin_key, is_builtin, is_default, included_sheets "
                        "FROM report_templates WHERE company_id = :company "
                        "ORDER BY name"
                    ),
                    {"company": company_id},
                )
                .mappings()
                .all()
            )
            assert len(templates) == 3
            assert {row["name"] for row in templates} == {
                "Management Summary",
                "Detailed Operations",
                "Diesel Report",
            }
            assert all(row["is_builtin"] for row in templates)
            assert [row["name"] for row in templates if row["is_default"]] == ["Management Summary"]
            detailed = next(row for row in templates if row["name"] == "Detailed Operations")
            assert len(detailed["included_sheets"]) == 8
    finally:
        command.upgrade(config, "head")
        with postgres_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM report_templates WHERE company_id = :company"),
                {"company": company_id},
            )
            connection.execute(
                text("DELETE FROM companies WHERE id = :company"),
                {"company": company_id},
            )


def test_0017_backfills_site_short_names_and_internal_codes(
    postgres_engine: Engine,
) -> None:
    config = _alembic_config(postgres_engine)
    company_id = UUID("70000000-0000-0000-0000-000000000001")
    generated_site_id = UUID("70000000-0000-0000-0000-000000000002")
    explicit_site_id = UUID("70000000-0000-0000-0000-000000000003")
    blank_name_site_id = UUID("70000000-0000-0000-0000-000000000004")
    command.downgrade(config, "0016_report_templates")
    try:
        with postgres_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO companies (id, name, status, reporting_timezone, "
                    "operational_day_start_minutes) VALUES "
                    "(:id, 'Site Identity Migration', 'ACTIVE', 'Asia/Kolkata', 0)"
                ),
                {"id": company_id},
            )
            connection.execute(
                text(
                    "INSERT INTO sites (id, company_id, name, code, status) VALUES "
                    "(:generated, :company, 'Generated Code Site', NULL, 'ACTIVE'), "
                    "(:explicit, :company, 'Explicit Code Site', 'LEGACY-CODE', 'ACTIVE'), "
                    "(:blank_name, :company, '   ', NULL, 'ACTIVE')"
                ),
                {
                    "generated": generated_site_id,
                    "explicit": explicit_site_id,
                    "blank_name": blank_name_site_id,
                    "company": company_id,
                },
            )

        command.upgrade(config, "head")

        with postgres_engine.connect() as connection:
            sites = (
                connection.execute(
                    text(
                        "SELECT id, name, short_name, code FROM sites "
                        "WHERE company_id = :company ORDER BY id"
                    ),
                    {"company": company_id},
                )
                .mappings()
                .all()
            )
            assert [dict(row) for row in sites] == [
                {
                    "id": generated_site_id,
                    "name": "Generated Code Site",
                    "short_name": "Generated Code Site",
                    "code": f"SITE-{generated_site_id.hex.upper()}",
                },
                {
                    "id": explicit_site_id,
                    "name": "Explicit Code Site",
                    "short_name": "Explicit Code Site",
                    "code": "LEGACY-CODE",
                },
                {
                    "id": blank_name_site_id,
                    "name": "   ",
                    "short_name": f"Legacy Site {blank_name_site_id.hex.upper()}",
                    "code": f"SITE-{blank_name_site_id.hex.upper()}",
                },
            ]
            nullable: dict[str, str] = {
                str(row["column_name"]): str(row["is_nullable"])
                for row in connection.execute(
                    text(
                        "SELECT column_name, is_nullable FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'sites' "
                        "AND column_name IN ('short_name', 'code')"
                    )
                ).mappings()
            }
            assert nullable == {"code": "NO", "short_name": "NO"}
    finally:
        command.upgrade(config, "head")
        with postgres_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM sites WHERE company_id = :company"),
                {"company": company_id},
            )
            connection.execute(
                text("DELETE FROM report_templates WHERE company_id = :company"),
                {"company": company_id},
            )
            connection.execute(
                text("DELETE FROM companies WHERE id = :company"),
                {"company": company_id},
            )
