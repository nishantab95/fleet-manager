from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from typing import NoReturn
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from openpyxl import Workbook  # type: ignore[import-untyped]
from openpyxl.styles import Alignment, Font, PatternFill  # type: ignore[import-untyped]
from openpyxl.utils import get_column_letter  # type: ignore[import-untyped]
from openpyxl.worksheet.worksheet import Worksheet  # type: ignore[import-untyped]
from sqlalchemy import String, func, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import (
    get_app_settings,
    get_current_session,
    get_object_storage,
    require_owner_admin,
)
from fleet_api.api.schemas import (
    ClosureActionRequest,
    ClosureHistoryResponse,
    ClosureResponse,
    DashboardResponse,
    DriverDutyReportResponse,
    ReportEventResponse,
    ReportExceptionResponse,
    ReportHistoryResponse,
    SiteDailyReportResponse,
    TipperDailyReportResponse,
)
from fleet_api.auth.service import AuthContext
from fleet_api.core.config import Settings
from fleet_api.db.models import Assignment, CompanyMembership, DutySession, FleetAsset, Site, User
from fleet_api.db.session import get_db
from fleet_api.domain.enums import (
    DutySessionStatus,
    FleetAssetType,
    OperationalEventType,
    SiteClosureStatus,
    VerificationStatus,
)
from fleet_api.domain.errors import (
    ClosureBlockedError,
    ConflictError,
    DomainError,
    NotFoundError,
    ObjectStorageUnavailableError,
    RoleViolationError,
    TenantConsistencyError,
)
from fleet_api.domain.report_templates import (
    DIESEL_REGISTER,
    DUTY_REGISTER,
    EXCEPTIONS,
    MACHINERY_DAILY,
    MANAGEMENT_DASHBOARD,
    METER_READINGS,
    SHEET_IDS,
    STANDARD_MACHINERY_COLUMNS,
    STANDARD_MANAGEMENT_COLUMNS,
    STANDARD_TIPPER_COLUMNS,
    TIPPER_DAILY,
    TRIP_REGISTER,
    ReportTemplateConfig,
    ReportTemplateService,
)
from fleet_api.domain.reporting import (
    AssetDailyReport,
    ClosureSnapshot,
    DashboardReport,
    OperationalDay,
    ReportEvent,
    ReportEvidenceContext,
    ReportException,
    ReportHistory,
    ReportingService,
    SiteDailyReport,
)
from fleet_api.storage.objects import ObjectStorage

from .simple_site_workbook import build_simple_site_workbook

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


def _fail(exc: DomainError) -> NoReturn:
    if isinstance(exc, ClosureBlockedError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CLOSURE_BLOCKED", "message": str(exc), "blockers": exc.blockers},
        ) from exc
    if isinstance(exc, ObjectStorageUnavailableError):
        http_status, code = status.HTTP_503_SERVICE_UNAVAILABLE, "OBJECT_STORAGE_UNAVAILABLE"
    elif isinstance(exc, NotFoundError):
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


def _history_response(history: ReportHistory) -> ReportHistoryResponse:
    return ReportHistoryResponse(
        status=history.status,
        actor_name=history.actor_name,
        reason=history.reason,
        created_at=history.created_at,
    )


def _event_response(event: ReportEvent) -> ReportEventResponse:
    return ReportEventResponse(
        event_id=event.event_id,
        event_type=event.event_type,
        assignment_id=event.assignment_id,
        duty_session_id=event.duty_session_id,
        tipper_id=event.asset_id,
        tipper_registration_number=event.asset_registration_number,
        asset_code=event.asset_code,
        asset_type=FleetAssetType(event.asset_type),
        site_id=event.site_id,
        site_name=event.site_name,
        driver_name=event.driver_name,
        driver_phone=event.driver_phone,
        supervisor_name=event.supervisor_name,
        device_created_at=event.device_created_at,
        server_received_at=event.server_received_at,
        verification_status=event.verification_status,
        reading_type=event.reading_type,
        reading_value=event.reading_value,
        litres=event.litres,
        emergency_category=event.emergency_category,
        emergency_status=event.emergency_status,
        emergency_description=event.emergency_description,
        evidence_available=event.evidence_available,
        verification_history=[_history_response(item) for item in event.verification_history],
    )


def _exception_response(item: ReportException) -> ReportExceptionResponse:
    return ReportExceptionResponse(
        code=item.code,
        description=item.description,
        assignment_id=item.assignment_id,
        tipper_id=item.asset_id,
        tipper_registration_number=item.asset_registration_number,
        site_id=item.site_id,
        event_id=item.event_id,
    )


def _duration_seconds(value: timedelta | None) -> float | None:
    return value.total_seconds() if value is not None else None


