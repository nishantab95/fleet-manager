from __future__ import annotations

from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import (
    get_app_settings,
    get_object_storage,
    require_driver,
)
from fleet_api.api.schemas import (
    DriverAssignmentResponse,
    DriverDeviceRequest,
    DriverDeviceResponse,
    DriverDutyStateResponse,
    DriverEventRequest,
    DriverEventResponse,
    EvidenceUploadResponse,
)
from fleet_api.auth.service import AuthContext
from fleet_api.core.config import Settings
from fleet_api.db.session import get_db
from fleet_api.domain.driver import (
    create_driver_event,
    get_current_assignment,
    get_current_duty_state,
    register_device,
    upload_evidence,
)
from fleet_api.domain.errors import (
    AssignmentNotEffectiveError,
    DomainError,
    DutyAlreadyStartedError,
    DutyAssignmentMismatchError,
    DutyEventOutsideSessionError,
    DutyKmValidationError,
    DutyNotStartedError,
    EvidenceValidationError,
    ObjectStorageUnavailableError,
    RoleViolationError,
    TenantConsistencyError,
)
from fleet_api.storage.objects import ObjectStorage

router = APIRouter(prefix="/api/v1/driver", tags=["driver"])


def _fail(exc: DomainError) -> NoReturn:
    if isinstance(exc, RoleViolationError):
        http_status = status.HTTP_403_FORBIDDEN
        code = "FORBIDDEN"
    elif isinstance(exc, ObjectStorageUnavailableError):
        http_status = status.HTTP_503_SERVICE_UNAVAILABLE
        code = "OBJECT_STORAGE_UNAVAILABLE"
    elif isinstance(exc, TenantConsistencyError | EvidenceValidationError):
        http_status = status.HTTP_403_FORBIDDEN if isinstance(exc, TenantConsistencyError) else 422
        code = "FORBIDDEN" if isinstance(exc, TenantConsistencyError) else "VALIDATION_ERROR"
    elif isinstance(exc, AssignmentNotEffectiveError):
        http_status = 422
        code = "ASSIGNMENT_INVALID"
    elif isinstance(exc, DutyNotStartedError):
        http_status = 422
        code = "DUTY_NOT_STARTED"
    elif isinstance(exc, DutyAlreadyStartedError):
        http_status = 409
        code = "DUTY_ALREADY_STARTED"
    elif isinstance(exc, DutyAssignmentMismatchError):
        http_status = 422
        code = "DUTY_ASSIGNMENT_MISMATCH"
    elif isinstance(exc, DutyEventOutsideSessionError):
        http_status = 422
        code = "DUTY_EVENT_OUTSIDE_SESSION"
    elif isinstance(exc, DutyKmValidationError):
        http_status = 422
        code = "INVALID_END_KM"
    else:
        http_status = 422
        code = "VALIDATION_ERROR"
    raise HTTPException(
        status_code=http_status,
        detail={"code": code, "message": str(exc)},
    ) from exc


@router.get("/assignment/current", response_model=DriverAssignmentResponse | None)
def current_assignment(
    context: Annotated[AuthContext, Depends(require_driver)],
    db: Annotated[Session, Depends(get_db)],
) -> DriverAssignmentResponse | None:
    try:
        current = get_current_assignment(db, context)
    except DomainError as exc:
        _fail(exc)
    if current is None:
        return None
    return DriverAssignmentResponse(
        assignment_id=current.assignment.id,
        tipper_id=current.tipper.id,
        tipper_registration_number=current.tipper.registration_number,
        tipper_short_name=current.tipper.short_name,
        site_id=current.site.id,
        site_name=current.site.name,
        supervisor_name=(
            current.supervisor_membership.display_name or current.supervisor.display_name
        ),
        regular_duty_minutes=current.assignment.regular_duty_minutes,
    )


@router.get("/duty/current", response_model=DriverDutyStateResponse)
def current_duty(
    context: Annotated[AuthContext, Depends(require_driver)],
    db: Annotated[Session, Depends(get_db)],
) -> DriverDutyStateResponse:
    try:
        state = get_current_duty_state(db, context).session
    except DomainError as exc:
        _fail(exc)
    if state is None:
        return DriverDutyStateResponse(status="NONE")
    return DriverDutyStateResponse(
        status=state.status.value,
        session_id=state.id,
        assignment_id=state.assignment_id,
        tipper_id=state.tipper_id,
        site_id=state.site_id,
        started_at=state.started_at,
        start_km=state.start_km,
        ended_at=state.ended_at,
        end_km=state.end_km,
        regular_duty_minutes=state.configured_regular_duty_minutes,
    )


@router.post("/device", response_model=DriverDeviceResponse)
def register_driver_device(
    payload: DriverDeviceRequest,
    context: Annotated[AuthContext, Depends(require_driver)],
    db: Annotated[Session, Depends(get_db)],
) -> DriverDeviceResponse:
    try:
        device = register_device(
            db,
            context,
            installation_identifier=payload.installation_identifier,
            platform=payload.platform,
        )
        db.commit()
        return DriverDeviceResponse(
            device_id=device.id,
            installation_identifier=device.installation_identifier,
            platform=device.platform,
        )
    except DomainError as exc:
        db.rollback()
        _fail(exc)


@router.post("/events", response_model=DriverEventResponse)
def submit_driver_event(
    payload: DriverEventRequest,
    context: Annotated[AuthContext, Depends(require_driver)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    db: Annotated[Session, Depends(get_db)],
) -> DriverEventResponse:
    try:
        device = register_device(
            db,
            context,
            installation_identifier=payload.installation_identifier,
            platform=payload.platform,
        )
        result = create_driver_event(
            db,
            context,
            settings,
            client_event_uuid=payload.client_event_uuid,
            event_type=payload.event_type,
            device_created_at=payload.device_created_at,
            device=device,
            reading_type=payload.reading_type,
            reading_value=payload.reading_value,
            litres=payload.litres,
            category=payload.category,
            description=payload.description,
            object_reference=payload.object_reference,
        )
        db.commit()
        return DriverEventResponse(
            event_id=result.event.id,
            client_event_uuid=payload.client_event_uuid,
            status="already_accepted" if result.duplicate else "accepted",
            verification_status=result.event.verification_status.value,
        )
    except DomainError as exc:
        db.rollback()
        _fail(exc)


@router.post("/evidence", response_model=EvidenceUploadResponse)
async def upload_driver_evidence(
    client_event_uuid: UUID,
    file: Annotated[UploadFile, File(...)],
    context: Annotated[AuthContext, Depends(require_driver)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    db: Annotated[Session, Depends(get_db)],
) -> EvidenceUploadResponse:
    try:
        content = await file.read(settings.evidence_max_bytes + 1)
        evidence = upload_evidence(
            db,
            context,
            storage,
            settings,
            client_event_uuid=client_event_uuid,
            content_type=file.content_type or "",
            content=content,
        )
        db.commit()
        return EvidenceUploadResponse(
            client_event_uuid=evidence.client_event_uuid,
            object_reference=evidence.object_key,
            content_type=evidence.content_type,
            size_bytes=evidence.size_bytes,
        )
    except DomainError as exc:
        db.rollback()
        _fail(exc)
