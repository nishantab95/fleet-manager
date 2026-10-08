from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from fleet_api.auth.service import AuthContext
from fleet_api.db.models import (
    AssetSiteDeployment,
    Assignment,
    FleetAsset,
    HourMeterReading,
    KmReading,
    MaintenanceCriterion,
    MaintenancePlan,
    MaintenanceRecord,
    MaintenanceSchedule,
    MaintenanceTemplate,
    MaintenanceTemplateCriterion,
    MaintenanceTemplateItem,
    MaintenanceWorkOrder,
    OperationalEvent,
    Site,
)
from fleet_api.domain.audit import write_audit_log
from fleet_api.domain.enums import (
    AssetOwnershipType,
    FleetAssetType,
    MaintenanceActionType,
    MaintenanceCriterionBasis,
    MaintenanceDueState,
    MaintenancePlanSource,
    MaintenanceResponsibility,
    MaintenanceTaskCode,
    MaintenanceTemplateSourceType,
    MaintenanceTemplateVerificationStatus,
    MaintenanceWorkOrderStatus,
    VerificationStatus,
)
from fleet_api.domain.errors import ConflictError, DomainError, NotFoundError


@dataclass(frozen=True)
class TaskCatalogEntry:
    code: MaintenanceTaskCode
    label: str
    default_action: MaintenanceActionType
    wheeled_default: bool
    tracked_default: bool


TASK_CATALOG = (
    TaskCatalogEntry(
        MaintenanceTaskCode.ENGINE_SERVICE,
        "Engine Service",
        MaintenanceActionType.SERVICE,
        True,
        True,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.ENGINE_OIL, "Engine Oil", MaintenanceActionType.REPLACE, True, True
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.ENGINE_OIL_FILTER,
        "Engine Oil Filter",
        MaintenanceActionType.REPLACE,
        True,
        True,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.AIR_FILTER_CLEAN,
        "Air Filter Cleaning",
        MaintenanceActionType.CLEAN,
        True,
        True,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.AIR_FILTER_REPLACE,
        "Air Filter Replacement",
        MaintenanceActionType.REPLACE,
        True,
        True,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.FUEL_FILTER, "Fuel Filter", MaintenanceActionType.REPLACE, True, True
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.GREASING, "Greasing", MaintenanceActionType.LUBRICATE, True, True
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.TYRE_PRESSURE_CHECK,
        "Tyre Pressure Check",
        MaintenanceActionType.INSPECT,
        True,
        False,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.TYRE_INSPECTION,
        "Tyre Inspection",
        MaintenanceActionType.INSPECT,
        True,
        False,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.TYRE_ROTATION,
        "Tyre Rotation",
        MaintenanceActionType.SERVICE,
        True,
        False,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.TYRE_REPLACEMENT,
        "Tyre Replacement",
        MaintenanceActionType.REPLACE,
        True,
        False,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.HUB_SERVICE, "Hub Service", MaintenanceActionType.SERVICE, True, False
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.WHEEL_BEARING_INSPECTION,
        "Wheel Bearing Inspection",
        MaintenanceActionType.INSPECT,
        True,
        False,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.BRAKE_INSPECTION,
        "Brake Inspection",
        MaintenanceActionType.INSPECT,
        True,
        False,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.BRAKE_SERVICE,
        "Brake Service",
        MaintenanceActionType.SERVICE,
        True,
        False,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.TRANSMISSION_SERVICE,
        "Transmission Service",
        MaintenanceActionType.SERVICE,
        True,
        False,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.DIFFERENTIAL_OIL,
        "Differential Oil",
        MaintenanceActionType.REPLACE,
        True,
        False,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.HYDRAULIC_OIL,
        "Hydraulic Oil",
        MaintenanceActionType.REPLACE,
        True,
        True,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.HYDRAULIC_FILTER,
        "Hydraulic Filter",
        MaintenanceActionType.REPLACE,
        True,
        True,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.HYDRAULIC_HOSE_INSPECTION,
        "Hydraulic Hose Inspection",
        MaintenanceActionType.INSPECT,
        True,
        True,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.COOLANT, "Coolant Service", MaintenanceActionType.SERVICE, True, True
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.BATTERY_INSPECTION,
        "Battery Inspection",
        MaintenanceActionType.INSPECT,
        True,
        True,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.BELT_HOSE_INSPECTION,
        "Belt / Hose Inspection",
        MaintenanceActionType.INSPECT,
        True,
        True,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.UNDERCARRIAGE_INSPECTION,
        "Undercarriage Inspection",
        MaintenanceActionType.INSPECT,
        False,
        True,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.TRACK_TENSION_CHECK,
        "Track Tension Check",
        MaintenanceActionType.INSPECT,
        False,
        True,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.SWING_BEARING_GREASING,
        "Swing Bearing Greasing",
        MaintenanceActionType.LUBRICATE,
        False,
        True,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.GENERAL_INSPECTION,
        "General Inspection",
        MaintenanceActionType.INSPECT,
        True,
        True,
    ),
    TaskCatalogEntry(
        MaintenanceTaskCode.CUSTOM, "Custom task", MaintenanceActionType.SERVICE, True, True
    ),
)
TASK_BY_CODE = {entry.code: entry for entry in TASK_CATALOG}


