from __future__ import annotations

from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_admin_service
from fleet_api.api.schemas import (
    AssignmentCloseRequest,
    AssignmentCreateRequest,
    AssignmentResponse,
    CompanySettingsResponse,
    CompanySettingsUpdateRequest,
    PersonCreateRequest,
    PersonResponse,
    PersonUpdateRequest,
    SiteCreateRequest,
    SiteResponse,
    SiteUpdateRequest,
    SupervisorSiteAccessCreateRequest,
    SupervisorSiteAccessResponse,
    TipperCreateRequest,
    TipperResponse,
    TipperUpdateRequest,
)
from fleet_api.db.models import Assignment, CompanyMembership, Site, User
from fleet_api.db.session import get_db
from fleet_api.domain.admin import AdminService
from fleet_api.domain.errors import (
    AssignmentConflictError,
    ConflictError,
    DomainError,
    DuplicateAccessError,
    NotFoundError,
    PhoneNormalizationError,
    RoleViolationError,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _fail(db: Session, exc: DomainError) -> NoReturn:
    db.rollback()
    if isinstance(exc, NotFoundError):
        code, message, http_status = "NOT_FOUND", str(exc), status.HTTP_404_NOT_FOUND
    elif isinstance(exc, AssignmentConflictError | ConflictError | DuplicateAccessError):
        code, message, http_status = "CONFLICT", str(exc), status.HTTP_409_CONFLICT
    elif isinstance(exc, RoleViolationError):
        code, message, http_status = "FORBIDDEN", str(exc), status.HTTP_403_FORBIDDEN
    elif isinstance(exc, PhoneNormalizationError):
        code, message, http_status = "VALIDATION_ERROR", "phone number is invalid", 422
    else:
        code, message, http_status = "VALIDATION_ERROR", str(exc), 422
    from fastapi import HTTPException

    raise HTTPException(
        status_code=http_status,
        detail={"code": code, "message": message},
    ) from exc


@router.get("/company", response_model=CompanySettingsResponse)
def get_company_settings(
    service: AdminService = Depends(get_admin_service),
) -> CompanySettingsResponse:
    company = service.get_company_settings()
    return CompanySettingsResponse(
        company_id=company.id,
        reporting_timezone=company.reporting_timezone,
        operational_day_start_minutes=company.operational_day_start_minutes,
    )


@router.patch("/company", response_model=CompanySettingsResponse)
def update_company_settings(
    payload: CompanySettingsUpdateRequest,
    service: AdminService = Depends(get_admin_service),
    db: Session = Depends(get_db),
) -> CompanySettingsResponse:
    try:
        company = service.update_company_settings(
            reporting_timezone=payload.reporting_timezone,
            operational_day_start_minutes=payload.operational_day_start_minutes,
        )
        db.commit()
        return CompanySettingsResponse(
            company_id=company.id,
            reporting_timezone=company.reporting_timezone,
            operational_day_start_minutes=company.operational_day_start_minutes,
        )
    except DomainError as exc:
        _fail(db, exc)


@router.get("/sites", response_model=list[SiteResponse])
def list_sites(service: AdminService = Depends(get_admin_service)) -> list[SiteResponse]:
    return [SiteResponse.model_validate(site) for site in service.list_sites()]


@router.post("/sites", response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
def create_site(
    payload: SiteCreateRequest,
    service: AdminService = Depends(get_admin_service),
    db: Session = Depends(get_db),
) -> SiteResponse:
    try:
        site = service.create_site(name=payload.name, code=payload.code)
        db.commit()
        return SiteResponse.model_validate(site)
    except DomainError as exc:
        _fail(db, exc)


@router.get("/sites/{site_id}", response_model=SiteResponse)
def get_site(site_id: UUID, service: AdminService = Depends(get_admin_service)) -> SiteResponse:
    try:
        return SiteResponse.model_validate(service.get_site(site_id))
    except DomainError as exc:
        _fail(service.session, exc)


@router.patch("/sites/{site_id}", response_model=SiteResponse)
def update_site(
    site_id: UUID,
    payload: SiteUpdateRequest,
    service: AdminService = Depends(get_admin_service),
    db: Session = Depends(get_db),
) -> SiteResponse:
    try:
        site = service.update_site(
            site_id,
            name=payload.name,
            code=payload.code,
            status=payload.status,
            code_was_sent="code" in payload.model_fields_set,
        )
        db.commit()
        return SiteResponse.model_validate(site)
    except DomainError as exc:
        _fail(db, exc)


@router.get("/tippers", response_model=list[TipperResponse])
def list_tippers(service: AdminService = Depends(get_admin_service)) -> list[TipperResponse]:
    return [TipperResponse.model_validate(tipper) for tipper in service.list_tippers()]


@router.post("/tippers", response_model=TipperResponse, status_code=status.HTTP_201_CREATED)
def create_tipper(
    payload: TipperCreateRequest,
    service: AdminService = Depends(get_admin_service),
    db: Session = Depends(get_db),
) -> TipperResponse:
    try:
        tipper = service.create_tipper(
            registration_number=payload.registration_number,
            short_name=payload.short_name,
        )
        db.commit()
        return TipperResponse.model_validate(tipper)
    except DomainError as exc:
        _fail(db, exc)


@router.get("/tippers/{tipper_id}", response_model=TipperResponse)
def get_tipper(
    tipper_id: UUID, service: AdminService = Depends(get_admin_service)
) -> TipperResponse:
    try:
        return TipperResponse.model_validate(service.get_tipper(tipper_id))
    except DomainError as exc:
        _fail(service.session, exc)


@router.patch("/tippers/{tipper_id}", response_model=TipperResponse)
def update_tipper(
    tipper_id: UUID,
    payload: TipperUpdateRequest,
    service: AdminService = Depends(get_admin_service),
    db: Session = Depends(get_db),
) -> TipperResponse:
    try:
        tipper = service.update_tipper(
            tipper_id,
            registration_number=payload.registration_number,
            short_name=payload.short_name,
            status=payload.status,
            registration_was_sent="registration_number" in payload.model_fields_set,
            short_name_was_sent="short_name" in payload.model_fields_set,
        )
        db.commit()
        return TipperResponse.model_validate(tipper)
    except DomainError as exc:
        _fail(db, exc)


@router.get("/people", response_model=list[PersonResponse])
def list_people(service: AdminService = Depends(get_admin_service)) -> list[PersonResponse]:
    return [
        PersonResponse(
            user_id=user.id,
            membership_id=membership.id,
            phone=user.phone_number,
            display_name=user.display_name,
            role=membership.role,
            status=membership.status,
            user_status=user.status.value,
        )
        for membership, user in service.list_people()
    ]


@router.post("/people", response_model=PersonResponse, status_code=status.HTTP_201_CREATED)
def create_person(
    payload: PersonCreateRequest,
    service: AdminService = Depends(get_admin_service),
    db: Session = Depends(get_db),
) -> PersonResponse:
    try:
        membership, user = service.create_person(
            phone=payload.phone,
            display_name=payload.display_name,
            role=payload.role,
        )
        db.commit()
        return PersonResponse(
            user_id=user.id,
            membership_id=membership.id,
            phone=user.phone_number,
            display_name=user.display_name,
            role=membership.role,
            status=membership.status,
            user_status=user.status.value,
        )
    except DomainError as exc:
        _fail(db, exc)


@router.patch("/people/{membership_id}", response_model=PersonResponse)
def update_person(
    membership_id: UUID,
    payload: PersonUpdateRequest,
    service: AdminService = Depends(get_admin_service),
    db: Session = Depends(get_db),
) -> PersonResponse:
    try:
        membership, user = service.update_person(
            membership_id,
            role=payload.role,
            status=payload.status,
        )
        db.commit()
        return PersonResponse(
            user_id=user.id,
            membership_id=membership.id,
            phone=user.phone_number,
            display_name=user.display_name,
            role=membership.role,
            status=membership.status,
            user_status=user.status.value,
        )
    except DomainError as exc:
        _fail(db, exc)


@router.get("/supervisor-site-access", response_model=list[SupervisorSiteAccessResponse])
def list_supervisor_access(
    service: AdminService = Depends(get_admin_service),
) -> list[SupervisorSiteAccessResponse]:
    return [
        SupervisorSiteAccessResponse(
            id=access.id,
            supervisor_membership_id=access.supervisor_membership_id,
            supervisor_name=supervisor_name,
            site_id=access.site_id,
            site_name=site_name,
        )
        for access, supervisor_name, site_name in service.list_supervisor_access()
    ]


@router.post(
    "/supervisor-site-access",
    response_model=SupervisorSiteAccessResponse,
    status_code=status.HTTP_201_CREATED,
)
def grant_supervisor_access(
    payload: SupervisorSiteAccessCreateRequest,
    service: AdminService = Depends(get_admin_service),
    db: Session = Depends(get_db),
) -> SupervisorSiteAccessResponse:
    try:
        access = service.grant_supervisor_access(
            supervisor_membership_id=payload.supervisor_membership_id,
            site_id=payload.site_id,
        )
        db.commit()
        supervisor = service.session.get(CompanyMembership, access.supervisor_membership_id)
        site = service.session.get(Site, access.site_id)
        assert supervisor is not None and site is not None
        user = service.session.get(User, supervisor.user_id)
        assert user is not None
        return SupervisorSiteAccessResponse(
            id=access.id,
            supervisor_membership_id=access.supervisor_membership_id,
            supervisor_name=user.display_name,
            site_id=access.site_id,
            site_name=site.name,
        )
    except DomainError as exc:
        _fail(db, exc)


@router.delete("/supervisor-site-access/{access_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_supervisor_access(
    access_id: UUID,
    service: AdminService = Depends(get_admin_service),
    db: Session = Depends(get_db),
) -> Response:
    try:
        service.revoke_supervisor_access(access_id)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except DomainError as exc:
        _fail(db, exc)


@router.get("/assignments", response_model=list[AssignmentResponse])
def list_assignments(
    service: AdminService = Depends(get_admin_service),
) -> list[AssignmentResponse]:
    return [
        AssignmentResponse(
            id=assignment.id,
            driver_membership_id=assignment.driver_membership_id,
            driver_name=driver_name,
            supervisor_membership_id=assignment.supervisor_membership_id,
            supervisor_name=supervisor_name,
            tipper_id=assignment.tipper_id,
            registration_number=registration_number,
            site_id=assignment.site_id,
            site_name=site_name,
            starts_at=assignment.starts_at,
            ends_at=assignment.ends_at,
            regular_duty_minutes=assignment.regular_duty_minutes,
        )
        for assignment, registration_number, site_name, driver_name, supervisor_name in (
            service.list_assignments()
        )
    ]


def _assignment_response(row: tuple[Assignment, str, str, str, str]) -> AssignmentResponse:
    assignment = row[0]
    return AssignmentResponse(
        id=assignment.id,
        driver_membership_id=assignment.driver_membership_id,
        driver_name=row[3],
        supervisor_membership_id=assignment.supervisor_membership_id,
        supervisor_name=row[4],
        tipper_id=assignment.tipper_id,
        registration_number=row[1],
        site_id=assignment.site_id,
        site_name=row[2],
        starts_at=assignment.starts_at,
        ends_at=assignment.ends_at,
        regular_duty_minutes=assignment.regular_duty_minutes,
    )


@router.get("/assignments/{assignment_id}", response_model=AssignmentResponse)
def get_assignment(
    assignment_id: UUID,
    service: AdminService = Depends(get_admin_service),
) -> AssignmentResponse:
    try:
        return _assignment_response(service.get_assignment(assignment_id))
    except DomainError as exc:
        _fail(service.session, exc)


@router.post("/assignments", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
def create_assignment(
    payload: AssignmentCreateRequest,
    service: AdminService = Depends(get_admin_service),
    db: Session = Depends(get_db),
) -> AssignmentResponse:
    try:
        assignment = service.create_admin_assignment(
            driver_membership_id=payload.driver_membership_id,
            supervisor_membership_id=payload.supervisor_membership_id,
            tipper_id=payload.tipper_id,
            site_id=payload.site_id,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            regular_duty_minutes=payload.regular_duty_minutes,
        )
        db.commit()
        row = next(row for row in service.list_assignments() if row[0].id == assignment.id)
        return _assignment_response(row)
    except DomainError as exc:
        _fail(db, exc)


@router.post("/assignments/{assignment_id}/close", response_model=AssignmentResponse)
def close_assignment(
    assignment_id: UUID,
    payload: AssignmentCloseRequest,
    service: AdminService = Depends(get_admin_service),
    db: Session = Depends(get_db),
) -> AssignmentResponse:
    try:
        service.close_admin_assignment(assignment_id, ends_at=payload.ends_at)
        db.commit()
        row = next(row for row in service.list_assignments() if row[0].id == assignment_id)
        return _assignment_response(row)
    except DomainError as exc:
        _fail(db, exc)
