from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
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
    FleetAsset,
    HourMeterReading,
    KmReading,
    OperationalEvent,
    Site,
    SupervisorSiteAccess,
    User,
)
from fleet_api.db.models.common import utc_now
from fleet_api.domain.assets import capabilities_for_asset
from fleet_api.domain.audit import write_audit_log
from fleet_api.domain.enums import (
    DevicePlatform,
    DeviceStatus,
    DutySessionStatus,
    EmergencyCategory,
    EmergencyStatus,
    FleetAssetStatus,
    HourMeterReadingType,
    KmReadingType,
    MembershipRole,
    MembershipStatus,
    OperationalEventType,
    SiteStatus,
    UserStatus,
    VerificationStatus,
)
from fleet_api.domain.errors import (
    AssignmentNotEffectiveError,
    ConflictError,
    DeviceHandoverBlockedError,
    DeviceHandoverRequiredError,
    DomainError,
    DutyAlreadyStartedError,
    DutyAssignmentMismatchError,
    DutyEventOutsideSessionError,
    DutyHourMeterContinuityError,
    DutyHourMeterOutOfRangeError,
    DutyHourMeterValidationError,
    DutyKmValidationError,
    DutyNotStartedError,
    DutyOdometerContinuityError,
    DutyOdometerOutOfRangeError,
    EvidenceValidationError,
    ObjectStorageUnavailableError,
    RoleViolationError,
    TenantConsistencyError,
)
from fleet_api.domain.events import (
    create_diesel_event,
    create_emergency_event,
    create_hour_meter_reading,
    create_km_reading,
    create_trip_event,
)
from fleet_api.storage.objects import ObjectStorage


@dataclass(frozen=True)
class DriverAssignment:
    assignment: Assignment
    asset: FleetAsset
    site: Site
    supervisor_names: list[str]


@dataclass(frozen=True)
class DriverEventResult:
    event: OperationalEvent
    duplicate: bool


@dataclass(frozen=True)
class DriverDutyState:
    session: DutySession | None


@dataclass(frozen=True)
class DriverMeterCaptureResult:
    capture_group_uuid: UUID
    events: tuple[OperationalEvent, ...]
    duty_session: DutySession
    duplicate: bool


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
        select(Assignment, FleetAsset, Site)
        .join(FleetAsset, FleetAsset.id == Assignment.asset_id)
        .join(Site, Site.id == Assignment.site_id)
        .where(
            Assignment.company_id == context.company.id,
            Assignment.driver_membership_id == context.membership.id,
            Assignment.starts_at <= at,
            (Assignment.ends_at.is_(None) | (Assignment.ends_at > at)),
            FleetAsset.status == FleetAssetStatus.ACTIVE,
            Site.status == SiteStatus.ACTIVE,
        )
        .order_by(Assignment.starts_at.desc(), Assignment.id)
    ).first()
    if row is None:
        return None
    assignment, asset, site = row._tuple()
    supervisor_names = [
        membership.display_name or user.display_name
        for membership, user in session.execute(
            select(CompanyMembership, User)
            .join(
                SupervisorSiteAccess,
                (SupervisorSiteAccess.company_id == CompanyMembership.company_id)
                & (SupervisorSiteAccess.supervisor_membership_id == CompanyMembership.id),
            )
            .join(User, User.id == CompanyMembership.user_id)
            .where(
                SupervisorSiteAccess.company_id == context.company.id,
                SupervisorSiteAccess.site_id == site.id,
                CompanyMembership.role == MembershipRole.SUPERVISOR,
                CompanyMembership.status == MembershipStatus.ACTIVE,
                User.status == UserStatus.ACTIVE,
            )
            .order_by(CompanyMembership.display_name, User.display_name)
        )
    ]
    return DriverAssignment(assignment, asset, site, supervisor_names)


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
    asset_id: UUID,
    before: datetime,
) -> Decimal | None:
    """Return the latest non-rejected END KM for this asset before START.

    Pending verification is intentionally continuity-valid: the driver must
    not be able to roll the physical odometer backward while review is still
    outstanding. Rejected readings are excluded; approved and amended
    readings remain valid history.
    """

    valid_statuses = {
        VerificationStatus.PENDING_VERIFICATION,
        VerificationStatus.APPROVED,
        VerificationStatus.AMENDED,
    }
    return session.scalar(
        select(KmReading.reading_value)
        .join(OperationalEvent, OperationalEvent.id == KmReading.event_id)
        .join(DutySession, DutySession.id == OperationalEvent.duty_session_id)
        .where(
            DutySession.company_id == company_id,
            DutySession.asset_id == asset_id,
            DutySession.status == DutySessionStatus.CLOSED,
            DutySession.ended_at < before,
            KmReading.reading_type == KmReadingType.END_READING,
            OperationalEvent.verification_status.in_(valid_statuses),
        )
        .order_by(DutySession.ended_at.desc(), DutySession.id.desc())
        .limit(1)
    )


