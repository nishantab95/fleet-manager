from __future__ import annotations

from datetime import date
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import (
    get_app_settings,
    get_object_storage,
    get_supervisor_driver_assignment_service,
    require_supervisor,
)
from fleet_api.api.schemas import (
    AssetSiteDeploymentResponse,
    DriverAssetAssignmentRequest,
    DriverAssetAssignmentResponse,
    DriverCandidateResponse,
    SiteDeployedAssetResponse,
    SupervisorBatchVerificationRequest,
    SupervisorBatchVerificationResponse,
    SupervisorCompletenessResponse,
    SupervisorEventResponse,
    SupervisorSiteResponse,
    SupervisorVerificationHistoryResponse,
    SupervisorVerificationRequest,
)
from fleet_api.auth.service import AuthContext
from fleet_api.core.config import Settings
from fleet_api.db.session import get_db
from fleet_api.domain.driver_assignments import (
    DriverAssetAssignmentService,
    DriverAssetAssignmentView,
)
from fleet_api.domain.enums import VerificationStatus
from fleet_api.domain.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    ObjectStorageUnavailableError,
    RoleViolationError,
    TenantConsistencyError,
)
from fleet_api.domain.supervisor import SupervisorEvent, SupervisorService
from fleet_api.storage.objects import ObjectStorage

router = APIRouter(prefix="/api/v1/supervisor", tags=["supervisor"])


def _fail(exc: DomainError) -> NoReturn:
    if isinstance(exc, ObjectStorageUnavailableError):
        http_status, code = status.HTTP_503_SERVICE_UNAVAILABLE, "OBJECT_STORAGE_UNAVAILABLE"
    elif isinstance(exc, NotFoundError):
        http_status, code = status.HTTP_404_NOT_FOUND, "NOT_FOUND"
    elif isinstance(exc, ConflictError):
        http_status, code = status.HTTP_409_CONFLICT, "CONFLICT"
    elif isinstance(exc, TenantConsistencyError | RoleViolationError):
        http_status, code = status.HTTP_403_FORBIDDEN, "FORBIDDEN"
    else:
        http_status, code = 422, "VALIDATION_ERROR"
    raise HTTPException(
        status_code=http_status,
        detail={"code": code, "message": str(exc)},
    ) from exc


def _event_response(view: SupervisorEvent) -> SupervisorEventResponse:
    return SupervisorEventResponse(
        event_id=view.event.id,
        event_type=view.event.event_type,
        assignment_id=view.assignment.id,
        duty_session_id=view.event.duty_session_id,
        driver_name=view.driver.display_name,
        driver_phone=(view.driver.phone_number if view.emergency is not None else None),
        tipper_registration_number=view.asset.registration_number or view.asset.asset_code,
        site_id=view.site.id,
        site_name=view.site.name,
        device_created_at=view.event.device_created_at,
        server_received_at=view.event.server_received_at,
        verification_status=view.event.verification_status,
        reading_type=view.km.reading_type if view.km is not None else None,
        reading_value=view.km.reading_value if view.km is not None else None,
        litres=view.diesel.litres if view.diesel is not None else None,
        emergency_category=view.emergency.category if view.emergency is not None else None,
        emergency_status=view.emergency.status.value if view.emergency is not None else None,
        emergency_description=view.emergency.description if view.emergency is not None else None,
        evidence_id=view.evidence.id if view.evidence is not None else None,
        evidence_available=view.evidence is not None,
        verification_history=[
            SupervisorVerificationHistoryResponse(
                status=item.status,
                reason=item.reason,
                actor_name=item.actor_name,
                created_at=item.created_at,
            )
            for item in view.history
        ],
    )


def _service(db: Session, context: AuthContext) -> SupervisorService:
    return SupervisorService(db, context)


