from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID
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
    OperationalEvent,
    Site,
    SupervisorSiteAccess,
    User,
)
from fleet_api.db.models.common import utc_now
from fleet_api.domain.assets import capabilities_for, capabilities_for_asset
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
from fleet_api.domain.private_files import store_private_evidence
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
class MultiMeterCaptureResult:
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
        select(DutySession.end_km)
        .join(OperationalEvent, OperationalEvent.id == DutySession.end_event_id)
        .where(
            DutySession.company_id == company_id,
            DutySession.asset_id == asset_id,
            DutySession.status == DutySessionStatus.CLOSED,
            DutySession.ended_at < before,
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
        select(DutySession.end_hmr)
        .join(OperationalEvent, OperationalEvent.id == DutySession.end_event_id)
        .where(
            DutySession.company_id == company_id,
            DutySession.asset_id == asset_id,
            DutySession.status == DutySessionStatus.CLOSED,
            DutySession.ended_at < before,
            DutySession.end_hmr.is_not(None),
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
    assignment = _assignment_at_event(
        session,
        context=context,
        device_created_at=device_created_at,
        settings=settings,
    )
    asset = session.get(FleetAsset, assignment.asset_id)
    if asset is None or asset.company_id != context.company.id:
        raise TenantConsistencyError("assignment asset does not belong to this company")
    capabilities = capabilities_for(asset.asset_type)
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
    km_client_event_uuid: UUID | None,
    odometer_km: Decimal | str | None,
    km_object_reference: str | None,
    hmr_client_event_uuid: UUID | None,
    hour_meter_hours: Decimal | str | None,
    hmr_object_reference: str | None,
) -> MultiMeterCaptureResult:
    """Persist one logical START/END capture as independently reviewable meter events."""

    assignment = _assignment_at_event(
        session,
        context=context,
        device_created_at=device_created_at,
        settings=settings,
    )
    asset = session.get(FleetAsset, assignment.asset_id)
    if asset is None or asset.company_id != context.company.id:
        raise TenantConsistencyError("assignment asset does not belong to this company")
    capabilities = capabilities_for_asset(asset)
    if capabilities.supports_odometer != (odometer_km is not None):
        raise DomainError("odometer value must match the asset's enabled meters")
    if capabilities.supports_hour_meter != (hour_meter_hours is not None):
        raise DomainError("hour-meter value must match the asset's enabled meters")
    if odometer_km is None and hour_meter_hours is None:
        raise DomainError("at least one meter reading is required")
    if odometer_km is not None and km_client_event_uuid is None:
        raise DomainError("km_client_event_uuid is required")
    if hour_meter_hours is not None and hmr_client_event_uuid is None:
        raise DomainError("hmr_client_event_uuid is required")
    existing = list(
        session.scalars(
            select(OperationalEvent).where(
                OperationalEvent.company_id == context.company.id,
                OperationalEvent.capture_group_uuid == capture_group_uuid,
            )
        )
    )
    if existing:
        expected_order = [
            item for item in (km_client_event_uuid, hmr_client_event_uuid) if item is not None
        ]
        by_client_uuid = {item.client_event_uuid: item for item in existing}
        if set(by_client_uuid) != set(expected_order):
            raise TenantConsistencyError("capture group UUID is already used by another capture")
        ordered = tuple(by_client_uuid[item] for item in expected_order)
        duty = session.get(DutySession, ordered[0].duty_session_id)
        if duty is None or duty.driver_membership_id != context.membership.id:
            raise TenantConsistencyError("capture group UUID is not owned by this driver")
        return MultiMeterCaptureResult(ordered, duty, True)
    km_value = (
        _validate_odometer_reading(settings, odometer_km) if odometer_km is not None else None
    )
    hmr_value = (
        _validate_hour_meter_reading(settings, hour_meter_hours)
        if hour_meter_hours is not None
        else None
    )
    is_start = reading_type == KmReadingType.START_READING
    active_duty = _active_duty_session(session, context=context, lock=True)
    if is_start and active_duty is not None:
        raise DutyAlreadyStartedError("an active duty session already exists")
    if not is_start:
        active_duty = _require_active_duty(
            session,
            context=context,
            assignment=assignment,
            device_created_at=device_created_at,
        )
        if km_value is not None and (
            active_duty.start_km is None or km_value < active_duty.start_km
        ):
            raise DutyKmValidationError(
                "END_READING must be greater than or equal to START_READING"
            )
        if hmr_value is not None and (
            active_duty.start_hmr is None or hmr_value < active_duty.start_hmr
        ):
            raise DutyHourMeterValidationError("END HMR must be greater than or equal to START HMR")
    if is_start and km_value is not None:
        previous_km = _previous_valid_end_km(
            session,
            company_id=context.company.id,
            asset_id=assignment.asset_id,
            before=device_created_at,
        )
        if previous_km is not None and km_value < previous_km:
            raise DutyOdometerContinuityError(
                "START KM cannot be lower than the previous END KM",
                previous_end_km=previous_km,
            )
    if is_start and hmr_value is not None:
        previous_hmr = _previous_valid_end_hmr(
            session,
            company_id=context.company.id,
            asset_id=assignment.asset_id,
            before=device_created_at,
        )
        if previous_hmr is not None and hmr_value < previous_hmr:
            raise DutyHourMeterContinuityError(
                "START HMR cannot be lower than the previous END HMR",
                previous_end_hmr=previous_hmr,
            )
    events: list[OperationalEvent] = []
    if km_value is not None and km_client_event_uuid is not None:
        _evidence_for_event(
            session,
            context=context,
            client_event_uuid=km_client_event_uuid,
            object_reference=km_object_reference,
            required=True,
        )
        reading = create_km_reading(
            session,
            company_id=context.company.id,
            assignment_id=assignment.id,
            client_event_uuid=km_client_event_uuid,
            device_created_at=device_created_at,
            reading_type=reading_type,
            reading_value=km_value,
            object_reference=km_object_reference,
            device_id=device.id,
        )
        event = session.get(OperationalEvent, reading.event_id)
        assert event is not None
        events.append(event)
    if hmr_value is not None and hmr_client_event_uuid is not None:
        _evidence_for_event(
            session,
            context=context,
            client_event_uuid=hmr_client_event_uuid,
            object_reference=hmr_object_reference,
            required=True,
        )
        hmr_reading = create_hour_meter_reading(
            session,
            company_id=context.company.id,
            assignment_id=assignment.id,
            client_event_uuid=hmr_client_event_uuid,
            device_created_at=device_created_at,
            reading_type=HourMeterReadingType(reading_type.value),
            reading_value=hmr_value,
            object_reference=hmr_object_reference,
            device_id=device.id,
        )
        event = session.get(OperationalEvent, hmr_reading.event_id)
        assert event is not None
        events.append(event)
    for event in events:
        event.capture_group_uuid = capture_group_uuid
    if is_start:
        first_event = events[0]
        active_duty = DutySession(
            company_id=context.company.id,
            assignment_id=assignment.id,
            driver_membership_id=context.membership.id,
            asset_id=assignment.asset_id,
            site_id=assignment.site_id,
            operational_date=_operational_date(context, device_created_at),
            start_event_id=first_event.id,
            start_km=km_value,
            start_hmr=hmr_value,
            started_at=device_created_at,
            configured_regular_duty_minutes=assignment.regular_duty_minutes,
            regular_duty_ends_at=device_created_at
            + timedelta(minutes=assignment.regular_duty_minutes),
            status=DutySessionStatus.ACTIVE,
        )
        session.add(active_duty)
        session.flush()
    else:
        assert active_duty is not None
        active_duty.end_event_id = events[0].id
        active_duty.end_km = km_value
        active_duty.end_hmr = hmr_value
        active_duty.ended_at = device_created_at
        active_duty.status = DutySessionStatus.CLOSED
        active_duty.final_overtime_minutes = max(
            0,
            int((device_created_at - active_duty.regular_duty_ends_at).total_seconds() // 60),
        )
    for event in events:
        event.duty_session_id = active_duty.id
    session.flush()
    return MultiMeterCaptureResult(tuple(events), active_duty, False)


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
    return store_private_evidence(
        session,
        context,
        storage,
        reference_uuid=client_event_uuid,
        purpose="events",
        content_type=content_type,
        content=content,
        allowed_mime_types=settings.evidence_mime_types,
        max_bytes=settings.evidence_max_bytes,
    )
