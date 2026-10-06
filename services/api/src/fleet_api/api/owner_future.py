from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import (
    get_app_settings,
    get_asset_document_service,
    get_maintenance_service,
    get_object_storage,
    require_owner_admin,
)
from fleet_api.core.config import Settings
from fleet_api.core.features import FutureFeature, feature_registry, require_feature
from fleet_api.db.models import (
    AssetDocumentPolicy,
    AssetDocumentRevision,
    MaintenanceCriterion,
    MaintenanceRecord,
    MaintenanceSchedule,
    MaintenanceWorkOrder,
)
from fleet_api.db.session import get_db
from fleet_api.domain.asset_documents import (
    AssetComplianceView,
    AssetDocumentService,
    AssetDocumentView,
)
from fleet_api.domain.enums import (
    AssetDocumentExpiryStatus,
    AssetOwnershipType,
    FleetAssetType,
    MaintenanceBasis,
    MaintenanceCriterionBasis,
    MaintenanceDueStatus,
    MaintenanceScheduleStatus,
    MaintenanceWorkOrderStatus,
)
from fleet_api.domain.errors import ConflictError, DomainError, NotFoundError
from fleet_api.domain.maintenance import MaintenanceScheduleView, MaintenanceService
from fleet_api.storage.objects import ObjectStorage

maintenance_router = APIRouter(
    prefix="/api/v1/owner/maintenance",
    tags=["owner-maintenance-future"],
    dependencies=[Depends(require_feature(FutureFeature.MAINTENANCE))],
)
document_router = APIRouter(
    prefix="/api/v1/owner/asset-documents",
    tags=["owner-asset-documents-future"],
    dependencies=[Depends(require_feature(FutureFeature.ASSET_DOCUMENTS))],
)
feature_router = APIRouter(prefix="/api/v1/owner", tags=["owner-future-features"])


@feature_router.get("/future-features")
def future_features(
    settings: Annotated[Settings, Depends(get_app_settings)],
    _: Annotated[object, Depends(require_owner_admin)],
) -> dict[str, bool]:
    registry = feature_registry(settings)
    return {
        "maintenance": registry.maintenance_enabled,
        "asset_documents": registry.asset_documents_enabled,
        "notifications": registry.notifications_enabled,
        "telematics": registry.telematics_enabled,
        "fuel_integrations": registry.fuel_integrations_enabled,
        "toll_expenses": registry.toll_expenses_enabled,
        "multi_meter": registry.multi_meter_enabled,
        "payroll": registry.payroll_enabled,
        "attendance_location": registry.attendance_location_enabled,
    }


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


class MaintenanceScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: UUID
    maintenance_type: str = Field(min_length=1, max_length=64)
    custom_label: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    interval_basis: MaintenanceBasis
    interval_value: Decimal = Field(gt=0)
    warning_threshold: Decimal = Field(default=Decimal("0"), ge=0)
    last_service_meter: Decimal | None = Field(default=None, ge=0)
    last_service_date: date | None = None
    notes: str | None = Field(default=None, max_length=4000)


class MaintenanceScheduleResponse(BaseModel):
    id: UUID
    asset_id: UUID
    maintenance_type: str
    custom_label: str | None
    description: str | None
    interval_basis: MaintenanceBasis
    interval_value: Decimal
    warning_threshold: Decimal
    last_service_meter: Decimal | None
    last_service_date: date | None
    next_due_meter: Decimal | None
    next_due_date: date | None
    status: MaintenanceScheduleStatus
    current_meter: Decimal | None = None
    due_status: MaintenanceDueStatus = MaintenanceDueStatus.UNKNOWN
    notes: str | None
    created_at: datetime
    updated_at: datetime
    criteria: list[MaintenanceCriterionResponse] = Field(default_factory=list)


class MaintenanceCriterionResponse(BaseModel):
    id: UUID
    basis: MaintenanceCriterionBasis
    interval_value: Decimal
    warning_threshold: Decimal
    last_baseline_value: Decimal | None
    last_baseline_date: date | None
    next_due_value: Decimal | None
    next_due_date: date | None
    current_value: Decimal | None = None
    due_status: MaintenanceDueStatus = MaintenanceDueStatus.UNKNOWN


class MaintenanceCriterionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    basis: MaintenanceCriterionBasis
    interval_value: Decimal = Field(gt=0)
    warning_threshold: Decimal = Field(default=Decimal("0"), ge=0)
    last_baseline_value: Decimal | None = Field(default=None, ge=0)
    last_baseline_date: date | None = None


class MaintenanceRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    performed_on: date
    meter_value: Decimal | None = Field(default=None, ge=0)
    odometer_km: Decimal | None = Field(default=None, ge=0)
    hour_meter_hours: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=4000)


class MaintenanceRecordResponse(BaseModel):
    id: UUID
    schedule_id: UUID
    asset_id: UUID
    work_order_id: UUID | None
    performed_on: date
    meter_value: Decimal | None
    completion_odometer_km: Decimal | None
    completion_hour_meter: Decimal | None
    notes: str | None
    vendor_name: str | None
    labor_cost: Decimal
    parts_cost: Decimal
    other_cost: Decimal
    created_at: datetime


def _schedule_response(
    schedule: MaintenanceSchedule, view: MaintenanceScheduleView | None = None
) -> MaintenanceScheduleResponse:
    response = MaintenanceScheduleResponse.model_validate(schedule, from_attributes=True)
    if view is not None:
        response.current_meter = view.current_meter
        response.due_status = view.due_status
        response.criteria = [
            MaintenanceCriterionResponse(
                id=item.criterion.id,
                basis=item.criterion.basis,
                interval_value=item.criterion.interval_value,
                warning_threshold=item.criterion.warning_threshold,
                last_baseline_value=item.criterion.last_baseline_value,
                last_baseline_date=item.criterion.last_baseline_date,
                next_due_value=item.criterion.next_due_value,
                next_due_date=item.criterion.next_due_date,
                current_value=item.current_value,
                due_status=item.due_status,
            )
            for item in view.criteria
        ]
    return response


def _record_response(record: MaintenanceRecord) -> MaintenanceRecordResponse:
    return MaintenanceRecordResponse.model_validate(record, from_attributes=True)


@maintenance_router.get("/schedules", response_model=list[MaintenanceScheduleResponse])
def list_maintenance_schedules(
    service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
    asset_id: UUID | None = None,
    as_of: date = Query(default_factory=date.today),
) -> list[MaintenanceScheduleResponse]:
    return [
        _schedule_response(item.schedule, item)
        for item in service.list_schedule_views(asset_id=asset_id, as_of=as_of)
    ]


@maintenance_router.post(
    "/schedules",
    response_model=MaintenanceScheduleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_maintenance_schedule(
    payload: MaintenanceScheduleCreate,
    service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
    db: Annotated[Session, Depends(get_db)],
) -> MaintenanceScheduleResponse:
    try:
        schedule = service.create_schedule(**payload.model_dump())
        db.commit()
        db.refresh(schedule)
        return _schedule_response(schedule)
    except DomainError as exc:
        _fail(db, exc)


@maintenance_router.post(
    "/schedules/{schedule_id}/criteria",
    response_model=MaintenanceCriterionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_feature(FutureFeature.MULTI_METER))],
)
def add_maintenance_criterion(
    schedule_id: UUID,
    payload: MaintenanceCriterionCreate,
    service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
    db: Annotated[Session, Depends(get_db)],
) -> MaintenanceCriterionResponse:
    try:
        item: MaintenanceCriterion = service.add_criterion(schedule_id, **payload.model_dump())
        db.commit()
        db.refresh(item)
        return MaintenanceCriterionResponse.model_validate(item, from_attributes=True)
    except DomainError as exc:
        _fail(db, exc)


@maintenance_router.get(
    "/schedules/{schedule_id}/records",
    response_model=list[MaintenanceRecordResponse],
)
def list_maintenance_records(
    schedule_id: UUID,
    service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
    db: Annotated[Session, Depends(get_db)],
) -> list[MaintenanceRecordResponse]:
    try:
        return [_record_response(item) for item in service.list_records(schedule_id)]
    except DomainError as exc:
        _fail(db, exc)


