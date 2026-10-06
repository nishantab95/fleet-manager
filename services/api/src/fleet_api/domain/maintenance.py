from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fleet_api.auth.service import AuthContext, ensure_role
from fleet_api.db.models import (
    Assignment,
    FleetAsset,
    HourMeterReading,
    KmReading,
    MaintenanceAttachment,
    MaintenanceCriterion,
    MaintenanceRecord,
    MaintenanceSchedule,
    MaintenanceWorkOrder,
    OperationalEvent,
)
from fleet_api.domain.assets import capabilities_for_asset
from fleet_api.domain.audit import write_audit_log
from fleet_api.domain.enums import (
    MaintenanceBasis,
    MaintenanceCriterionBasis,
    MaintenanceDueStatus,
    MaintenanceScheduleStatus,
    MaintenanceWorkOrderStatus,
    MembershipRole,
    VerificationStatus,
)
from fleet_api.domain.errors import ConflictError, DomainError, NotFoundError

BUILT_IN_MAINTENANCE_TYPES = frozenset(
    {
        "ENGINE_OIL",
        "HYDRAULIC_OIL",
        "TRANSMISSION_OIL",
        "AIR_FILTER",
        "FUEL_FILTER",
        "TYRES",
        "BRAKES",
        "BATTERY",
        "GREASING",
        "GENERAL_SERVICE",
        "FITNESS_INSPECTION",
        "CUSTOM",
    }
)


@dataclass(frozen=True)
class MaintenanceScheduleView:
    schedule: MaintenanceSchedule
    current_meter: Decimal | None
    due_status: MaintenanceDueStatus
    criteria: tuple[MaintenanceCriterionView, ...] = ()


@dataclass(frozen=True)
class MaintenanceCriterionView:
    criterion: MaintenanceCriterion
    current_value: Decimal | None
    due_status: MaintenanceDueStatus


def _criterion_basis(basis: MaintenanceBasis) -> MaintenanceCriterionBasis:
    return {
        MaintenanceBasis.KM: MaintenanceCriterionBasis.ODOMETER_KM,
        MaintenanceBasis.HMR: MaintenanceCriterionBasis.HOUR_METER_HOURS,
        MaintenanceBasis.DATE: MaintenanceCriterionBasis.CALENDAR_TIME,
    }[basis]


def _legacy_basis(basis: MaintenanceCriterionBasis) -> MaintenanceBasis:
    return {
        MaintenanceCriterionBasis.ODOMETER_KM: MaintenanceBasis.KM,
        MaintenanceCriterionBasis.HOUR_METER_HOURS: MaintenanceBasis.HMR,
        MaintenanceCriterionBasis.CALENDAR_TIME: MaintenanceBasis.DATE,
    }[basis]