def _tipper_response(item: AssetDailyReport) -> TipperDailyReportResponse:
    return TipperDailyReportResponse(
        assignment_id=item.assignment.id,
        tipper_id=item.asset.id,
        registration_number=item.asset.registration_number or item.asset.asset_code,
        short_name=item.asset.short_name,
        asset_type=item.asset.asset_type,
        site_id=item.site.id,
        site_name=item.site.name,
        driver_name=item.driver_name,
        supervisor_name=item.supervisor_name,
        assignment_starts_at=item.assignment.starts_at,
        assignment_ends_at=item.assignment.ends_at,
        approved_trip_count=(
            item.approved_trip_count if item.asset.asset_type.value == "TIPPER" else None
        ),
        pending_trip_count=(
            item.pending_trip_count if item.asset.asset_type.value == "TIPPER" else None
        ),
        disputed_trip_count=(
            item.disputed_trip_count if item.asset.asset_type.value == "TIPPER" else None
        ),
        rejected_trip_count=(
            item.rejected_trip_count if item.asset.asset_type.value == "TIPPER" else None
        ),
        trips_state=item.trips_state.value,
        start_km=item.start_km,
        end_km=item.end_km,
        distance_km=item.distance_km,
        start_hmr=item.start_hmr,
        end_hmr=item.end_hmr,
        machine_hours=item.machine_hours,
        distance_state=item.distance_state.value,
        machine_hours_state=item.machine_hours_state.value,
        km_per_approved_trip=item.km_per_approved_trip,
        verified_diesel_issued=item.verified_diesel_issued,
        pending_diesel_issued=item.pending_diesel_issued,
        diesel_issued_per_approved_trip=item.diesel_issued_per_approved_trip,
        first_trip_completed_at=item.first_trip_completed_at,
        last_trip_completed_at=item.last_trip_completed_at,
        recorded_activity_span_seconds=_duration_seconds(item.recorded_activity_span),
        avg_trip_completion_interval_seconds=_duration_seconds(item.avg_trip_completion_interval),
        median_trip_completion_interval_seconds=_duration_seconds(
            item.median_trip_completion_interval
        ),
        longest_trip_gap_seconds=_duration_seconds(item.longest_trip_gap),
        pending_diesel_count=item.pending_diesel_count,
        disputed_diesel_count=item.disputed_diesel_count,
        unresolved_emergency_count=item.unresolved_emergency_count,
        missing_start_reading=item.missing_start_reading,
        missing_end_reading=item.missing_end_reading,
        completeness_status=item.completeness_status,
        closure_status=item.closure_status,
        exceptions=[_exception_response(exception) for exception in item.exceptions],
        events=[_event_response(event) for event in item.events],
    )


def _closure_response(site: Site, day: OperationalDay, closure: ClosureSnapshot) -> ClosureResponse:
    return ClosureResponse(
        site_id=site.id,
        site_name=site.name,
        operational_date=day.operational_date,
        reporting_timezone=day.reporting_timezone,
        workday_start_minutes=day.workday_start_minutes,
        status=closure.status,
        blockers=[_exception_response(blocker) for blocker in closure.blockers],
        history=[
            ClosureHistoryResponse(
                status=item.status,
                actor_name=item.actor_name,
                reason=item.reason,
                created_at=item.created_at,
            )
            for item in closure.history
        ],
    )


def _site_response(report: SiteDailyReport) -> SiteDailyReportResponse:
    return SiteDailyReportResponse(
        site_id=report.site.id,
        site_name=report.site.name,
        operational_date=report.operational_day.operational_date,
        reporting_timezone=report.operational_day.reporting_timezone,
        assigned_tippers_count=report.assigned_assets_count,
        approved_trip_count=report.approved_trip_count,
        pending_trip_count=report.pending_trip_count,
        disputed_trip_count=report.disputed_trip_count,
        total_km=report.total_km,
        verified_diesel_issued=report.verified_diesel_issued,
        missing_reading_count=report.missing_reading_count,
        unresolved_emergency_count=report.unresolved_emergency_count,
        closure=_closure_response(report.site, report.operational_day, report.closure),
        tippers=[_tipper_response(item) for item in report.rows],
    )