def _assignment_response(
    view: DriverAssetAssignmentView,
) -> DriverAssetAssignmentResponse:
    return DriverAssetAssignmentResponse(
        assignment_id=view.assignment.id,
        asset_id=view.asset.id,
        asset_code=view.asset.asset_code,
        registration_number=view.asset.registration_number,
        driver_membership_id=view.driver_membership.id,
        driver_name=view.driver_membership.display_name or view.driver.display_name,
        asset_site_deployment_id=view.deployment.id,
        site_id=view.site.id,
        site_name=view.site.name,
        starts_at=view.assignment.starts_at,
        ends_at=view.assignment.ends_at,
        regular_duty_minutes=view.assignment.regular_duty_minutes,
    )


def _evidence_headers(view: SupervisorEvent) -> dict[str, str]:
    return {
        "Cache-Control": "private, no-store",
        "Content-Disposition": "inline",
        "X-Fleet-Evidence-Event-Type": view.event.event_type.value,
        "X-Fleet-Evidence-Driver": view.driver.display_name,
        "X-Fleet-Evidence-Tipper": view.asset.registration_number or view.asset.asset_code,
        "X-Fleet-Evidence-Timestamp": view.event.device_created_at.isoformat(),
    }


@router.get("/sites", response_model=list[SupervisorSiteResponse])
def list_supervisor_sites(
    context: Annotated[AuthContext, Depends(require_supervisor)],
    db: Annotated[Session, Depends(get_db)],
) -> list[SupervisorSiteResponse]:
    try:
        return [
            SupervisorSiteResponse(
                id=site.id,
                name=site.name,
                code=site.code,
                status=site.status,
            )
            for site in _service(db, context).list_sites()
        ]
    except DomainError as exc:
        _fail(exc)


@router.get(
    "/sites/{site_id}/assets",
    response_model=list[SiteDeployedAssetResponse],
)
def list_supervisor_site_assets(
    site_id: UUID,
    context: Annotated[AuthContext, Depends(require_supervisor)],
    db: Annotated[Session, Depends(get_db)],
) -> list[SiteDeployedAssetResponse]:
    try:
        return [
            SiteDeployedAssetResponse(
                asset_id=view.asset.id,
                asset_code=view.asset.asset_code,
                asset_type=view.asset.asset_type,
                ownership_type=view.asset.ownership_type,
                registration_number=view.asset.registration_number,
                short_name=view.asset.short_name,
                status=view.asset.status,
                current_deployment=AssetSiteDeploymentResponse(
                    id=view.deployment.id,
                    asset_id=view.asset.id,
                    site_id=view.deployment.site_id,
                    site_name=view.site_name,
                    starts_at=view.deployment.starts_at,
                    ends_at=view.deployment.ends_at,
                ),
                driver_membership_id=view.driver_membership_id,
                driver_name=view.driver_name,
                duty_status=view.duty_status,
                pending_review_count=view.pending_review_count,
            )
            for view in _service(db, context).list_site_assets(site_id)
        ]
    except DomainError as exc:
        _fail(exc)


@router.get(
    "/sites/{site_id}/assets/{asset_id}/assignment",
    response_model=DriverAssetAssignmentResponse,
    responses={204: {"description": "Asset has no current Driver / Operator"}},
)
def current_asset_assignment(
    site_id: UUID,
    asset_id: UUID,
    service: DriverAssetAssignmentService = Depends(
        get_supervisor_driver_assignment_service
    ),
) -> DriverAssetAssignmentResponse | Response:
    try:
        service.ensure_asset_site(asset_id, site_id)
        view = service.current(asset_id)
        if view is None:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        return _assignment_response(view)
    except DomainError as exc:
        service.session.rollback()
        _fail(exc)


@router.get(
    "/sites/{site_id}/assets/{asset_id}/assignments",
    response_model=list[DriverAssetAssignmentResponse],
)
def asset_assignment_history(
    site_id: UUID,
    asset_id: UUID,
    service: DriverAssetAssignmentService = Depends(
        get_supervisor_driver_assignment_service
    ),
) -> list[DriverAssetAssignmentResponse]:
    try:
        service.ensure_asset_site(asset_id, site_id)
        return [_assignment_response(view) for view in service.history(asset_id)]
    except DomainError as exc:
        service.session.rollback()
        _fail(exc)


