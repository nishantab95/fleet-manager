from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fleet_api.db.models import (
    Assignment,
    CompanyMembership,
    Device,
    DieselEvent,
    EmergencyEvent,
    EventVerification,
    KmReading,
    OperationalEvent,
    TripEvent,
)
from fleet_api.domain.enums import (
    EmergencyCategory,
    EmergencyStatus,
    KmReadingType,
    MembershipRole,
    OperationalEventType,
    VerificationStatus,
)
from fleet_api.domain.errors import (
    AssignmentNotEffectiveError,
    DomainError,
    EventTypeMismatchError,
    RoleViolationError,
    TenantConsistencyError,
)


def _event_context(
    session: Session,
    *,
    company_id: UUID,
    assignment_id: UUID,
    device_id: UUID | None,
    device_created_at: datetime,
) -> None:
    assignment = session.get(Assignment, assignment_id)
    if assignment is None or assignment.company_id != company_id:
        raise TenantConsistencyError("assignment does not belong to this company")
    if device_created_at < assignment.starts_at or (
        assignment.ends_at is not None and device_created_at >= assignment.ends_at
    ):
        raise AssignmentNotEffectiveError("event timestamp is outside the assignment interval")
    if device_id is not None:
        device = session.get(Device, device_id)
        if device is None or device.company_id != company_id:
            raise TenantConsistencyError("device does not belong to this company")


def _existing_or_new_event(
    session: Session,
    *,
    company_id: UUID,
    assignment_id: UUID,
    client_event_uuid: UUID,
    device_id: UUID | None,
    device_created_at: datetime,
    event_type: OperationalEventType,
) -> tuple[OperationalEvent, bool]:
    _event_context(
        session,
        company_id=company_id,
        assignment_id=assignment_id,
        device_id=device_id,
        device_created_at=device_created_at,
    )
    existing = session.scalar(
        select(OperationalEvent).where(
            OperationalEvent.company_id == company_id,
            OperationalEvent.client_event_uuid == client_event_uuid,
        )
    )
    if existing is not None:
        if existing.event_type != event_type:
            raise EventTypeMismatchError("client event UUID is already used by another event type")
        return existing, True
    event = OperationalEvent(
        company_id=company_id,
        assignment_id=assignment_id,
        client_event_uuid=client_event_uuid,
        device_id=device_id,
        device_created_at=device_created_at,
        event_type=event_type,
    )
    try:
        # Keep the unique-key race inside a savepoint so a concurrent retry
        # can recover the committed envelope without poisoning the caller's
        # transaction. PostgreSQL's company/client UUID constraint remains
        # the authoritative idempotency boundary.
        with session.begin_nested():
            session.add(event)
            session.flush()
    except IntegrityError:
        existing = session.scalar(
            select(OperationalEvent).where(
                OperationalEvent.company_id == company_id,
                OperationalEvent.client_event_uuid == client_event_uuid,
            )
        )
        if existing is None:
            raise
        if existing.event_type != event_type:
            raise EventTypeMismatchError(
                "client event UUID is already used by another event type"
            ) from None
        return existing, True
    return event, False


def create_trip_event(
    session: Session,
    *,
    company_id: UUID,
    assignment_id: UUID,
    client_event_uuid: UUID,
    device_created_at: datetime,
    device_id: UUID | None = None,
) -> TripEvent:
    event, existing = _existing_or_new_event(
        session,
        company_id=company_id,
        assignment_id=assignment_id,
        client_event_uuid=client_event_uuid,
        device_id=device_id,
        device_created_at=device_created_at,
        event_type=OperationalEventType.TRIP_COMPLETE,
    )
    trip = session.get(TripEvent, event.id)
    if existing:
        if trip is None:
            raise DomainError("idempotent event envelope has no trip payload")
        return trip
    trip = TripEvent(event_id=event.id)
    session.add(trip)
    session.flush()
    return trip