def _maintenance_type(value: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", value.strip().upper()).strip("_")
    if normalized not in BUILT_IN_MAINTENANCE_TYPES:
        raise DomainError("maintenance_type is not supported")
    return normalized


def _clean(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def _money(value: Decimal) -> Decimal:
    if not value.is_finite() or value < 0 or value > Decimal("999999999999.99"):
        raise DomainError("cost must be finite, non-negative, and within storage limits")
    return value.quantize(Decimal("0.01"))


def maintenance_due_status(
    *,
    basis: MaintenanceBasis,
    next_due_meter: Decimal | None,
    next_due_date: date | None,
    current_meter: Decimal | None,
    as_of: date,
    warning_threshold: Decimal,
) -> MaintenanceDueStatus:
    """Classify due state without ever treating unknown readings as zero."""

    if basis == MaintenanceBasis.DATE:
        if next_due_date is None:
            return MaintenanceDueStatus.UNKNOWN
        days_remaining = Decimal((next_due_date - as_of).days)
        if days_remaining < 0:
            return MaintenanceDueStatus.OVERDUE
        if days_remaining == 0:
            return MaintenanceDueStatus.DUE
        if days_remaining <= warning_threshold:
            return MaintenanceDueStatus.DUE_SOON
        return MaintenanceDueStatus.NOT_DUE
    if next_due_meter is None or current_meter is None:
        return MaintenanceDueStatus.UNKNOWN
    remaining = next_due_meter - current_meter
    if remaining < 0:
        return MaintenanceDueStatus.OVERDUE
    if remaining == 0:
        return MaintenanceDueStatus.DUE
    if remaining <= warning_threshold:
        return MaintenanceDueStatus.DUE_SOON
    return MaintenanceDueStatus.NOT_DUE


class MaintenanceService:
    """Owner-only, tenant-scoped maintenance lifecycle."""

    def __init__(
        self,
        session: Session,
        context: AuthContext,
        *,
        request_id: str | None = None,
    ) -> None:
        ensure_role(context, MembershipRole.OWNER_ADMIN)
        self.session = session
        self.company_id = context.company.id
        self.actor_id = context.membership.id
        self.request_id = request_id

    def _asset(self, asset_id: UUID) -> FleetAsset:
        asset = self.session.scalar(
            select(FleetAsset).where(
                FleetAsset.company_id == self.company_id,
                FleetAsset.id == asset_id,
            )
        )
        if asset is None:
            raise NotFoundError("asset not found")
        return asset

    def _schedule(self, schedule_id: UUID, *, lock: bool = False) -> MaintenanceSchedule:
        query = select(MaintenanceSchedule).where(
            MaintenanceSchedule.company_id == self.company_id,
            MaintenanceSchedule.id == schedule_id,
        )
        if lock:
            query = query.with_for_update()
        schedule = self.session.scalar(query)
        if schedule is None:
            raise NotFoundError("maintenance schedule not found")
        return schedule

    def _work_order(self, work_order_id: UUID, *, lock: bool = False) -> MaintenanceWorkOrder:
        query = select(MaintenanceWorkOrder).where(
            MaintenanceWorkOrder.company_id == self.company_id,
            MaintenanceWorkOrder.id == work_order_id,
        )
        if lock:
            query = query.with_for_update()
        work_order = self.session.scalar(query)
        if work_order is None:
            raise NotFoundError("maintenance work order not found")
        return work_order

    @staticmethod
    def _validate_basis(asset: FleetAsset, basis: MaintenanceBasis) -> None:
        capabilities = capabilities_for_asset(asset)
        if basis == MaintenanceBasis.KM and not capabilities.supports_odometer:
            raise DomainError("KM maintenance is not supported for this asset type")
        if basis == MaintenanceBasis.HMR and not capabilities.supports_hour_meter:
            raise DomainError("HMR maintenance is not supported for this asset type")

    @staticmethod
    def _validate_interval(
        basis: MaintenanceBasis, value: Decimal, warning_threshold: Decimal
    ) -> None:
        if not value.is_finite() or value <= 0 or value > Decimal("9999999999.99"):
            raise DomainError("interval_value must be positive and within storage limits")
        if basis == MaintenanceBasis.DATE and value != value.to_integral_value():
            raise DomainError("DATE interval_value must be a whole number of days")
        if not warning_threshold.is_finite() or warning_threshold < 0 or warning_threshold > value:
            raise DomainError("warning_threshold must be between zero and interval_value")
        if (
            basis == MaintenanceBasis.DATE
            and warning_threshold != warning_threshold.to_integral_value()
        ):
            raise DomainError("DATE warning_threshold must be a whole number of days")

    def current_meter(self, asset_id: UUID, basis: MaintenanceBasis) -> Decimal | None:
        """Return the maximum approved/amended Fleet Manager reading for the asset."""

        if basis == MaintenanceBasis.DATE:
            return None
        reading = KmReading if basis == MaintenanceBasis.KM else HourMeterReading
        return self.session.scalar(
            select(func.max(reading.reading_value))
            .join(OperationalEvent, OperationalEvent.id == reading.event_id)
            .join(Assignment, Assignment.id == OperationalEvent.assignment_id)
            .where(
                OperationalEvent.company_id == self.company_id,
                Assignment.company_id == self.company_id,
                Assignment.asset_id == asset_id,
                OperationalEvent.verification_status.in_(
                    [VerificationStatus.APPROVED, VerificationStatus.AMENDED]
                ),
            )
        )

    def _view(self, schedule: MaintenanceSchedule, *, as_of: date) -> MaintenanceScheduleView:
        criteria = list(
            self.session.scalars(
                select(MaintenanceCriterion)
                .where(
                    MaintenanceCriterion.company_id == self.company_id,
                    MaintenanceCriterion.schedule_id == schedule.id,
                )
                .order_by(MaintenanceCriterion.created_at, MaintenanceCriterion.id)
            )
        )
        criterion_views: list[MaintenanceCriterionView] = []
        for criterion in criteria:
            legacy_basis = _legacy_basis(criterion.basis)
            current = self.current_meter(schedule.asset_id, legacy_basis)
            criterion_views.append(
                MaintenanceCriterionView(
                    criterion,
                    current,
                    maintenance_due_status(
                        basis=legacy_basis,
                        next_due_meter=criterion.next_due_value,
                        next_due_date=criterion.next_due_date,
                        current_meter=current,
                        as_of=as_of,
                        warning_threshold=criterion.warning_threshold,
                    ),
                )
            )
        if not criterion_views:
            current = self.current_meter(schedule.asset_id, schedule.interval_basis)
            state = maintenance_due_status(
                basis=schedule.interval_basis,
                next_due_meter=schedule.next_due_meter,
                next_due_date=schedule.next_due_date,
                current_meter=current,
                as_of=as_of,
                warning_threshold=schedule.warning_threshold,
            )
            return MaintenanceScheduleView(schedule, current, state)
        severity = {
            MaintenanceDueStatus.UNKNOWN: 0,
            MaintenanceDueStatus.NOT_DUE: 1,
            MaintenanceDueStatus.DUE_SOON: 2,
            MaintenanceDueStatus.DUE: 3,
            MaintenanceDueStatus.OVERDUE: 4,
        }
        overall = max(criterion_views, key=lambda item: severity[item.due_status]).due_status
        primary = next(
            (
                item
                for item in criterion_views
                if item.criterion.basis == _criterion_basis(schedule.interval_basis)
            ),
            criterion_views[0],
        )
        return MaintenanceScheduleView(
            schedule, primary.current_value, overall, tuple(criterion_views)
        )

    def create_schedule(
        self,
        *,
        asset_id: UUID,
        maintenance_type: str,
        interval_basis: MaintenanceBasis,
        interval_value: Decimal,
        last_service_meter: Decimal | None,
        last_service_date: date | None,
        notes: str | None,
        custom_label: str | None = None,
        description: str | None = None,
        warning_threshold: Decimal = Decimal("0"),
    ) -> MaintenanceSchedule:
        asset = self._asset(asset_id)
        self._validate_basis(asset, interval_basis)
        self._validate_interval(interval_basis, interval_value, warning_threshold)
        normalized_type = _maintenance_type(maintenance_type)
        normalized_label = _clean(custom_label)
        if normalized_type == "CUSTOM" and not normalized_label:
            raise DomainError("custom_label is required for CUSTOM maintenance")
        if normalized_type != "CUSTOM" and normalized_label:
            raise DomainError("custom_label is only allowed for CUSTOM maintenance")
        if interval_basis == MaintenanceBasis.DATE:
            if last_service_meter is not None:
                raise DomainError("DATE maintenance cannot contain a meter value")
            next_due_date = (
                last_service_date + timedelta(days=int(interval_value))
                if last_service_date is not None
                else None
            )
            next_due_meter = None
        else:
            if last_service_meter is not None and last_service_meter < 0:
                raise DomainError("last_service_meter cannot be negative")
            next_due_meter = (
                last_service_meter + interval_value if last_service_meter is not None else None
            )
            next_due_date = None
        schedule = MaintenanceSchedule(
            company_id=self.company_id,
            asset_id=asset.id,
            maintenance_type=normalized_type,
            custom_label=normalized_label,
            description=_clean(description),
            interval_basis=interval_basis,
            interval_value=interval_value,
            warning_threshold=warning_threshold,
            last_service_meter=last_service_meter,
            last_service_date=last_service_date,
            next_due_meter=next_due_meter,
            next_due_date=next_due_date,
            status=MaintenanceScheduleStatus.ACTIVE,
            notes=_clean(notes),
            created_by=self.actor_id,
        )
        self.session.add(schedule)
        self.session.flush()
        self.session.add(
            MaintenanceCriterion(
                company_id=self.company_id,
                schedule_id=schedule.id,
                basis=_criterion_basis(interval_basis),
                interval_value=interval_value,
                warning_threshold=warning_threshold,
                last_baseline_value=last_service_meter,
                last_baseline_date=last_service_date,
                next_due_value=next_due_meter,
                next_due_date=next_due_date,
                created_by=self.actor_id,
            )
        )
        self.session.flush()
        self._audit(
            "MAINTENANCE_SCHEDULE_CREATED",
            "MAINTENANCE_SCHEDULE",
            schedule.id,
            {
                "asset_id": str(asset.id),
                "maintenance_type": normalized_type,
                "interval_basis": interval_basis.value,
                "interval_value": str(interval_value),
            },
        )
        return schedule

    def add_criterion(
        self,
        schedule_id: UUID,
        *,
        basis: MaintenanceCriterionBasis,
        interval_value: Decimal,
        warning_threshold: Decimal,
        last_baseline_value: Decimal | None = None,
        last_baseline_date: date | None = None,
    ) -> MaintenanceCriterion:
        schedule = self._schedule(schedule_id, lock=True)
        asset = self._asset(schedule.asset_id)
        legacy_basis = _legacy_basis(basis)
        self._validate_basis(asset, legacy_basis)
        self._validate_interval(legacy_basis, interval_value, warning_threshold)
        existing = self.session.scalar(
            select(MaintenanceCriterion.id).where(
                MaintenanceCriterion.company_id == self.company_id,
                MaintenanceCriterion.schedule_id == schedule.id,
                MaintenanceCriterion.basis == basis,
            )
        )
        if existing is not None:
            raise ConflictError("this maintenance criterion already exists")
        if basis == MaintenanceCriterionBasis.CALENDAR_TIME:
            if last_baseline_value is not None:
                raise DomainError("calendar criteria cannot contain a meter baseline")
            next_due_value = None
            next_due_date = (
                last_baseline_date + timedelta(days=int(interval_value))
                if last_baseline_date is not None
                else None
            )
        else:
            if last_baseline_date is not None:
                raise DomainError("meter criteria cannot contain a date baseline")
            if last_baseline_value is not None and last_baseline_value < 0:
                raise DomainError("meter baseline cannot be negative")
            next_due_value = (
                last_baseline_value + interval_value if last_baseline_value is not None else None
            )
            next_due_date = None
        criterion = MaintenanceCriterion(
            company_id=self.company_id,
            schedule_id=schedule.id,
            basis=basis,
            interval_value=interval_value,
            warning_threshold=warning_threshold,
            last_baseline_value=last_baseline_value,
            last_baseline_date=last_baseline_date,
            next_due_value=next_due_value,
            next_due_date=next_due_date,
            created_by=self.actor_id,
        )
        self.session.add(criterion)
        self.session.flush()
        self._audit(
            "MAINTENANCE_CRITERION_ADDED",
            "MAINTENANCE_CRITERION",
            criterion.id,
            {"schedule_id": str(schedule.id), "basis": basis.value},
        )
        return criterion

    def set_schedule_status(
        self, schedule_id: UUID, status: MaintenanceScheduleStatus
    ) -> MaintenanceSchedule:
        schedule = self._schedule(schedule_id, lock=True)
        before = schedule.status
        schedule.status = status
        self.session.flush()
        self._audit(
            "MAINTENANCE_SCHEDULE_STATUS_CHANGED",
            "MAINTENANCE_SCHEDULE",
            schedule.id,
            {"status": status.value},
            old_values={"status": before.value},
        )
        return schedule

    def list_schedule_views(
        self, *, asset_id: UUID | None = None, as_of: date
    ) -> list[MaintenanceScheduleView]:
        query = select(MaintenanceSchedule).where(MaintenanceSchedule.company_id == self.company_id)
        if asset_id is not None:
            self._asset(asset_id)
            query = query.where(MaintenanceSchedule.asset_id == asset_id)
        return [
            self._view(item, as_of=as_of)
            for item in self.session.scalars(
                query.order_by(MaintenanceSchedule.created_at, MaintenanceSchedule.id)
            )
        ]

    def list_schedules(self, *, asset_id: UUID | None = None) -> list[MaintenanceSchedule]:
        return [
            view.schedule
            for view in self.list_schedule_views(asset_id=asset_id, as_of=date.today())
        ]

    def create_work_order(
        self,
        *,
        asset_id: UUID,
        schedule_id: UUID | None,
        title: str,
        description: str | None,
        vendor_name: str | None,
        scheduled_for: date | None,
        notes: str | None,
    ) -> MaintenanceWorkOrder:
        self._asset(asset_id)
        if schedule_id is not None:
            schedule = self._schedule(schedule_id)
            if schedule.asset_id != asset_id:
                raise DomainError("work order schedule belongs to another asset")
        clean_title = title.strip()
        if not clean_title:
            raise DomainError("work order title is required")
        work_order = MaintenanceWorkOrder(
            company_id=self.company_id,
            asset_id=asset_id,
            schedule_id=schedule_id,
            title=clean_title,
            description=_clean(description),
            status=(
                MaintenanceWorkOrderStatus.SCHEDULED
                if scheduled_for is not None
                else MaintenanceWorkOrderStatus.DRAFT
            ),
            vendor_name=_clean(vendor_name),
            scheduled_for=scheduled_for,
            labor_cost=Decimal("0"),
            parts_cost=Decimal("0"),
            other_cost=Decimal("0"),
            notes=_clean(notes),
            created_by=self.actor_id,
        )
        self.session.add(work_order)
        self.session.flush()
        self._audit(
            "MAINTENANCE_WORK_ORDER_CREATED",
            "MAINTENANCE_WORK_ORDER",
            work_order.id,
            {"asset_id": str(asset_id), "status": work_order.status.value},
        )
        return work_order

    def update_work_order_status(
        self,
        work_order_id: UUID,
        new_status: MaintenanceWorkOrderStatus,
    ) -> MaintenanceWorkOrder:
        work_order = self._work_order(work_order_id, lock=True)
        allowed = {
            MaintenanceWorkOrderStatus.DRAFT: {
                MaintenanceWorkOrderStatus.SCHEDULED,
                MaintenanceWorkOrderStatus.IN_PROGRESS,
                MaintenanceWorkOrderStatus.CANCELLED,
            },
            MaintenanceWorkOrderStatus.SCHEDULED: {
                MaintenanceWorkOrderStatus.IN_PROGRESS,
                MaintenanceWorkOrderStatus.CANCELLED,
            },
            MaintenanceWorkOrderStatus.IN_PROGRESS: {MaintenanceWorkOrderStatus.CANCELLED},
            MaintenanceWorkOrderStatus.COMPLETED: set(),
            MaintenanceWorkOrderStatus.CANCELLED: set(),
        }
        if new_status == MaintenanceWorkOrderStatus.COMPLETED:
            raise DomainError("use the completion action to complete a work order")
        if new_status not in allowed[work_order.status]:
            raise ConflictError(
                f"cannot move work order from {work_order.status.value} to {new_status.value}"
            )
        previous = work_order.status
        work_order.status = new_status
        if new_status == MaintenanceWorkOrderStatus.IN_PROGRESS:
            work_order.started_at = datetime.now(UTC)
        self.session.flush()
        self._audit(
            "MAINTENANCE_WORK_ORDER_STATUS_CHANGED",
            "MAINTENANCE_WORK_ORDER",
            work_order.id,
            {"status": new_status.value},
            old_values={"status": previous.value},
        )
        return work_order

    def complete_work_order(
        self,
        work_order_id: UUID,
        *,
        performed_on: date,
        meter_value: Decimal | None,
        vendor_name: str | None,
        labor_cost: Decimal,
        parts_cost: Decimal,
        other_cost: Decimal,
        notes: str | None,
        odometer_km: Decimal | None = None,
        hour_meter_hours: Decimal | None = None,
    ) -> tuple[MaintenanceWorkOrder, MaintenanceRecord]:
        work_order = self._work_order(work_order_id, lock=True)
        if work_order.status not in {
            MaintenanceWorkOrderStatus.DRAFT,
            MaintenanceWorkOrderStatus.SCHEDULED,
            MaintenanceWorkOrderStatus.IN_PROGRESS,
        }:
            raise ConflictError("work order cannot be completed from its current state")
        if work_order.schedule_id is None:
            raise DomainError("a schedule is required before completing a work order")
        schedule = self._schedule(work_order.schedule_id, lock=True)
        record = self._record_completion(
            schedule,
            performed_on=performed_on,
            meter_value=meter_value,
            odometer_km=odometer_km,
            hour_meter_hours=hour_meter_hours,
            notes=notes,
            vendor_name=vendor_name,
            labor_cost=_money(labor_cost),
            parts_cost=_money(parts_cost),
            other_cost=_money(other_cost),
            work_order_id=work_order.id,
        )
        work_order.status = MaintenanceWorkOrderStatus.COMPLETED
        work_order.completed_at = datetime.now(UTC)
        work_order.completion_meter = meter_value
        work_order.completion_odometer_km = record.completion_odometer_km
        work_order.completion_hour_meter = record.completion_hour_meter
        work_order.vendor_name = _clean(vendor_name) or work_order.vendor_name
        work_order.labor_cost = record.labor_cost
        work_order.parts_cost = record.parts_cost
        work_order.other_cost = record.other_cost
        work_order.notes = _clean(notes) or work_order.notes
        self.session.flush()
        self._audit(
            "MAINTENANCE_WORK_ORDER_COMPLETED",
            "MAINTENANCE_WORK_ORDER",
            work_order.id,
            {"record_id": str(record.id), "schedule_id": str(schedule.id)},
        )
        return work_order, record

    def add_record(
        self,
        *,
        schedule_id: UUID,
        performed_on: date,
        meter_value: Decimal | None,
        notes: str | None,
        odometer_km: Decimal | None = None,
        hour_meter_hours: Decimal | None = None,
    ) -> MaintenanceRecord:
        schedule = self._schedule(schedule_id, lock=True)
        return self._record_completion(
            schedule,
            performed_on=performed_on,
            meter_value=meter_value,
            odometer_km=odometer_km,
            hour_meter_hours=hour_meter_hours,
            notes=notes,
            vendor_name=None,
            labor_cost=Decimal("0"),
            parts_cost=Decimal("0"),
            other_cost=Decimal("0"),
            work_order_id=None,
        )

    def _record_completion(
        self,
        schedule: MaintenanceSchedule,
        *,
        performed_on: date,
        meter_value: Decimal | None,
        odometer_km: Decimal | None,
        hour_meter_hours: Decimal | None,
        notes: str | None,
        vendor_name: str | None,
        labor_cost: Decimal,
        parts_cost: Decimal,
        other_cost: Decimal,
        work_order_id: UUID | None,
    ) -> MaintenanceRecord:
        if schedule.status != MaintenanceScheduleStatus.ACTIVE:
            raise DomainError("maintenance schedule is inactive")
        if schedule.last_service_date is not None and performed_on < schedule.last_service_date:
            raise DomainError("maintenance record cannot precede the last service date")
        if meter_value is not None:
            if schedule.interval_basis == MaintenanceBasis.KM and odometer_km is None:
                odometer_km = meter_value
            elif schedule.interval_basis == MaintenanceBasis.HMR and hour_meter_hours is None:
                hour_meter_hours = meter_value
            elif schedule.interval_basis == MaintenanceBasis.DATE:
                raise DomainError("DATE maintenance records cannot contain a meter value")
        supplied = {
            MaintenanceCriterionBasis.ODOMETER_KM: odometer_km,
            MaintenanceCriterionBasis.HOUR_METER_HOURS: hour_meter_hours,
        }
        for value in supplied.values():
            if value is not None and (not value.is_finite() or value < 0):
                raise DomainError("completion meters must be finite and non-negative")
        criteria = list(
            self.session.scalars(
                select(MaintenanceCriterion).where(
                    MaintenanceCriterion.company_id == self.company_id,
                    MaintenanceCriterion.schedule_id == schedule.id,
                )
            )
        )
        for criterion in criteria:
            if criterion.basis == MaintenanceCriterionBasis.CALENDAR_TIME:
                criterion.last_baseline_date = performed_on
                criterion.next_due_date = performed_on + timedelta(
                    days=int(criterion.interval_value)
                )
                continue
            value = supplied[criterion.basis]
            if value is None:
                continue
            if criterion.last_baseline_value is not None and value < criterion.last_baseline_value:
                raise DomainError("maintenance meter value cannot move backwards")
            criterion.last_baseline_value = value
            criterion.next_due_value = value + criterion.interval_value
        primary_value = supplied.get(_criterion_basis(schedule.interval_basis))
        if schedule.interval_basis == MaintenanceBasis.DATE:
            schedule.next_due_date = performed_on + timedelta(days=int(schedule.interval_value))
        elif primary_value is not None:
            if (
                schedule.last_service_meter is not None
                and primary_value < schedule.last_service_meter
            ):
                raise DomainError("maintenance meter value cannot move backwards")
            schedule.last_service_meter = primary_value
            schedule.next_due_meter = primary_value + schedule.interval_value
        elif len(criteria) <= 1:
            raise DomainError("meter maintenance requires its corresponding meter value")
        schedule.last_service_date = performed_on
        record = MaintenanceRecord(
            company_id=self.company_id,
            schedule_id=schedule.id,
            work_order_id=work_order_id,
            asset_id=schedule.asset_id,
            performed_on=performed_on,
            meter_value=meter_value,
            completion_odometer_km=odometer_km,
            completion_hour_meter=hour_meter_hours,
            notes=_clean(notes),
            vendor_name=_clean(vendor_name),
            labor_cost=labor_cost,
            parts_cost=parts_cost,
            other_cost=other_cost,
            created_by=self.actor_id,
        )
        self.session.add(record)
        self.session.flush()
        self._audit(
            "MAINTENANCE_RECORDED",
            "MAINTENANCE_RECORD",
            record.id,
            {
                "schedule_id": str(schedule.id),
                "asset_id": str(schedule.asset_id),
                "performed_on": performed_on.isoformat(),
                "meter_value": str(meter_value) if meter_value is not None else None,
            },
        )
        return record

    def list_work_orders(
        self, *, status: MaintenanceWorkOrderStatus | None = None
    ) -> list[MaintenanceWorkOrder]:
        query = select(MaintenanceWorkOrder).where(
            MaintenanceWorkOrder.company_id == self.company_id
        )
        if status is not None:
            query = query.where(MaintenanceWorkOrder.status == status)
        return list(
            self.session.scalars(
                query.order_by(MaintenanceWorkOrder.created_at.desc(), MaintenanceWorkOrder.id)
            )
        )

    def list_records(self, schedule_id: UUID | None = None) -> list[MaintenanceRecord]:
        query = select(MaintenanceRecord).where(MaintenanceRecord.company_id == self.company_id)
        if schedule_id is not None:
            self._schedule(schedule_id)
            query = query.where(MaintenanceRecord.schedule_id == schedule_id)
            return list(
                self.session.scalars(
                    query.order_by(MaintenanceRecord.performed_on, MaintenanceRecord.created_at)
                )
            )
        return list(
            self.session.scalars(
                query.order_by(
                    MaintenanceRecord.performed_on.desc(),
                    MaintenanceRecord.created_at.desc(),
                )
            )
        )

    def add_attachment(
        self,
        *,
        work_order_id: UUID,
        evidence_object_id: UUID,
        file_name: str,
    ) -> MaintenanceAttachment:
        self._work_order(work_order_id)
        attachment = MaintenanceAttachment(
            company_id=self.company_id,
            work_order_id=work_order_id,
            evidence_object_id=evidence_object_id,
            file_name=file_name.strip() or "attachment",
            created_by=self.actor_id,
        )
        self.session.add(attachment)
        self.session.flush()
        self._audit(
            "MAINTENANCE_ATTACHMENT_ADDED",
            "MAINTENANCE_WORK_ORDER",
            work_order_id,
            {"evidence_object_id": str(evidence_object_id)},
        )
        return attachment

    def _audit(
        self,
        action: str,
        entity_type: str,
        entity_id: UUID,
        new_values: dict[str, object],
        *,
        old_values: dict[str, object] | None = None,
    ) -> None:
        write_audit_log(
            self.session,
            company_id=self.company_id,
            actor_membership_id=self.actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_values=old_values,
            new_values=new_values,
            request_id=self.request_id,
        )
