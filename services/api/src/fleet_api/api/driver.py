from __future__ import annotations

from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import (
    get_app_settings,
    get_driver_maintenance_proof_service,
    get_object_storage,
    require_driver,
)
from fleet_api.api.maintenance_schemas import (
    DriverMaintenanceDueItemResponse,
    DriverMaintenanceProofRequest,
    MaintenanceProofEvidenceResponse,
    MaintenanceProofResponse,
)
from fleet_api.api.schemas import (
    DriverAssignmentResponse,
    DriverDeviceRequest,
    DriverDeviceResponse,
    DriverDutyStateResponse,
    DriverEventRequest,
    DriverEventResponse,
    DriverMeterCaptureRequest,
    DriverMeterCaptureResponse,
    EvidenceUploadResponse,
)
from fleet_api.auth.service import AuthContext
from fleet_api.core.config import Settings
from fleet_api.db.session import get_db
from fleet_api.domain.driver import (
    create_driver_event,
    create_multi_meter_capture,
    get_current_assignment,
    get_current_duty_state,
    register_device,
    upload_evidence,
    validate_driver_event_uuid,
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
    NotFoundError,
    ObjectStorageUnavailableError,
    RoleViolationError,
    TenantConsistencyError,
)
from fleet_api.domain.maintenance import company_manages_maintenance, task_label
from fleet_api.domain.maintenance_proof import MaintenanceProofService, MaintenanceProofView
from fleet_api.storage.objects import ObjectStorage

router = APIRouter(prefix="/api/v1/driver", tags=["driver"])


def _maintenance_proof_response(
    view: MaintenanceProofView, *, duplicate: bool = False
) -> MaintenanceProofResponse:
    submission = view.submission
    return MaintenanceProofResponse(
        id=submission.id,
        client_submission_uuid=submission.client_submission_uuid,
        asset_id=submission.asset_id,
        asset_code=view.asset.asset_code,
        schedule_id=submission.schedule_id,
        task_label=task_label(view.schedule.task_code, view.schedule.custom_label),
        status=submission.status,
        driver_name=view.driver_name,
        site_id=submission.site_id,
        site_name=view.site.short_name,
        assignment_id=submission.assignment_id,
        duty_session_id=submission.duty_session_id,
        submitted_at=submission.submitted_at,
        note=submission.note,
        evidence=[
            MaintenanceProofEvidenceResponse(
                evidence_id=item.id,
                content_type=item.content_type,
                size_bytes=item.size_bytes,
            )
            for item in view.evidence
        ],
        reviewed_by_membership_id=submission.reviewed_by_membership_id,
        reviewed_at=submission.reviewed_at,
        review_reason=submission.review_reason,
        work_order_id=submission.work_order_id,
        duplicate=duplicate,
    )


def _fail(exc: DomainError) -> NoReturn:
    if isinstance(exc, NotFoundError):
        http_status = status.HTTP_404_NOT_FOUND
        code = "NOT_FOUND"
    elif isinstance(exc, ConflictError):
        http_status = status.HTTP_409_CONFLICT
        code = "CONFLICT"
    elif isinstance(exc, RoleViolationError):
        http_status = status.HTTP_403_FORBIDDEN
        code = "FORBIDDEN"
    elif isinstance(exc, ObjectStorageUnavailableError):
        http_status = status.HTTP_503_SERVICE_UNAVAILABLE
        code = "OBJECT_STORAGE_UNAVAILABLE"
    elif isinstance(exc, DeviceHandoverRequiredError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "DEVICE_HANDOVER_REQUIRED",
                "message": str(exc),
                "current_membership_id": str(exc.current_membership_id),
            },
        ) from exc
    elif isinstance(exc, DeviceHandoverBlockedError):
        http_status = status.HTTP_409_CONFLICT
        code = "DEVICE_HANDOVER_BLOCKED"
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
    elif isinstance(exc, DutyOdometerContinuityError):
        http_status = 422
        code = "ODOMETER_CONTINUITY"
    elif isinstance(exc, DutyOdometerOutOfRangeError):
        http_status = 422
        code = "ODOMETER_OUT_OF_RANGE"
    elif isinstance(exc, DutyHourMeterValidationError):
        http_status = 422
        code = "INVALID_END_HMR"
    elif isinstance(exc, DutyHourMeterContinuityError):
        http_status = 422
        code = "HOUR_METER_CONTINUITY"
    elif isinstance(exc, DutyHourMeterOutOfRangeError):
        http_status = 422
        code = "HOUR_METER_OUT_OF_RANGE"
    else:
        http_status = 422
        code = "VALIDATION_ERROR"
    detail: dict[str, object] = {"code": code, "message": str(exc)}
    if isinstance(exc, DutyOdometerContinuityError):
        detail["previous_end_km"] = str(exc.previous_end_km)
    if isinstance(exc, DutyHourMeterContinuityError):
        detail["previous_end_hmr"] = str(exc.previous_end_hmr)
    raise HTTPException(
        status_code=http_status,
        detail=detail,
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
        tipper_id=current.asset.id,
        asset_code=current.asset.asset_code,
        asset_type=current.asset.asset_type,
        supports_odometer_km=current.asset.supports_odometer_km,
        supports_hour_meter=current.asset.supports_hour_meter,
        company_maintenance_managed=company_manages_maintenance(current.asset),
        tipper_registration_number=current.asset.registration_number,
        tipper_short_name=current.asset.short_name,
        site_id=current.site.id,
        site_name=current.site.name,
        supervisor_name=(
            current.supervisor_names[0] if len(current.supervisor_names) == 1 else None
        ),
        supervisor_names=current.supervisor_names,
        regular_duty_minutes=current.assignment.regular_duty_minutes,
    )


