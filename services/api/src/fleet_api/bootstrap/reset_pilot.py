"""Explicit, non-production reset for operational data in the named pilot fixture."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from fleet_api.bootstrap.pilot import COMPANY_NAME, SITE_NAME, TIPPER_REGISTRATION
from fleet_api.core.config import get_settings
from fleet_api.db.models import (
    AuditLog,
    Company,
    DieselEvent,
    EmergencyEvent,
    EventVerification,
    EvidenceObject,
    KmReading,
    OperationalEvent,
    Site,
    SiteDailyClosure,
    SiteDailyClosureHistory,
    Tipper,
    TripEvent,
)
from fleet_api.db.session import SessionLocal
from fleet_api.domain.assets import normalize_registration_number
from fleet_api.domain.errors import ObjectStorageUnavailableError
from fleet_api.storage.objects import build_object_storage


def _require_fixture(session: Session) -> Company:
    company = session.scalar(select(Company).where(Company.name == COMPANY_NAME))
    if company is None:
        raise RuntimeError(f"fixture {COMPANY_NAME!r} does not exist; run bootstrap-pilot first")
    site = session.scalar(select(Site).where(Site.company_id == company.id, Site.name == SITE_NAME))
    tipper = session.scalar(
        select(Tipper).where(
            Tipper.company_id == company.id,
            Tipper.registration_number == normalize_registration_number(TIPPER_REGISTRATION),
        )
    )
    if site is None or tipper is None:
        raise RuntimeError("Pilot Construction fixture is incomplete; refusing a partial reset")
    return company


def reset_pilot_operational_data(
    session: Session, *, delete_objects: bool = True
) -> dict[str, int]:
    settings = get_settings()
    if settings.environment.lower() in {"production", "prod"}:
        raise RuntimeError("pilot reset is forbidden in production")
    company = _require_fixture(session)
    event_ids = list(
        session.scalars(
            select(OperationalEvent.id).where(OperationalEvent.company_id == company.id)
        )
    )
    event_uuids = list(
        session.scalars(
            select(OperationalEvent.client_event_uuid).where(
                OperationalEvent.company_id == company.id
            )
        )
    )
    evidence = list(
        session.scalars(select(EvidenceObject).where(EvidenceObject.company_id == company.id))
    )

    deleted_objects = 0
    if delete_objects and evidence:
        try:
            storage = build_object_storage(settings)
            for item in evidence:
                storage.delete_private(object_key=item.object_key)
                deleted_objects += 1
        except ObjectStorageUnavailableError:
            # The local unavailable provider has no readable objects. Metadata is
            # still removed so the pilot can be repeated safely.
            pass

    if event_ids:
        session.execute(delete(EventVerification).where(EventVerification.company_id == company.id))
        session.execute(delete(TripEvent).where(TripEvent.event_id.in_(event_ids)))
        session.execute(delete(KmReading).where(KmReading.event_id.in_(event_ids)))
        session.execute(delete(DieselEvent).where(DieselEvent.event_id.in_(event_ids)))
        session.execute(delete(EmergencyEvent).where(EmergencyEvent.event_id.in_(event_ids)))
        session.execute(delete(OperationalEvent).where(OperationalEvent.id.in_(event_ids)))
    session.execute(delete(EvidenceObject).where(EvidenceObject.company_id == company.id))
    session.execute(
        delete(SiteDailyClosureHistory).where(SiteDailyClosureHistory.company_id == company.id)
    )
    session.execute(delete(SiteDailyClosure).where(SiteDailyClosure.company_id == company.id))
    session.execute(
        delete(AuditLog).where(
            AuditLog.company_id == company.id,
            AuditLog.entity_type.in_(["SITE_DAILY_CLOSURE", "EMERGENCY_EVENT"]),
        )
    )
    session.flush()
    return {
        "events": len(event_ids),
        "evidence_metadata": len(evidence),
        "evidence_objects": deleted_objects,
        "client_event_uuids": len(event_uuids),
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Reset only Pilot Construction operational data")
    parser.add_argument(
        "--confirm-pilot-reset",
        action="store_true",
        help="explicitly confirm the named fixture reset",
    )
    parser.add_argument("--yes", action="store_true", help="confirm non-interactive execution")
    args = parser.parse_args(argv)
    if not args.confirm_pilot_reset or not args.yes:
        raise SystemExit("refusing reset: pass --confirm-pilot-reset --yes")
    with SessionLocal.begin() as session:
        counts = reset_pilot_operational_data(session)
    print("PILOT_OPERATIONAL_RESET_SUCCEEDED")
    for key, value in counts.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
