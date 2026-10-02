from __future__ import annotations

from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_owner_deployment_service
from fleet_api.api.schemas import (
    AssetDeploymentRequest,
    AssetSiteDeploymentResponse,
    SiteDeployedAssetResponse,
)
from fleet_api.db.session import get_db
from fleet_api.domain.deployments import (
    DeployedAssetView,
    DeploymentView,
    OwnerDeploymentService,
)
from fleet_api.domain.errors import ConflictError, DomainError, NotFoundError

router = APIRouter(prefix="/api/v1/owner", tags=["owner-deployments"])


def _fail(db: Session, exc: DomainError) -> NoReturn:
    db.rollback()
    if isinstance(exc, NotFoundError):
        http_status, code = status.HTTP_404_NOT_FOUND, "NOT_FOUND"
    elif isinstance(exc, ConflictError):
        http_status, code = status.HTTP_409_CONFLICT, "CONFLICT"
    else:
        http_status, code = status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDATION_ERROR"
    raise HTTPException(
        status_code=http_status,
        detail={"code": code, "message": str(exc)},
    ) from exc


def _deployment_response(view: DeploymentView) -> AssetSiteDeploymentResponse:
    return AssetSiteDeploymentResponse(
        id=view.deployment.id,
        asset_id=view.deployment.asset_id,
        site_id=view.site.id,
        site_name=view.site.short_name,
        starts_at=view.deployment.starts_at,
        ends_at=view.deployment.ends_at,
    )


def _asset_response(view: DeployedAssetView) -> SiteDeployedAssetResponse:
    return SiteDeployedAssetResponse(
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


@router.get(
    "/assets/{asset_id}/deployment",
    response_model=AssetSiteDeploymentResponse,
    responses={204: {"description": "Asset is not currently deployed"}},
)
def current_deployment(
    asset_id: UUID,
    service: OwnerDeploymentService = Depends(get_owner_deployment_service),
) -> AssetSiteDeploymentResponse | Response:
    try:
        view = service.current(asset_id)
        if view is None:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        return _deployment_response(view)
    except DomainError as exc:
        _fail(service.session, exc)


@router.get(
    "/assets/{asset_id}/deployments",
    response_model=list[AssetSiteDeploymentResponse],
)
def deployment_history(
    asset_id: UUID,
    service: OwnerDeploymentService = Depends(get_owner_deployment_service),
) -> list[AssetSiteDeploymentResponse]:
    try:
        return [_deployment_response(view) for view in service.history(asset_id)]
    except DomainError as exc:
        _fail(service.session, exc)


@router.post(
    "/assets/{asset_id}/deployment",
    response_model=AssetSiteDeploymentResponse,
)
def deploy_asset(
    asset_id: UUID,
    payload: AssetDeploymentRequest,
    service: OwnerDeploymentService = Depends(get_owner_deployment_service),
    db: Session = Depends(get_db),
) -> AssetSiteDeploymentResponse:
    try:
        view = service.deploy(asset_id, payload.site_id)
        db.commit()
        return _deployment_response(view)
    except DomainError as exc:
        _fail(db, exc)


@router.delete(
    "/assets/{asset_id}/deployment",
    response_model=AssetSiteDeploymentResponse,
)
def remove_asset_deployment(
    asset_id: UUID,
    service: OwnerDeploymentService = Depends(get_owner_deployment_service),
    db: Session = Depends(get_db),
) -> AssetSiteDeploymentResponse:
    try:
        view = service.remove(asset_id)
        db.commit()
        return _deployment_response(view)
    except DomainError as exc:
        _fail(db, exc)


@router.get(
    "/sites/{site_id}/assets",
    response_model=list[SiteDeployedAssetResponse],
)
def site_assets(
    site_id: UUID,
    service: OwnerDeploymentService = Depends(get_owner_deployment_service),
) -> list[SiteDeployedAssetResponse]:
    try:
        return [_asset_response(view) for view in service.site_assets(site_id)]
    except DomainError as exc:
        _fail(service.session, exc)
