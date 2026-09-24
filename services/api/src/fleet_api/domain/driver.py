from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import PurePosixPath
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fleet_api.auth.service import AuthContext
from fleet_api.core.config import Settings
from fleet_api.db.models import (
    Assignment,
    CompanyMembership,
    Device,
    DutySession,
    EmergencyEvent,
    EvidenceObject,
    OperationalEvent,
    Site,
    Tipper,
    User,
)
from fleet_api.db.models.common import utc_now
from fleet_api.domain.enums import (
    DevicePlatform,
    DeviceStatus,
    DutySessionStatus,
    EmergencyCategory,
    EmergencyStatus,
    KmReadingType,
    MembershipRole,
    OperationalEventType,
    SiteStatus,
    TipperStatus,
    VerificationStatus,
)
from fleet_api.domain.errors import (
    AssignmentNotEffectiveError,
    DomainError,
    DutyAlreadyStartedError,
    DutyAssignmentMismatchError,
    DutyEventOutsideSessionError,
    DutyKmValidationError,
    DutyNotStartedError,
    DutyOdometerContinuityError,
    EvidenceValidationError,
    ObjectStorageUnavailableError,
    RoleViolationError,
    TenantConsistencyError,
)
from fleet_api.domain.events import (
    create_diesel_event,
    create_emergency_event,
    create_km_reading,
    create_trip_event,
)
from fleet_api.storage.objects import ObjectStorage


@dataclass(frozen=True)
class DriverAssignment:
    assignment: Assignment
    tipper: Tipper
    site: Site
    supervisor_membership: CompanyMembership
    supervisor: User


@dataclass(frozen=True)
class DriverEventResult:
    event: OperationalEvent
    duplicate: bool


@dataclass(frozen=True)
class DriverDutyState:
    session: DutySession | None


def _require_driver(context: AuthContext) -> None:
    if context.membership.role != MembershipRole.DRIVER:
        raise RoleViolationError("driver membership is required")


def _assignment_query(
    session: Session,
    *,
    context: AuthContext,
    at: datetime,
) -> DriverAssignment | None:
    row = session.execute(
        select(Assignment, Tipper, Site, CompanyMembership, User)
        .join(Tipper, Tipper.id == Assignment.tipper_id)
        .join(Site, Site.id == Assignment.site_id)
        .join(
            CompanyMembership,
            CompanyMembership.id == Assignment.supervisor_membership_id,
        )
        .join(User, User.id == CompanyMembership.user_id)
        .where(
            Assignment.company_id == context.company.id,
            Assignment.driver_membership_id == context.membership.id,
            Assignment.starts_at <= at,
            (Assignment.ends_at.is_(None) | (Assignment.ends_at > at)),
            Tipper.status == TipperStatus.ACTIVE,
            Site.status == SiteStatus.ACTIVE,
            CompanyMembership.status == "ACTIVE",
        )
        .order_by(Assignment.starts_at.desc(), Assignment.id)
    ).first()
    if row is None:
        return None
    assignment, tipper, site, supervisor_membership, supervisor = row._tuple()
    return DriverAssignment(assignment, tipper, site, supervisor_membership, supervisor)


def get_current_assignment(session: Session, context: AuthContext) -> DriverAssignment | None:
    _require_driver(context)
    return _assignment_query(session, context=context, at=utc_now())