@dataclass(frozen=True)
class CriterionInput:
    basis: MaintenanceCriterionBasis
    interval_value: Decimal
    warning_value: Decimal
    baseline_value: Decimal | None = None
    baseline_date: date | None = None
    enabled: bool = True


@dataclass(frozen=True)
class CriterionEvaluation:
    basis: MaintenanceCriterionBasis
    state: MaintenanceDueState
    current_value: Decimal | None
    due_value: Decimal | None
    current_date: date | None
    due_date: date | None
    warning_value: Decimal


@dataclass(frozen=True)
class ScheduleEvaluation:
    schedule: MaintenanceSchedule
    asset: FleetAsset
    site_name: str | None
    state: MaintenanceDueState
    triggered_by: tuple[MaintenanceCriterionBasis, ...]
    criteria: tuple[CriterionEvaluation, ...]


_STATE_RANK = {
    MaintenanceDueState.UNKNOWN: -1,
    MaintenanceDueState.NOT_DUE: 0,
    MaintenanceDueState.DUE_SOON: 1,
    MaintenanceDueState.DUE: 2,
    MaintenanceDueState.OVERDUE: 3,
}


def evaluate_criterion(
    criterion: MaintenanceCriterion,
    *,
    current_odometer_km: Decimal | None,
    current_hour_meter: Decimal | None,
    as_of: date,
) -> CriterionEvaluation:
    due_value: Decimal | None = None
    current_value: Decimal | None = None
    due_date: date | None = None
    current_date: date | None = None
    if criterion.basis == MaintenanceCriterionBasis.CALENDAR_DAYS:
        current_date = as_of
        if criterion.baseline_date is None:
            state = MaintenanceDueState.UNKNOWN
        else:
            due_date = criterion.baseline_date + timedelta(days=int(criterion.interval_value))
            warning_date = due_date - timedelta(days=int(criterion.warning_value))
            if as_of > due_date:
                state = MaintenanceDueState.OVERDUE
            elif as_of == due_date:
                state = MaintenanceDueState.DUE
            elif as_of >= warning_date:
                state = MaintenanceDueState.DUE_SOON
            else:
                state = MaintenanceDueState.NOT_DUE
    else:
        current_value = (
            current_odometer_km
            if criterion.basis == MaintenanceCriterionBasis.ODOMETER_KM
            else current_hour_meter
        )
        if criterion.baseline_value is None or current_value is None:
            state = MaintenanceDueState.UNKNOWN
        else:
            due_value = criterion.baseline_value + criterion.interval_value
            if current_value > due_value:
                state = MaintenanceDueState.OVERDUE
            elif current_value == due_value:
                state = MaintenanceDueState.DUE
            elif current_value >= due_value - criterion.warning_value:
                state = MaintenanceDueState.DUE_SOON
            else:
                state = MaintenanceDueState.NOT_DUE
    return CriterionEvaluation(
        basis=criterion.basis,
        state=state,
        current_value=current_value,
        due_value=due_value,
        current_date=current_date,
        due_date=due_date,
        warning_value=criterion.warning_value,
    )


def overall_due_state(
    criteria: tuple[CriterionEvaluation, ...],
) -> tuple[MaintenanceDueState, tuple[MaintenanceCriterionBasis, ...]]:
    known = [item for item in criteria if item.state != MaintenanceDueState.UNKNOWN]
    if not known:
        return MaintenanceDueState.UNKNOWN, ()
    best_rank = max(_STATE_RANK[item.state] for item in known)
    state = next(state for state, rank in _STATE_RANK.items() if rank == best_rank)
    return state, tuple(item.basis for item in known if item.state == state)


def task_label(code: MaintenanceTaskCode, custom_label: str | None) -> str:
    return custom_label or TASK_BY_CODE[code].label


def company_manages_maintenance(asset: FleetAsset) -> bool:
    """Return whether the Asset's current tenant is authoritative for service.

    Current Pilot rental links are disabled, so a rented Asset remains
    externally maintained even though its operational meters stay fully active.
    The explicit responsibility value keeps this rule extensible without
    conflating meter capabilities with ownership.
    """

    return (
        asset.ownership_type == AssetOwnershipType.OWNED
        and asset.maintenance_responsibility
        in {
            MaintenanceResponsibility.OWNER_COMPANY,
            MaintenanceResponsibility.SHARED,
        }
    )