@router.get(
    "/sites/{site_id}/assets/{asset_id}/eligible-drivers",
    response_model=list[DriverCandidateResponse],
)
def eligible_asset_drivers(
    site_id: UUID,
    asset_id: UUID,
    service: DriverAssetAssignmentService = Depends(
        get_supervisor_driver_assignment_service
    ),
) -> list[DriverCandidateResponse]:
    try:
        service.ensure_asset_site(asset_id, site_id)
        return [
            DriverCandidateResponse(
                membership_id=item.membership.id,
                display_name=item.membership.display_name or item.user.display_name,
            )
            for item in service.eligible_drivers(asset_id)
        ]
    except DomainError as exc:
        service.session.rollback()
        _fail(exc)


@router.post(
    "/sites/{site_id}/assets/{asset_id}/assignment",
    response_model=DriverAssetAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def assign_asset_driver(
    site_id: UUID,
    asset_id: UUID,
    payload: DriverAssetAssignmentRequest,
    service: DriverAssetAssignmentService = Depends(
        get_supervisor_driver_assignment_service
    ),
) -> DriverAssetAssignmentResponse:
    try:
        service.ensure_asset_site(asset_id, site_id)
        view = service.assign(
            asset_id,
            payload.driver_membership_id,
            regular_duty_minutes=payload.regular_duty_minutes or 600,
        )
        service.session.commit()
        return _assignment_response(view)
    except DomainError as exc:
        service.session.rollback()
        _fail(exc)


@router.delete(
    "/sites/{site_id}/assets/{asset_id}/assignment",
    response_model=DriverAssetAssignmentResponse,
)
def unassign_asset_driver(
    site_id: UUID,
    asset_id: UUID,
    service: DriverAssetAssignmentService = Depends(
        get_supervisor_driver_assignment_service
    ),
) -> DriverAssetAssignmentResponse:
    try:
        service.ensure_asset_site(asset_id, site_id)
        view = service.unassign(asset_id)
        service.session.commit()
        return _assignment_response(view)
    except DomainError as exc:
        service.session.rollback()
        _fail(exc)


@router.post(
    "/sites/{site_id}/assets/{asset_id}/assignment/reassign",
    response_model=DriverAssetAssignmentResponse,
)
def reassign_asset_driver(
    site_id: UUID,
    asset_id: UUID,
    payload: DriverAssetAssignmentRequest,
    service: DriverAssetAssignmentService = Depends(
        get_supervisor_driver_assignment_service
    ),
) -> DriverAssetAssignmentResponse:
    try:
        service.ensure_asset_site(asset_id, site_id)
        view = service.reassign(
            asset_id,
            payload.driver_membership_id,
            regular_duty_minutes=payload.regular_duty_minutes,
        )
        service.session.commit()
        return _assignment_response(view)
    except DomainError as exc:
        service.session.rollback()
        _fail(exc)


@router.get("/sites/{site_id}/events", response_model=list[SupervisorEventResponse])
def list_supervisor_events(
    site_id: UUID,
    context: Annotated[AuthContext, Depends(require_supervisor)],
    db: Annotated[Session, Depends(get_db)],
    verification_status: VerificationStatus | None = None,
    review_date: date | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 200,
) -> list[SupervisorEventResponse]:
    try:
        views = _service(db, context).list_events(
            site_id,
            verification_status=verification_status,
            review_date=review_date,
            limit=limit,
        )
        return [_event_response(view) for view in views]
    except DomainError as exc:
        _fail(exc)


@router.get(
    "/sites/{site_id}/completeness",
    response_model=list[SupervisorCompletenessResponse],
)
def site_completeness(
    site_id: UUID,
    review_date: date,
    context: Annotated[AuthContext, Depends(require_supervisor)],
    db: Annotated[Session, Depends(get_db)],
) -> list[SupervisorCompletenessResponse]:
    try:
        return [
            SupervisorCompletenessResponse(
                assignment_id=item.assignment.id,
                driver_name=item.driver.display_name,
                tipper_registration_number=(
                    item.asset.registration_number or item.asset.asset_code
                ),
                site_id=item.site.id,
                site_name=item.site.name,
                has_start_reading=item.has_start_reading,
                has_end_reading=item.has_end_reading,
                start_reading_value=item.start_reading_value,
                end_reading_value=item.end_reading_value,
                odometer_regression=item.odometer_regression,
                pending_trip_verification=item.pending_trip_verification,
                pending_diesel_verification=item.pending_diesel_verification,
                unresolved_emergency=item.unresolved_emergency,
            )
            for item in _service(db, context).completeness(site_id, review_date)
        ]
    except DomainError as exc:
        _fail(exc)


@router.post("/events/{event_id}/verify", response_model=SupervisorEventResponse)
def verify_supervisor_event(
    event_id: UUID,
    payload: SupervisorVerificationRequest,
    context: Annotated[AuthContext, Depends(require_supervisor)],
    db: Annotated[Session, Depends(get_db)],
) -> SupervisorEventResponse:
    try:
        view = _service(db, context).verify_event(
            event_id,
            decision=VerificationStatus(payload.decision),
            reason=payload.reason,
            expected_status=payload.expected_status,
        )
        db.commit()
        return _event_response(view)
    except DomainError as exc:
        db.rollback()
        _fail(exc)


@router.post(
    "/events/verify-batch",
    response_model=SupervisorBatchVerificationResponse,
)
def verify_supervisor_batch(
    payload: SupervisorBatchVerificationRequest,
    context: Annotated[AuthContext, Depends(require_supervisor)],
    db: Annotated[Session, Depends(get_db)],
) -> SupervisorBatchVerificationResponse:
    try:
        views = _service(db, context).verify_batch(
            payload.event_ids,
            decision=VerificationStatus(payload.decision),
            reason=payload.reason,
            expected_status=payload.expected_status,
        )
        db.commit()
        return SupervisorBatchVerificationResponse(events=[_event_response(view) for view in views])
    except DomainError as exc:
        db.rollback()
        _fail(exc)


@router.post("/events/{event_id}/emergency/acknowledge", response_model=SupervisorEventResponse)
def acknowledge_supervisor_emergency(
    event_id: UUID,
    context: Annotated[AuthContext, Depends(require_supervisor)],
    db: Annotated[Session, Depends(get_db)],
) -> SupervisorEventResponse:
    try:
        view = _service(db, context).acknowledge_emergency(event_id)
        db.commit()
        return _event_response(view)
    except DomainError as exc:
        db.rollback()
        _fail(exc)


@router.post("/events/{event_id}/emergency/resolve", response_model=SupervisorEventResponse)
def resolve_supervisor_emergency(
    event_id: UUID,
    context: Annotated[AuthContext, Depends(require_supervisor)],
    db: Annotated[Session, Depends(get_db)],
) -> SupervisorEventResponse:
    try:
        view = _service(db, context).resolve_emergency(event_id)
        db.commit()
        return _event_response(view)
    except DomainError as exc:
        db.rollback()
        _fail(exc)


@router.get("/events/{event_id}/evidence")
def read_supervisor_evidence(
    event_id: UUID,
    context: Annotated[AuthContext, Depends(require_supervisor)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    del settings
    try:
        view = _service(db, context).evidence_view_for_event(event_id)
        assert view.evidence is not None
        content, content_type = storage.read_private(object_key=view.evidence.object_key)
        return Response(
            content=content,
            media_type=content_type,
            headers=_evidence_headers(view),
        )
    except DomainError as exc:
        _fail(exc)
