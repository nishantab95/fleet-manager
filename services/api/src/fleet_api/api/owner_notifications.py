from __future__ import annotations

from datetime import datetime
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_in_app_notification_service
from fleet_api.core.features import FutureFeature, require_feature
from fleet_api.db.models import InAppNotification
from fleet_api.db.session import get_db
from fleet_api.domain.enums import NotificationCategory, NotificationState
from fleet_api.domain.errors import DomainError, NotFoundError
from fleet_api.domain.notifications import InAppNotificationService

router = APIRouter(
    prefix="/api/v1/owner/notifications",
    tags=["owner-notifications"],
    dependencies=[Depends(require_feature(FutureFeature.NOTIFICATIONS))],
)


class NotificationResponse(BaseModel):
    id: UUID
    category: NotificationCategory
    title: str
    body: str
    state: NotificationState
    deep_link: dict[str, str] | None
    read_at: datetime | None
    acknowledged_at: datetime | None
    created_at: datetime


class NotificationStateInput(BaseModel):
    state: NotificationState


def _response(item: InAppNotification) -> NotificationResponse:
    return NotificationResponse.model_validate(item, from_attributes=True)


def _fail(db: Session, exc: DomainError) -> NoReturn:
    db.rollback()
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, NotFoundError) else 422
    raise HTTPException(status_code=code, detail={"code": "NOT_FOUND", "message": str(exc)})


@router.get("", response_model=list[NotificationResponse])
def list_notifications(
    service: Annotated[InAppNotificationService, Depends(get_in_app_notification_service)],
    db: Annotated[Session, Depends(get_db)],
    unread_only: bool = False,
) -> list[NotificationResponse]:
    service.evaluate()
    db.commit()
    return [_response(item) for item in service.list_mine(unread_only=unread_only)]


@router.get("/unread-count")
def unread_count(
    service: Annotated[InAppNotificationService, Depends(get_in_app_notification_service)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, int]:
    service.evaluate()
    db.commit()
    return {"unread_count": service.unread_count()}


@router.patch("/{notification_id}", response_model=NotificationResponse)
def mark_notification(
    notification_id: UUID,
    payload: NotificationStateInput,
    service: Annotated[InAppNotificationService, Depends(get_in_app_notification_service)],
    db: Annotated[Session, Depends(get_db)],
) -> NotificationResponse:
    try:
        item = service.mark(notification_id, payload.state)
        db.commit()
        db.refresh(item)
        return _response(item)
    except DomainError as exc:
        _fail(db, exc)


@router.post("/read-all")
def mark_all_read(
    service: Annotated[InAppNotificationService, Depends(get_in_app_notification_service)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, int]:
    count = service.mark_all_read()
    db.commit()
    return {"updated": count}