@router.get("/maintenance/due", response_model=list[DriverMaintenanceDueItemResponse])
def driver_due_maintenance(
    service: Annotated[MaintenanceProofService, Depends(get_driver_maintenance_proof_service)],
) -> list[DriverMaintenanceDueItemResponse]:
    try:
        return [
            DriverMaintenanceDueItemResponse(
                schedule_id=item.schedule.id,
                asset_id=item.asset.id,
                task_label=task_label(item.schedule.task_code, item.schedule.custom_label),
                status=item.state,
            )
            for item in service.driver_due_items()
        ]
    except DomainError as exc:
        _fail(exc)


@router.post("/maintenance/proofs", response_model=MaintenanceProofResponse)
def submit_maintenance_proof(
    payload: DriverMaintenanceProofRequest,
    service: Annotated[MaintenanceProofService, Depends(get_driver_maintenance_proof_service)],
    db: Annotated[Session, Depends(get_db)],
) -> MaintenanceProofResponse:
    try:
        result = service.submit(
            client_submission_uuid=payload.client_submission_uuid,
            schedule_id=payload.schedule_id,
            evidence_object_references=payload.evidence_object_references,
            note=payload.note,
        )
        db.commit()
        return _maintenance_proof_response(result.view, duplicate=result.duplicate)
    except DomainError as exc:
        db.rollback()
        _fail(exc)
    except IntegrityError:
        db.rollback()
        _fail(ConflictError("maintenance proof was submitted concurrently"))


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
        tipper_id=state.asset_id,
        site_id=state.site_id,
        started_at=state.started_at,
        start_km=state.start_km,
        ended_at=state.ended_at,
        end_km=state.end_km,
        start_hmr=state.start_hmr,
        end_hmr=state.end_hmr,
        machine_hours=(
            state.end_hmr - state.start_hmr
            if state.start_hmr is not None and state.end_hmr is not None
            else None
        ),
        regular_duty_minutes=state.configured_regular_duty_minutes,
    )


@router.post("/device", response_model=DriverDeviceResponse)
def register_driver_device(
    payload: DriverDeviceRequest,
    context: Annotated[AuthContext, Depends(require_driver)],
    db: Annotated[Session, Depends(get_db)],
) -> DriverDeviceResponse:
    try:
        device, handed_over = register_device(
            db,
            context,
            installation_identifier=payload.installation_identifier,
            platform=payload.platform,
            allow_handover=payload.allow_handover,
            local_state_clear=payload.local_state_clear,
        )
        db.commit()
        return DriverDeviceResponse(
            device_id=device.id,
            installation_identifier=device.installation_identifier,
            platform=device.platform,
            membership_id=context.membership.id,
            handed_over=handed_over,
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
        validate_driver_event_uuid(
            db,
            context,
            client_event_uuid=payload.client_event_uuid,
        )
        device, _ = register_device(
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


@router.post("/meter-captures", response_model=DriverMeterCaptureResponse)
def submit_meter_capture(
    payload: DriverMeterCaptureRequest,
    context: Annotated[AuthContext, Depends(require_driver)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    db: Annotated[Session, Depends(get_db)],
) -> DriverMeterCaptureResponse:
    try:
        for client_uuid in (
            payload.km_client_event_uuid,
            payload.hmr_client_event_uuid,
        ):
            if client_uuid is not None:
                validate_driver_event_uuid(db, context, client_event_uuid=client_uuid)
        device, _ = register_device(
            db,
            context,
            installation_identifier=payload.installation_identifier,
            platform=payload.platform,
        )
        result = create_multi_meter_capture(
            db,
            context,
            settings,
            capture_group_uuid=payload.capture_group_uuid,
            reading_type=payload.reading_type,
            device_created_at=payload.device_created_at,
            device=device,
            object_reference=payload.object_reference,
            km_client_event_uuid=payload.km_client_event_uuid,
            odometer_km=payload.odometer_km,
            km_object_reference=payload.km_object_reference,
            hmr_client_event_uuid=payload.hmr_client_event_uuid,
            hour_meter=payload.hour_meter,
            hmr_object_reference=payload.hmr_object_reference,
        )
        db.commit()
        return DriverMeterCaptureResponse(
            capture_group_uuid=result.capture_group_uuid,
            event_ids=[event.id for event in result.events],
            duty_session_id=result.duty_session.id,
            status="already_accepted" if result.duplicate else "accepted",
        )
    except DomainError as exc:
        db.rollback()
        _fail(exc)
    except IntegrityError:
        db.rollback()
        _fail(ConflictError("meter capture was submitted concurrently"))


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