def _active_duty_session(
    session: Session,
    *,
    context: AuthContext,
    lock: bool = False,
) -> DutySession | None:
    statement = (
        select(DutySession)
        .where(
            DutySession.company_id == context.company.id,
            DutySession.driver_membership_id == context.membership.id,
            DutySession.status == DutySessionStatus.ACTIVE,
        )
        .order_by(DutySession.started_at.desc(), DutySession.id.desc())
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalars(statement).first()


def get_current_duty_state(session: Session, context: AuthContext) -> DriverDutyState:
    _require_driver(context)
    active = _active_duty_session(session, context=context)
    if active is not None:
        return DriverDutyState(active)
    assignment = get_current_assignment(session, context)
    if assignment is None:
        return DriverDutyState(None)
    closed = session.scalar(
        select(DutySession)
        .where(
            DutySession.company_id == context.company.id,
            DutySession.driver_membership_id == context.membership.id,
            DutySession.assignment_id == assignment.assignment.id,
            DutySession.status == DutySessionStatus.CLOSED,
        )
        .order_by(DutySession.ended_at.desc(), DutySession.id.desc())
    )
    return DriverDutyState(closed)


def _operational_date(context: AuthContext, timestamp: datetime) -> date:
    """Label a session by the operational date at its START timestamp.

    The label is for reporting/grouping only. A session remains one lifecycle
    record when its END timestamp crosses midnight.
    """
    try:
        local = timestamp.astimezone(ZoneInfo(context.company.reporting_timezone))
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise DomainError("company reporting timezone is invalid") from exc
    return (local - timedelta(minutes=context.company.operational_day_start_minutes)).date()


def _previous_valid_end_km(
    session: Session,
    *,
    company_id: UUID,
    tipper_id: UUID,
    before: datetime,
) -> Decimal | None:
    """Return the latest non-rejected END KM for this tipper before START."""

    valid_statuses = {
        VerificationStatus.PENDING_VERIFICATION,
        VerificationStatus.APPROVED,
        VerificationStatus.AMENDED,
    }
    return session.scalar(
        select(DutySession.end_km)
        .join(OperationalEvent, OperationalEvent.id == DutySession.end_event_id)
        .where(
            DutySession.company_id == company_id,
            DutySession.tipper_id == tipper_id,
            DutySession.status == DutySessionStatus.CLOSED,
            DutySession.ended_at < before,
            OperationalEvent.verification_status.in_(valid_statuses),
        )
        .order_by(DutySession.ended_at.desc(), DutySession.id.desc())
        .limit(1)
    )


def _require_active_duty(
    session: Session,
    *,
    context: AuthContext,
    assignment: Assignment,
    device_created_at: datetime,
) -> DutySession:
    active = _active_duty_session(session, context=context, lock=True)
    if active is None:
        raise DutyNotStartedError("an active duty session is required")
    if active.assignment_id != assignment.id:
        raise DutyAssignmentMismatchError(
            "the active duty session belongs to another assignment; "
            "end it before starting this assignment"
        )
    if device_created_at < active.started_at:
        raise DutyEventOutsideSessionError("event timestamp is before the active duty session")
    return active


def _assignment_at_event(
    session: Session,
    *,
    context: AuthContext,
    device_created_at: datetime,
    settings: Settings,
) -> Assignment:
    _require_driver(context)
    if device_created_at.tzinfo is None:
        raise DomainError("device_created_at must include a timezone")
    now = utc_now()
    if device_created_at > now + timedelta(seconds=settings.event_future_skew_seconds):
        raise DomainError("device_created_at is too far in the future")
    assignment = session.scalar(
        select(Assignment)
        .where(
            Assignment.company_id == context.company.id,
            Assignment.driver_membership_id == context.membership.id,
            Assignment.starts_at <= device_created_at,
            (Assignment.ends_at.is_(None) | (Assignment.ends_at > device_created_at)),
        )
        .order_by(Assignment.starts_at.desc(), Assignment.id)
    )
    if assignment is None:
        raise AssignmentNotEffectiveError("event timestamp has no driver assignment")
    return assignment


def register_device(
    session: Session,
    context: AuthContext,
    *,
    installation_identifier: str,
    platform: DevicePlatform,
) -> Device:
    _require_driver(context)
    clean_identifier = installation_identifier.strip()
    if not clean_identifier or len(clean_identifier) > 200:
        raise DomainError("installation_identifier is invalid")
    device = session.scalar(
        select(Device).where(
            Device.company_id == context.company.id,
            Device.installation_identifier == clean_identifier,
        )
    )
    if device is None:
        device = Device(
            company_id=context.company.id,
            membership_id=context.membership.id,
            installation_identifier=clean_identifier,
            platform=platform,
            status=DeviceStatus.ACTIVE,
        )
        session.add(device)
        try:
            session.flush()
        except IntegrityError:
            # React development mode can replay the registration effect. Treat
            # the company/installation unique key as an idempotency boundary.
            session.rollback()
            device = session.scalar(
                select(Device).where(
                    Device.company_id == context.company.id,
                    Device.installation_identifier == clean_identifier,
                )
            )
            if device is None:
                raise
    elif device.membership_id != context.membership.id:
        raise TenantConsistencyError("device belongs to another driver")
    if device.membership_id != context.membership.id:
        raise TenantConsistencyError("device belongs to another driver")
    if device.status != DeviceStatus.ACTIVE:
        raise DomainError("device is revoked")
    return device


def _evidence_for_event(
    session: Session,
    *,
    context: AuthContext,
    client_event_uuid: UUID,
    object_reference: str | None,
    required: bool,
) -> None:
    if object_reference is None:
        if required:
            raise EvidenceValidationError("supporting evidence is required")
        return
    evidence = session.scalar(
        select(EvidenceObject).where(
            EvidenceObject.company_id == context.company.id,
            EvidenceObject.membership_id == context.membership.id,
            EvidenceObject.client_event_uuid == client_event_uuid,
            EvidenceObject.object_key == object_reference,
        )
    )
    if evidence is None:
        raise EvidenceValidationError("evidence is not owned by this driver event")


def create_driver_event(
    session: Session,
    context: AuthContext,
    settings: Settings,
    *,
    client_event_uuid: UUID,
    event_type: OperationalEventType,
    device_created_at: datetime,
    device: Device,
    reading_type: KmReadingType | None = None,
    reading_value: Decimal | None = None,
    litres: Decimal | None = None,
    category: EmergencyCategory | None = None,
    description: str | None = None,
    object_reference: str | None = None,
) -> DriverEventResult:
    assignment = _assignment_at_event(
        session,
        context=context,
        device_created_at=device_created_at,
        settings=settings,
    )
    if device.company_id != context.company.id or device.membership_id != context.membership.id:
        raise TenantConsistencyError("device is not owned by the authenticated driver")
    existing = session.scalar(
        select(OperationalEvent).where(
            OperationalEvent.company_id == context.company.id,
            OperationalEvent.client_event_uuid == client_event_uuid,
        )
    )
    if existing is not None:
        existing_assignment = session.get(Assignment, existing.assignment_id)
        if (
            existing.event_type != event_type
            or existing_assignment is None
            or existing_assignment.driver_membership_id != context.membership.id
            or existing.device_id != device.id
        ):
            raise TenantConsistencyError("client event UUID is not owned by this driver")
        return DriverEventResult(event=existing, duplicate=True)
    if event_type == OperationalEventType.EMERGENCY:
        # Emergency is a one-tap signal. A second client UUID inside the short
        # retry window is treated as the same signal so rapid repeat taps do
        # not create duplicate alerts. Deliberate later emergencies remain
        # separate events, and the normal UUID idempotency boundary is kept.
        duplicate_cutoff = device_created_at - timedelta(seconds=10)
        recent_emergencies = session.scalars(
            select(OperationalEvent)
            .where(
                OperationalEvent.company_id == context.company.id,
                OperationalEvent.assignment_id == assignment.id,
                OperationalEvent.event_type == OperationalEventType.EMERGENCY,
            )
            .order_by(OperationalEvent.device_created_at.desc(), OperationalEvent.id.desc())
        ).all()
        recent_emergency = next(
            (
                candidate
                for candidate in recent_emergencies
                if duplicate_cutoff <= candidate.device_created_at <= device_created_at
                if (emergency := session.get(EmergencyEvent, candidate.id)) is not None
                and emergency.status in {EmergencyStatus.OPEN, EmergencyStatus.ACKNOWLEDGED}
            ),
            None,
        )
        if recent_emergency is not None:
            return DriverEventResult(event=recent_emergency, duplicate=True)
    active_duty: DutySession | None = None
    _evidence_for_event(
        session,
        context=context,
        client_event_uuid=client_event_uuid,
        object_reference=object_reference,
        required=event_type == OperationalEventType.KM_READING,
    )
    if event_type in {OperationalEventType.TRIP_COMPLETE, OperationalEventType.DIESEL}:
        active_duty = _require_active_duty(
            session,
            context=context,
            assignment=assignment,
            device_created_at=device_created_at,
        )
    elif event_type == OperationalEventType.KM_READING:
        if reading_type is None or reading_value is None:
            raise DomainError("reading_type and reading_value are required")
        if reading_type == KmReadingType.START_READING:
            active_duty = _active_duty_session(session, context=context, lock=True)
            if active_duty is not None:
                raise DutyAlreadyStartedError("an active duty session already exists")
            previous_end_km = _previous_valid_end_km(
                session,
                company_id=context.company.id,
                tipper_id=assignment.tipper_id,
                before=device_created_at,
            )
            if previous_end_km is not None and reading_value < previous_end_km:
                raise DutyOdometerContinuityError(
                    f"START KM {reading_value} is below the previous valid END KM "
                    f"{previous_end_km} for this tipper"
                )
        elif reading_type == KmReadingType.END_READING:
            active_duty = _require_active_duty(
                session,
                context=context,
                assignment=assignment,
                device_created_at=device_created_at,
            )
            if reading_value < active_duty.start_km:
                raise DutyKmValidationError(
                    "END_READING must be greater than or equal to START_READING"
                )
    elif event_type == OperationalEventType.EMERGENCY:
        active_duty = _active_duty_session(session, context=context)
    new_duty: DutySession | None = None
    if event_type == OperationalEventType.TRIP_COMPLETE:
        create_trip_event(
            session,
            company_id=context.company.id,
            assignment_id=assignment.id,
            client_event_uuid=client_event_uuid,
            device_created_at=device_created_at,
            device_id=device.id,
        )
    elif event_type == OperationalEventType.KM_READING:
        assert reading_type is not None and reading_value is not None
        km_reading = create_km_reading(
            session,
            company_id=context.company.id,
            assignment_id=assignment.id,
            client_event_uuid=client_event_uuid,
            device_created_at=device_created_at,
            reading_type=reading_type,
            reading_value=reading_value,
            object_reference=object_reference,
            device_id=device.id,
        )
        if reading_type == KmReadingType.START_READING:
            regular_minutes = assignment.regular_duty_minutes
            new_duty = DutySession(
                company_id=context.company.id,
                assignment_id=assignment.id,
                driver_membership_id=context.membership.id,
                tipper_id=assignment.tipper_id,
                site_id=assignment.site_id,
                operational_date=_operational_date(context, device_created_at),
                start_event_id=km_reading.event_id,
                start_km=reading_value,
                started_at=device_created_at,
                configured_regular_duty_minutes=regular_minutes,
                regular_duty_ends_at=device_created_at + timedelta(minutes=regular_minutes),
                status=DutySessionStatus.ACTIVE,
            )
            session.add(new_duty)
            try:
                with session.begin_nested():
                    session.flush()
            except IntegrityError as exc:
                raise DutyAlreadyStartedError("an active duty session already exists") from exc
            km_reading_event = session.get(OperationalEvent, km_reading.event_id)
            if km_reading_event is not None:
                km_reading_event.duty_session_id = new_duty.id
            session.flush()
        elif active_duty is not None and reading_type == KmReadingType.END_READING:
            active_duty.end_event_id = km_reading.event_id
            active_duty.end_km = reading_value
            active_duty.ended_at = device_created_at
            active_duty.status = DutySessionStatus.CLOSED
            active_duty.final_overtime_minutes = max(
                0,
                int((device_created_at - active_duty.regular_duty_ends_at).total_seconds() // 60),
            )
            session.flush()
    elif event_type == OperationalEventType.DIESEL:
        if litres is None:
            raise DomainError("litres are required")
        create_diesel_event(
            session,
            company_id=context.company.id,
            assignment_id=assignment.id,
            client_event_uuid=client_event_uuid,
            device_created_at=device_created_at,
            litres=litres,
            object_reference=object_reference,
            device_id=device.id,
        )
    elif event_type == OperationalEventType.EMERGENCY:
        create_emergency_event(
            session,
            company_id=context.company.id,
            assignment_id=assignment.id,
            client_event_uuid=client_event_uuid,
            device_created_at=device_created_at,
            category=category,
            description=description.strip() if description else None,
            device_id=device.id,
        )
    else:
        raise DomainError("event type is unsupported")
    event = session.scalar(
        select(OperationalEvent).where(
            OperationalEvent.company_id == context.company.id,
            OperationalEvent.client_event_uuid == client_event_uuid,
        )
    )
    if event is None:
        raise DomainError("event was not persisted")
    if active_duty is not None and event.duty_session_id is None:
        event.duty_session_id = active_duty.id
        session.flush()
    return DriverEventResult(event=event, duplicate=False)


def upload_evidence(
    session: Session,
    context: AuthContext,
    storage: ObjectStorage,
    settings: Settings,
    *,
    client_event_uuid: UUID,
    content_type: str,
    content: bytes,
) -> EvidenceObject:
    _require_driver(context)
    normalized_type = content_type.lower().split(";", maxsplit=1)[0].strip()
    if normalized_type not in settings.evidence_mime_types:
        raise EvidenceValidationError("unsupported evidence type")
    if not content or len(content) > settings.evidence_max_bytes:
        raise EvidenceValidationError("evidence size is invalid")
    if not _matches_image_signature(normalized_type, content):
        raise EvidenceValidationError("evidence content does not match its image type")
    existing = session.scalar(
        select(EvidenceObject).where(
            EvidenceObject.company_id == context.company.id,
            EvidenceObject.membership_id == context.membership.id,
            EvidenceObject.client_event_uuid == client_event_uuid,
        )
    )
    if existing is not None:
        return existing
    extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[normalized_type]
    object_key = str(
        PurePosixPath(
            "companies",
            str(context.company.id),
            "memberships",
            str(context.membership.id),
            "events",
            str(client_event_uuid),
            f"{uuid4()}.{extension}",
        )
    )
    stored_key: str | None = None
    try:
        stored_key = storage.put_private(
            object_key=object_key,
            content=content,
            content_type=normalized_type,
        )
        evidence = EvidenceObject(
            company_id=context.company.id,
            membership_id=context.membership.id,
            client_event_uuid=client_event_uuid,
            object_key=stored_key,
            content_type=normalized_type,
            size_bytes=len(content),
        )
        session.add(evidence)
        session.flush()
        return evidence
    except (IntegrityError, ObjectStorageUnavailableError):
        if stored_key is not None:
            try:
                storage.delete_private(object_key=stored_key)
            except ObjectStorageUnavailableError:
                pass
        raise


def _matches_image_signature(content_type: str, content: bytes) -> bool:
    """Reject MIME-spoofed uploads before they reach private object storage."""
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return False
