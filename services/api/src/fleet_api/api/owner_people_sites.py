from __future__ import annotations

from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_owner_people_site_service
from fleet_api.api.schemas import (
    OwnerPersonInviteRequest,
    OwnerPersonResponse,
    OwnerPersonSiteResponse,
    OwnerPersonUpdateRequest,
    OwnerSiteCreateRequest,
    OwnerSiteResponse,
    OwnerSiteSupervisorRequest,
    OwnerSiteSupervisorResponse,
    OwnerSiteUpdateRequest,
)
from fleet_api.db.session import get_db
from fleet_api.domain.errors import ConflictError, DomainError, NotFoundError
from fleet_api.domain.owner_people_sites import (
    OwnerPeopleSiteService,
    PersonView,
    SiteView,
)

router = APIRouter(prefix="/api/v1/owner", tags=["owner-people-sites"])


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


def _person_response(view: PersonView) -> OwnerPersonResponse:
    return OwnerPersonResponse(
        user_id=view.user.id,
        membership_id=view.membership.id,
        phone=view.user.phone_number,
        display_name=view.membership.display_name or view.user.display_name,
        role=view.membership.role,
        status=view.membership.status,
        auth_state=view.auth_state,
        phone_auth_linked=view.phone_auth_linked,
        sites=[
            OwnerPersonSiteResponse(site_id=site.site_id, site_name=site.site_name)
            for site in view.sites
        ],
        has_active_assignment=view.has_active_assignment,
        has_active_duty=view.has_active_duty,
        current_asset_id=view.current_asset_id,
        current_asset_code=view.current_asset_code,
        current_site_id=view.current_site_id,
        current_site_name=view.current_site_name,
    )


def _site_response(view: SiteView) -> OwnerSiteResponse:
    return OwnerSiteResponse(
        id=view.site.id,
        name=view.site.name,
        short_name=view.site.short_name,
        code=view.site.code,
        location_description=view.site.location_description,
        latitude=view.site.latitude,
        longitude=view.site.longitude,
        status=view.site.status,
        supervisors=[
            OwnerSiteSupervisorResponse(
                access_id=supervisor.access_id,
                membership_id=supervisor.membership_id,
                display_name=supervisor.display_name,
            )
            for supervisor in view.supervisors
        ],
        asset_count=view.asset_count,
    )


@router.get("/people", response_model=list[OwnerPersonResponse])
def list_people(
    service: OwnerPeopleSiteService = Depends(get_owner_people_site_service),
) -> list[OwnerPersonResponse]:
    return [_person_response(view) for view in service.list_people()]


@router.get("/people/{membership_id}", response_model=OwnerPersonResponse)
def get_person(
    membership_id: UUID,
    service: OwnerPeopleSiteService = Depends(get_owner_people_site_service),
) -> OwnerPersonResponse:
    try:
        return _person_response(service.get_person(membership_id))
    except DomainError as exc:
        _fail(service.session, exc)


@router.post(
    "/people/invite",
    response_model=OwnerPersonResponse,
    status_code=status.HTTP_201_CREATED,
)
def invite_person(
    payload: OwnerPersonInviteRequest,
    service: OwnerPeopleSiteService = Depends(get_owner_people_site_service),
    db: Session = Depends(get_db),
) -> OwnerPersonResponse:
    try:
        view = service.invite_person(
            phone=payload.phone,
            display_name=payload.display_name,
            role=payload.role,
        )
        db.commit()
        return _person_response(view)
    except DomainError as exc:
        _fail(db, exc)


@router.patch("/people/{membership_id}", response_model=OwnerPersonResponse)
def update_person(
    membership_id: UUID,
    payload: OwnerPersonUpdateRequest,
    service: OwnerPeopleSiteService = Depends(get_owner_people_site_service),
    db: Session = Depends(get_db),
) -> OwnerPersonResponse:
    try:
        view = service.update_person(
            membership_id,
            display_name=payload.display_name,
            phone=payload.phone,
            role=payload.role,
            fields_set=set(payload.model_fields_set),
        )
        db.commit()
        return _person_response(view)
    except DomainError as exc:
        _fail(db, exc)


@router.post("/people/{membership_id}/deactivate", response_model=OwnerPersonResponse)
def deactivate_person(
    membership_id: UUID,
    service: OwnerPeopleSiteService = Depends(get_owner_people_site_service),
    db: Session = Depends(get_db),
) -> OwnerPersonResponse:
    try:
        view = service.deactivate_person(membership_id)
        db.commit()
        return _person_response(view)
    except DomainError as exc:
        _fail(db, exc)


