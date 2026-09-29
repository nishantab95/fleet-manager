from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID

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
    config.set_main_option(
        "sqlalchemy.url", engine.url.render_as_string(hide_password=False)
    )
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
                    text(
                        "SELECT count(*) FROM operational_events "
                        "WHERE company_id = :company_id"
                    ),
                    {"company_id": COMPANY_ID},
                ),
                "verifications": connection.scalar(
                    text(
                        "SELECT count(*) FROM event_verifications "
                        "WHERE company_id = :company_id"
                    ),
                    {"company_id": COMPANY_ID},
                ),
                "evidence": connection.scalar(
                    text(
                        "SELECT count(*) FROM evidence_objects "
                        "WHERE company_id = :company_id"
                    ),
                    {"company_id": COMPANY_ID},
                ),
            }

        command.upgrade(config, "head")

        with postgres_engine.connect() as connection:
            asset = connection.execute(
                text(
                    "SELECT id, asset_code, asset_type, ownership_type, registration_number, "
                    "status FROM fleet_assets WHERE id = :id"
                ),
                {"id": ASSET_ID},
            ).mappings().one()
            assert dict(asset) == {
                "id": ASSET_ID,
                "asset_code": "TIPPER-12",
                "asset_type": "TIPPER",
                "ownership_type": "OWNED",
                "registration_number": "KA01AB1234",
                "status": "ACTIVE",
            }
            assert connection.scalar(
                text("SELECT asset_id FROM assignments WHERE id = :id"),
                {"id": ASSIGNMENT_ID},
            ) == ASSET_ID
            assert connection.scalar(
                text("SELECT asset_id FROM duty_sessions WHERE id = :id"),
                {"id": DUTY_ID},
            ) == ASSET_ID
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM operational_events "
                    "WHERE company_id = :company_id"
                ),
                {"company_id": COMPANY_ID},
            ) == legacy_counts["events"]
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM event_verifications "
                    "WHERE company_id = :company_id"
                ),
                {"company_id": COMPANY_ID},
            ) == legacy_counts["verifications"]
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM evidence_objects "
                    "WHERE company_id = :company_id"
                ),
                {"company_id": COMPANY_ID},
            ) == legacy_counts["evidence"]

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
            report = ReportingService(session, context).site_daily(
                SITE_ID, date(2026, 1, 15)
            )
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
