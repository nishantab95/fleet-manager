from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_current_session, require_driver, require_owner_admin
from fleet_api.auth.service import AuthContext
from fleet_api.core.features import FutureFeature, require_feature
from fleet_api.db.models import (
    AttendanceLocationSetting,
    AttendanceLocationSnapshot,
    CompensationProfile,
    PayrollLine,
    PayrollPeriod,
)
from fleet_api.db.session import get_db
from fleet_api.domain.attendance_location import (
    AttendanceLocationService,
    LocationSnapshotView,
)
from fleet_api.domain.enums import (
    AttendanceCalculationState,
    AttendanceConfidence,
    LocationSnapshotSource,
    LocationSnapshotStatus,
    PayBasis,
    PayrollPeriodStatus,
)
from fleet_api.domain.errors import ConflictError, DomainError, NotFoundError
from fleet_api.domain.workforce import AttendanceDay, WorkforceService

workforce_router = APIRouter(
    prefix="/api/v1/owner/workforce",
    tags=["owner-workforce"],
    dependencies=[
        Depends(require_feature(FutureFeature.PAYROLL)),
        Depends(require_owner_admin),
    ],
)
location_owner_router = APIRouter(
    prefix="/api/v1/owner/attendance-location",
    tags=["owner-attendance-location"],
    dependencies=[
        Depends(require_feature(FutureFeature.ATTENDANCE_LOCATION)),
        Depends(require_owner_admin),
    ],
)
location_driver_router = APIRouter(
    prefix="/api/v1/driver/attendance-location",
    tags=["driver-attendance-location"],
    dependencies=[
        Depends(require_feature(FutureFeature.ATTENDANCE_LOCATION)),
        Depends(require_driver),
    ],
)


def _fail(db: Session, exc: DomainError) -> NoReturn:
    db.rollback()
    if isinstance(exc, NotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, ConflictError):
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(
        status_code=code,
        detail={"code": "WORKFORCE_ERROR", "message": str(exc)},
    ) from exc


def _workforce(
    db: Annotated[Session, Depends(get_db)],
    context: Annotated[AuthContext, Depends(require_owner_admin)],
) -> WorkforceService:
    return WorkforceService(db, context)


def _location(
    db: Annotated[Session, Depends(get_db)],
    context: Annotated[AuthContext, Depends(get_current_session)],
) -> AttendanceLocationService:
    return AttendanceLocationService(db, context)


class CompensationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    membership_id: UUID
    pay_basis: PayBasis
    base_amount: Decimal = Field(ge=0)
    effective_from: date
    effective_to: date | None = None
    standard_duty_minutes: int = Field(default=600, ge=1, le=1440)
    overtime_rate_per_hour: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = Field(default=None, max_length=4000)


class CompensationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    membership_id: UUID
    pay_basis: PayBasis
    base_amount: Decimal
    effective_from: date
    effective_to: date | None
    standard_duty_minutes: int
    overtime_rate_per_hour: Decimal
    notes: str | None


class AttendanceResponse(BaseModel):
    membership_id: UUID
    display_name: str
    operational_date: date
    duty_minutes: int
    overtime_minutes: int
    state: AttendanceCalculationState
    location_confidence: AttendanceConfidence


class PayrollPeriodInput(BaseModel):
    starts_on: date
    ends_on: date


class PayrollPeriodStatusInput(BaseModel):
    status: PayrollPeriodStatus


class PayrollPeriodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    starts_on: date
    ends_on: date
    status: PayrollPeriodStatus
    reviewed_at: datetime | None
    finalized_at: datetime | None


class PayrollLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    period_id: UUID
    membership_id: UUID
    display_name_snapshot: str
    pay_basis_snapshot: PayBasis
    base_pay: Decimal
    duty_minutes: int
    overtime_minutes: int
    overtime_rate_per_hour: Decimal
    overtime_amount: Decimal
    adjustment_amount: Decimal
    calculated_gross_pay: Decimal
    calculation_state: str
    calculation_snapshot: dict[str, object]


class PayrollAdjustmentInput(BaseModel):
    amount: Decimal
    reason: str = Field(min_length=1, max_length=4000)


