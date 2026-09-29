from __future__ import annotations

from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_owner_asset_service
from fleet_api.api.schemas import (
    OwnerAssetAssignmentResponse,
    OwnerAssetCreateRequest,
    OwnerAssetResponse,
    OwnerAssetUpdateRequest,
)
from fleet_api.db.session import get_db
from fleet_api.domain.enums import (
    AssetOwnershipType,
    FleetAssetStatus,
    FleetAssetType,
)
from fleet_api.domain.errors import ConflictError, DomainError, NotFoundError
from fleet_api.domain.owner_assets import OwnerAssetService, OwnerAssetView

router = APIRouter(prefix="/api/v1/owner", tags=["owner-assets"])


def _fail(db: Session, exc: DomainError) -> NoReturn:
    db.rollback()
    if isinstance(exc, NotFoundError):
        code, http_status = "NOT_FOUND", status.HTTP_404_NOT_FOUND
    elif isinstance(exc, ConflictError):
        code, http_status = "CONFLICT", status.HTTP_409_CONFLICT
    else:
        code, http_status = "VALIDATION_ERROR", status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(
        status_code=http_status,
        detail={"code": code, "message": str(exc)},
    ) from exc


def _response(view: OwnerAssetView) -> OwnerAssetResponse:
    assignment = view.active_assignment
    return OwnerAssetResponse(
        id=view.asset.id,
        asset_code=view.asset.asset_code,
        asset_type=view.asset.asset_type,
        ownership_type=view.asset.ownership_type,
        registration_number=view.asset.registration_number,
        short_name=view.asset.short_name,
        manufacturer=view.asset.manufacturer,
        model=view.asset.model,
        status=view.asset.status,
        rental_party_name=view.asset.rental_party_name,
        rental_start_date=view.asset.rental_start_date,
        rental_end_date=view.asset.rental_end_date,
        has_active_assignment=assignment is not None,
        active_assignment=(
            OwnerAssetAssignmentResponse(
                assignment_id=assignment.assignment_id,
                site_id=assignment.site_id,
                site_name=assignment.site_name,
                driver_membership_id=assignment.driver_membership_id,
                driver_name=assignment.driver_name,
            )
            if assignment is not None
            else None
        ),
    )


@router.get("/assets", response_model=list[OwnerAssetResponse])
def list_assets(
    asset_status: FleetAssetStatus | None = Query(default=None, alias="status"),
    ownership_type: AssetOwnershipType | None = None,
    asset_type: FleetAssetType | None = None,
    service: OwnerAssetService = Depends(get_owner_asset_service),
) -> list[OwnerAssetResponse]:
    return [
        _response(view)
        for view in service.list_assets(
            status=asset_status,
            ownership_type=ownership_type,
            asset_type=asset_type,
        )
    ]


@router.get("/assets/{asset_id}", response_model=OwnerAssetResponse)
def get_asset(
    asset_id: UUID,
    service: OwnerAssetService = Depends(get_owner_asset_service),
) -> OwnerAssetResponse:
    try:
        return _response(service.get_asset(asset_id))
    except DomainError as exc:
        _fail(service.session, exc)


@router.post(
    "/assets",
    response_model=OwnerAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_asset(
    payload: OwnerAssetCreateRequest,
    service: OwnerAssetService = Depends(get_owner_asset_service),
    db: Session = Depends(get_db),
) -> OwnerAssetResponse:
    try:
        view = service.create_asset(
            asset_type=payload.asset_type,
            ownership_type=payload.ownership_type,
            asset_code=payload.asset_code,
            registration_number=payload.registration_number,
            short_name=payload.short_name,
            manufacturer=payload.manufacturer,
            model=payload.model,
            rental_party_name=payload.rental_party_name,
            rental_start_date=payload.rental_start_date,
            rental_end_date=payload.rental_end_date,
        )
        db.commit()
        return _response(view)
    except DomainError as exc:
        _fail(db, exc)


@router.patch("/assets/{asset_id}", response_model=OwnerAssetResponse)
def update_asset(
    asset_id: UUID,
    payload: OwnerAssetUpdateRequest,
    service: OwnerAssetService = Depends(get_owner_asset_service),
    db: Session = Depends(get_db),
) -> OwnerAssetResponse:
    try:
        view = service.update_asset(
            asset_id,
            asset_code=payload.asset_code,
            registration_number=payload.registration_number,
            short_name=payload.short_name,
            manufacturer=payload.manufacturer,
            model=payload.model,
            ownership_type=payload.ownership_type,
            rental_party_name=payload.rental_party_name,
            rental_start_date=payload.rental_start_date,
            rental_end_date=payload.rental_end_date,
            fields_set=set(payload.model_fields_set),
        )
        db.commit()
        return _response(view)
    except DomainError as exc:
        _fail(db, exc)


@router.post("/assets/{asset_id}/deactivate", response_model=OwnerAssetResponse)
def deactivate_asset(
    asset_id: UUID,
    service: OwnerAssetService = Depends(get_owner_asset_service),
    db: Session = Depends(get_db),
) -> OwnerAssetResponse:
    try:
        view = service.deactivate_asset(asset_id)
        db.commit()
        return _response(view)
    except DomainError as exc:
        _fail(db, exc)


@router.post("/assets/{asset_id}/reactivate", response_model=OwnerAssetResponse)
def reactivate_asset(
    asset_id: UUID,
    service: OwnerAssetService = Depends(get_owner_asset_service),
    db: Session = Depends(get_db),
) -> OwnerAssetResponse:
    try:
        view = service.reactivate_asset(asset_id)
        db.commit()
        return _response(view)
    except DomainError as exc:
        _fail(db, exc)