def create_km_reading(
    session: Session,
    *,
    company_id: UUID,
    assignment_id: UUID,
    client_event_uuid: UUID,
    device_created_at: datetime,
    reading_type: KmReadingType,
    reading_value: Decimal,
    object_reference: str | None = None,
    device_id: UUID | None = None,
) -> KmReading:
    if reading_value < 0:
        raise DomainError("reading_value must be non-negative")
    event, existing = _existing_or_new_event(
        session,
        company_id=company_id,
        assignment_id=assignment_id,
        client_event_uuid=client_event_uuid,
        device_id=device_id,
        device_created_at=device_created_at,
        event_type=OperationalEventType.KM_READING,
    )
    reading = session.get(KmReading, event.id)
    if existing:
        if reading is None:
            raise DomainError("idempotent event envelope has no km payload")
        return reading
    reading = KmReading(
        event_id=event.id,
        reading_type=reading_type,
        reading_value=reading_value,
        object_reference=object_reference,
    )
    session.add(reading)
    session.flush()
    return reading


def create_diesel_event(
    session: Session,
    *,
    company_id: UUID,
    assignment_id: UUID,
    client_event_uuid: UUID,
    device_created_at: datetime,
    litres: Decimal,
    object_reference: str | None = None,
    device_id: UUID | None = None,
) -> DieselEvent:
    if litres <= 0:
        raise DomainError("litres must be greater than zero")
    event, existing = _existing_or_new_event(
        session,
        company_id=company_id,
        assignment_id=assignment_id,
        client_event_uuid=client_event_uuid,
        device_id=device_id,
        device_created_at=device_created_at,
        event_type=OperationalEventType.DIESEL,
    )
    diesel = session.get(DieselEvent, event.id)
    if existing:
        if diesel is None:
            raise DomainError("idempotent event envelope has no diesel payload")
        return diesel
    diesel = DieselEvent(litres=litres, object_reference=object_reference, event_id=event.id)
    session.add(diesel)
    session.flush()
    return diesel


def create_emergency_event(
    session: Session,
    *,
    company_id: UUID,
    assignment_id: UUID,
    client_event_uuid: UUID,
    device_created_at: datetime,
    category: EmergencyCategory | None = None,
    description: str | None = None,
    device_id: UUID | None = None,
) -> EmergencyEvent:
    event, existing = _existing_or_new_event(
        session,
        company_id=company_id,
        assignment_id=assignment_id,
        client_event_uuid=client_event_uuid,
        device_id=device_id,
        device_created_at=device_created_at,
        event_type=OperationalEventType.EMERGENCY,
    )
    emergency = session.get(EmergencyEvent, event.id)
    if existing:
        if emergency is None:
            raise DomainError("idempotent event envelope has no emergency payload")
        return emergency
    emergency = EmergencyEvent(
        event_id=event.id,
        category=category,
        status=EmergencyStatus.OPEN,
        description=description,
    )
    session.add(emergency)
    session.flush()
    return emergency


def record_verification(
    session: Session,
    *,
    company_id: UUID,
    event_id: UUID,
    status: VerificationStatus,
    changed_by_membership_id: UUID | None = None,
    reason: str | None = None,
) -> EventVerification:
    event = session.get(OperationalEvent, event_id)
    if event is None or event.company_id != company_id:
        raise TenantConsistencyError("event does not belong to this company")
    if changed_by_membership_id is not None:
        membership = session.get(CompanyMembership, changed_by_membership_id)
        if membership is None or membership.company_id != company_id:
            raise TenantConsistencyError("verification actor does not belong to this company")
        if membership.role != MembershipRole.SUPERVISOR:
            raise RoleViolationError("only a supervisor membership can record verification")
    event.verification_status = status
    history = EventVerification(
        company_id=company_id,
        event_id=event_id,
        changed_by_membership_id=changed_by_membership_id,
        status=status,
        reason=reason,
    )
    session.add(history)
    session.flush()
    return history
