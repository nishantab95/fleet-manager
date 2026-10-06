from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from io import BytesIO
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook  # type: ignore[import-untyped]
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_fuel_integration_service
from fleet_api.core.features import FutureFeature, require_feature
from fleet_api.db.models import ExternalFuelTransaction, FuelImportBatch, FuelReconciliation
from fleet_api.db.session import get_db
from fleet_api.domain.enums import (
    FuelImportBatchStatus,
    FuelImportRowStatus,
    FuelReconciliationStatus,
    FuelSourceType,
)
from fleet_api.domain.errors import ConflictError, DomainError, NotFoundError
from fleet_api.domain.fuel_integrations import (
    FuelIntegrationService,
    fuel_csv_template,
    spreadsheet_safe,
)

router = APIRouter(
    prefix="/api/v1/owner/fuel",
    tags=["owner-fuel-integrations"],
    dependencies=[Depends(require_feature(FutureFeature.FUEL_INTEGRATIONS))],
)


def _fail(db: Session, exc: DomainError) -> NoReturn:
    db.rollback()
    if isinstance(exc, NotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, ConflictError):
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(status_code=code, detail={"code": "FUEL_ERROR", "message": str(exc)})


class BatchResponse(BaseModel):
    id: UUID
    file_name: str
    source_name: str
    status: FuelImportBatchStatus
    total_rows: int
    imported_rows: int
    rejected_rows: int
    created_at: datetime


class TransactionResponse(BaseModel):
    id: UUID
    batch_id: UUID
    row_number: int
    row_status: FuelImportRowStatus
    error_message: str | None
    asset_id: UUID | None
    asset_identifier: str
    source_type: FuelSourceType
    source_name: str
    external_transaction_id: str
    occurred_at: datetime | None
    litres: Decimal | None


class ImportResponse(BaseModel):
    batch: BatchResponse
    rows: list[TransactionResponse]


class ReconcileInput(BaseModel):
    tolerance_litres: Decimal = Field(default=Decimal("1.000"), ge=0)
    time_window_minutes: int = Field(default=720, ge=1, le=10080)


class ResolveInput(BaseModel):
    reason: str = Field(min_length=1, max_length=4000)


class ReconciliationResponse(BaseModel):
    id: UUID
    external_transaction_id: UUID
    operational_event_id: UUID | None
    status: FuelReconciliationStatus
    tolerance_litres: Decimal
    difference_litres: Decimal | None
    manually_resolved: bool
    resolution_reason: str | None
    resolved_by: UUID | None
    created_at: datetime
    updated_at: datetime


def _batch(item: FuelImportBatch) -> BatchResponse:
    return BatchResponse.model_validate(item, from_attributes=True)


def _transaction(item: ExternalFuelTransaction) -> TransactionResponse:
    return TransactionResponse.model_validate(item, from_attributes=True)


def _reconciliation(item: FuelReconciliation) -> ReconciliationResponse:
    return ReconciliationResponse.model_validate(item, from_attributes=True)


@router.get("/template.csv", response_class=Response)
def download_template() -> Response:
    return Response(
        content=fuel_csv_template(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="fuel-import-template.csv"'},
    )


@router.post("/imports", response_model=ImportResponse, status_code=status.HTTP_201_CREATED)
async def import_fuel_csv(
    file: Annotated[UploadFile, File(...)],
    source_name: Annotated[str, Form(min_length=1, max_length=120)],
    service: Annotated[FuelIntegrationService, Depends(get_fuel_integration_service)],
    db: Annotated[Session, Depends(get_db)],
) -> ImportResponse:
    try:
        content = await file.read(5_000_001)
        result = service.import_csv(
            file_name=file.filename or "fuel-import.csv",
            source_name=source_name,
            content=content,
        )
        db.commit()
        return ImportResponse(
            batch=_batch(result.batch), rows=[_transaction(item) for item in result.rows]
        )
    except DomainError as exc:
        _fail(db, exc)


@router.get("/imports", response_model=list[BatchResponse])
def list_imports(
    service: Annotated[FuelIntegrationService, Depends(get_fuel_integration_service)],
) -> list[BatchResponse]:
    return [_batch(item) for item in service.list_batches()]


@router.get("/transactions", response_model=list[TransactionResponse])
def list_transactions(
    service: Annotated[FuelIntegrationService, Depends(get_fuel_integration_service)],
) -> list[TransactionResponse]:
    return [_transaction(item) for item in service.list_transactions()]


@router.post("/imports/{batch_id}/reconcile", response_model=list[ReconciliationResponse])
def reconcile_import(
    batch_id: UUID,
    payload: ReconcileInput,
    service: Annotated[FuelIntegrationService, Depends(get_fuel_integration_service)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ReconciliationResponse]:
    try:
        items = service.reconcile_batch(batch_id, **payload.model_dump())
        db.commit()
        return [_reconciliation(item) for item in items]
    except DomainError as exc:
        _fail(db, exc)


@router.get("/reconciliations", response_model=list[ReconciliationResponse])
def list_reconciliations(
    service: Annotated[FuelIntegrationService, Depends(get_fuel_integration_service)],
) -> list[ReconciliationResponse]:
    return [_reconciliation(item) for item in service.list_reconciliations()]


@router.post("/reconciliations/{reconciliation_id}/resolve", response_model=ReconciliationResponse)
def resolve_reconciliation(
    reconciliation_id: UUID,
    payload: ResolveInput,
    service: Annotated[FuelIntegrationService, Depends(get_fuel_integration_service)],
    db: Annotated[Session, Depends(get_db)],
) -> ReconciliationResponse:
    try:
        item = service.resolve(reconciliation_id, reason=payload.reason)
        db.commit()
        db.refresh(item)
        return _reconciliation(item)
    except DomainError as exc:
        _fail(db, exc)


@router.get("/export.xlsx", response_class=StreamingResponse)
def export_fuel(
    service: Annotated[FuelIntegrationService, Depends(get_fuel_integration_service)],
) -> StreamingResponse:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Fuel Transactions"
    sheet.append(
        [
            "External ID",
            "Source",
            "Asset Identifier",
            "Occurred At",
            "Litres",
            "Row Status",
            "Error",
        ]
    )
    for item in service.list_transactions():
        sheet.append(
            [
                spreadsheet_safe(item.external_transaction_id),
                spreadsheet_safe(item.source_name),
                spreadsheet_safe(item.asset_identifier),
                item.occurred_at,
                float(item.litres) if item.litres is not None else None,
                item.row_status.value,
                spreadsheet_safe(item.error_message or ""),
            ]
        )
    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="fuel-reconciliation.xlsx"'},
    )
