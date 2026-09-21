from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fleet_api.db.models import (
    Assignment,
    AuditLog,
    Company,
    CompanyMembership,
    EmergencyEvent,
    EventVerification,
    OperationalEvent,
    Site,
    Tipper,
    TripEvent,
)
from fleet_api.domain.assignments import create_assignment, grant_supervisor_site_access
from fleet_api.domain.audit import write_audit_log
from fleet_api.domain.enums import (
    EmergencyCategory,
    KmReadingType,
    VerificationStatus,
)
from fleet_api.domain.errors import (
    AssignmentConflictError,
    AssignmentNotEffectiveError,
    DomainError,
    DuplicateAccessError,
    RoleViolationError,
    TenantConsistencyError,
)
from fleet_api.domain.events import (
    create_diesel_event,
    create_emergency_event,
    create_km_reading,
    create_trip_event,
    record_verification,
)

pytestmark = pytest.mark.postgres


def dt(day: int, hour: int = 8) -> datetime:
    return datetime(2026, 1, day, hour, tzinfo=UTC)


def value[T](records: dict[str, object], key: str, expected_type: type[T]) -> T:
    item = records[key]
    assert isinstance(item, expected_type)
    return item


def create_a_assignment(
    session: Session, records: dict[str, object], **overrides: object
) -> Assignment:
    company = value(records, "company_a", Company)
    driver = value(records, "driver_a", CompanyMembership)
    supervisor = value(records, "supervisor_a", CompanyMembership)
    tipper = value(records, "tipper_a", Tipper)
    site = value(records, "site_a", Site)
    params: dict[str, object] = {
        "company_id": company.id,
        "driver_membership_id": driver.id,
        "supervisor_membership_id": supervisor.id,
        "tipper_id": tipper.id,
        "site_id": site.id,
        "starts_at": dt(1),
    }
    params.update(overrides)
    return create_assignment(session, **params)  # type: ignore[arg-type]


