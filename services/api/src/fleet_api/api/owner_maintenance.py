from __future__ import annotations

from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_maintenance_service
from fleet_api.api.maintenance_schemas import (
    MaintenanceCriterionRequest,
    MaintenanceCriterionResponse,
    MaintenanceDueItemResponse,
    MaintenanceHistoryResponse,
    MaintenanceOverviewResponse,
    MaintenancePlanCopyRequest,
    MaintenancePlanResponse,
    MaintenanceScheduleRequest,
    MaintenanceScheduleResponse,
    MaintenanceTaskCatalogResponse,
    MaintenanceTemplateApplyRequest,
    MaintenanceTemplateCreateRequest,
    MaintenanceTemplateCriterionResponse,
    MaintenanceTemplateItemRequest,
    MaintenanceTemplateItemResponse,
    MaintenanceTemplateResponse,
    MaintenanceWorkOrderCompleteRequest,
    MaintenanceWorkOrderCreateRequest,
    MaintenanceWorkOrderResponse,
    MaintenanceWorkOrderTransitionRequest,
)
from fleet_api.db.models import MaintenanceWorkOrder
from fleet_api.db.session import get_db
from fleet_api.domain.enums import MaintenanceDueState, MaintenanceWorkOrderStatus
from fleet_api.domain.errors import ConflictError, DomainError, NotFoundError
from fleet_api.domain.maintenance import (
    TASK_CATALOG,
    CriterionInput,
    MaintenanceService,
    ScheduleEvaluation,
    task_label,
)

router = APIRouter(prefix="/api/v1/owner/maintenance", tags=["owner-maintenance"])


def _fail(db: Session, exc: DomainError) -> NoReturn:
    db.rollback()
    if isinstance(exc, NotFoundError):
        code, http_status = "NOT_FOUND", status.HTTP_404_NOT_FOUND
    elif isinstance(exc, ConflictError):
        code, http_status = "CONFLICT", status.HTTP_409_CONFLICT
    else:
        code, http_status = "VALIDATION_ERROR", status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(
        status_code=http_status, detail={"code": code, "message": str(exc)}
    ) from exc


def _criterion_inputs(
    criteria: list[MaintenanceCriterionRequest],
) -> list[CriterionInput]:
    return [
        CriterionInput(
            basis=item.basis,
            enabled=item.enabled,
            interval_value=item.interval_value,
            warning_value=item.warning_value,
            baseline_value=item.baseline_value,
            baseline_date=item.baseline_date,
        )
        for item in criteria
    ]


def _schedule_response(
    service: MaintenanceService,
    evaluation: ScheduleEvaluation,
) -> MaintenanceScheduleResponse:
    criteria_by_basis = {item.basis: item for item in evaluation.criteria}
    return MaintenanceScheduleResponse(
        id=evaluation.schedule.id,
        asset_id=evaluation.schedule.asset_id,
        task_code=evaluation.schedule.task_code,
        task_label=task_label(evaluation.schedule.task_code, evaluation.schedule.custom_label),
        action_type=evaluation.schedule.action_type,
        description=evaluation.schedule.description,
        enabled=evaluation.schedule.enabled,
        state=evaluation.state,
        triggered_by=list(evaluation.triggered_by),
        criteria=[
            MaintenanceCriterionResponse(
                id=criterion.id,
                basis=criterion.basis,
                enabled=criterion.enabled,
                interval_value=criterion.interval_value,
                warning_value=criterion.warning_value,
                baseline_value=criterion.baseline_value,
                baseline_date=criterion.baseline_date,
                state=criteria_by_basis[criterion.basis].state,
                current_value=criteria_by_basis[criterion.basis].current_value,
                due_value=criteria_by_basis[criterion.basis].due_value,
                current_date=criteria_by_basis[criterion.basis].current_date,
                due_date=criteria_by_basis[criterion.basis].due_date,
            )
            for criterion in service.criteria_for(evaluation.schedule.id)
            if criterion.enabled
        ],
    )


