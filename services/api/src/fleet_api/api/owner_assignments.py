from __future__ import annotations

from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_owner_driver_assignment_service
from fleet_api.api.schemas import (
    DriverAssetAssignmentRequest,
    DriverAssetAssignmentResponse,
    DriverCandidateResponse,
)
from fleet_api.db.session import get_db
from fleet_api.domain.driver_assignments import (
    DriverAssetAssignmentService,
    DriverAssetAssignmentView,
)
from fleet_api.domain.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    RoleViolationError,
    TenantConsistencyError,
)

router = APIRouter(prefix="/api/v1/owner", tags=["owner-driver-assignments"])


def _fail(db: Session, exc: DomainError) -> NoReturn:
    db.rollback()
    if isinstance(exc, NotFoundError):
        http_status, code = status.HTTP_404_NOT_FOUND, "NOT_FOUND"
    elif isinstance(exc, ConflictError):
        http_status, code = status.HTTP_409_CONFLICT, "CONFLICT"
    elif isinstance(exc, TenantConsistencyError | RoleViolationError):
        http_status, code = status.HTTP_403_FORBIDDEN, "FORBIDDEN"
    else:
        http_status, code = status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDATION_ERROR"
    raise HTTPException(
        status_code=http_status,
        detail={"code": code, "message": str(exc)},
    ) from exc


def assignment_response(view: DriverAssetAssignmentView) -> DriverAssetAssignmentResponse:
    return DriverAssetAssignmentResponse(
        assignment_id=view.assignment.id,
        asset_id=view.asset.id,
        asset_code=view.asset.asset_code,
        registration_number=view.asset.registration_number,
        driver_membership_id=view.driver_membership.id,
        driver_name=view.driver_membership.display_name or view.driver.display_name,
        asset_site_deployment_id=view.deployment.id,
        site_id=view.site.id,
        site_name=view.site.short_name,
        starts_at=view.assignment.starts_at,
        ends_at=view.assignment.ends_at,
        regular_duty_minutes=view.assignment.regular_duty_minutes,
    )


@router.get(
    "/assets/{asset_id}/assignment",
    response_model=DriverAssetAssignmentResponse,
    responses={204: {"description": "Asset has no current Driver / Operator"}},
)
def current_assignment(
    asset_id: UUID,
    service: DriverAssetAssignmentService = Depends(get_owner_driver_assignment_service),
) -> DriverAssetAssignmentResponse | Response:
    try:
        view = service.current(asset_id)
        if view is None:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        return assignment_response(view)
    except DomainError as exc:
        _fail(service.session, exc)


@router.get(
    "/assets/{asset_id}/assignments",
    response_model=list[DriverAssetAssignmentResponse],
)
def assignment_history(
    asset_id: UUID,
    service: DriverAssetAssignmentService = Depends(get_owner_driver_assignment_service),
) -> list[DriverAssetAssignmentResponse]:
    try:
        return [assignment_response(view) for view in service.history(asset_id)]
    except DomainError as exc:
        _fail(service.session, exc)


@router.get(
    "/assets/{asset_id}/eligible-drivers",
    response_model=list[DriverCandidateResponse],
)
def eligible_drivers(
    asset_id: UUID,
    service: DriverAssetAssignmentService = Depends(get_owner_driver_assignment_service),
) -> list[DriverCandidateResponse]:
    try:
        return [
            DriverCandidateResponse(
                membership_id=item.membership.id,
                display_name=item.membership.display_name or item.user.display_name,
                phone=item.user.phone_number,
                status=item.membership.status,
            )
            for item in service.eligible_drivers(asset_id)
        ]
    except DomainError as exc:
        _fail(service.session, exc)


@router.post(
    "/assets/{asset_id}/assignment",
    response_model=DriverAssetAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def assign_driver(
    asset_id: UUID,
    payload: DriverAssetAssignmentRequest,
    service: DriverAssetAssignmentService = Depends(get_owner_driver_assignment_service),
    db: Session = Depends(get_db),
) -> DriverAssetAssignmentResponse:
    try:
        view = service.assign(
            asset_id,
            payload.driver_membership_id,
            regular_duty_minutes=payload.regular_duty_minutes or 600,
        )
        db.commit()
        return assignment_response(view)
    except DomainError as exc:
        _fail(db, exc)


@router.delete(
    "/assets/{asset_id}/assignment",
    response_model=DriverAssetAssignmentResponse,
)
def unassign_driver(
    asset_id: UUID,
    service: DriverAssetAssignmentService = Depends(get_owner_driver_assignment_service),
    db: Session = Depends(get_db),
) -> DriverAssetAssignmentResponse:
    try:
        view = service.unassign(asset_id)
        db.commit()
        return assignment_response(view)
    except DomainError as exc:
        _fail(db, exc)


@router.post(
    "/assets/{asset_id}/assignment/reassign",
    response_model=DriverAssetAssignmentResponse,
)
def reassign_driver(
    asset_id: UUID,
    payload: DriverAssetAssignmentRequest,
    service: DriverAssetAssignmentService = Depends(get_owner_driver_assignment_service),
    db: Session = Depends(get_db),
) -> DriverAssetAssignmentResponse:
    try:
        view = service.reassign(
            asset_id,
            payload.driver_membership_id,
            regular_duty_minutes=payload.regular_duty_minutes,
        )
        db.commit()
        return assignment_response(view)
    except DomainError as exc:
        _fail(db, exc)
