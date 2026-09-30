from __future__ import annotations

from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_report_template_service
from fleet_api.api.schemas import (
    ReportTemplateCreateRequest,
    ReportTemplateDuplicateRequest,
    ReportTemplateResponse,
    ReportTemplateUpdateRequest,
)
from fleet_api.db.session import get_db
from fleet_api.domain.errors import ConflictError, DomainError, NotFoundError
from fleet_api.domain.report_templates import ReportTemplateService

router = APIRouter(prefix="/api/v1/owner/report-templates", tags=["owner-report-templates"])


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


@router.get("", response_model=list[ReportTemplateResponse])
def list_report_templates(
    service: ReportTemplateService = Depends(get_report_template_service),
    db: Session = Depends(get_db),
) -> list[ReportTemplateResponse]:
    try:
        templates = service.list_templates()
        db.commit()
        return [ReportTemplateResponse.model_validate(item) for item in templates]
    except DomainError as exc:
        _fail(db, exc)


@router.get("/{template_id}", response_model=ReportTemplateResponse)
def get_report_template(
    template_id: UUID,
    service: ReportTemplateService = Depends(get_report_template_service),
    db: Session = Depends(get_db),
) -> ReportTemplateResponse:
    try:
        template = service.get(template_id)
        db.commit()
        return ReportTemplateResponse.model_validate(template)
    except DomainError as exc:
        _fail(db, exc)


@router.post(
    "",
    response_model=ReportTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_report_template(
    payload: ReportTemplateCreateRequest,
    service: ReportTemplateService = Depends(get_report_template_service),
    db: Session = Depends(get_db),
) -> ReportTemplateResponse:
    try:
        template = service.create(**payload.model_dump())
        db.commit()
        return ReportTemplateResponse.model_validate(template)
    except DomainError as exc:
        _fail(db, exc)


@router.patch("/{template_id}", response_model=ReportTemplateResponse)
def update_report_template(
    template_id: UUID,
    payload: ReportTemplateUpdateRequest,
    service: ReportTemplateService = Depends(get_report_template_service),
    db: Session = Depends(get_db),
) -> ReportTemplateResponse:
    try:
        template = service.update(
            template_id,
            name=payload.name,
            included_sheets=payload.included_sheets,
            management_dashboard_columns=payload.management_dashboard_columns,
            tipper_daily_columns=payload.tipper_daily_columns,
            machinery_daily_columns=payload.machinery_daily_columns,
            fields_set=set(payload.model_fields_set),
        )
        db.commit()
        return ReportTemplateResponse.model_validate(template)
    except DomainError as exc:
        _fail(db, exc)


@router.post("/{template_id}/duplicate", response_model=ReportTemplateResponse)
def duplicate_report_template(
    template_id: UUID,
    payload: ReportTemplateDuplicateRequest,
    service: ReportTemplateService = Depends(get_report_template_service),
    db: Session = Depends(get_db),
) -> ReportTemplateResponse:
    try:
        template = service.duplicate(template_id, name=payload.name)
        db.commit()
        return ReportTemplateResponse.model_validate(template)
    except DomainError as exc:
        _fail(db, exc)


@router.post("/{template_id}/default", response_model=ReportTemplateResponse)
def set_default_report_template(
    template_id: UUID,
    service: ReportTemplateService = Depends(get_report_template_service),
    db: Session = Depends(get_db),
) -> ReportTemplateResponse:
    try:
        template = service.set_default(template_id)
        db.commit()
        return ReportTemplateResponse.model_validate(template)
    except DomainError as exc:
        _fail(db, exc)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report_template(
    template_id: UUID,
    service: ReportTemplateService = Depends(get_report_template_service),
    db: Session = Depends(get_db),
) -> Response:
    try:
        service.delete(template_id)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except DomainError as exc:
        _fail(db, exc)