def _previous_valid_end_hmr(
    session: Session,
    *,
    company_id: UUID,
    asset_id: UUID,
    before: datetime,
) -> Decimal | None:
    valid_statuses = {
        VerificationStatus.PENDING_VERIFICATION,
        VerificationStatus.APPROVED,
        VerificationStatus.AMENDED,
    }
    return session.scalar(
        select(HourMeterReading.reading_value)
        .join(OperationalEvent, OperationalEvent.id == HourMeterReading.event_id)
        .join(DutySession, DutySession.id == OperationalEvent.duty_session_id)
        .where(
            DutySession.company_id == company_id,
            DutySession.asset_id == asset_id,
            DutySession.status == DutySessionStatus.CLOSED,
            DutySession.ended_at < before,
            HourMeterReading.reading_type == HourMeterReadingType.END_READING,
            OperationalEvent.verification_status.in_(valid_statuses),
        )
        .order_by(DutySession.ended_at.desc(), DutySession.id.desc())
        .limit(1)
    )


def _format_odometer_km(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _validate_odometer_reading(settings: Settings, reading_value: Decimal | str) -> Decimal:
    """Validate a KM value before any event or duty-session mutation."""
    try:
        value = reading_value if isinstance(reading_value, Decimal) else Decimal(reading_value)
    except (InvalidOperation, ValueError):
        raise DutyOdometerOutOfRangeError(
            "KM reading looks invalid. Please check the odometer and enter the correct value."
        ) from None
    if not value.is_finite():
        raise DutyOdometerOutOfRangeError(
            "KM reading looks invalid. Please check the odometer and enter the correct value."
        )
    if value < 0 or value > settings.max_odometer_km:
        raise DutyOdometerOutOfRangeError(
            "KM reading looks invalid. Please check the odometer and enter the correct value."
        )
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise DutyOdometerOutOfRangeError(
            "KM reading looks invalid. Please check the odometer and enter the correct value."
        )
    return value


def _validate_hour_meter_reading(settings: Settings, reading_value: Decimal | str) -> Decimal:
    try:
        value = reading_value if isinstance(reading_value, Decimal) else Decimal(reading_value)
    except (InvalidOperation, ValueError):
        raise DutyHourMeterOutOfRangeError(
            "HMR looks invalid. Please check the hour meter and enter the correct value."
        ) from None
    if not value.is_finite() or value < 0 or value > settings.max_hour_meter_hours:
        raise DutyHourMeterOutOfRangeError(
            "HMR looks invalid. Please check the hour meter and enter the correct value."
        )
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise DutyHourMeterOutOfRangeError(
            "HMR looks invalid. Please check the hour meter and enter the correct value."
        )
    return value


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
    lock: bool = False,
) -> Assignment:
    _require_driver(context)
    if device_created_at.tzinfo is None:
        raise DomainError("device_created_at must include a timezone")
    now = utc_now()
    if device_created_at > now + timedelta(seconds=settings.event_future_skew_seconds):
        raise DomainError("device_created_at is too far in the future")
    statement = (
        select(Assignment)
        .where(
            Assignment.company_id == context.company.id,
            Assignment.driver_membership_id == context.membership.id,
            Assignment.starts_at <= device_created_at,
            (Assignment.ends_at.is_(None) | (Assignment.ends_at > device_created_at)),
        )
        .order_by(Assignment.starts_at.desc(), Assignment.id)
    )
    if lock:
        statement = statement.with_for_update()
    assignment = session.scalar(statement)
    if assignment is None:
        raise AssignmentNotEffectiveError("event timestamp has no driver assignment")
    return assignment