def _work_order_response(order: MaintenanceWorkOrder) -> MaintenanceWorkOrderResponse:
    parts = order.parts_cost
    labor = order.labor_cost
    other = order.other_cost
    return MaintenanceWorkOrderResponse(
        id=order.id,
        asset_id=order.asset_id,
        schedule_id=order.schedule_id,
        title=order.title,
        description=order.description,
        status=order.status,
        scheduled_for=order.scheduled_for,
        started_at=order.started_at,
        completed_at=order.completed_at,
        service_date=order.service_date,
        completion_odometer_km=order.completion_odometer_km,
        completion_hour_meter=order.completion_hour_meter,
        vendor=order.vendor,
        parts_cost=parts,
        labor_cost=labor,
        other_cost=other,
        total_cost=parts + labor + other,
        notes=order.notes,
    )


def _template_response(template: object) -> MaintenanceTemplateResponse:
    return MaintenanceTemplateResponse.model_validate(template, from_attributes=True)


@router.get("/overview", response_model=MaintenanceOverviewResponse)
def overview(
    service: MaintenanceService = Depends(get_maintenance_service),
) -> MaintenanceOverviewResponse:
    evaluations = service.evaluations()
    counts = service.alert_counts()
    due_items = [
        MaintenanceDueItemResponse(
            **_schedule_response(service, item).model_dump(),
            asset_code=item.asset.asset_code,
            site_name=item.site_name,
        )
        for item in evaluations
        if item.state
        in {
            MaintenanceDueState.OVERDUE,
            MaintenanceDueState.DUE,
            MaintenanceDueState.DUE_SOON,
        }
    ]
    return MaintenanceOverviewResponse(
        overdue=counts[MaintenanceDueState.OVERDUE],
        due=counts[MaintenanceDueState.DUE],
        due_soon=counts[MaintenanceDueState.DUE_SOON],
        unknown=counts[MaintenanceDueState.UNKNOWN],
        open_work_orders=service.open_work_order_count(),
        items=due_items,
    )


@router.get("/plans/{asset_id}", response_model=MaintenancePlanResponse)
def get_plan(
    asset_id: UUID,
    service: MaintenanceService = Depends(get_maintenance_service),
) -> MaintenancePlanResponse:
    asset = service._asset(asset_id)
    plan, schedules = service.list_plan(asset_id)
    evaluations = {item.schedule.id: item for item in service.evaluations(include_disabled=True)}
    items = [
        _schedule_response(service, evaluations[schedule.id])
        for schedule in schedules
        if schedule.id in evaluations
    ]
    return MaintenancePlanResponse(
        id=plan.id if plan else None,
        asset_id=asset.id,
        asset_code=asset.asset_code,
        asset_type=asset.asset_type,
        manufacturer=asset.manufacturer,
        model=asset.model,
        model_year=asset.model_year,
        is_wheeled=asset.is_wheeled,
        supports_odometer_km=asset.supports_odometer_km,
        supports_hour_meter=asset.supports_hour_meter,
        source=plan.source if plan else None,
        source_template_id=plan.source_template_id if plan else None,
        source_template_version=plan.source_template_version if plan else None,
        items=items,
    )