def test_company_site_tipper_and_membership_are_company_scoped(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    company = value(tenant_records, "company_a", Company)
    site = value(tenant_records, "site_a", Site)
    tipper = value(tenant_records, "tipper_a", Tipper)
    membership = value(tenant_records, "driver_a", CompanyMembership)

    assert site.company_id == company.id
    assert tipper.company_id == company.id
    assert membership.company_id == company.id
    assert db_session.scalar(select(func.count()).select_from(Company)) == 2


def test_cross_company_assignment_records_fail(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    company = value(tenant_records, "company_a", Company)
    driver = value(tenant_records, "driver_a", CompanyMembership)
    supervisor = value(tenant_records, "supervisor_a", CompanyMembership)
    tipper_b = value(tenant_records, "tipper_b", Tipper)
    site_a = value(tenant_records, "site_a", Site)

    with pytest.raises(TenantConsistencyError):
        create_assignment(
            db_session,
            company_id=company.id,
            driver_membership_id=driver.id,
            supervisor_membership_id=supervisor.id,
            tipper_id=tipper_b.id,
            site_id=site_a.id,
            starts_at=dt(1),
        )


@pytest.mark.parametrize(
    ("field", "record_key"),
    [
        ("driver_membership_id", "driver_b"),
        ("supervisor_membership_id", "supervisor_b"),
        ("tipper_id", "tipper_b"),
        ("site_id", "site_b"),
    ],
)
def test_each_cross_company_assignment_reference_fails(
    db_session: Session,
    tenant_records: dict[str, object],
    field: str,
    record_key: str,
) -> None:
    company = value(tenant_records, "company_a", Company)
    driver = value(tenant_records, "driver_a", CompanyMembership)
    supervisor = value(tenant_records, "supervisor_a", CompanyMembership)
    tipper = value(tenant_records, "tipper_a", Tipper)
    site = value(tenant_records, "site_a", Site)
    cross_company_record = tenant_records[record_key]
    cross_company_id = getattr(cross_company_record, "id", None)
    assert isinstance(cross_company_id, UUID)
    params: dict[str, object] = {
        "company_id": company.id,
        "driver_membership_id": driver.id,
        "supervisor_membership_id": supervisor.id,
        "tipper_id": tipper.id,
        "site_id": site.id,
        "starts_at": dt(1),
    }
    params[field] = cross_company_id
    with pytest.raises(TenantConsistencyError):
        create_assignment(db_session, **params)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("driver_key", "supervisor_key"),
    [("owner_a", "supervisor_a"), ("driver_a", "driver_a")],
)
def test_assignment_requires_driver_and_supervisor_roles(
    db_session: Session,
    tenant_records: dict[str, object],
    driver_key: str,
    supervisor_key: str,
) -> None:
    company = value(tenant_records, "company_a", Company)
    driver = value(tenant_records, driver_key, CompanyMembership)
    supervisor = value(tenant_records, supervisor_key, CompanyMembership)
    tipper = value(tenant_records, "tipper_a", Tipper)
    site = value(tenant_records, "site_a", Site)

    with pytest.raises(RoleViolationError):
        create_assignment(
            db_session,
            company_id=company.id,
            driver_membership_id=driver.id,
            supervisor_membership_id=supervisor.id,
            tipper_id=tipper.id,
            site_id=site.id,
            starts_at=dt(1),
        )


def test_assignment_end_must_follow_start(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    with pytest.raises(DomainError):
        create_a_assignment(db_session, tenant_records, ends_at=dt(1, 7))

    assignment = Assignment(
        company_id=value(tenant_records, "company_a", Company).id,
        driver_membership_id=value(tenant_records, "driver_a", CompanyMembership).id,
        supervisor_membership_id=value(tenant_records, "supervisor_a", CompanyMembership).id,
        tipper_id=value(tenant_records, "tipper_a", Tipper).id,
        site_id=value(tenant_records, "site_a", Site).id,
        starts_at=dt(1),
        ends_at=dt(1, 7),
    )
    invalid_assignment = db_session.begin_nested()
    db_session.add(assignment)
    with pytest.raises(IntegrityError):
        db_session.flush()
    invalid_assignment.rollback()


def test_driver_and_tipper_cannot_have_overlapping_assignments(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    first_scenario = db_session.begin_nested()
    create_a_assignment(db_session, tenant_records, ends_at=dt(3))
    with pytest.raises(AssignmentConflictError):
        create_a_assignment(db_session, tenant_records, starts_at=dt(2))
    first_scenario.rollback()

    second_scenario = db_session.begin_nested()
    create_a_assignment(db_session, tenant_records, ends_at=dt(3))
    driver_a2 = value(tenant_records, "driver_a2", CompanyMembership)
    with pytest.raises(AssignmentConflictError):
        create_a_assignment(
            db_session,
            tenant_records,
            driver_membership_id=driver_a2.id,
            starts_at=dt(2),
        )
    second_scenario.rollback()

    assignment = create_a_assignment(db_session, tenant_records, starts_at=dt(4))
    assert assignment.starts_at == dt(4)


def test_historical_assignment_is_not_rewritten_by_later_assignment(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    first = create_a_assignment(db_session, tenant_records, ends_at=dt(3))
    second = create_a_assignment(db_session, tenant_records, starts_at=dt(3))

    assert first.ends_at == dt(3)
    assert second.starts_at == dt(3)
    assert first.id != second.id


def test_supervisor_site_access_is_company_consistent_and_unique(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    company = value(tenant_records, "company_a", Company)
    supervisor = value(tenant_records, "supervisor_a", CompanyMembership)
    site = value(tenant_records, "site_a", Site)
    access_scenario = db_session.begin_nested()
    grant_supervisor_site_access(
        db_session,
        company_id=company.id,
        supervisor_membership_id=supervisor.id,
        site_id=site.id,
    )
    with pytest.raises(DuplicateAccessError):
        grant_supervisor_site_access(
            db_session,
            company_id=company.id,
            supervisor_membership_id=supervisor.id,
            site_id=site.id,
        )
    access_scenario.rollback()


def test_event_can_reference_historical_assignment_and_rejects_out_of_range_timestamp(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    assignment = create_a_assignment(db_session, tenant_records, ends_at=dt(3))
    event = create_trip_event(
        db_session,
        company_id=assignment.company_id,
        assignment_id=assignment.id,
        client_event_uuid=UUID("00000000-0000-0000-0000-000000000001"),
        device_created_at=dt(2),
    )
    assert db_session.get(TripEvent, event.event_id) is not None
    with pytest.raises(AssignmentNotEffectiveError):
        create_trip_event(
            db_session,
            company_id=assignment.company_id,
            assignment_id=assignment.id,
            client_event_uuid=UUID("00000000-0000-0000-0000-000000000002"),
            device_created_at=dt(3),
        )


def test_same_client_event_uuid_is_idempotent_but_distinct_uuids_are_distinct(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    assignment = create_a_assignment(db_session, tenant_records)
    first = create_trip_event(
        db_session,
        company_id=assignment.company_id,
        assignment_id=assignment.id,
        client_event_uuid=UUID("00000000-0000-0000-0000-000000000010"),
        device_created_at=dt(1, 9),
    )
    retry = create_trip_event(
        db_session,
        company_id=assignment.company_id,
        assignment_id=assignment.id,
        client_event_uuid=UUID("00000000-0000-0000-0000-000000000010"),
        device_created_at=dt(1, 9),
    )
    second = create_trip_event(
        db_session,
        company_id=assignment.company_id,
        assignment_id=assignment.id,
        client_event_uuid=UUID("00000000-0000-0000-0000-000000000011"),
        device_created_at=dt(1, 9),
    )

    assert first.event_id == retry.event_id
    assert second.event_id != first.event_id
    assert db_session.scalar(select(func.count()).select_from(OperationalEvent)) == 2


def test_km_and_diesel_values_are_positive(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    assignment = create_a_assignment(db_session, tenant_records)
    with pytest.raises(DomainError):
        create_km_reading(
            db_session,
            company_id=assignment.company_id,
            assignment_id=assignment.id,
            client_event_uuid=UUID("00000000-0000-0000-0000-000000000020"),
            device_created_at=dt(1, 9),
            reading_type=KmReadingType.START_READING,
            reading_value=Decimal("-1"),
        )
    with pytest.raises(DomainError):
        create_diesel_event(
            db_session,
            company_id=assignment.company_id,
            assignment_id=assignment.id,
            client_event_uuid=UUID("00000000-0000-0000-0000-000000000021"),
            device_created_at=dt(1, 9),
            litres=Decimal("0"),
        )


def test_event_categories_and_verification_statuses_are_constrained(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    assignment = create_a_assignment(db_session, tenant_records)
    with pytest.raises(ValueError):
        EmergencyCategory("NOT_A_REAL_CATEGORY")
    with pytest.raises(ValueError):
        VerificationStatus("NOT_A_REAL_STATUS")
    emergency = create_emergency_event(
        db_session,
        company_id=assignment.company_id,
        assignment_id=assignment.id,
        client_event_uuid=UUID("00000000-0000-0000-0000-000000000030"),
        device_created_at=dt(1, 9),
        category=EmergencyCategory.BREAKDOWN,
    )
    assert db_session.get(EmergencyEvent, emergency.event_id) is not None


def test_verification_history_preserves_each_status_change(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    assignment = create_a_assignment(db_session, tenant_records)
    trip = create_trip_event(
        db_session,
        company_id=assignment.company_id,
        assignment_id=assignment.id,
        client_event_uuid=UUID("00000000-0000-0000-0000-000000000040"),
        device_created_at=dt(1, 9),
    )
    supervisor = value(tenant_records, "supervisor_a", CompanyMembership)
    first = record_verification(
        db_session,
        company_id=assignment.company_id,
        event_id=trip.event_id,
        status=VerificationStatus.APPROVED,
        changed_by_membership_id=supervisor.id,
    )
    second = record_verification(
        db_session,
        company_id=assignment.company_id,
        event_id=trip.event_id,
        status=VerificationStatus.DISPUTED,
        changed_by_membership_id=supervisor.id,
        reason="Evidence requires review",
    )
    assert first.id != second.id
    assert db_session.scalar(select(func.count()).select_from(EventVerification)) == 2
    event = db_session.get(OperationalEvent, trip.event_id)
    assert event is not None
    assert event.verification_status == VerificationStatus.DISPUTED


def test_audit_log_preserves_explicit_actor_and_values(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    company = value(tenant_records, "company_a", Company)
    actor = value(tenant_records, "supervisor_a", CompanyMembership)
    target = value(tenant_records, "tipper_a", Tipper)
    audit = write_audit_log(
        db_session,
        company_id=company.id,
        actor_membership_id=actor.id,
        action="TIPPER_RENAMED",
        entity_type="Tipper",
        entity_id=target.id,
        old_values={"short_name": "Old"},
        new_values={"short_name": "New"},
        reason="Operational correction",
    )
    stored = db_session.get(AuditLog, audit.id)
    assert stored is not None
    assert stored.old_values == {"short_name": "Old"}
    assert stored.new_values == {"short_name": "New"}