def register_device(
    session: Session,
    context: AuthContext,
    *,
    installation_identifier: str,
    platform: DevicePlatform,
    allow_handover: bool = False,
    local_state_clear: bool = False,
) -> tuple[Device, bool]:
    _require_driver(context)
    clean_identifier = installation_identifier.strip()
    if not clean_identifier or len(clean_identifier) > 200:
        raise DomainError("installation_identifier is invalid")
    device = session.scalar(
        select(Device)
        .where(
            Device.company_id == context.company.id,
            Device.installation_identifier == clean_identifier,
        )
        .with_for_update()
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
    if device.status != DeviceStatus.ACTIVE:
        raise DomainError("device is revoked")
    handed_over = False
    if device.membership_id != context.membership.id:
        if device.membership_id is None:
            raise TenantConsistencyError("device has no current driver binding")
        if not allow_handover:
            raise DeviceHandoverRequiredError(current_membership_id=device.membership_id)
        if not local_state_clear:
            raise DeviceHandoverBlockedError(
                "This phone still has an active duty or unsynced records for another "
                "driver. Finish and sync that work before changing driver."
            )
        active_old_duty = session.scalar(
            select(DutySession.id).where(
                DutySession.company_id == context.company.id,
                DutySession.driver_membership_id == device.membership_id,
                DutySession.status == DutySessionStatus.ACTIVE,
            )
        )
        if active_old_duty is not None:
            raise DeviceHandoverBlockedError(
                "This phone still has an active duty or unsynced records for another "
                "driver. Finish and sync that work before changing driver."
            )
        old_membership_id = device.membership_id
        device.membership_id = context.membership.id
        device.platform = platform
        write_audit_log(
            session,
            company_id=context.company.id,
            actor_membership_id=context.membership.id,
            action="DEVICE_DRIVER_HANDOVER",
            entity_type="Device",
            entity_id=device.id,
            old_values={"membership_id": str(old_membership_id)},
            new_values={"membership_id": str(context.membership.id)},
        )
        handed_over = True
    return device, handed_over


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


def validate_driver_event_uuid(
    session: Session,
    context: AuthContext,
    *,
    client_event_uuid: UUID,
) -> None:
    """Reject another driver's UUID before device registration side effects."""
    _require_driver(context)
    owner_membership_id = session.scalar(
        select(Assignment.driver_membership_id)
        .join(OperationalEvent, OperationalEvent.assignment_id == Assignment.id)
        .where(
            OperationalEvent.company_id == context.company.id,
            OperationalEvent.client_event_uuid == client_event_uuid,
        )
    )
    if owner_membership_id is not None and owner_membership_id != context.membership.id:
        raise TenantConsistencyError("client event UUID is not owned by this driver")


def create_driver_event(
    session: Session,
    context: AuthContext,
    settings: Settings,
    *,
    client_event_uuid: UUID,
    event_type: OperationalEventType,
    device_created_at: datetime,
    device: Device,
    reading_type: KmReadingType | HourMeterReadingType | None = None,
    reading_value: Decimal | str | None = None,
    litres: Decimal | None = None,
    category: EmergencyCategory | None = None,
    description: str | None = None,
    object_reference: str | None = None,
) -> DriverEventResult:
    duty_start = (
        event_type in {OperationalEventType.KM_READING, OperationalEventType.HMR_READING}
        and reading_type is not None
        and reading_type.value == KmReadingType.START_READING.value
    )
    assignment = _assignment_at_event(
        session,
        context=context,
        device_created_at=device_created_at,
        settings=settings,
        lock=duty_start,
    )
    asset = session.get(FleetAsset, assignment.asset_id)
    if asset is None or asset.company_id != context.company.id:
        raise TenantConsistencyError("assignment asset does not belong to this company")
    capabilities = capabilities_for_asset(asset)
    supported = {
        OperationalEventType.TRIP_COMPLETE: capabilities.supports_trip_complete,
        OperationalEventType.KM_READING: capabilities.supports_odometer,
        OperationalEventType.HMR_READING: capabilities.supports_hour_meter,
        OperationalEventType.DIESEL: capabilities.supports_diesel,
        OperationalEventType.EMERGENCY: capabilities.supports_emergency,
    }
    if not supported[event_type]:
        raise DomainError(f"{event_type.value} is not supported for {asset.asset_type.value}")
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
    km_reading_value: Decimal | None = None
    hmr_reading_value: Decimal | None = None
    if event_type == OperationalEventType.KM_READING:
        if reading_type is None or reading_value is None:
            raise DomainError("reading_type and reading_value are required")
        km_reading_value = _validate_odometer_reading(settings, reading_value)
    elif event_type == OperationalEventType.HMR_READING:
        if reading_type is None or reading_value is None:
            raise DomainError("reading_type and reading_value are required")
        hmr_reading_value = _validate_hour_meter_reading(settings, reading_value)
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
        required=event_type in {OperationalEventType.KM_READING, OperationalEventType.HMR_READING},
    )
    if event_type in {OperationalEventType.TRIP_COMPLETE, OperationalEventType.DIESEL}:
        active_duty = _require_active_duty(
            session,
            context=context,
            assignment=assignment,
            device_created_at=device_created_at,
        )
    elif event_type == OperationalEventType.KM_READING:
        if reading_type == KmReadingType.START_READING:
            active_duty = _active_duty_session(session, context=context, lock=True)
            if active_duty is not None:
                raise DutyAlreadyStartedError("an active duty session already exists")
            previous_end_km = _previous_valid_end_km(
                session,
                company_id=context.company.id,
                asset_id=assignment.asset_id,
                before=device_created_at,
            )
            assert km_reading_value is not None
            if previous_end_km is not None and km_reading_value < previous_end_km:
                raise DutyOdometerContinuityError(
                    "START KM cannot be lower than the previous END KM "
                    f"({_format_odometer_km(previous_end_km)}). Please check the odometer.",
                    previous_end_km=previous_end_km,
                )
        elif reading_type == KmReadingType.END_READING:
            active_duty = _require_active_duty(
                session,
                context=context,
                assignment=assignment,
                device_created_at=device_created_at,
            )
            assert km_reading_value is not None
            if active_duty.start_km is None or km_reading_value < active_duty.start_km:
                raise DutyKmValidationError(
                    "END_READING must be greater than or equal to START_READING"
                )
    elif event_type == OperationalEventType.HMR_READING:
        assert reading_type is not None
        if reading_type.value == HourMeterReadingType.START_READING.value:
            active_duty = _active_duty_session(session, context=context, lock=True)
            if active_duty is not None:
                raise DutyAlreadyStartedError("an active duty session already exists")
            previous_end_hmr = _previous_valid_end_hmr(
                session,
                company_id=context.company.id,
                asset_id=assignment.asset_id,
                before=device_created_at,
            )
            assert hmr_reading_value is not None
            if previous_end_hmr is not None and hmr_reading_value < previous_end_hmr:
                raise DutyHourMeterContinuityError(
                    "START HMR cannot be lower than the previous END HMR "
                    f"({_format_odometer_km(previous_end_hmr)}). Please check the hour meter.",
                    previous_end_hmr=previous_end_hmr,
                )
        else:
            active_duty = _require_active_duty(
                session,
                context=context,
                assignment=assignment,
                device_created_at=device_created_at,
            )
            assert hmr_reading_value is not None
            if active_duty.start_hmr is None or hmr_reading_value < active_duty.start_hmr:
                raise DutyHourMeterValidationError(
                    "END HMR must be greater than or equal to START HMR"
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
        assert reading_type is not None and km_reading_value is not None
        km_reading = create_km_reading(
            session,
            company_id=context.company.id,
            assignment_id=assignment.id,
            client_event_uuid=client_event_uuid,
            device_created_at=device_created_at,
            reading_type=KmReadingType(reading_type.value),
            reading_value=km_reading_value,
            object_reference=object_reference,
            device_id=device.id,
        )
        if reading_type == KmReadingType.START_READING:
            regular_minutes = assignment.regular_duty_minutes
            new_duty = DutySession(
                company_id=context.company.id,
                assignment_id=assignment.id,
                driver_membership_id=context.membership.id,
                asset_id=assignment.asset_id,
                site_id=assignment.site_id,
                operational_date=_operational_date(context, device_created_at),
                start_event_id=km_reading.event_id,
                start_km=km_reading_value,
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
            active_duty.end_km = km_reading_value
            active_duty.ended_at = device_created_at
            active_duty.status = DutySessionStatus.CLOSED
            active_duty.final_overtime_minutes = max(
                0,
                int((device_created_at - active_duty.regular_duty_ends_at).total_seconds() // 60),
            )
            session.flush()
    elif event_type == OperationalEventType.HMR_READING:
        assert reading_type is not None and hmr_reading_value is not None
        hmr_type = HourMeterReadingType(reading_type.value)
        hmr_reading = create_hour_meter_reading(
            session,
            company_id=context.company.id,
            assignment_id=assignment.id,
            client_event_uuid=client_event_uuid,
            device_created_at=device_created_at,
            reading_type=hmr_type,
            reading_value=hmr_reading_value,
            object_reference=object_reference,
            device_id=device.id,
        )
        if hmr_type == HourMeterReadingType.START_READING:
            regular_minutes = assignment.regular_duty_minutes
            new_duty = DutySession(
                company_id=context.company.id,
                assignment_id=assignment.id,
                driver_membership_id=context.membership.id,
                asset_id=assignment.asset_id,
                site_id=assignment.site_id,
                operational_date=_operational_date(context, device_created_at),
                start_event_id=hmr_reading.event_id,
                start_km=None,
                start_hmr=hmr_reading_value,
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
            hmr_event = session.get(OperationalEvent, hmr_reading.event_id)
            if hmr_event is not None:
                hmr_event.duty_session_id = new_duty.id
            session.flush()
        elif active_duty is not None:
            active_duty.end_event_id = hmr_reading.event_id
            active_duty.end_hmr = hmr_reading_value
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


def create_multi_meter_capture(
    session: Session,
    context: AuthContext,
    settings: Settings,
    *,
    capture_group_uuid: UUID,
    reading_type: KmReadingType,
    device_created_at: datetime,
    device: Device,
    object_reference: str | None,
    km_client_event_uuid: UUID | None,
    odometer_km: Decimal | str | None,
    km_object_reference: str | None,
    hmr_client_event_uuid: UUID | None,
    hour_meter: Decimal | str | None,
    hmr_object_reference: str | None,
) -> DriverMeterCaptureResult:
    """Atomically persist every meter from one Driver START/END action."""

    assignment = _assignment_at_event(
        session,
        context=context,
        device_created_at=device_created_at,
        settings=settings,
        lock=True,
    )
    asset = session.get(FleetAsset, assignment.asset_id)
    if asset is None or asset.company_id != context.company.id:
        raise TenantConsistencyError("assignment asset does not belong to this company")
    capabilities = capabilities_for_asset(asset)
    submitted_km = odometer_km is not None or km_client_event_uuid is not None
    submitted_hmr = hour_meter is not None or hmr_client_event_uuid is not None
    if submitted_km != capabilities.supports_odometer:
        raise DomainError("odometer reading must match this asset's meter capability")
    if submitted_hmr != capabilities.supports_hour_meter:
        raise DomainError("hour-meter reading must match this asset's meter capability")
    if not submitted_km and not submitted_hmr:
        raise DomainError("at least one meter reading is required")
    if submitted_km and (odometer_km is None or km_client_event_uuid is None):
        raise DomainError("odometer value and client event UUID are both required")
    if submitted_hmr and (hour_meter is None or hmr_client_event_uuid is None):
        raise DomainError("hour-meter value and client event UUID are both required")
    if device.company_id != context.company.id or device.membership_id != context.membership.id:
        raise TenantConsistencyError("device is not owned by the authenticated driver")
    if object_reference is not None and (
        km_object_reference is not None or hmr_object_reference is not None
    ):
        raise DomainError(
            "meter capture must use one shared evidence reference or legacy per-meter evidence"
        )
    effective_km_reference = object_reference or km_object_reference
    effective_hmr_reference = object_reference or hmr_object_reference

    km_value = (
        _validate_odometer_reading(settings, odometer_km) if odometer_km is not None else None
    )
    hmr_value = (
        _validate_hour_meter_reading(settings, hour_meter) if hour_meter is not None else None
    )

    existing = list(
        session.scalars(
            select(OperationalEvent)
            .where(
                OperationalEvent.company_id == context.company.id,
                OperationalEvent.capture_group_uuid == capture_group_uuid,
            )
            .order_by(OperationalEvent.event_type)
        ).all()
    )
    expected_uuids = {
        value for value in (km_client_event_uuid, hmr_client_event_uuid) if value is not None
    }
    if existing:
        if {event.client_event_uuid for event in existing} != expected_uuids:
            raise TenantConsistencyError("capture group UUID is already used by another submission")
        expected_types = {
            event_type
            for event_type, submitted in (
                (OperationalEventType.KM_READING, submitted_km),
                (OperationalEventType.HMR_READING, submitted_hmr),
            )
            if submitted
        }
        if {event.event_type for event in existing} != expected_types:
            raise TenantConsistencyError("capture group meter types do not match this submission")
        if any(
            event.device_id != device.id or event.assignment_id != assignment.id
            for event in existing
        ):
            raise TenantConsistencyError("capture group is not owned by this device")
        for event in existing:
            if event.event_type == OperationalEventType.KM_READING:
                persisted_km = session.get(KmReading, event.id)
                if (
                    persisted_km is None
                    or persisted_km.reading_type != reading_type
                    or persisted_km.reading_value != km_value
                ):
                    raise ConflictError(
                        "capture group KM payload does not match the accepted event"
                    )
            elif event.event_type == OperationalEventType.HMR_READING:
                persisted_hmr = session.get(HourMeterReading, event.id)
                if (
                    persisted_hmr is None
                    or persisted_hmr.reading_type != HourMeterReadingType(reading_type.value)
                    or persisted_hmr.reading_value != hmr_value
                ):
                    raise ConflictError(
                        "capture group HMR payload does not match the accepted event"
                    )
        duty_ids = {event.duty_session_id for event in existing}
        if len(duty_ids) != 1 or None in duty_ids:
            raise ConflictError("meter capture exists without one shared duty session")
        duty = session.get(DutySession, existing[0].duty_session_id)
        if duty is None:
            raise ConflictError("meter capture exists without its duty session")
        return DriverMeterCaptureResult(capture_group_uuid, tuple(existing), duty, True)

    reused = session.scalar(
        select(OperationalEvent.id).where(
            OperationalEvent.company_id == context.company.id,
            OperationalEvent.client_event_uuid.in_(expected_uuids),
        )
    )
    if reused is not None:
        raise ConflictError("client event UUID is already used by another submission")
    if object_reference is not None:
        _evidence_for_event(
            session,
            context=context,
            client_event_uuid=capture_group_uuid,
            object_reference=object_reference,
            required=True,
        )
    elif km_client_event_uuid is not None:
        _evidence_for_event(
            session,
            context=context,
            client_event_uuid=km_client_event_uuid,
            object_reference=km_object_reference,
            required=True,
        )
    if object_reference is None and hmr_client_event_uuid is not None:
        _evidence_for_event(
            session,
            context=context,
            client_event_uuid=hmr_client_event_uuid,
            object_reference=hmr_object_reference,
            required=True,
        )

    active = _active_duty_session(session, context=context, lock=True)
    is_start = reading_type == KmReadingType.START_READING
    if is_start:
        if active is not None:
            raise DutyAlreadyStartedError("an active duty session already exists")
        if km_value is not None:
            previous_km = _previous_valid_end_km(
                session,
                company_id=context.company.id,
                asset_id=assignment.asset_id,
                before=device_created_at,
            )
            if previous_km is not None and km_value < previous_km:
                raise DutyOdometerContinuityError(
                    "START KM cannot be lower than the previous END KM "
                    f"({_format_odometer_km(previous_km)}). Please check the odometer.",
                    previous_end_km=previous_km,
                )
        if hmr_value is not None:
            previous_hmr = _previous_valid_end_hmr(
                session,
                company_id=context.company.id,
                asset_id=assignment.asset_id,
                before=device_created_at,
            )
            if previous_hmr is not None and hmr_value < previous_hmr:
                raise DutyHourMeterContinuityError(
                    "START HMR cannot be lower than the previous END HMR "
                    f"({_format_odometer_km(previous_hmr)}). Please check the hour meter.",
                    previous_end_hmr=previous_hmr,
                )
    else:
        active = _require_active_duty(
            session,
            context=context,
            assignment=assignment,
            device_created_at=device_created_at,
        )
        if km_value is not None and (active.start_km is None or km_value < active.start_km):
            raise DutyKmValidationError(
                "END_READING must be greater than or equal to START_READING"
            )
        if hmr_value is not None and (active.start_hmr is None or hmr_value < active.start_hmr):
            raise DutyHourMeterValidationError("END HMR must be greater than or equal to START HMR")

    event_ids: list[UUID] = []
    if km_client_event_uuid is not None and km_value is not None:
        km = create_km_reading(
            session,
            company_id=context.company.id,
            assignment_id=assignment.id,
            client_event_uuid=km_client_event_uuid,
            device_created_at=device_created_at,
            reading_type=reading_type,
            reading_value=km_value,
            object_reference=effective_km_reference,
            device_id=device.id,
            capture_group_uuid=capture_group_uuid,
        )
        event_ids.append(km.event_id)
    if hmr_client_event_uuid is not None and hmr_value is not None:
        hmr = create_hour_meter_reading(
            session,
            company_id=context.company.id,
            assignment_id=assignment.id,
            client_event_uuid=hmr_client_event_uuid,
            device_created_at=device_created_at,
            reading_type=HourMeterReadingType(reading_type.value),
            reading_value=hmr_value,
            object_reference=effective_hmr_reference,
            device_id=device.id,
            capture_group_uuid=capture_group_uuid,
        )
        event_ids.append(hmr.event_id)
    if not event_ids:
        raise DomainError("meter capture did not create an event")

    if is_start:
        regular_minutes = assignment.regular_duty_minutes
        duty = DutySession(
            company_id=context.company.id,
            assignment_id=assignment.id,
            driver_membership_id=context.membership.id,
            asset_id=assignment.asset_id,
            site_id=assignment.site_id,
            operational_date=_operational_date(context, device_created_at),
            start_event_id=event_ids[0],
            start_km=km_value,
            start_hmr=hmr_value,
            started_at=device_created_at,
            configured_regular_duty_minutes=regular_minutes,
            regular_duty_ends_at=device_created_at + timedelta(minutes=regular_minutes),
            status=DutySessionStatus.ACTIVE,
        )
        session.add(duty)
        try:
            with session.begin_nested():
                session.flush()
        except IntegrityError as exc:
            raise DutyAlreadyStartedError("an active duty session already exists") from exc
    else:
        assert active is not None
        duty = active
        duty.end_event_id = event_ids[0]
        duty.end_km = km_value
        duty.end_hmr = hmr_value
        duty.ended_at = device_created_at
        duty.status = DutySessionStatus.CLOSED
        duty.final_overtime_minutes = max(
            0, int((device_created_at - duty.regular_duty_ends_at).total_seconds() // 60)
        )
    for event_id in event_ids:
        loaded_event = session.get(OperationalEvent, event_id)
        if loaded_event is not None:
            loaded_event.duty_session_id = duty.id
    session.flush()
    events = tuple(
        loaded_event
        for event_id in event_ids
        if (loaded_event := session.get(OperationalEvent, event_id)) is not None
    )
    return DriverMeterCaptureResult(capture_group_uuid, events, duty, False)


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