def _duty_reports(
    db: Session,
    context: AuthContext,
    requested_date: date | None = None,
    report: DashboardReport | None = None,
) -> list[DriverDutyReportResponse]:
    service = _service(db, context)
    day = service.operational_day(requested_date)
    report = report or service.dashboard(day.operational_date)
    report_by_assignment = {
        row.assignment.id: row for site_report in report.sites for row in site_report.rows
    }
    rows = db.execute(
        select(
            DutySession,
            Assignment,
            FleetAsset,
            Site,
            sql_cast(func.coalesce(CompanyMembership.display_name, User.display_name), String),
        )
        .join(Assignment, Assignment.id == DutySession.assignment_id)
        .join(FleetAsset, FleetAsset.id == DutySession.asset_id)
        .join(Site, Site.id == DutySession.site_id)
        .join(CompanyMembership, CompanyMembership.id == DutySession.driver_membership_id)
        .join(User, User.id == CompanyMembership.user_id)
        .where(
            DutySession.company_id == context.company.id,
            DutySession.operational_date == day.operational_date,
        )
        .order_by(DutySession.started_at, DutySession.id)
    ).all()
    now = datetime.now(UTC)
    reports: list[DriverDutyReportResponse] = []
    for duty, assignment, asset, site, driver_name in rows:
        daily = report_by_assignment.get(assignment.id)
        actual_end = duty.ended_at
        actual_reference = actual_end or now
        span = max(0.0, (actual_reference - duty.started_at).total_seconds())
        overtime = duty.final_overtime_minutes
        if overtime is None:
            overtime = max(
                0,
                int((actual_reference - duty.regular_duty_ends_at).total_seconds() // 60),
            )
        reports.append(
            DriverDutyReportResponse(
                operational_date=duty.operational_date,
                session_id=duty.id,
                assignment_id=assignment.id,
                driver_name=driver_name,
                asset_code=asset.asset_code,
                tipper_registration_number=asset.registration_number or asset.asset_code,
                asset_type=asset.asset_type,
                site_name=site.name,
                duty_start=duty.started_at,
                start_km=duty.start_km,
                start_hmr=duty.start_hmr,
                regular_duty_minutes=duty.configured_regular_duty_minutes,
                regular_duty_ends_at=duty.regular_duty_ends_at,
                actual_duty_end=actual_end,
                end_km=duty.end_km,
                end_hmr=duty.end_hmr,
                machine_hours=(
                    duty.end_hmr - duty.start_hmr
                    if duty.start_hmr is not None and duty.end_hmr is not None
                    else None
                ),
                verified_diesel_issued=(
                    daily.verified_diesel_issued if daily is not None else Decimal("0")
                ),
                pending_diesel_issued=(
                    daily.pending_diesel_issued if daily is not None else Decimal("0")
                ),
                actual_duty_span_seconds=span,
                overtime_minutes=overtime,
                status=duty.status.value,
            )
        )
    return reports


def _dashboard_response(
    report: DashboardReport,
    duty_reports: list[DriverDutyReportResponse] | None = None,
) -> DashboardResponse:
    duty_reports = duty_reports or []
    return DashboardResponse(
        operational_date=report.operational_day.operational_date,
        reporting_timezone=report.operational_day.reporting_timezone,
        workday_start_minutes=report.operational_day.workday_start_minutes,
        assigned_tippers_count=report.assigned_assets_count,
        approved_trip_count=report.approved_trip_count,
        pending_trip_count=report.pending_trip_count,
        total_km=report.total_km,
        verified_diesel_issued=report.verified_diesel_issued,
        pending_verification_count=report.pending_verification_count,
        missing_reading_count=report.missing_reading_count,
        unresolved_emergency_count=report.unresolved_emergency_count,
        sites_not_closed_count=report.sites_not_closed_count,
        complete_tippers_count=report.complete_assets_count,
        drivers_on_duty=sum(item.status == DutySessionStatus.ACTIVE.value for item in duty_reports),
        drivers_past_regular_duty=sum(
            item.status == DutySessionStatus.ACTIVE.value and item.overtime_minutes > 0
            for item in duty_reports
        ),
        closed_duties_count=sum(
            item.status == DutySessionStatus.CLOSED.value for item in duty_reports
        ),
        sites=[_site_response(site) for site in report.sites],
        exceptions=[_exception_response(item) for item in report.exceptions],
    )


def _service(db: Session, context: AuthContext) -> ReportingService:
    return ReportingService(db, context)


def _evidence_headers(view: ReportEvidenceContext) -> dict[str, str]:
    return {
        "Cache-Control": "private, no-store",
        "Content-Disposition": "inline",
        "X-Fleet-Evidence-Event-Type": view.event.event_type.value,
        "X-Fleet-Evidence-Driver": view.driver_name,
        "X-Fleet-Evidence-Tipper": view.asset.registration_number or view.asset.asset_code,
        "X-Fleet-Evidence-Timestamp": view.event.device_created_at.isoformat(),
    }


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(
    operational_date: date | None = Query(default=None),
    context: AuthContext = Depends(require_owner_admin),
    db: Session = Depends(get_db),
) -> DashboardResponse:
    try:
        report = _service(db, context).dashboard(operational_date)
        return _dashboard_response(
            report,
            _duty_reports(
                db,
                context,
                report.operational_day.operational_date,
                report=report,
            ),
        )
    except DomainError as exc:
        _fail(exc)


@router.get("/duty", response_model=list[DriverDutyReportResponse])
def duty_report(
    operational_date: date | None = Query(default=None),
    context: AuthContext = Depends(require_owner_admin),
    db: Session = Depends(get_db),
) -> list[DriverDutyReportResponse]:
    try:
        return _duty_reports(db, context, operational_date)
    except DomainError as exc:
        _fail(exc)


@router.get("/sites/{site_id}/daily", response_model=SiteDailyReportResponse)
def site_daily_report(
    site_id: UUID,
    operational_date: date | None = Query(default=None),
    context: AuthContext = Depends(require_owner_admin),
    db: Session = Depends(get_db),
) -> SiteDailyReportResponse:
    try:
        return _site_response(_service(db, context).site_daily(site_id, operational_date))
    except DomainError as exc:
        _fail(exc)


@router.get("/tippers/{tipper_id}/daily", response_model=list[TipperDailyReportResponse])
def tipper_daily_report(
    tipper_id: UUID,
    operational_date: date | None = Query(default=None),
    context: AuthContext = Depends(require_owner_admin),
    db: Session = Depends(get_db),
) -> list[TipperDailyReportResponse]:
    try:
        return [
            _tipper_response(item)
            for item in _service(db, context).asset_daily(tipper_id, operational_date)
        ]
    except DomainError as exc:
        _fail(exc)


@router.get("/exceptions", response_model=list[ReportExceptionResponse])
def report_exceptions(
    operational_date: date | None = Query(default=None),
    context: AuthContext = Depends(require_owner_admin),
    db: Session = Depends(get_db),
) -> list[ReportExceptionResponse]:
    try:
        return [
            _exception_response(item) for item in _service(db, context).exceptions(operational_date)
        ]
    except DomainError as exc:
        _fail(exc)


@router.get("/sites/{site_id}/closure", response_model=ClosureResponse)
def get_closure(
    site_id: UUID,
    operational_date: date | None = Query(default=None),
    context: AuthContext = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> ClosureResponse:
    try:
        service = _service(db, context)
        day = service.operational_day(operational_date)
        site = service._authorize_site(site_id)
        return _closure_response(site, day, service.closure(site_id, day.operational_date))
    except DomainError as exc:
        _fail(exc)


@router.post("/sites/{site_id}/closure/close", response_model=ClosureResponse)
def close_site(
    site_id: UUID,
    payload: ClosureActionRequest,
    operational_date: date | None = Query(default=None),
    context: AuthContext = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> ClosureResponse:
    try:
        service = _service(db, context)
        closure = service.close_site(site_id, operational_date, reason=payload.reason)
        db.commit()
        day = service.operational_day(operational_date)
        return _closure_response(service._site(site_id), day, closure)
    except DomainError as exc:
        db.rollback()
        _fail(exc)


@router.post("/sites/{site_id}/closure/reopen", response_model=ClosureResponse)
def reopen_site(
    site_id: UUID,
    payload: ClosureActionRequest,
    operational_date: date | None = Query(default=None),
    context: AuthContext = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> ClosureResponse:
    try:
        if not payload.reason:
            raise DomainError("a reopening reason is required")
        service = _service(db, context)
        closure = service.reopen_site(site_id, operational_date, reason=payload.reason)
        db.commit()
        day = service.operational_day(operational_date)
        return _closure_response(service._site(site_id), day, closure)
    except DomainError as exc:
        db.rollback()
        _fail(exc)


def _safe_excel_text(value: object) -> object:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _event_actor_time(event: ReportEvent) -> tuple[str | None, datetime | None]:
    for item in reversed(event.verification_history):
        if item.status == VerificationStatus.APPROVED:
            return item.actor_name, item.created_at
    return None, None


def _excel_report_datetime(value: datetime, reporting_zone: ZoneInfo) -> datetime:
    """Convert an aware timestamp to the report timezone for Excel's naive cells."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(reporting_zone).replace(tzinfo=None)


def _evidence_application_url(base_url: str, event_id: UUID) -> str:
    return f"{base_url.rstrip('/')}/evidence/{event_id}"


@dataclass(frozen=True)
class _ExcelFormula:
    value: str


@dataclass(frozen=True)
class _SummaryColumn:
    field_id: str
    label: str
    value_index: int


MANAGEMENT_COLUMN_REGISTRY = (
    _SummaryColumn("asset", "Asset", 0),
    _SummaryColumn("asset_type", "Type", 1),
    _SummaryColumn("site", "Site", 2),
    _SummaryColumn("operator", "Driver / Operator", 3),
    _SummaryColumn("assignment_status", "Assignment Status", 4),
    _SummaryColumn("duty_status", "Duty Status", 5),
    _SummaryColumn("trips", "Trips", 6),
    _SummaryColumn("distance_km", "Distance KM", 7),
    _SummaryColumn("machine_hours", "Machine Hours", 8),
    _SummaryColumn("verified_diesel_l", "Verified Diesel L", 9),
    _SummaryColumn("pending_status", "Pending / Status", 10),
)
TIPPER_COLUMN_REGISTRY = (
    _SummaryColumn("asset", "Asset", 2),
    _SummaryColumn("site", "Site", 1),
    _SummaryColumn("registration", "Registration", 3),
    _SummaryColumn("driver", "Driver", 4),
    _SummaryColumn("start_km", "Start KM", 6),
    _SummaryColumn("end_km", "End KM", 7),
    _SummaryColumn("distance_km", "Distance KM", 8),
    _SummaryColumn("approved_trips", "Approved Trips", 9),
    _SummaryColumn("diesel_l", "Diesel L", 10),
    _SummaryColumn("duty_start", "Duty Start", 11),
    _SummaryColumn("duty_end", "Duty End", 12),
    _SummaryColumn("pending", "Pending", 13),
    _SummaryColumn("status", "Status", 14),
)
MACHINERY_COLUMN_REGISTRY = (
    _SummaryColumn("asset", "Asset", 2),
    _SummaryColumn("asset_type", "Asset Type", 3),
    _SummaryColumn("site", "Site", 1),
    _SummaryColumn("operator", "Operator", 4),
    _SummaryColumn("start_hmr", "Start HMR", 6),
    _SummaryColumn("end_hmr", "End HMR", 7),
    _SummaryColumn("machine_hours", "Machine Hours", 8),
    _SummaryColumn("diesel_l", "Diesel L", 9),
    _SummaryColumn("duty_start", "Duty Start", 10),
    _SummaryColumn("duty_end", "Duty End", 11),
    _SummaryColumn("pending", "Pending", 12),
    _SummaryColumn("status", "Status", 13),
)


def _select_summary_columns(
    registry: tuple[_SummaryColumn, ...],
    selected_ids: tuple[str, ...],
    rows: list[list[object]],
) -> tuple[list[str], list[list[object]]]:
    selected = set(selected_ids)
    columns = [column for column in registry if column.field_id in selected]
    return (
        [column.label for column in columns],
        [[row[column.value_index] for column in columns] for row in rows],
    )


def _detailed_template_config() -> ReportTemplateConfig:
    return ReportTemplateConfig(
        id=UUID(int=0),
        name="Detailed Operations",
        included_sheets=SHEET_IDS,
        management_dashboard_columns=STANDARD_MANAGEMENT_COLUMNS,
        tipper_daily_columns=STANDARD_TIPPER_COLUMNS,
        machinery_daily_columns=STANDARD_MACHINERY_COLUMNS,
    )


def _template_filename_segment(name: str) -> str:
    segment = "-".join(part for part in re.split(r"[^A-Za-z0-9]+", name) if part)
    return segment or "Report"


def _evidence_formula(base_url: str, event_id: UUID) -> _ExcelFormula:
    url = _evidence_application_url(base_url, event_id)
    return _ExcelFormula(f'=HYPERLINK("{url}","Open Evidence")')


def _asset_type_label(asset_type: FleetAssetType) -> str:
    return asset_type.value.replace("_", " ")


def _assignment_status(assignment: Assignment) -> str:
    return "CURRENT" if assignment.ends_at is None else "HISTORICAL"


def _metric_value(value: object, state: object) -> object:
    state_value = getattr(state, "value", state)
    if state_value == "NOT_APPLICABLE":
        return "—"
    if state_value == "MISSING":
        return "MISSING"
    return value


def _pending_status(row: AssetDailyReport) -> str:
    pending_events = sum(
        1
        for event in row.events
        if event.event_type != OperationalEventType.EMERGENCY
        and event.verification_status == VerificationStatus.PENDING_VERIFICATION
    )
    details: list[str] = []
    if row.pending_diesel_issued:
        details.append(f"Diesel {row.pending_diesel_issued:g} L pending")
    if pending_events:
        details.append(f"{pending_events} pending")
    details.append(row.completeness_status.replace("_", " "))
    return " · ".join(details)


def _append_excel_row(worksheet: Worksheet, row: list[object]) -> None:
    worksheet.append(
        [
            value.value if isinstance(value, _ExcelFormula) else _safe_excel_text(value)
            for value in row
        ]
    )


def _format_report_sheet(
    worksheet: Worksheet,
    *,
    title: str,
    timezone_name: str,
    header_row: int = 4,
) -> None:
    worksheet["A1"] = title
    worksheet["A1"].font = Font(bold=True, size=15, color="173C35")
    worksheet["A2"] = "Times shown in:"
    worksheet["B2"] = timezone_name
    worksheet["A2"].font = Font(bold=True, color="173C35")
    header_fill = PatternFill("solid", fgColor="1F4E78")
    for cell in worksheet[header_row]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    worksheet.freeze_panes = f"A{header_row + 1}"
    worksheet.auto_filter.ref = (
        f"A{header_row}:{get_column_letter(worksheet.max_column)}"
        f"{max(header_row, worksheet.max_row)}"
    )
    for column in range(1, worksheet.max_column + 1):
        width = min(
            max(
                len(str(worksheet.cell(row=row, column=column).value or ""))
                for row in range(1, worksheet.max_row + 1)
            )
            + 2,
            32,
        )
        worksheet.column_dimensions[get_column_letter(column)].width = width
    for row in worksheet.iter_rows(min_row=header_row + 1):
        for cell in row:
            if isinstance(cell.value, timedelta):
                cell.number_format = '[h]"h "mm"m"'
            elif cell.is_date:
                cell.number_format = "yyyy-mm-dd hh:mm"
    for column in range(1, worksheet.max_column + 1):
        header = worksheet.cell(row=header_row, column=column).value
        if header == "Date":
            for row in range(header_row + 1, worksheet.max_row + 1):
                worksheet.cell(row=row, column=column).number_format = "yyyy-mm-dd"
        if header in {"Pending", "Pending / Status"}:
            worksheet.column_dimensions[get_column_letter(column)].width = 36
            for row in range(header_row + 1, worksheet.max_row + 1):
                worksheet.cell(row=row, column=column).alignment = Alignment(
                    vertical="top", wrap_text=True
                )
        if header in {
            "Start KM",
            "End KM",
            "Distance KM",
            "Start HMR",
            "End HMR",
            "Machine Hours",
            "Diesel L",
            "Verified Diesel L",
            "Value",
            "Meter Start",
            "Meter End",
            "Usage",
        }:
            for row in range(header_row + 1, worksheet.max_row + 1):
                worksheet.cell(row=row, column=column).number_format = "0.00"


def _add_report_sheet(
    workbook: Workbook,
    *,
    title: str,
    timezone_name: str,
    headers: list[str],
    rows: list[list[object]],
) -> Worksheet:
    worksheet = workbook.create_sheet(title)
    worksheet.append([])
    worksheet.append([])
    worksheet.append([])
    worksheet.append(headers)
    for row in rows:
        _append_excel_row(worksheet, row)
    _format_report_sheet(worksheet, title=title, timezone_name=timezone_name)
    return worksheet


def _build_workbook(
    report: DashboardReport,
    *,
    web_public_base_url: str,
    duty_reports: list[DriverDutyReportResponse] | None = None,
    template: ReportTemplateConfig | None = None,
) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    selected_template = template or _detailed_template_config()
    included_sheets = set(selected_template.included_sheets)
    timezone_name = report.operational_day.reporting_timezone
    reporting_zone = ZoneInfo(timezone_name)
    management_rows: list[list[object]] = []
    tipper_rows: list[list[object]] = []
    machinery_rows: list[list[object]] = []
    trip_rows: list[list[object]] = []
    meter_rows: list[list[object]] = []
    diesel_rows: list[list[object]] = []
    exception_rows: list[list[object]] = []
    duty_rows: list[list[object]] = []
    duty_by_assignment = {duty.assignment_id: duty for duty in (duty_reports or [])}
    for site in report.sites:
        for row in site.rows:
            assignment_status = _assignment_status(row.assignment)
            duty = duty_by_assignment.get(row.assignment.id)
            duty_status = duty.status if duty is not None else "NO DUTY"
            pending_status = _pending_status(row)
            asset_type = _asset_type_label(row.asset.asset_type)
            approved_trip_events = sorted(
                (
                    event
                    for event in row.events
                    if event.event_type.value == "TRIP_COMPLETE"
                    and event.verification_status == VerificationStatus.APPROVED
                ),
                key=lambda event: event.device_created_at,
            )
            previous_approved_by_event: dict[UUID, tuple[datetime, timedelta]] = {}
            previous: ReportEvent | None = None
            for event in approved_trip_events:
                if previous is not None:
                    previous_approved_by_event[event.event_id] = (
                        _excel_report_datetime(previous.device_created_at, reporting_zone),
                        event.device_created_at - previous.device_created_at,
                    )
                previous = event
            management_rows.append(
                [
                    row.asset.asset_code,
                    asset_type,
                    site.site.name,
                    row.driver_name,
                    assignment_status,
                    duty_status,
                    _metric_value(row.approved_trip_count, row.trips_state),
                    _metric_value(row.distance_km, row.distance_state),
                    _metric_value(row.machine_hours, row.machine_hours_state),
                    row.verified_diesel_issued,
                    pending_status,
                ]
            )
            common_times = (
                _excel_report_datetime(duty.duty_start, reporting_zone)
                if duty is not None
                else None,
                _excel_report_datetime(duty.actual_duty_end, reporting_zone)
                if duty is not None and duty.actual_duty_end is not None
                else None,
            )
            if row.asset.asset_type == FleetAssetType.TIPPER:
                tipper_rows.append(
                    [
                        report.operational_day.operational_date,
                        site.site.name,
                        row.asset.asset_code,
                        row.asset.registration_number or "—",
                        row.driver_name,
                        assignment_status,
                        row.start_km,
                        row.end_km,
                        _metric_value(row.distance_km, row.distance_state),
                        row.approved_trip_count,
                        row.verified_diesel_issued,
                        common_times[0],
                        common_times[1],
                        pending_status,
                        row.completeness_status.replace("_", " "),
                    ]
                )
            else:
                machinery_rows.append(
                    [
                        report.operational_day.operational_date,
                        site.site.name,
                        row.asset.asset_code,
                        asset_type,
                        row.driver_name,
                        assignment_status,
                        row.start_hmr,
                        row.end_hmr,
                        _metric_value(row.machine_hours, row.machine_hours_state),
                        row.verified_diesel_issued,
                        common_times[0],
                        common_times[1],
                        pending_status,
                        row.completeness_status.replace("_", " "),
                    ]
                )
            for event in row.events:
                actor, verified_at = _event_actor_time(event)
                if event.event_type.value == "TRIP_COMPLETE":
                    previous_approved = previous_approved_by_event.get(event.event_id)
                    trip_rows.append(
                        [
                            report.operational_day.operational_date,
                            site.site.name,
                            row.asset.asset_code,
                            row.driver_name,
                            assignment_status,
                            _excel_report_datetime(event.device_created_at, reporting_zone),
                            event.verification_status.value,
                            actor,
                            _excel_report_datetime(verified_at, reporting_zone)
                            if verified_at is not None
                            else None,
                            previous_approved[0] if previous_approved else None,
                            previous_approved[1] if previous_approved else None,
                        ]
                    )
                elif event.event_type.value in {"KM_READING", "HMR_READING"}:
                    meter_rows.append(
                        [
                            _excel_report_datetime(event.device_created_at, reporting_zone),
                            site.site.name,
                            row.asset.asset_code,
                            asset_type,
                            row.driver_name,
                            assignment_status,
                            "ODOMETER" if event.event_type.value == "KM_READING" else "HMR",
                            "START" if event.reading_type == "START_READING" else "END",
                            event.reading_value,
                            "km" if event.event_type.value == "KM_READING" else "h",
                            event.verification_status.value,
                            (
                                _evidence_formula(web_public_base_url, event.event_id)
                                if event.evidence_available
                                else "Not available"
                            ),
                        ]
                    )
                elif event.event_type.value == "DIESEL":
                    diesel_rows.append(
                        [
                            _excel_report_datetime(event.device_created_at, reporting_zone),
                            site.site.name,
                            row.asset.asset_code,
                            asset_type,
                            row.driver_name,
                            assignment_status,
                            event.litres,
                            event.verification_status.value,
                            (
                                _evidence_formula(web_public_base_url, event.event_id)
                                if event.evidence_available
                                else "Not available"
                            ),
                        ]
                    )
            for exception in row.exceptions:
                exception_rows.append(
                    [
                        report.operational_day.operational_date,
                        site.site.name,
                        row.asset.asset_code,
                        asset_type,
                        assignment_status,
                        exception.code,
                        exception.description,
                        "OPEN",
                    ]
                )
        if site.rows and site.closure.status != SiteClosureStatus.CLOSED:
            exception_rows.append(
                [
                    report.operational_day.operational_date,
                    site.site.name,
                    "",
                    "",
                    "",
                    "SITE_NOT_CLOSED",
                    f"Site is {site.closure.status.value}",
                    "OPEN",
                ]
            )
    for duty in duty_reports or []:
        machinery = duty.asset_type != FleetAssetType.TIPPER
        duty_rows.append(
            [
                duty.operational_date,
                duty.site_name,
                duty.asset_code,
                _asset_type_label(duty.asset_type),
                duty.driver_name,
                _assignment_status(
                    next(
                        row.assignment
                        for site_report in report.sites
                        for row in site_report.rows
                        if row.assignment.id == duty.assignment_id
                    )
                ),
                _excel_report_datetime(duty.duty_start, reporting_zone),
                _excel_report_datetime(duty.actual_duty_end, reporting_zone)
                if duty.actual_duty_end
                else None,
                timedelta(seconds=duty.actual_duty_span_seconds)
                if duty.actual_duty_span_seconds is not None
                else None,
                duty.start_hmr if machinery else duty.start_km,
                duty.end_hmr if machinery else duty.end_km,
                "h" if machinery else "km",
                duty.machine_hours
                if machinery
                else (
                    duty.end_km - duty.start_km
                    if duty.start_km is not None and duty.end_km is not None
                    else None
                ),
                duty.status,
            ]
        )
    if MANAGEMENT_DASHBOARD in included_sheets:
        management_headers, selected_management_rows = _select_summary_columns(
            MANAGEMENT_COLUMN_REGISTRY,
            selected_template.management_dashboard_columns,
            management_rows,
        )
        dashboard = _add_report_sheet(
            workbook,
            title="Management Dashboard",
            timezone_name=timezone_name,
            headers=management_headers,
            rows=selected_management_rows,
        )
        dashboard["C2"] = "Operational Date"
        dashboard["D2"] = report.operational_day.operational_date
        dashboard["D2"].number_format = "yyyy-mm-dd"
    if TIPPER_DAILY in included_sheets:
        tipper_headers, selected_tipper_rows = _select_summary_columns(
            TIPPER_COLUMN_REGISTRY,
            selected_template.tipper_daily_columns,
            tipper_rows,
        )
        _add_report_sheet(
            workbook,
            title="Tipper Daily",
            timezone_name=timezone_name,
            headers=tipper_headers,
            rows=selected_tipper_rows,
        )
    if MACHINERY_DAILY in included_sheets:
        machinery_headers, selected_machinery_rows = _select_summary_columns(
            MACHINERY_COLUMN_REGISTRY,
            selected_template.machinery_daily_columns,
            machinery_rows,
        )
        _add_report_sheet(
            workbook,
            title="Machinery Daily",
            timezone_name=timezone_name,
            headers=machinery_headers,
            rows=selected_machinery_rows,
        )
    if TRIP_REGISTER in included_sheets:
        _add_report_sheet(
            workbook,
            title="Trip Register",
            timezone_name=timezone_name,
            headers=[
                "Date",
                "Site",
                "Asset",
                "Driver",
                "Assignment Status",
                "Trip Event Time",
                "Verification",
                "Verified By",
                "Verified At",
                "Previous Approved Trip Time",
                "Interval Since Previous Approved Trip",
            ],
            rows=trip_rows,
        )
    if METER_READINGS in included_sheets:
        _add_report_sheet(
            workbook,
            title="Meter Readings",
            timezone_name=timezone_name,
            headers=[
                "Date/Time",
                "Site",
                "Asset",
                "Asset Type",
                "Driver / Operator",
                "Assignment Status",
                "Meter Type",
                "Reading Type",
                "Value",
                "Unit",
                "Verification",
                "Evidence",
            ],
            rows=meter_rows,
        )
    if DIESEL_REGISTER in included_sheets:
        _add_report_sheet(
            workbook,
            title="Diesel Register",
            timezone_name=timezone_name,
            headers=[
                "Date/Time",
                "Site",
                "Asset",
                "Type",
                "Driver / Operator",
                "Assignment Status",
                "Diesel L",
                "Verification",
                "Evidence",
            ],
            rows=diesel_rows,
        )
    if DUTY_REGISTER in included_sheets:
        _add_report_sheet(
            workbook,
            title="Duty Register",
            timezone_name=timezone_name,
            headers=[
                "Date",
                "Site",
                "Asset",
                "Type",
                "Driver / Operator",
                "Assignment Status",
                "Duty Start",
                "Duty End",
                "Duration",
                "Meter Start",
                "Meter End",
                "Meter Unit",
                "Usage",
                "Status",
            ],
            rows=duty_rows,
        )
    if EXCEPTIONS in included_sheets:
        exceptions_sheet = _add_report_sheet(
            workbook,
            title="Exceptions",
            timezone_name=timezone_name,
            headers=[
                "Date",
                "Site",
                "Asset",
                "Type",
                "Assignment Status",
                "Exception Type",
                "Description",
                "Status",
            ],
            rows=exception_rows,
        )
        description_column = next(
            cell.column_letter for cell in exceptions_sheet[4] if cell.value == "Description"
        )
        exceptions_sheet.column_dimensions[description_column].width = 48
        for cell in exceptions_sheet[description_column]:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


@router.get("/daily.xlsx")
def daily_excel(
    operational_date: date | None = Query(default=None),
    template_id: UUID | None = Query(default=None),
    context: AuthContext = Depends(require_owner_admin),
    settings: Settings = Depends(get_app_settings),
    db: Session = Depends(get_db),
) -> Response:
    try:
        template_service = ReportTemplateService(db, context)
        report_template = template_service.resolve_for_export(template_id)
        report = _service(db, context).dashboard(operational_date)
        duties = _duty_reports(
            db,
            context,
            report.operational_day.operational_date,
            report=report,
        )
        content = _build_workbook(
            report,
            web_public_base_url=settings.web_public_base_url,
            duty_reports=duties,
            template=template_service.config(report_template),
        )
        db.commit()
        template_segment = _template_filename_segment(report_template.name)
        filename = (
            f"FleetManager-{report.operational_day.operational_date.isoformat()}-"
            f"{template_segment}.xlsx"
        )
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except DomainError as exc:
        db.rollback()
        _fail(exc)


@router.get("/sites/{site_id}/simple-workbook.xlsx")
def simple_site_workbook(
    site_id: UUID,
    from_date: date = Query(),
    to_date: date = Query(),
    context: AuthContext = Depends(require_owner_admin),
    db: Session = Depends(get_db),
) -> Response:
    try:
        report = _service(db, context).site_period(site_id, from_date, to_date)
        duty_sessions = list(
            db.scalars(
                select(DutySession)
                .where(
                    DutySession.company_id == context.company.id,
                    DutySession.site_id == report.site.id,
                    DutySession.operational_date >= from_date,
                    DutySession.operational_date <= to_date,
                )
                .order_by(
                    DutySession.operational_date,
                    DutySession.started_at,
                    DutySession.id,
                )
            ).all()
        )
        content = build_simple_site_workbook(report, duty_sessions)
        db.commit()
        site_segment = _template_filename_segment(report.site.short_name or report.site.name)
        filename = f"{site_segment}-{from_date.isoformat()}-to-{to_date.isoformat()}.xlsx"
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except DomainError as exc:
        db.rollback()
        _fail(exc)


@router.get("/events/{event_id}/evidence")
def report_evidence(
    event_id: UUID,
    context: AuthContext = Depends(require_owner_admin),
    storage: ObjectStorage = Depends(get_object_storage),
    db: Session = Depends(get_db),
) -> Response:
    try:
        view = _service(db, context).evidence_context_for_event(event_id)
        content, content_type = storage.read_private(object_key=view.evidence.object_key)
        return Response(
            content=content,
            media_type=content_type,
            headers=_evidence_headers(view),
        )
    except DomainError as exc:
        _fail(exc)