@maintenance_router.post(
    "/schedules/{schedule_id}/records",
    response_model=MaintenanceRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_maintenance_record(
    schedule_id: UUID,
    payload: MaintenanceRecordCreate,
    service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
    db: Annotated[Session, Depends(get_db)],
) -> MaintenanceRecordResponse:
    try:
        record = service.add_record(schedule_id=schedule_id, **payload.model_dump())
        db.commit()
        db.refresh(record)
        return _record_response(record)
    except DomainError as exc:
        _fail(db, exc)


class MaintenanceScheduleStatusUpdate(BaseModel):
    status: MaintenanceScheduleStatus


@maintenance_router.patch(
    "/schedules/{schedule_id}/status", response_model=MaintenanceScheduleResponse
)
def update_maintenance_schedule_status(
    schedule_id: UUID,
    payload: MaintenanceScheduleStatusUpdate,
    service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
    db: Annotated[Session, Depends(get_db)],
) -> MaintenanceScheduleResponse:
    try:
        item = service.set_schedule_status(schedule_id, payload.status)
        db.commit()
        db.refresh(item)
        return _schedule_response(item)
    except DomainError as exc:
        _fail(db, exc)


class MaintenanceWorkOrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: UUID
    schedule_id: UUID | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    vendor_name: str | None = Field(default=None, max_length=200)
    scheduled_for: date | None = None
    notes: str | None = Field(default=None, max_length=4000)


class MaintenanceWorkOrderResponse(BaseModel):
    id: UUID
    asset_id: UUID
    schedule_id: UUID | None
    title: str
    description: str | None
    status: MaintenanceWorkOrderStatus
    vendor_name: str | None
    scheduled_for: date | None
    started_at: datetime | None
    completed_at: datetime | None
    completion_meter: Decimal | None
    completion_odometer_km: Decimal | None
    completion_hour_meter: Decimal | None
    labor_cost: Decimal
    parts_cost: Decimal
    other_cost: Decimal
    notes: str | None
    created_at: datetime
    updated_at: datetime


class MaintenanceWorkOrderStatusUpdate(BaseModel):
    status: MaintenanceWorkOrderStatus


class MaintenanceWorkOrderComplete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    performed_on: date
    meter_value: Decimal | None = Field(default=None, ge=0)
    odometer_km: Decimal | None = Field(default=None, ge=0)
    hour_meter_hours: Decimal | None = Field(default=None, ge=0)
    vendor_name: str | None = Field(default=None, max_length=200)
    labor_cost: Decimal = Field(default=Decimal("0"), ge=0)
    parts_cost: Decimal = Field(default=Decimal("0"), ge=0)
    other_cost: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = Field(default=None, max_length=4000)


class MaintenanceCompletionResponse(BaseModel):
    work_order: MaintenanceWorkOrderResponse
    record: MaintenanceRecordResponse


def _work_order_response(item: MaintenanceWorkOrder) -> MaintenanceWorkOrderResponse:
    return MaintenanceWorkOrderResponse.model_validate(item, from_attributes=True)


@maintenance_router.get("/work-orders", response_model=list[MaintenanceWorkOrderResponse])
def list_maintenance_work_orders(
    service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
    work_order_status: MaintenanceWorkOrderStatus | None = Query(default=None, alias="status"),
) -> list[MaintenanceWorkOrderResponse]:
    return [
        _work_order_response(item) for item in service.list_work_orders(status=work_order_status)
    ]


@maintenance_router.post(
    "/work-orders",
    response_model=MaintenanceWorkOrderResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_maintenance_work_order(
    payload: MaintenanceWorkOrderCreate,
    service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
    db: Annotated[Session, Depends(get_db)],
) -> MaintenanceWorkOrderResponse:
    try:
        item = service.create_work_order(**payload.model_dump())
        db.commit()
        db.refresh(item)
        return _work_order_response(item)
    except DomainError as exc:
        _fail(db, exc)


@maintenance_router.patch(
    "/work-orders/{work_order_id}/status", response_model=MaintenanceWorkOrderResponse
)
def update_maintenance_work_order_status(
    work_order_id: UUID,
    payload: MaintenanceWorkOrderStatusUpdate,
    service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
    db: Annotated[Session, Depends(get_db)],
) -> MaintenanceWorkOrderResponse:
    try:
        item = service.update_work_order_status(work_order_id, payload.status)
        db.commit()
        db.refresh(item)
        return _work_order_response(item)
    except DomainError as exc:
        _fail(db, exc)


@maintenance_router.post(
    "/work-orders/{work_order_id}/complete", response_model=MaintenanceCompletionResponse
)
def complete_maintenance_work_order(
    work_order_id: UUID,
    payload: MaintenanceWorkOrderComplete,
    service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
    db: Annotated[Session, Depends(get_db)],
) -> MaintenanceCompletionResponse:
    try:
        work_order, record = service.complete_work_order(work_order_id, **payload.model_dump())
        db.commit()
        db.refresh(work_order)
        db.refresh(record)
        return MaintenanceCompletionResponse(
            work_order=_work_order_response(work_order), record=_record_response(record)
        )
    except DomainError as exc:
        _fail(db, exc)


@maintenance_router.get("/history", response_model=list[MaintenanceRecordResponse])
def list_all_maintenance_records(
    service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
) -> list[MaintenanceRecordResponse]:
    return [_record_response(item) for item in service.list_records()]


def _xlsx_response(workbook: Workbook, name: str) -> StreamingResponse:
    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@maintenance_router.get("/export.xlsx", response_class=StreamingResponse)
def export_maintenance(
    service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
    as_of: date = Query(default_factory=date.today),
) -> StreamingResponse:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Maintenance"
    sheet.append(
        [
            "Asset ID",
            "Maintenance Type",
            "Basis",
            "Interval",
            "Current Meter",
            "Next Due Meter",
            "Next Due Date",
            "Due Status",
            "Schedule Status",
        ]
    )
    for view in service.list_schedule_views(as_of=as_of):
        item = view.schedule
        sheet.append(
            [
                str(item.asset_id),
                item.custom_label or item.maintenance_type,
                item.interval_basis.value,
                float(item.interval_value),
                float(view.current_meter) if view.current_meter is not None else None,
                float(item.next_due_meter) if item.next_due_meter is not None else None,
                item.next_due_date,
                view.due_status.value,
                item.status.value,
            ]
        )
    return _xlsx_response(workbook, "maintenance.xlsx")


class DocumentEvidenceResponse(BaseModel):
    upload_id: UUID
    evidence_object_id: UUID
    content_type: str
    size_bytes: int


class AssetDocumentRevisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_object_id: UUID
    document_number: str | None = Field(default=None, max_length=120)
    issue_date: date | None = None
    expiry_date: date | None = None
    issuer: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)


class AssetDocumentCreate(AssetDocumentRevisionInput):
    asset_id: UUID
    document_type: str = Field(min_length=1, max_length=64)
    expiry_warning_days: int = Field(default=30, ge=0, le=3650)


class AssetDocumentResponse(BaseModel):
    id: UUID
    asset_id: UUID
    document_type: str
    expiry_warning_days: int
    revision_number: int
    document_number: str | None
    issue_date: date | None
    expiry_date: date | None
    issuer: str | None
    notes: str | None
    evidence_object_id: UUID
    expiry_status: AssetDocumentExpiryStatus
    created_at: datetime


class AssetDocumentRevisionResponse(BaseModel):
    id: UUID
    revision_number: int
    document_number: str | None
    issue_date: date | None
    expiry_date: date | None
    issuer: str | None
    notes: str | None
    evidence_object_id: UUID
    created_at: datetime


class AssetDocumentPolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_type: FleetAssetType
    ownership_type: AssetOwnershipType | None = None
    document_type: str = Field(min_length=1, max_length=64)
    required: bool = True
    expiry_warning_days: int = Field(default=30, ge=0, le=3650)


class AssetDocumentPolicyResponse(BaseModel):
    id: UUID
    asset_type: FleetAssetType
    ownership_type: AssetOwnershipType | None
    document_type: str
    required: bool
    expiry_warning_days: int
    created_at: datetime


class AssetComplianceResponse(BaseModel):
    asset_id: UUID
    asset_code: str
    asset_type: FleetAssetType
    ownership_type: AssetOwnershipType
    policy_id: UUID
    document_type: str
    required: bool
    status: AssetDocumentExpiryStatus
    document_id: UUID | None
    revision_number: int | None
    expiry_date: date | None


def _document_response(view: AssetDocumentView) -> AssetDocumentResponse:
    document, revision = view.document, view.revision
    return AssetDocumentResponse(
        id=document.id,
        asset_id=document.asset_id,
        document_type=document.document_type,
        expiry_warning_days=document.expiry_warning_days,
        revision_number=revision.revision_number,
        document_number=revision.document_number,
        issue_date=revision.issue_date,
        expiry_date=revision.expiry_date,
        issuer=revision.issuer,
        notes=revision.notes,
        evidence_object_id=revision.evidence_object_id,
        expiry_status=view.expiry_status,
        created_at=document.created_at,
    )


def _revision_response(revision: AssetDocumentRevision) -> AssetDocumentRevisionResponse:
    return AssetDocumentRevisionResponse.model_validate(revision, from_attributes=True)


def _policy_response(policy: AssetDocumentPolicy) -> AssetDocumentPolicyResponse:
    return AssetDocumentPolicyResponse.model_validate(policy, from_attributes=True)


def _compliance_response(view: AssetComplianceView) -> AssetComplianceResponse:
    return AssetComplianceResponse(
        asset_id=view.asset.id,
        asset_code=view.asset.asset_code,
        asset_type=view.asset.asset_type,
        ownership_type=view.asset.ownership_type,
        policy_id=view.policy.id,
        document_type=view.policy.document_type,
        required=view.policy.required,
        status=view.status,
        document_id=view.document.id if view.document else None,
        revision_number=view.revision.revision_number if view.revision else None,
        expiry_date=view.revision.expiry_date if view.revision else None,
    )


@document_router.get("/policies", response_model=list[AssetDocumentPolicyResponse])
def list_document_policies(
    service: Annotated[AssetDocumentService, Depends(get_asset_document_service)],
) -> list[AssetDocumentPolicyResponse]:
    return [_policy_response(item) for item in service.list_policies()]


@document_router.put("/policies", response_model=AssetDocumentPolicyResponse)
def upsert_document_policy(
    payload: AssetDocumentPolicyInput,
    service: Annotated[AssetDocumentService, Depends(get_asset_document_service)],
    db: Annotated[Session, Depends(get_db)],
) -> AssetDocumentPolicyResponse:
    try:
        item = service.upsert_policy(**payload.model_dump())
        db.commit()
        db.refresh(item)
        return _policy_response(item)
    except DomainError as exc:
        _fail(db, exc)


@document_router.get("/compliance", response_model=list[AssetComplianceResponse])
def asset_document_compliance(
    service: Annotated[AssetDocumentService, Depends(get_asset_document_service)],
    db: Annotated[Session, Depends(get_db)],
    as_of: date = Query(default_factory=date.today),
    asset_id: UUID | None = None,
) -> list[AssetComplianceResponse]:
    try:
        return [
            _compliance_response(item)
            for item in service.compliance_matrix(as_of=as_of, asset_id=asset_id)
        ]
    except DomainError as exc:
        _fail(db, exc)


@document_router.get("/export.xlsx", response_class=StreamingResponse)
def export_document_compliance(
    service: Annotated[AssetDocumentService, Depends(get_asset_document_service)],
    as_of: date = Query(default_factory=date.today),
) -> StreamingResponse:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Compliance"
    sheet.append(
        [
            "Asset Code",
            "Asset Type",
            "Ownership",
            "Document Type",
            "Required",
            "Status",
            "Expiry Date",
            "Revision",
        ]
    )
    for view in service.compliance_matrix(as_of=as_of):
        sheet.append(
            [
                view.asset.asset_code,
                view.asset.asset_type.value,
                view.asset.ownership_type.value,
                view.policy.document_type,
                view.policy.required,
                view.status.value,
                view.revision.expiry_date if view.revision else None,
                view.revision.revision_number if view.revision else None,
            ]
        )
    return _xlsx_response(workbook, "asset-compliance.xlsx")


@document_router.post(
    "/evidence",
    response_model=DocumentEvidenceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document_evidence(
    upload_id: UUID,
    file: Annotated[UploadFile, File(...)],
    service: Annotated[AssetDocumentService, Depends(get_asset_document_service)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    db: Annotated[Session, Depends(get_db)],
) -> DocumentEvidenceResponse:
    try:
        content = await file.read(settings.evidence_max_bytes + 1)
        evidence = service.upload(
            storage,
            settings,
            upload_id=upload_id,
            content_type=file.content_type or "",
            content=content,
        )
        db.commit()
        return DocumentEvidenceResponse(
            upload_id=upload_id,
            evidence_object_id=evidence.id,
            content_type=evidence.content_type,
            size_bytes=evidence.size_bytes,
        )
    except DomainError as exc:
        _fail(db, exc)


@document_router.get("", response_model=list[AssetDocumentResponse])
def list_asset_documents(
    service: Annotated[AssetDocumentService, Depends(get_asset_document_service)],
    db: Annotated[Session, Depends(get_db)],
    asset_id: UUID | None = None,
    as_of: date = Query(default_factory=date.today),
) -> list[AssetDocumentResponse]:
    try:
        return [
            _document_response(view)
            for view in service.list_documents(asset_id=asset_id, as_of=as_of)
        ]
    except DomainError as exc:
        _fail(db, exc)


@document_router.post(
    "",
    response_model=AssetDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_asset_document(
    payload: AssetDocumentCreate,
    service: Annotated[AssetDocumentService, Depends(get_asset_document_service)],
    db: Annotated[Session, Depends(get_db)],
    as_of: date = Query(default_factory=date.today),
) -> AssetDocumentResponse:
    try:
        values = payload.model_dump()
        values["expiry_date_value"] = values.pop("expiry_date")
        view = service.create(as_of=as_of, **values)
        db.commit()
        return _document_response(view)
    except DomainError as exc:
        _fail(db, exc)


@document_router.post(
    "/{document_id}/revisions",
    response_model=AssetDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def replace_asset_document(
    document_id: UUID,
    payload: AssetDocumentRevisionInput,
    service: Annotated[AssetDocumentService, Depends(get_asset_document_service)],
    db: Annotated[Session, Depends(get_db)],
    as_of: date = Query(default_factory=date.today),
) -> AssetDocumentResponse:
    try:
        values = payload.model_dump()
        values["expiry_date_value"] = values.pop("expiry_date")
        view = service.replace(document_id, as_of=as_of, **values)
        db.commit()
        return _document_response(view)
    except DomainError as exc:
        _fail(db, exc)


@document_router.get(
    "/{document_id}/revisions",
    response_model=list[AssetDocumentRevisionResponse],
)
def list_asset_document_revisions(
    document_id: UUID,
    service: Annotated[AssetDocumentService, Depends(get_asset_document_service)],
    db: Annotated[Session, Depends(get_db)],
) -> list[AssetDocumentRevisionResponse]:
    try:
        return [_revision_response(item) for item in service.revisions(document_id)]
    except DomainError as exc:
        _fail(db, exc)


@document_router.get("/{document_id}/file", response_class=Response)
def read_asset_document_file(
    document_id: UUID,
    service: Annotated[AssetDocumentService, Depends(get_asset_document_service)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    try:
        evidence = service.latest_private_evidence(document_id)
        content, content_type = storage.read_private(object_key=evidence.object_key)
        return Response(
            content=content,
            media_type=content_type,
            headers={
                "Cache-Control": "private, no-store",
                "Content-Disposition": f'attachment; filename="asset-document-{document_id}"',
            },
        )
    except DomainError as exc:
        _fail(db, exc)
