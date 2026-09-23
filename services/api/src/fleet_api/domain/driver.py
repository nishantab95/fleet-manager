from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fleet_api.auth.service import AuthContext
from fleet_api.core.config import Settings
from fleet_api.db.models import (
    Assignment,
    CompanyMembership,
    Device,
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
    EmergencyCategory,
    KmReadingType,
    MembershipRole,
    OperationalEventType,
    SiteStatus,
    TipperStatus,
)
from fleet_api.domain.errors import (
    AssignmentNotEffectiveError,
    DomainError,
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
    _evidence_for_event(
        session,
        context=context,
        client_event_uuid=client_event_uuid,
        object_reference=object_reference,
        required=event_type in {OperationalEventType.KM_READING, OperationalEventType.DIESEL},
    )
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
        if reading_type is None or reading_value is None:
            raise DomainError("reading_type and reading_value are required")
        create_km_reading(
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
        if category is None:
            raise DomainError("emergency category is required")
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