@router.post("/people/{membership_id}/reactivate", response_model=OwnerPersonResponse)
def reactivate_person(
    membership_id: UUID,
    service: OwnerPeopleSiteService = Depends(get_owner_people_site_service),
    db: Session = Depends(get_db),
) -> OwnerPersonResponse:
    try:
        view = service.reactivate_person(membership_id)
        db.commit()
        return _person_response(view)
    except DomainError as exc:
        _fail(db, exc)


@router.get("/sites", response_model=list[OwnerSiteResponse])
def list_sites(
    service: OwnerPeopleSiteService = Depends(get_owner_people_site_service),
) -> list[OwnerSiteResponse]:
    return [_site_response(view) for view in service.list_sites()]


@router.get("/sites/{site_id}", response_model=OwnerSiteResponse)
def get_site(
    site_id: UUID,
    service: OwnerPeopleSiteService = Depends(get_owner_people_site_service),
) -> OwnerSiteResponse:
    try:
        return _site_response(service.get_site(site_id))
    except DomainError as exc:
        _fail(service.session, exc)


@router.post("/sites", response_model=OwnerSiteResponse, status_code=status.HTTP_201_CREATED)
def create_site(
    payload: OwnerSiteCreateRequest,
    service: OwnerPeopleSiteService = Depends(get_owner_people_site_service),
    db: Session = Depends(get_db),
) -> OwnerSiteResponse:
    try:
        view = service.create_site(
            name=payload.name,
            short_name=payload.short_name,
            code=payload.code,
            location_description=payload.location_description,
            latitude=payload.latitude,
            longitude=payload.longitude,
        )
        db.commit()
        return _site_response(view)
    except DomainError as exc:
        _fail(db, exc)


@router.patch("/sites/{site_id}", response_model=OwnerSiteResponse)
def update_site(
    site_id: UUID,
    payload: OwnerSiteUpdateRequest,
    service: OwnerPeopleSiteService = Depends(get_owner_people_site_service),
    db: Session = Depends(get_db),
) -> OwnerSiteResponse:
    try:
        view = service.update_site(
            site_id,
            name=payload.name,
            short_name=payload.short_name,
            code=payload.code,
            location_description=payload.location_description,
            latitude=payload.latitude,
            longitude=payload.longitude,
            fields_set=set(payload.model_fields_set),
        )
        db.commit()
        return _site_response(view)
    except DomainError as exc:
        _fail(db, exc)


@router.post("/sites/{site_id}/deactivate", response_model=OwnerSiteResponse)
def deactivate_site(
    site_id: UUID,
    service: OwnerPeopleSiteService = Depends(get_owner_people_site_service),
    db: Session = Depends(get_db),
) -> OwnerSiteResponse:
    try:
        view = service.deactivate_site(site_id)
        db.commit()
        return _site_response(view)
    except DomainError as exc:
        _fail(db, exc)


@router.post("/sites/{site_id}/reactivate", response_model=OwnerSiteResponse)
def reactivate_site(
    site_id: UUID,
    service: OwnerPeopleSiteService = Depends(get_owner_people_site_service),
    db: Session = Depends(get_db),
) -> OwnerSiteResponse:
    try:
        view = service.reactivate_site(site_id)
        db.commit()
        return _site_response(view)
    except DomainError as exc:
        _fail(db, exc)


@router.get("/sites/{site_id}/supervisors", response_model=list[OwnerSiteSupervisorResponse])
def list_site_supervisors(
    site_id: UUID,
    service: OwnerPeopleSiteService = Depends(get_owner_people_site_service),
) -> list[OwnerSiteSupervisorResponse]:
    try:
        return _site_response(service.get_site(site_id)).supervisors
    except DomainError as exc:
        _fail(service.session, exc)


@router.post("/sites/{site_id}/supervisors", response_model=OwnerSiteResponse)
def grant_site_supervisor(
    site_id: UUID,
    payload: OwnerSiteSupervisorRequest,
    service: OwnerPeopleSiteService = Depends(get_owner_people_site_service),
    db: Session = Depends(get_db),
) -> OwnerSiteResponse:
    try:
        view = service.grant_supervisor(site_id, payload.supervisor_membership_id)
        db.commit()
        return _site_response(view)
    except DomainError as exc:
        _fail(db, exc)


@router.delete("/sites/{site_id}/supervisors/{membership_id}", response_model=OwnerSiteResponse)
def revoke_site_supervisor(
    site_id: UUID,
    membership_id: UUID,
    service: OwnerPeopleSiteService = Depends(get_owner_people_site_service),
    db: Session = Depends(get_db),
) -> OwnerSiteResponse:
    try:
        view = service.revoke_supervisor(site_id, membership_id)
        db.commit()
        return _site_response(view)
    except DomainError as exc:
        _fail(db, exc)