def _attendance(item: AttendanceDay) -> AttendanceResponse:
    return AttendanceResponse(
        membership_id=item.membership_id,
        display_name=item.display_name,
        operational_date=item.operational_date,
        duty_minutes=item.duty_minutes,
        overtime_minutes=item.overtime_minutes,
        state=item.state,
        location_confidence=item.location_confidence,
    )


@workforce_router.get("/compensation", response_model=list[CompensationResponse])
def list_compensation(
    service: Annotated[WorkforceService, Depends(_workforce)],
    membership_id: UUID | None = None,
) -> list[CompensationProfile]:
    return service.list_compensation_profiles(membership_id)


@workforce_router.post(
    "/compensation",
    response_model=CompensationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_compensation(
    payload: CompensationInput,
    service: Annotated[WorkforceService, Depends(_workforce)],
    db: Annotated[Session, Depends(get_db)],
) -> CompensationProfile:
    try:
        item = service.create_compensation_profile(**payload.model_dump())
        db.commit()
        db.refresh(item)
        return item
    except DomainError as exc:
        _fail(db, exc)


@workforce_router.get("/attendance", response_model=list[AttendanceResponse])
def attendance(
    service: Annotated[WorkforceService, Depends(_workforce)],
    starts_on: date,
    ends_on: date,
) -> list[AttendanceResponse]:
    try:
        return [_attendance(item) for item in service.attendance(starts_on, ends_on)]
    except DomainError as exc:
        _fail(service.session, exc)


@workforce_router.get("/payroll-periods", response_model=list[PayrollPeriodResponse])
def list_payroll_periods(
    service: Annotated[WorkforceService, Depends(_workforce)],
) -> list[PayrollPeriod]:
    return service.list_periods()


@workforce_router.post(
    "/payroll-periods",
    response_model=PayrollPeriodResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_payroll_period(
    payload: PayrollPeriodInput,
    service: Annotated[WorkforceService, Depends(_workforce)],
    db: Annotated[Session, Depends(get_db)],
) -> PayrollPeriod:
    try:
        item = service.create_payroll_period(payload.starts_on, payload.ends_on)
        db.commit()
        db.refresh(item)
        return item
    except DomainError as exc:
        _fail(db, exc)


@workforce_router.patch(
    "/payroll-periods/{period_id}/status",
    response_model=PayrollPeriodResponse,
)
def set_payroll_period_status(
    period_id: UUID,
    payload: PayrollPeriodStatusInput,
    service: Annotated[WorkforceService, Depends(_workforce)],
    db: Annotated[Session, Depends(get_db)],
) -> PayrollPeriod:
    try:
        item = service.set_period_status(period_id, payload.status)
        db.commit()
        db.refresh(item)
        return item
    except DomainError as exc:
        _fail(db, exc)


@workforce_router.get(
    "/payroll-periods/{period_id}/lines", response_model=list[PayrollLineResponse]
)
def payroll_lines(
    period_id: UUID,
    service: Annotated[WorkforceService, Depends(_workforce)],
) -> list[PayrollLine]:
    try:
        return service.lines(period_id)
    except DomainError as exc:
        _fail(service.session, exc)


@workforce_router.post("/payroll-lines/{line_id}/adjustments", response_model=PayrollLineResponse)
def add_payroll_adjustment(
    line_id: UUID,
    payload: PayrollAdjustmentInput,
    service: Annotated[WorkforceService, Depends(_workforce)],
    db: Annotated[Session, Depends(get_db)],
) -> PayrollLine:
    try:
        _, line = service.add_adjustment(line_id, **payload.model_dump())
        db.commit()
        db.refresh(line)
        return line
    except DomainError as exc:
        _fail(db, exc)


def _excel_safe(value: str) -> str:
    return f"'{value}" if value.startswith(("=", "+", "-", "@")) else value


@workforce_router.get("/payroll-periods/{period_id}/export.xlsx")
def export_payroll(
    period_id: UUID,
    service: Annotated[WorkforceService, Depends(_workforce)],
) -> StreamingResponse:
    try:
        lines = service.lines(period_id)
    except DomainError as exc:
        _fail(service.session, exc)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Payroll"
    sheet.append(
        [
            "Driver",
            "Pay basis",
            "Base pay",
            "Duty minutes",
            "Overtime minutes",
            "Overtime amount",
            "Adjustments",
            "Gross pay",
            "State",
        ]
    )
    for line in lines:
        sheet.append(
            [
                _excel_safe(line.display_name_snapshot),
                line.pay_basis_snapshot.value,
                float(line.base_pay),
                line.duty_minutes,
                line.overtime_minutes,
                float(line.overtime_amount),
                float(line.adjustment_amount),
                float(line.calculated_gross_pay),
                line.calculation_state,
            ]
        )
    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="payroll.xlsx"'},
    )


class LocationSettingsInput(BaseModel):
    site_match_required: bool = True
    asset_proximity_threshold_m: Decimal = Field(default=Decimal("100"), gt=0)
    gps_freshness_seconds: int = Field(default=900, gt=0)
    max_accuracy_m: Decimal = Field(default=Decimal("100"), gt=0)
    retention_days: int = Field(default=30, gt=0, le=3650)


class LocationSettingsResponse(LocationSettingsInput):
    model_config = ConfigDict(from_attributes=True)


class LocationCaptureInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: LocationSnapshotSource
    status: LocationSnapshotStatus
    captured_at_device: datetime
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    accuracy_m: Decimal | None = Field(default=None, ge=0)
    permission_state: str | None = Field(default=None, max_length=40)
    operational_event_id: UUID | None = None


class LocationSnapshotResponse(BaseModel):
    id: UUID
    membership_id: UUID
    duty_session_id: UUID | None
    assignment_id: UUID
    asset_id: UUID
    site_id: UUID
    operational_event_id: UUID | None
    captured_at_device: datetime
    received_at_server: datetime
    latitude: Decimal | None
    longitude: Decimal | None
    accuracy_m: Decimal | None
    source: LocationSnapshotSource
    status: LocationSnapshotStatus
    permission_state: str | None
    confidence: AttendanceConfidence = AttendanceConfidence.UNKNOWN
    site_distance_m: Decimal | None = None
    asset_distance_m: Decimal | None = None


def _location_response(item: AttendanceLocationSnapshot) -> LocationSnapshotResponse:
    return LocationSnapshotResponse.model_validate(item, from_attributes=True)


def _location_view_response(item: LocationSnapshotView) -> LocationSnapshotResponse:
    response = _location_response(item.snapshot)
    response.confidence = item.confidence
    response.site_distance_m = item.site_distance_m
    response.asset_distance_m = item.asset_distance_m
    return response


@location_owner_router.get("/settings", response_model=LocationSettingsResponse | None)
def get_location_settings(
    service: Annotated[AttendanceLocationService, Depends(_location)],
) -> AttendanceLocationSetting | None:
    return service.get_settings()


@location_owner_router.put("/settings", response_model=LocationSettingsResponse)
def put_location_settings(
    payload: LocationSettingsInput,
    service: Annotated[AttendanceLocationService, Depends(_location)],
    db: Annotated[Session, Depends(get_db)],
) -> AttendanceLocationSetting:
    try:
        item = service.put_settings(**payload.model_dump())
        db.commit()
        db.refresh(item)
        return item
    except DomainError as exc:
        _fail(db, exc)


@location_owner_router.get("/snapshots", response_model=list[LocationSnapshotResponse])
def list_location_snapshots(
    service: Annotated[AttendanceLocationService, Depends(_location)],
    membership_id: UUID | None = None,
) -> list[LocationSnapshotResponse]:
    return [
        _location_view_response(item)
        for item in service.list_snapshots(membership_id=membership_id)
    ]


@location_owner_router.post("/retention", response_model=dict[str, int])
def apply_location_retention(
    service: Annotated[AttendanceLocationService, Depends(_location)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, int]:
    deleted = service.purge_expired()
    db.commit()
    return {"deleted": deleted}


@location_driver_router.post(
    "/snapshots",
    response_model=LocationSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
def capture_location_snapshot(
    payload: LocationCaptureInput,
    service: Annotated[AttendanceLocationService, Depends(_location)],
    db: Annotated[Session, Depends(get_db)],
) -> LocationSnapshotResponse:
    try:
        item = service.capture(**payload.model_dump())
        db.commit()
        db.refresh(item)
        return _location_response(item)
    except DomainError as exc:
        _fail(db, exc)