@router.post(
    "/plans/{asset_id}/items",
    response_model=MaintenanceScheduleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_item(
    asset_id: UUID,
    payload: MaintenanceScheduleRequest,
    service: MaintenanceService = Depends(get_maintenance_service),
    db: Session = Depends(get_db),
) -> MaintenanceScheduleResponse:
    try:
        schedule = service.save_schedule(
            asset_id,
            task_code=payload.task_code,
            custom_label=payload.custom_label,
            action_type=payload.action_type,
            description=payload.description,
            enabled=payload.enabled,
            criteria=_criterion_inputs(payload.criteria),
        )
        db.commit()
        evaluation = next(item for item in service.evaluations() if item.schedule.id == schedule.id)
        return _schedule_response(service, evaluation)
    except DomainError as exc:
        _fail(db, exc)


@router.put("/plans/{asset_id}/items/{schedule_id}", response_model=MaintenanceScheduleResponse)
def update_item(
    asset_id: UUID,
    schedule_id: UUID,
    payload: MaintenanceScheduleRequest,
    service: MaintenanceService = Depends(get_maintenance_service),
    db: Session = Depends(get_db),
) -> MaintenanceScheduleResponse:
    try:
        schedule = service.save_schedule(
            asset_id,
            schedule_id=schedule_id,
            task_code=payload.task_code,
            custom_label=payload.custom_label,
            action_type=payload.action_type,
            description=payload.description,
            enabled=payload.enabled,
            criteria=_criterion_inputs(payload.criteria),
        )
        db.commit()
        evaluation = next(item for item in service.evaluations() if item.schedule.id == schedule.id)
        return _schedule_response(service, evaluation)
    except DomainError as exc:
        _fail(db, exc)


@router.delete(
    "/plans/items/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def remove_item(
    schedule_id: UUID,
    service: MaintenanceService = Depends(get_maintenance_service),
    db: Session = Depends(get_db),
) -> Response:
    try:
        service.remove_custom_schedule(schedule_id)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except DomainError as exc:
        _fail(db, exc)


@router.get("/catalog/{asset_id}", response_model=list[MaintenanceTaskCatalogResponse])
def task_catalog(
    asset_id: UUID,
    service: MaintenanceService = Depends(get_maintenance_service),
) -> list[MaintenanceTaskCatalogResponse]:
    suggested = {item.code for item in service.generic_starter(asset_id)}
    return [
        MaintenanceTaskCatalogResponse(
            code=item.code,
            label=item.label,
            default_action=item.default_action,
            suggested_for_asset=item.code in suggested,
        )
        for item in TASK_CATALOG
    ]


@router.get("/work-orders", response_model=list[MaintenanceWorkOrderResponse])
def list_work_orders(
    service: MaintenanceService = Depends(get_maintenance_service),
) -> list[MaintenanceWorkOrderResponse]:
    return [_work_order_response(item) for item in service.list_work_orders()]


@router.post("/work-orders", response_model=MaintenanceWorkOrderResponse, status_code=201)
def create_work_order(
    payload: MaintenanceWorkOrderCreateRequest,
    service: MaintenanceService = Depends(get_maintenance_service),
    db: Session = Depends(get_db),
) -> MaintenanceWorkOrderResponse:
    try:
        order = service.create_work_order(
            payload.asset_id,
            schedule_id=payload.schedule_id,
            title=payload.title,
            description=payload.description,
            scheduled_for=payload.scheduled_for,
        )
        db.commit()
        return _work_order_response(order)
    except DomainError as exc:
        _fail(db, exc)


@router.post("/work-orders/{work_order_id}/transition", response_model=MaintenanceWorkOrderResponse)
def transition_work_order(
    work_order_id: UUID,
    payload: MaintenanceWorkOrderTransitionRequest,
    service: MaintenanceService = Depends(get_maintenance_service),
    db: Session = Depends(get_db),
) -> MaintenanceWorkOrderResponse:
    if payload.status == MaintenanceWorkOrderStatus.COMPLETED:
        raise HTTPException(
            422, detail={"code": "VALIDATION_ERROR", "message": "use the completion endpoint"}
        )
    try:
        order = service.transition_work_order(work_order_id, payload.status)
        db.commit()
        return _work_order_response(order)
    except DomainError as exc:
        _fail(db, exc)


@router.post("/work-orders/{work_order_id}/complete", response_model=MaintenanceWorkOrderResponse)
def complete_work_order(
    work_order_id: UUID,
    payload: MaintenanceWorkOrderCompleteRequest,
    service: MaintenanceService = Depends(get_maintenance_service),
    db: Session = Depends(get_db),
) -> MaintenanceWorkOrderResponse:
    try:
        order, _record = service.complete_work_order(
            work_order_id,
            service_date=payload.service_date,
            odometer_km=payload.odometer_km,
            hour_meter=payload.hour_meter,
            vendor=payload.vendor,
            parts_cost=payload.parts_cost,
            labor_cost=payload.labor_cost,
            other_cost=payload.other_cost,
            notes=payload.notes,
        )
        db.commit()
        return _work_order_response(order)
    except DomainError as exc:
        _fail(db, exc)


@router.get("/history", response_model=list[MaintenanceHistoryResponse])
def history(
    asset_id: UUID | None = Query(default=None),
    service: MaintenanceService = Depends(get_maintenance_service),
) -> list[MaintenanceHistoryResponse]:
    return [
        MaintenanceHistoryResponse.model_validate(item, from_attributes=True)
        for item in service.list_history(asset_id)
    ]


@router.get("/templates", response_model=list[MaintenanceTemplateResponse])
def list_templates(
    service: MaintenanceService = Depends(get_maintenance_service),
) -> list[MaintenanceTemplateResponse]:
    return [_template_response(item) for item in service.list_templates()]


@router.post("/templates", response_model=MaintenanceTemplateResponse, status_code=201)
def create_template(
    payload: MaintenanceTemplateCreateRequest,
    service: MaintenanceService = Depends(get_maintenance_service),
    db: Session = Depends(get_db),
) -> MaintenanceTemplateResponse:
    try:
        template = service.create_template(**payload.model_dump())
        db.commit()
        return _template_response(template)
    except DomainError as exc:
        _fail(db, exc)


@router.get(
    "/templates/{template_id}/items",
    response_model=list[MaintenanceTemplateItemResponse],
)
def list_template_items(
    template_id: UUID,
    service: MaintenanceService = Depends(get_maintenance_service),
) -> list[MaintenanceTemplateItemResponse]:
    try:
        return [
            MaintenanceTemplateItemResponse(
                id=item.id,
                template_id=item.template_id,
                task_code=item.task_code,
                task_label=task_label(item.task_code, item.custom_label),
                action_type=item.action_type,
                description=item.description,
                enabled=item.enabled,
                criteria=[
                    MaintenanceTemplateCriterionResponse.model_validate(
                        criterion, from_attributes=True
                    )
                    for criterion in criteria
                ],
            )
            for item, criteria in service.template_items(template_id)
        ]
    except DomainError as exc:
        _fail(service.session, exc)


@router.post(
    "/templates/{template_id}/items",
    response_model=MaintenanceTemplateItemResponse,
    status_code=201,
)
def add_template_item(
    template_id: UUID,
    payload: MaintenanceTemplateItemRequest,
    service: MaintenanceService = Depends(get_maintenance_service),
    db: Session = Depends(get_db),
) -> MaintenanceTemplateItemResponse:
    try:
        item = service.add_template_item(
            template_id,
            task_code=payload.task_code,
            custom_label=payload.custom_label,
            action_type=payload.action_type,
            description=payload.description,
            enabled=payload.enabled,
            criteria=_criterion_inputs(payload.criteria),
        )
        db.commit()
        criteria = service.template_items(template_id)
        created_item, created_criteria = next(row for row in criteria if row[0].id == item.id)
        return MaintenanceTemplateItemResponse(
            id=created_item.id,
            template_id=created_item.template_id,
            task_code=created_item.task_code,
            task_label=task_label(created_item.task_code, created_item.custom_label),
            action_type=created_item.action_type,
            description=created_item.description,
            enabled=created_item.enabled,
            criteria=[
                MaintenanceTemplateCriterionResponse.model_validate(criterion, from_attributes=True)
                for criterion in created_criteria
            ],
        )
    except DomainError as exc:
        _fail(db, exc)


@router.get("/templates/matches/{asset_id}", response_model=list[MaintenanceTemplateResponse])
def matching_templates(
    asset_id: UUID,
    service: MaintenanceService = Depends(get_maintenance_service),
) -> list[MaintenanceTemplateResponse]:
    return [_template_response(item) for item in service.matching_templates(asset_id)]


@router.post("/plans/{asset_id}/apply-template", response_model=MaintenancePlanResponse)
def apply_template(
    asset_id: UUID,
    payload: MaintenanceTemplateApplyRequest,
    service: MaintenanceService = Depends(get_maintenance_service),
    db: Session = Depends(get_db),
) -> MaintenancePlanResponse:
    try:
        service.apply_template(asset_id, payload.template_id)
        db.commit()
        return get_plan(asset_id, service)
    except DomainError as exc:
        _fail(db, exc)


@router.post("/plans/{asset_id}/copy", response_model=MaintenancePlanResponse)
def copy_plan(
    asset_id: UUID,
    payload: MaintenancePlanCopyRequest,
    service: MaintenanceService = Depends(get_maintenance_service),
    db: Session = Depends(get_db),
) -> MaintenancePlanResponse:
    try:
        service.copy_plan(asset_id, payload.source_asset_id)
        db.commit()
        return get_plan(asset_id, service)
    except DomainError as exc:
        _fail(db, exc)