class MaintenanceService:
    """Owner-only tenant boundary for plans, templates, work orders, and history."""

    def __init__(
        self, session: Session, context: AuthContext, *, request_id: str | None = None
    ) -> None:
        self.session = session
        self.company_id = context.company.id
        self.actor_membership_id = context.membership.id
        self.request_id = request_id

    def _audit(
        self,
        action: str,
        entity_type: str,
        entity_id: UUID,
        *,
        old_values: dict[str, object] | None = None,
        new_values: dict[str, object] | None = None,
    ) -> None:
        write_audit_log(
            self.session,
            company_id=self.company_id,
            actor_membership_id=self.actor_membership_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_values=old_values,
            new_values=new_values,
            request_id=self.request_id,
        )

    def _asset(self, asset_id: UUID) -> FleetAsset:
        asset = self.session.scalar(
            select(FleetAsset).where(
                FleetAsset.company_id == self.company_id, FleetAsset.id == asset_id
            )
        )
        if asset is None:
            raise NotFoundError("asset was not found")
        return asset

    def _schedule(self, schedule_id: UUID) -> MaintenanceSchedule:
        schedule = self.session.scalar(
            select(MaintenanceSchedule).where(
                MaintenanceSchedule.company_id == self.company_id,
                MaintenanceSchedule.id == schedule_id,
            )
        )
        if schedule is None:
            raise NotFoundError("maintenance item was not found")
        return schedule

    def _maintenance_asset(self, asset_id: UUID) -> FleetAsset:
        asset = self._asset(asset_id)
        if not company_manages_maintenance(asset):
            raise DomainError("maintenance is managed by the rental owner")
        return asset

    def ensure_plan(
        self,
        asset_id: UUID,
        *,
        source: MaintenancePlanSource = MaintenancePlanSource.CUSTOM,
        source_template: MaintenanceTemplate | None = None,
        source_asset_id: UUID | None = None,
    ) -> MaintenancePlan:
        self._maintenance_asset(asset_id)
        plan = self.session.scalar(
            select(MaintenancePlan).where(
                MaintenancePlan.company_id == self.company_id,
                MaintenancePlan.asset_id == asset_id,
            )
        )
        if plan is not None:
            return plan
        plan = MaintenancePlan(
            company_id=self.company_id,
            asset_id=asset_id,
            source=source,
            source_template_id=source_template.id if source_template else None,
            source_template_version=source_template.version if source_template else None,
            source_asset_id=source_asset_id,
            created_by_membership_id=self.actor_membership_id,
        )
        self.session.add(plan)
        self.session.flush()
        self._audit(
            "MAINTENANCE_PLAN_CREATED",
            "MAINTENANCE_PLAN",
            plan.id,
            new_values={"asset_id": str(asset_id), "source": source.value},
        )
        return plan

    def _validate_criteria(self, asset: FleetAsset, criteria: list[CriterionInput]) -> None:
        enabled = [criterion for criterion in criteria if criterion.enabled]
        if not enabled:
            raise DomainError("at least one maintenance trigger must be enabled")
        bases = [criterion.basis for criterion in criteria]
        if len(bases) != len(set(bases)):
            raise DomainError("a maintenance trigger type may appear only once")
        for criterion in criteria:
            if criterion.interval_value <= 0:
                raise DomainError("maintenance interval must be greater than zero")
            if criterion.warning_value < 0 or criterion.warning_value >= criterion.interval_value:
                raise DomainError("warning threshold must be non-negative and below interval")
            if criterion.basis == MaintenanceCriterionBasis.ODOMETER_KM and (
                not asset.is_wheeled or not asset.supports_odometer_km
            ):
                raise DomainError(
                    "KM triggers are unavailable for a non-wheeled asset or one without an odometer"
                )
            if (
                criterion.basis == MaintenanceCriterionBasis.HOUR_METER_HOURS
                and not asset.supports_hour_meter
            ):
                raise DomainError(
                    "hour triggers are unavailable for an asset without an hour meter"
                )
            if criterion.basis == MaintenanceCriterionBasis.CALENDAR_DAYS:
                if criterion.interval_value != criterion.interval_value.to_integral_value():
                    raise DomainError("calendar interval must use whole days")
                if criterion.baseline_value is not None:
                    raise DomainError("calendar triggers use a date baseline")
            elif criterion.baseline_date is not None:
                raise DomainError("meter triggers use a numeric baseline")

    def save_schedule(
        self,
        asset_id: UUID,
        *,
        task_code: MaintenanceTaskCode,
        custom_label: str | None,
        action_type: MaintenanceActionType,
        description: str | None,
        enabled: bool,
        criteria: list[CriterionInput],
        schedule_id: UUID | None = None,
    ) -> MaintenanceSchedule:
        asset = self._maintenance_asset(asset_id)
        self._validate_criteria(asset, criteria)
        old_values: dict[str, object] | None
        clean_label = custom_label.strip() if custom_label else None
        if task_code == MaintenanceTaskCode.CUSTOM and not clean_label:
            raise DomainError("custom maintenance tasks require a label")
        if schedule_id is None:
            plan = self.ensure_plan(asset_id)
            schedule = MaintenanceSchedule(
                company_id=self.company_id,
                plan_id=plan.id,
                asset_id=asset_id,
                task_code=task_code,
                custom_label=clean_label,
                action_type=action_type,
                description=description.strip() if description else None,
                enabled=enabled,
                created_by_membership_id=self.actor_membership_id,
            )
            self.session.add(schedule)
            self.session.flush()
            action = "MAINTENANCE_ITEM_CREATED"
            old_values = None
        else:
            schedule = self._schedule(schedule_id)
            if schedule.asset_id != asset_id:
                raise NotFoundError("maintenance item was not found")
            old_values = {
                "task_code": schedule.task_code.value,
                "enabled": schedule.enabled,
            }
            schedule.task_code = task_code
            schedule.custom_label = clean_label
            schedule.action_type = action_type
            schedule.description = description.strip() if description else None
            schedule.enabled = enabled
            existing = self.session.scalars(
                select(MaintenanceCriterion).where(
                    MaintenanceCriterion.company_id == self.company_id,
                    MaintenanceCriterion.schedule_id == schedule.id,
                )
            ).all()
            for criterion in existing:
                self.session.delete(criterion)
            self.session.flush()
            action = "MAINTENANCE_ITEM_UPDATED"
        for item in criteria:
            self.session.add(
                MaintenanceCriterion(
                    company_id=self.company_id,
                    schedule_id=schedule.id,
                    basis=item.basis,
                    enabled=item.enabled,
                    interval_value=item.interval_value,
                    warning_value=item.warning_value,
                    baseline_value=item.baseline_value,
                    baseline_date=item.baseline_date,
                )
            )
        self.session.flush()
        self._audit(
            action,
            "MAINTENANCE_ITEM",
            schedule.id,
            old_values=old_values,
            new_values={
                "asset_id": str(asset_id),
                "task_code": task_code.value,
                "enabled": enabled,
                "triggers": [item.basis.value for item in criteria if item.enabled],
            },
        )
        return schedule

    def list_plan(self, asset_id: UUID) -> tuple[MaintenancePlan | None, list[MaintenanceSchedule]]:
        self._maintenance_asset(asset_id)
        plan = self.session.scalar(
            select(MaintenancePlan).where(
                MaintenancePlan.company_id == self.company_id,
                MaintenancePlan.asset_id == asset_id,
            )
        )
        if plan is None:
            return None, []
        schedules = list(
            self.session.scalars(
                select(MaintenanceSchedule)
                .where(
                    MaintenanceSchedule.company_id == self.company_id,
                    MaintenanceSchedule.plan_id == plan.id,
                )
                .order_by(MaintenanceSchedule.task_code, MaintenanceSchedule.id)
            ).all()
        )
        return plan, schedules

    def criteria_for(self, schedule_id: UUID) -> list[MaintenanceCriterion]:
        return list(
            self.session.scalars(
                select(MaintenanceCriterion)
                .where(
                    MaintenanceCriterion.company_id == self.company_id,
                    MaintenanceCriterion.schedule_id == schedule_id,
                )
                .order_by(MaintenanceCriterion.basis)
            ).all()
        )

    def remove_custom_schedule(self, schedule_id: UUID) -> None:
        schedule = self._schedule(schedule_id)
        self._maintenance_asset(schedule.asset_id)
        if schedule.task_code != MaintenanceTaskCode.CUSTOM:
            raise DomainError("catalog tasks must be disabled instead of removed")
        self._audit(
            "MAINTENANCE_CUSTOM_ITEM_REMOVED",
            "MAINTENANCE_ITEM",
            schedule.id,
            old_values={"asset_id": str(schedule.asset_id), "label": schedule.custom_label},
        )
        self.session.delete(schedule)
        self.session.flush()

    def current_meters(self, asset_id: UUID) -> tuple[Decimal | None, Decimal | None]:
        self._asset(asset_id)
        base = (
            select(OperationalEvent.id)
            .join(Assignment, Assignment.id == OperationalEvent.assignment_id)
            .where(
                OperationalEvent.company_id == self.company_id,
                Assignment.asset_id == asset_id,
                OperationalEvent.verification_status == VerificationStatus.APPROVED,
            )
        )
        km = self.session.scalar(
            select(KmReading.reading_value)
            .join(OperationalEvent, OperationalEvent.id == KmReading.event_id)
            .where(KmReading.event_id.in_(base))
            .order_by(OperationalEvent.device_created_at.desc(), OperationalEvent.id.desc())
            .limit(1)
        )
        hmr = self.session.scalar(
            select(HourMeterReading.reading_value)
            .join(OperationalEvent, OperationalEvent.id == HourMeterReading.event_id)
            .where(HourMeterReading.event_id.in_(base))
            .order_by(OperationalEvent.device_created_at.desc(), OperationalEvent.id.desc())
            .limit(1)
        )
        return km, hmr

    def evaluations(
        self, *, as_of: date | None = None, include_disabled: bool = False
    ) -> list[ScheduleEvaluation]:
        evaluation_date = as_of or datetime.now(UTC).date()
        query = (
            select(MaintenanceSchedule, FleetAsset, Site.short_name)
            .join(
                FleetAsset,
                and_(
                    FleetAsset.company_id == MaintenanceSchedule.company_id,
                    FleetAsset.id == MaintenanceSchedule.asset_id,
                ),
            )
            .outerjoin(
                AssetSiteDeployment,
                and_(
                    AssetSiteDeployment.company_id == MaintenanceSchedule.company_id,
                    AssetSiteDeployment.asset_id == MaintenanceSchedule.asset_id,
                    AssetSiteDeployment.ends_at.is_(None),
                ),
            )
            .outerjoin(
                Site,
                and_(
                    Site.company_id == AssetSiteDeployment.company_id,
                    Site.id == AssetSiteDeployment.site_id,
                ),
            )
            .where(
                MaintenanceSchedule.company_id == self.company_id,
                FleetAsset.ownership_type == AssetOwnershipType.OWNED,
                FleetAsset.maintenance_responsibility.in_(
                    [
                        MaintenanceResponsibility.OWNER_COMPANY,
                        MaintenanceResponsibility.SHARED,
                    ]
                ),
            )
            .order_by(FleetAsset.asset_code, MaintenanceSchedule.task_code)
        )
        if not include_disabled:
            query = query.where(MaintenanceSchedule.enabled.is_(True))
        rows = self.session.execute(query).all()
        meter_cache: dict[UUID, tuple[Decimal | None, Decimal | None]] = {}
        result: list[ScheduleEvaluation] = []
        for schedule, asset, site_name in rows:
            if asset.id not in meter_cache:
                meter_cache[asset.id] = self.current_meters(asset.id)
            km, hmr = meter_cache[asset.id]
            evaluated = tuple(
                evaluate_criterion(
                    criterion,
                    current_odometer_km=km,
                    current_hour_meter=hmr,
                    as_of=evaluation_date,
                )
                for criterion in self.criteria_for(schedule.id)
                if criterion.enabled
            )
            state, triggered_by = overall_due_state(evaluated)
            if not schedule.enabled:
                state, triggered_by = MaintenanceDueState.UNKNOWN, ()
            result.append(
                ScheduleEvaluation(
                    schedule=schedule,
                    asset=asset,
                    site_name=site_name,
                    state=state,
                    triggered_by=triggered_by,
                    criteria=evaluated,
                )
            )
        return sorted(
            result,
            key=lambda item: (-_STATE_RANK[item.state], item.asset.asset_code, item.schedule.id),
        )

    def create_work_order(
        self,
        asset_id: UUID,
        *,
        schedule_id: UUID | None,
        title: str,
        description: str | None,
        scheduled_for: date | None,
    ) -> MaintenanceWorkOrder:
        self._maintenance_asset(asset_id)
        if schedule_id is not None and self._schedule(schedule_id).asset_id != asset_id:
            raise DomainError("maintenance item does not belong to this asset")
        clean_title = title.strip()
        if not clean_title:
            raise DomainError("work order title is required")
        order = MaintenanceWorkOrder(
            company_id=self.company_id,
            asset_id=asset_id,
            schedule_id=schedule_id,
            title=clean_title,
            description=description.strip() if description else None,
            status=MaintenanceWorkOrderStatus.DRAFT,
            scheduled_for=scheduled_for,
            created_by_membership_id=self.actor_membership_id,
        )
        self.session.add(order)
        self.session.flush()
        self._audit(
            "MAINTENANCE_WORK_ORDER_CREATED",
            "MAINTENANCE_WORK_ORDER",
            order.id,
            new_values={"asset_id": str(asset_id), "status": order.status.value},
        )
        return order

    def _work_order(self, work_order_id: UUID, *, lock: bool = False) -> MaintenanceWorkOrder:
        query = select(MaintenanceWorkOrder).where(
            MaintenanceWorkOrder.company_id == self.company_id,
            MaintenanceWorkOrder.id == work_order_id,
        )
        if lock:
            query = query.with_for_update()
        order = self.session.scalar(query)
        if order is None:
            raise NotFoundError("maintenance work order was not found")
        return order

    def transition_work_order(
        self, work_order_id: UUID, target: MaintenanceWorkOrderStatus
    ) -> MaintenanceWorkOrder:
        order = self._work_order(work_order_id, lock=True)
        self._maintenance_asset(order.asset_id)
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
        if target not in allowed[order.status]:
            raise ConflictError(f"cannot transition {order.status.value} to {target.value}")
        old_status = order.status
        order.status = target
        now = datetime.now(UTC)
        if target == MaintenanceWorkOrderStatus.IN_PROGRESS:
            order.started_at = now
        elif target == MaintenanceWorkOrderStatus.CANCELLED:
            order.cancelled_at = now
        self.session.flush()
        self._audit(
            "MAINTENANCE_WORK_ORDER_STATUS_CHANGED",
            "MAINTENANCE_WORK_ORDER",
            order.id,
            old_values={"status": old_status.value},
            new_values={"status": target.value},
        )
        return order

    def complete_work_order(
        self,
        work_order_id: UUID,
        *,
        service_date: date,
        odometer_km: Decimal | None,
        hour_meter: Decimal | None,
        vendor: str | None,
        parts_cost: Decimal,
        labor_cost: Decimal,
        other_cost: Decimal,
        notes: str | None,
    ) -> tuple[MaintenanceWorkOrder, MaintenanceRecord]:
        order = self._work_order(work_order_id, lock=True)
        if order.status not in {
            MaintenanceWorkOrderStatus.DRAFT,
            MaintenanceWorkOrderStatus.SCHEDULED,
            MaintenanceWorkOrderStatus.IN_PROGRESS,
        }:
            raise ConflictError("only an open work order can be completed")
        asset = self._maintenance_asset(order.asset_id)
        if odometer_km is not None and not asset.supports_odometer_km:
            raise DomainError("odometer completion is unavailable for this asset")
        if hour_meter is not None and not asset.supports_hour_meter:
            raise DomainError("hour-meter completion is unavailable for this asset")
        costs = [parts_cost, labor_cost, other_cost]
        if any(value < 0 for value in costs):
            raise DomainError("maintenance costs cannot be negative")
        money = [value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) for value in costs]
        schedule = self._schedule(order.schedule_id) if order.schedule_id else None
        if schedule is not None:
            for criterion in self.criteria_for(schedule.id):
                if criterion.basis == MaintenanceCriterionBasis.CALENDAR_DAYS:
                    criterion.baseline_date = service_date
                elif (
                    criterion.basis == MaintenanceCriterionBasis.ODOMETER_KM
                    and odometer_km is not None
                ):
                    criterion.baseline_value = odometer_km
                elif (
                    criterion.basis == MaintenanceCriterionBasis.HOUR_METER_HOURS
                    and hour_meter is not None
                ):
                    criterion.baseline_value = hour_meter
        now = datetime.now(UTC)
        order.status = MaintenanceWorkOrderStatus.COMPLETED
        order.completed_at = now
        order.service_date = service_date
        order.completion_odometer_km = odometer_km
        order.completion_hour_meter = hour_meter
        order.vendor = vendor.strip() if vendor else None
        order.parts_cost, order.labor_cost, order.other_cost = money
        order.notes = notes.strip() if notes else None
        order.completed_by_membership_id = self.actor_membership_id
        label = task_label(schedule.task_code, schedule.custom_label) if schedule else order.title
        record = MaintenanceRecord(
            company_id=self.company_id,
            work_order_id=order.id,
            asset_id=order.asset_id,
            schedule_id=schedule.id if schedule else None,
            task_code=schedule.task_code if schedule else None,
            task_label=label,
            service_date=service_date,
            odometer_km=odometer_km,
            hour_meter=hour_meter,
            vendor=order.vendor,
            parts_cost=money[0],
            labor_cost=money[1],
            other_cost=money[2],
            total_cost=sum(money, Decimal("0.00")),
            notes=order.notes,
            actor_membership_id=self.actor_membership_id,
        )
        self.session.add(record)
        self.session.flush()
        self._audit(
            "MAINTENANCE_WORK_ORDER_COMPLETED",
            "MAINTENANCE_WORK_ORDER",
            order.id,
            new_values={
                "record_id": str(record.id),
                "service_date": service_date.isoformat(),
                "total_cost": str(record.total_cost),
            },
        )
        return order, record

    def list_work_orders(self) -> list[MaintenanceWorkOrder]:
        return list(
            self.session.scalars(
                select(MaintenanceWorkOrder)
                .join(
                    FleetAsset,
                    and_(
                        FleetAsset.company_id == MaintenanceWorkOrder.company_id,
                        FleetAsset.id == MaintenanceWorkOrder.asset_id,
                    ),
                )
                .where(MaintenanceWorkOrder.company_id == self.company_id)
                .where(
                    FleetAsset.ownership_type == AssetOwnershipType.OWNED,
                    FleetAsset.maintenance_responsibility.in_(
                        [
                            MaintenanceResponsibility.OWNER_COMPANY,
                            MaintenanceResponsibility.SHARED,
                        ]
                    ),
                )
                .order_by(MaintenanceWorkOrder.created_at.desc(), MaintenanceWorkOrder.id)
            ).all()
        )

    def list_history(self, asset_id: UUID | None = None) -> list[MaintenanceRecord]:
        query = select(MaintenanceRecord).where(MaintenanceRecord.company_id == self.company_id)
        if asset_id is not None:
            self._asset(asset_id)
            query = query.where(MaintenanceRecord.asset_id == asset_id)
        return list(
            self.session.scalars(
                query.order_by(MaintenanceRecord.service_date.desc(), MaintenanceRecord.id)
            ).all()
        )

    def create_template(
        self,
        *,
        name: str,
        version: str,
        source_type: MaintenanceTemplateSourceType,
        source_reference: str | None,
        verification_status: MaintenanceTemplateVerificationStatus,
        asset_type: FleetAssetType | None,
        manufacturer: str | None,
        model: str | None,
        model_year_min: int | None,
        model_year_max: int | None,
        is_generic: bool,
    ) -> MaintenanceTemplate:
        clean_name, clean_version = name.strip(), version.strip()
        if not clean_name or not clean_version:
            raise DomainError("template name and version are required")
        if model_year_min and model_year_max and model_year_max < model_year_min:
            raise DomainError("template model-year range is invalid")
        template = MaintenanceTemplate(
            company_id=self.company_id,
            name=clean_name,
            version=clean_version,
            source_type=source_type,
            source_reference=source_reference.strip() if source_reference else None,
            verification_status=verification_status,
            asset_type=asset_type,
            manufacturer=manufacturer.strip() if manufacturer else None,
            model=model.strip() if model else None,
            model_year_min=model_year_min,
            model_year_max=model_year_max,
            is_generic=is_generic,
            created_by_membership_id=self.actor_membership_id,
        )
        self.session.add(template)
        self.session.flush()
        self._audit(
            "MAINTENANCE_TEMPLATE_CREATED",
            "MAINTENANCE_TEMPLATE",
            template.id,
            new_values={"name": clean_name, "version": clean_version},
        )
        return template

    def list_templates(self) -> list[MaintenanceTemplate]:
        return list(
            self.session.scalars(
                select(MaintenanceTemplate)
                .where(MaintenanceTemplate.company_id == self.company_id)
                .order_by(MaintenanceTemplate.name, MaintenanceTemplate.version.desc())
            ).all()
        )

    def matching_templates(self, asset_id: UUID) -> list[MaintenanceTemplate]:
        asset = self._maintenance_asset(asset_id)
        templates = self.list_templates()

        def matches(template: MaintenanceTemplate) -> bool:
            if template.asset_type is not None and template.asset_type != asset.asset_type:
                return False
            if template.manufacturer and (
                not asset.manufacturer
                or template.manufacturer.casefold() != asset.manufacturer.casefold()
            ):
                return False
            if template.model and (
                not asset.model or template.model.casefold() != asset.model.casefold()
            ):
                return False
            if template.model_year_min is not None and (
                asset.model_year is None or asset.model_year < template.model_year_min
            ):
                return False
            if template.model_year_max is not None and (
                asset.model_year is None or asset.model_year > template.model_year_max
            ):
                return False
            return True

        def score(template: MaintenanceTemplate) -> tuple[int, int, int, str, str]:
            verified = int(
                template.verification_status == MaintenanceTemplateVerificationStatus.VERIFIED
            )
            specificity = sum(
                value is not None
                for value in (
                    template.asset_type,
                    template.manufacturer,
                    template.model,
                    template.model_year_min,
                    template.model_year_max,
                )
            )
            return (
                verified,
                specificity,
                int(not template.is_generic),
                template.version,
                str(template.id),
            )

        return sorted((item for item in templates if matches(item)), key=score, reverse=True)

    def add_template_item(
        self,
        template_id: UUID,
        *,
        task_code: MaintenanceTaskCode,
        custom_label: str | None,
        action_type: MaintenanceActionType,
        description: str | None,
        enabled: bool,
        criteria: list[CriterionInput],
    ) -> MaintenanceTemplateItem:
        template = self.session.scalar(
            select(MaintenanceTemplate).where(
                MaintenanceTemplate.company_id == self.company_id,
                MaintenanceTemplate.id == template_id,
            )
        )
        if template is None:
            raise NotFoundError("maintenance template was not found")
        clean_label = custom_label.strip() if custom_label else None
        if task_code == MaintenanceTaskCode.CUSTOM and not clean_label:
            raise DomainError("custom maintenance tasks require a label")
        if not criteria:
            raise DomainError("template item requires at least one trigger")
        bases = [criterion.basis for criterion in criteria]
        if len(bases) != len(set(bases)):
            raise DomainError("a template trigger type may appear only once")
        for criterion in criteria:
            if (
                criterion.interval_value <= 0
                or criterion.warning_value < 0
                or criterion.warning_value >= criterion.interval_value
            ):
                raise DomainError("template interval and warning values are invalid")
        item = MaintenanceTemplateItem(
            company_id=self.company_id,
            template_id=template.id,
            task_code=task_code,
            custom_label=clean_label,
            action_type=action_type,
            description=description.strip() if description else None,
            enabled=enabled,
        )
        self.session.add(item)
        self.session.flush()
        for criterion in criteria:
            self.session.add(
                MaintenanceTemplateCriterion(
                    company_id=self.company_id,
                    template_item_id=item.id,
                    basis=criterion.basis,
                    interval_value=criterion.interval_value,
                    warning_value=criterion.warning_value,
                )
            )
        self.session.flush()
        self._audit(
            "MAINTENANCE_TEMPLATE_ITEM_CREATED",
            "MAINTENANCE_TEMPLATE_ITEM",
            item.id,
            new_values={"template_id": str(template.id), "task_code": task_code.value},
        )
        return item

    def template_items(
        self, template_id: UUID
    ) -> list[tuple[MaintenanceTemplateItem, list[MaintenanceTemplateCriterion]]]:
        template = self.session.scalar(
            select(MaintenanceTemplate.id).where(
                MaintenanceTemplate.company_id == self.company_id,
                MaintenanceTemplate.id == template_id,
            )
        )
        if template is None:
            raise NotFoundError("maintenance template was not found")
        items = self.session.scalars(
            select(MaintenanceTemplateItem)
            .where(
                MaintenanceTemplateItem.company_id == self.company_id,
                MaintenanceTemplateItem.template_id == template_id,
            )
            .order_by(MaintenanceTemplateItem.task_code, MaintenanceTemplateItem.id)
        ).all()
        return [
            (
                item,
                list(
                    self.session.scalars(
                        select(MaintenanceTemplateCriterion)
                        .where(
                            MaintenanceTemplateCriterion.company_id == self.company_id,
                            MaintenanceTemplateCriterion.template_item_id == item.id,
                        )
                        .order_by(MaintenanceTemplateCriterion.basis)
                    ).all()
                ),
            )
            for item in items
        ]

    def apply_template(self, asset_id: UUID, template_id: UUID) -> MaintenancePlan:
        asset = self._maintenance_asset(asset_id)
        if (
            self.session.scalar(
                select(MaintenancePlan.id).where(
                    MaintenancePlan.company_id == self.company_id,
                    MaintenancePlan.asset_id == asset_id,
                )
            )
            is not None
        ):
            raise ConflictError("asset already has a maintenance plan")
        template = self.session.scalar(
            select(MaintenanceTemplate).where(
                MaintenanceTemplate.company_id == self.company_id,
                MaintenanceTemplate.id == template_id,
            )
        )
        if template is None or template not in self.matching_templates(asset_id):
            raise DomainError("maintenance template does not match this asset")
        items = self.session.scalars(
            select(MaintenanceTemplateItem).where(
                MaintenanceTemplateItem.company_id == self.company_id,
                MaintenanceTemplateItem.template_id == template.id,
            )
        ).all()
        plan = self.ensure_plan(
            asset_id,
            source=MaintenancePlanSource.SUGGESTED_TEMPLATE,
            source_template=template,
        )
        for item in items:
            criteria = self.session.scalars(
                select(MaintenanceTemplateCriterion).where(
                    MaintenanceTemplateCriterion.company_id == self.company_id,
                    MaintenanceTemplateCriterion.template_item_id == item.id,
                )
            ).all()
            compatible_criteria = [
                criterion
                for criterion in criteria
                if not (
                    criterion.basis == MaintenanceCriterionBasis.ODOMETER_KM
                    and (not asset.is_wheeled or not asset.supports_odometer_km)
                )
                and not (
                    criterion.basis == MaintenanceCriterionBasis.HOUR_METER_HOURS
                    and not asset.supports_hour_meter
                )
            ]
            if not compatible_criteria:
                continue
            schedule = self.save_schedule(
                asset_id,
                task_code=item.task_code,
                custom_label=item.custom_label,
                action_type=item.action_type,
                description=item.description,
                enabled=item.enabled,
                criteria=[
                    CriterionInput(
                        basis=criterion.basis,
                        interval_value=criterion.interval_value,
                        warning_value=criterion.warning_value,
                    )
                    for criterion in compatible_criteria
                ],
            )
            schedule.source_template_item_id = item.id
            schedule.plan_id = plan.id
        self.session.flush()
        return plan

    def copy_plan(self, asset_id: UUID, source_asset_id: UUID) -> MaintenancePlan:
        asset = self._maintenance_asset(asset_id)
        self._maintenance_asset(source_asset_id)
        if asset_id == source_asset_id:
            raise DomainError("an asset cannot copy its own maintenance plan")
        if (
            self.session.scalar(
                select(MaintenancePlan.id).where(
                    MaintenancePlan.company_id == self.company_id,
                    MaintenancePlan.asset_id == asset_id,
                )
            )
            is not None
        ):
            raise ConflictError("asset already has a maintenance plan")
        source_plan, source_schedules = self.list_plan(source_asset_id)
        if source_plan is None or not source_schedules:
            raise DomainError("source asset has no maintenance plan to copy")
        plan = self.ensure_plan(
            asset_id,
            source=MaintenancePlanSource.COPIED_ASSET,
            source_asset_id=source_asset_id,
        )
        for source_schedule in source_schedules:
            compatible = [
                criterion
                for criterion in self.criteria_for(source_schedule.id)
                if not (
                    criterion.basis == MaintenanceCriterionBasis.ODOMETER_KM
                    and (not asset.is_wheeled or not asset.supports_odometer_km)
                )
                and not (
                    criterion.basis == MaintenanceCriterionBasis.HOUR_METER_HOURS
                    and not asset.supports_hour_meter
                )
            ]
            if not compatible:
                continue
            copied = self.save_schedule(
                asset_id,
                task_code=source_schedule.task_code,
                custom_label=source_schedule.custom_label,
                action_type=source_schedule.action_type,
                description=source_schedule.description,
                enabled=source_schedule.enabled,
                criteria=[
                    CriterionInput(
                        basis=criterion.basis,
                        enabled=criterion.enabled,
                        interval_value=criterion.interval_value,
                        warning_value=criterion.warning_value,
                    )
                    for criterion in compatible
                ],
            )
            copied.plan_id = plan.id
        self.session.flush()
        self._audit(
            "MAINTENANCE_PLAN_COPIED",
            "MAINTENANCE_PLAN",
            plan.id,
            new_values={
                "asset_id": str(asset_id),
                "source_asset_id": str(source_asset_id),
            },
        )
        return plan

    def generic_starter(self, asset_id: UUID) -> list[TaskCatalogEntry]:
        asset = self._maintenance_asset(asset_id)
        return [
            item
            for item in TASK_CATALOG
            if item.code != MaintenanceTaskCode.CUSTOM
            and (item.wheeled_default if asset.is_wheeled else item.tracked_default)
        ]

    def alert_counts(self) -> dict[MaintenanceDueState, int]:
        counts = {state: 0 for state in MaintenanceDueState}
        for item in self.evaluations():
            counts[item.state] += 1
        return counts

    def open_work_order_count(self) -> int:
        return int(
            self.session.scalar(
                select(func.count(MaintenanceWorkOrder.id)).where(
                    MaintenanceWorkOrder.company_id == self.company_id,
                    MaintenanceWorkOrder.asset_id.in_(
                        select(FleetAsset.id).where(
                            FleetAsset.company_id == self.company_id,
                            FleetAsset.ownership_type == AssetOwnershipType.OWNED,
                            FleetAsset.maintenance_responsibility.in_(
                                [
                                    MaintenanceResponsibility.OWNER_COMPANY,
                                    MaintenanceResponsibility.SHARED,
                                ]
                            ),
                        )
                    ),
                    MaintenanceWorkOrder.status.not_in(
                        [
                            MaintenanceWorkOrderStatus.COMPLETED,
                            MaintenanceWorkOrderStatus.CANCELLED,
                        ]
                    ),
                )
            )
            or 0
        )
