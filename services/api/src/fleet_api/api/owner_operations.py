from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_owner_operation_planner
from fleet_api.api.schemas import (
    OwnerOperationExecuteRequest,
    OwnerOperationItemResponse,
    OwnerOperationPlanResponse,
    OwnerOperationRequest,
    OwnerOperationResultResponse,
)
from fleet_api.db.session import get_db
from fleet_api.domain.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    RoleViolationError,
    TenantConsistencyError,
)
from fleet_api.domain.owner_operations import (
    OperationItem,
    OwnerOperationIntent,
    OwnerOperationPlan,
    OwnerOperationPlanner,
    SiteAssetResolution,
)

router = APIRouter(prefix="/api/v1/owner/operations", tags=["owner-operations"])


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


def _intent(payload: OwnerOperationRequest) -> OwnerOperationIntent:
    return OwnerOperationIntent(
        action=payload.action,
        asset_id=payload.asset_id,
        person_membership_id=payload.person_membership_id,
        site_id=payload.site_id,
        target_site_id=payload.target_site_id,
        driver_membership_id=payload.driver_membership_id,
        selected_site_ids=tuple(payload.selected_site_ids),
        selected_supervisor_ids=tuple(payload.selected_supervisor_ids),
        selected_asset_ids=tuple(payload.selected_asset_ids),
        asset_resolutions=tuple(
            SiteAssetResolution(
                asset_id=item.asset_id,
                action=item.action,
                target_site_id=item.target_site_id,
                assignment_action=item.assignment_action,
            )
            for item in payload.asset_resolutions
        ),
        assignment_action=payload.assignment_action,
        activate_membership=payload.activate_membership,
        regular_duty_minutes=payload.regular_duty_minutes,
    )


def _item_response(item: OperationItem) -> OwnerOperationItemResponse:
    return OwnerOperationItemResponse(
        kind=item.kind,
        id=item.id,
        label=item.label,
        status=item.status,
        details=item.details,
    )


def _plan_response(plan: OwnerOperationPlan) -> OwnerOperationPlanResponse:
    return OwnerOperationPlanResponse(
        action=plan.action,
        state_token=plan.state_token,
        title=plan.title,
        summary=plan.summary,
        current_state=[_item_response(item) for item in plan.current_state],
        dependencies=[_item_response(item) for item in plan.dependencies],
        warnings=plan.warnings,
        allowed_resolutions=plan.allowed_resolutions,
        blocked_reasons=plan.blocked_reasons,
        planned_changes=plan.planned_changes,
        can_execute=plan.can_execute,
    )


@router.post("/preview", response_model=OwnerOperationPlanResponse)
def preview_owner_operation(
    payload: OwnerOperationRequest,
    planner: OwnerOperationPlanner = Depends(get_owner_operation_planner),
) -> OwnerOperationPlanResponse:
    try:
        return _plan_response(planner.preview(_intent(payload)))
    except DomainError as exc:
        _fail(planner.session, exc)


@router.post("/execute", response_model=OwnerOperationResultResponse)
def execute_owner_operation(
    payload: OwnerOperationExecuteRequest,
    planner: OwnerOperationPlanner = Depends(get_owner_operation_planner),
    db: Session = Depends(get_db),
) -> OwnerOperationResultResponse:
    try:
        result = planner.execute(
            _intent(payload),
            expected_state_token=payload.state_token,
        )
        db.commit()
        return OwnerOperationResultResponse(
            action=result.action,
            completed_changes=result.completed_changes,
            message=result.message,
        )
    except DomainError as exc:
        _fail(db, exc)
