"""Print a read-only Pilot event/duty snapshot without credentials or tokens."""

from __future__ import annotations

import json

from sqlalchemy import text

from fleet_api.bootstrap.pilot import COMPANY_NAME, TIPPER_REGISTRATION
from fleet_api.db.session import engine
from fleet_api.domain.assets import normalize_registration_number


EVENTS = text(
    """
    SELECT
      oe.id AS event_id,
      oe.client_event_uuid,
      oe.event_type,
      oe.device_created_at,
      oe.server_received_at,
      oe.verification_status,
      oe.duty_session_id
    FROM operational_events AS oe
    JOIN companies AS c ON c.id = oe.company_id
    JOIN assignments AS a
      ON a.id = oe.assignment_id AND a.company_id = oe.company_id
    JOIN tippers AS t ON t.id = a.tipper_id AND t.company_id = a.company_id
    WHERE c.name = :company_name
      AND t.registration_number = :tipper_registration
    ORDER BY oe.device_created_at, oe.server_received_at, oe.id
    """
)

DUTIES = text(
    """
    SELECT
      ds.id AS session_id,
      ds.start_event_id,
      ds.start_km,
      ds.end_event_id,
      ds.end_km,
      ds.status,
      ds.started_at,
      ds.ended_at,
      ds.updated_at
    FROM duty_sessions AS ds
    JOIN companies AS c ON c.id = ds.company_id
    JOIN tippers AS t
      ON t.id = ds.tipper_id AND t.company_id = ds.company_id
    WHERE c.name = :company_name
      AND t.registration_number = :tipper_registration
    ORDER BY ds.started_at, ds.id
    """
)


def _json_rows(rows: list[dict[str, object]]) -> str:
    return json.dumps(rows, default=str, indent=2)


def main() -> None:
    parameters = {
        "company_name": COMPANY_NAME,
        "tipper_registration": normalize_registration_number(TIPPER_REGISTRATION),
    }
    with engine.connect() as connection:
        event_rows = [dict(row) for row in connection.execute(EVENTS, parameters).mappings()]
        duty_rows = [dict(row) for row in connection.execute(DUTIES, parameters).mappings()]
        connection.rollback()

    print("BACKEND_EVENT_TABLE")
    print(_json_rows(event_rows))
    print("BACKEND_DUTY_TABLE")
    print(_json_rows(duty_rows))


if __name__ == "__main__":
    main()
