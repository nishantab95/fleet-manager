from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import String, and_, func, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.orm import Session, aliased

from fleet_api.auth.service import AuthContext, ensure_supervisor_site_access
from fleet_api.db.models import (
    Assignment,
    CompanyMembership,
    DieselEvent,
    EmergencyEvent,
    EventVerification,
    EvidenceObject,
    KmReading,
    OperationalEvent,
    Site,
    SiteDailyClosure,
    SiteDailyClosureHistory,
    Tipper,
    User,
)
from fleet_api.db.models.common import utc_now
from fleet_api.domain.audit import write_audit_log
from fleet_api.domain.enums import (
    EmergencyStatus,
    MembershipRole,
    OperationalEventType,
    SiteClosureStatus,
    VerificationStatus,
)
from fleet_api.domain.errors import (
    ClosureBlockedError,
    ConflictError,
    DomainError,
    NotFoundError,
    RoleViolationError,
    TenantConsistencyError,
)


@dataclass(frozen=True)
class OperationalDay:
    operational_date: date
    start_utc: datetime
    end_utc: datetime
    reporting_timezone: str
    workday_start_minutes: int


@dataclass(frozen=True)
class ReportHistory:
    status: VerificationStatus
    actor_name: str | None
    reason: str | None
    created_at: datetime


@dataclass(frozen=True)
class ReportEvent:
    event_id: UUID
    event_type: OperationalEventType
    assignment_id: UUID
    tipper_id: UUID
    tipper_registration_number: str
    site_id: UUID
    site_name: str
    driver_name: str
    driver_phone: str | None
    supervisor_name: str
    device_created_at: datetime
    server_received_at: datetime
    verification_status: VerificationStatus
    reading_type: str | None
    reading_value: Decimal | None
    litres: Decimal | None
    emergency_category: str | None
    emergency_status: str | None
    emergency_description: str | None
    evidence_available: bool
    verification_history: list[ReportHistory]


@dataclass(frozen=True)
class ReportEvidenceContext:
    event: OperationalEvent
    tipper: Tipper
    driver_name: str
    evidence: EvidenceObject


@dataclass(frozen=True)
class ReportException:
    code: str
    description: str
    assignment_id: UUID
    tipper_id: UUID
    tipper_registration_number: str
    site_id: UUID
    event_id: UUID | None = None


@dataclass(frozen=True)
class TipperDailyReport:
    assignment: Assignment
    tipper: Tipper
    site: Site
    driver_name: str
    supervisor_name: str
    approved_trip_count: int
    pending_trip_count: int
    disputed_trip_count: int
    rejected_trip_count: int
    start_km: Decimal | None
    end_km: Decimal | None
    distance_km: Decimal | None
    km_per_approved_trip: Decimal | None
    verified_diesel_issued: Decimal
    diesel_issued_per_approved_trip: Decimal | None
    first_trip_completed_at: datetime | None
    last_trip_completed_at: datetime | None
    recorded_activity_span: timedelta | None
    avg_trip_completion_interval: timedelta | None
    median_trip_completion_interval: timedelta | None
    longest_trip_gap: timedelta | None
    pending_diesel_count: int
    disputed_diesel_count: int
    unresolved_emergency_count: int
    missing_start_reading: bool
    missing_end_reading: bool
    completeness_status: str
    closure_status: SiteClosureStatus
    exceptions: list[ReportException]
    events: list[ReportEvent]


@dataclass(frozen=True)
class ClosureHistory:
    status: SiteClosureStatus
    actor_name: str | None
    reason: str | None
    created_at: datetime


@dataclass(frozen=True)
class ClosureSnapshot:
    status: SiteClosureStatus
    blockers: list[ReportException]
    history: list[ClosureHistory]


@dataclass(frozen=True)
class SiteDailyReport:
    site: Site
    operational_day: OperationalDay
    rows: list[TipperDailyReport]
    assigned_tippers_count: int
    approved_trip_count: int
    pending_trip_count: int
    disputed_trip_count: int
    total_km: Decimal | None
    verified_diesel_issued: Decimal
    missing_reading_count: int
    unresolved_emergency_count: int
    closure: ClosureSnapshot


@dataclass(frozen=True)
class DashboardReport:
    operational_day: OperationalDay
    assigned_tippers_count: int
    approved_trip_count: int
    pending_trip_count: int
    total_km: Decimal | None
    verified_diesel_issued: Decimal
    pending_verification_count: int
    missing_reading_count: int
    unresolved_emergency_count: int
    sites_not_closed_count: int
    complete_tippers_count: int
    sites: list[SiteDailyReport]
    exceptions: list[ReportException]


@dataclass(frozen=True)
class _EventParts:
    event: OperationalEvent
    assignment: Assignment
    tipper: Tipper
    site: Site
    driver_name: str
    driver_phone: str
    supervisor_name: str
    km: KmReading | None
    diesel: DieselEvent | None
    emergency: EmergencyEvent | None
    evidence_available: bool
    history: list[ReportHistory]


def _duration_microseconds(value: timedelta) -> int:
    return (value.days * 86_400 + value.seconds) * 1_000_000 + value.microseconds


def _trip_timing_metrics(
    timestamps: list[datetime],
) -> tuple[
    datetime | None,
    datetime | None,
    timedelta | None,
    timedelta | None,
    timedelta | None,
    timedelta | None,
]:
    """Calculate timing metrics from approved completion timestamps only."""
    ordered = sorted(timestamps)
    if not ordered:
        return None, None, None, None, None, None
    if len(ordered) == 1:
        return ordered[0], ordered[0], timedelta(0), None, None, None

    intervals = [ordered[index] - ordered[index - 1] for index in range(1, len(ordered))]
    interval_values = sorted(_duration_microseconds(interval) for interval in intervals)
    middle = len(interval_values) // 2
    if len(interval_values) % 2:
        median_microseconds: float = float(interval_values[middle])
    else:
        median_microseconds = (interval_values[middle - 1] + interval_values[middle]) / 2
    return (
        ordered[0],
        ordered[-1],
        ordered[-1] - ordered[0],
        timedelta(microseconds=sum(interval_values) / len(interval_values)),
        timedelta(microseconds=median_microseconds),
        max(intervals),
    )


class ReportingService:
    """Tenant-scoped reporting and explicit site/day closure operations."""

    def __init__(self, session: Session, context: AuthContext) -> None:
        self.session = session
        self.context = context
        self.company_id = context.company.id

    def _zone(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.context.company.reporting_timezone)
        except ZoneInfoNotFoundError as exc:
            raise DomainError("company reporting timezone is invalid") from exc

    def operational_day(self, requested_date: date | None = None) -> OperationalDay:
        zone = self._zone()
        start_minutes = self.context.company.operational_day_start_minutes
        local_now = datetime.now(zone)
        label = requested_date
        if label is None:
            label = local_now.date()
            if local_now.hour * 60 + local_now.minute < start_minutes:
                label -= timedelta(days=1)
        local_start = datetime.combine(label, time.min).replace(tzinfo=zone) + timedelta(
            minutes=start_minutes
        )
        local_end = datetime.combine(label + timedelta(days=1), time.min).replace(
            tzinfo=zone
        ) + timedelta(minutes=start_minutes)
        return OperationalDay(
            operational_date=label,
            start_utc=local_start.astimezone(UTC),
            end_utc=local_end.astimezone(UTC),
            reporting_timezone=self.context.company.reporting_timezone,
            workday_start_minutes=start_minutes,
        )

    def _site(self, site_id: UUID) -> Site:
        site = self.session.scalar(
            select(Site).where(Site.id == site_id, Site.company_id == self.company_id)
        )
        if site is None:
            raise NotFoundError("site was not found")
        return site

    def _tipper(self, tipper_id: UUID) -> Tipper:
        tipper = self.session.scalar(
            select(Tipper).where(Tipper.id == tipper_id, Tipper.company_id == self.company_id)
        )
        if tipper is None:
            raise NotFoundError("tipper was not found")
        return tipper

    def _authorize_site(self, site_id: UUID) -> Site:
        site = self._site(site_id)
        if self.context.membership.role == MembershipRole.OWNER_ADMIN:
            return site
        if self.context.membership.role == MembershipRole.SUPERVISOR:
            try:
                ensure_supervisor_site_access(self.session, self.context, site_id=site_id)
            except TenantConsistencyError:
                raise
            return site
        raise RoleViolationError("owner or permitted supervisor membership is required")

    def _assignment_rows(
        self,
        day: OperationalDay,
        *,
        site_id: UUID | None = None,
        tipper_id: UUID | None = None,
    ) -> list[tuple[Assignment, Tipper, Site, str, str]]:
        driver_membership = aliased(CompanyMembership)
        supervisor_membership = aliased(CompanyMembership)
        driver_user = aliased(User)
        supervisor_user = aliased(User)
        statement = (
            select(
                Assignment,
                Tipper,
                Site,
                sql_cast(
                    func.coalesce(driver_membership.display_name, driver_user.display_name),
                    String,
                ),
                sql_cast(
                    func.coalesce(supervisor_membership.display_name, supervisor_user.display_name),
                    String,
                ),
            )
            .join(Tipper, Tipper.id == Assignment.tipper_id)
            .join(Site, Site.id == Assignment.site_id)
            .join(driver_membership, driver_membership.id == Assignment.driver_membership_id)
            .join(driver_user, driver_user.id == driver_membership.user_id)
            .join(
                supervisor_membership,
                supervisor_membership.id == Assignment.supervisor_membership_id,
            )
            .join(supervisor_user, supervisor_user.id == supervisor_membership.user_id)
            .where(
                Assignment.company_id == self.company_id,
                Assignment.starts_at < day.end_utc,
                (Assignment.ends_at.is_(None) | (Assignment.ends_at > day.start_utc)),
            )
            .order_by(Site.name, Tipper.registration_number, Assignment.starts_at)
        )
        if site_id is not None:
            statement = statement.where(Assignment.site_id == site_id)
        if tipper_id is not None:
            statement = statement.where(Assignment.tipper_id == tipper_id)
        return [row._tuple() for row in self.session.execute(statement).all()]

    def _event_parts(
        self,
        day: OperationalDay,
        assignment_ids: list[UUID],
    ) -> dict[UUID, list[_EventParts]]:
        if not assignment_ids:
            return {}
        driver_membership = aliased(CompanyMembership)
        supervisor_membership = aliased(CompanyMembership)
        driver_user = aliased(User)
        supervisor_user = aliased(User)
        statement = (
            select(
                OperationalEvent,
                Assignment,
                Tipper,
                Site,
                sql_cast(
                    func.coalesce(driver_membership.display_name, driver_user.display_name),
                    String,
                ),
                driver_user.phone_number,
                sql_cast(
                    func.coalesce(supervisor_membership.display_name, supervisor_user.display_name),
                    String,
                ),
            )
            .join(Assignment, Assignment.id == OperationalEvent.assignment_id)
            .join(Tipper, Tipper.id == Assignment.tipper_id)
            .join(Site, Site.id == Assignment.site_id)
            .join(driver_membership, driver_membership.id == Assignment.driver_membership_id)
            .join(driver_user, driver_user.id == driver_membership.user_id)
            .join(
                supervisor_membership,
                supervisor_membership.id == Assignment.supervisor_membership_id,
            )
            .join(supervisor_user, supervisor_user.id == supervisor_membership.user_id)
            .where(
                OperationalEvent.company_id == self.company_id,
                OperationalEvent.assignment_id.in_(assignment_ids),
                OperationalEvent.device_created_at >= day.start_utc,
                OperationalEvent.device_created_at < day.end_utc,
            )
            .order_by(OperationalEvent.device_created_at, OperationalEvent.id)
        )
        rows = [row._tuple() for row in self.session.execute(statement).all()]
        event_ids = [row[0].id for row in rows]
        client_ids = [row[0].client_event_uuid for row in rows]
        km_by_event = {
            reading.event_id: reading
            for reading in self.session.scalars(
                select(KmReading).where(KmReading.event_id.in_(event_ids))
            ).all()
        }
        diesel_by_event = {
            diesel.event_id: diesel
            for diesel in self.session.scalars(
                select(DieselEvent).where(DieselEvent.event_id.in_(event_ids))
            ).all()
        }
        emergency_by_event = {
            emergency.event_id: emergency
            for emergency in self.session.scalars(
                select(EmergencyEvent).where(EmergencyEvent.event_id.in_(event_ids))
            ).all()
        }
        evidence_by_client = {
            evidence.client_event_uuid: evidence
            for evidence in self.session.scalars(
                select(EvidenceObject).where(
                    EvidenceObject.company_id == self.company_id,
                    EvidenceObject.client_event_uuid.in_(client_ids),
                )
            ).all()
        }
        history_by_event: dict[UUID, list[ReportHistory]] = defaultdict(list)
        history_rows = self.session.execute(
            select(EventVerification, User.display_name)
            .outerjoin(
                CompanyMembership,
                and_(
                    CompanyMembership.id == EventVerification.changed_by_membership_id,
                    CompanyMembership.company_id == EventVerification.company_id,
                ),
            )
            .outerjoin(User, User.id == CompanyMembership.user_id)
            .where(
                EventVerification.company_id == self.company_id,
                EventVerification.event_id.in_(event_ids),
            )
            .order_by(EventVerification.created_at, EventVerification.id)
        )
        for verification, actor_name in history_rows:
            history_by_event[verification.event_id].append(
                ReportHistory(
                    status=verification.status,
                    actor_name=actor_name,
                    reason=verification.reason,
                    created_at=verification.created_at,
                )
            )
        result: dict[UUID, list[_EventParts]] = defaultdict(list)
        for event, assignment, tipper, site, driver_name, driver_phone, supervisor_name in rows:
            result[assignment.id].append(
                _EventParts(
                    event=event,
                    assignment=assignment,
                    tipper=tipper,
                    site=site,
                    driver_name=driver_name,
                    driver_phone=driver_phone,
                    supervisor_name=supervisor_name,
                    km=km_by_event.get(event.id),
                    diesel=diesel_by_event.get(event.id),
                    emergency=emergency_by_event.get(event.id),
                    evidence_available=event.client_event_uuid in evidence_by_client,
                    history=history_by_event.get(event.id, []),
                )
            )
        return result

    @staticmethod
    def _report_event(parts: _EventParts) -> ReportEvent:
        return ReportEvent(
            event_id=parts.event.id,
            event_type=parts.event.event_type,
            assignment_id=parts.assignment.id,
            tipper_id=parts.tipper.id,
            tipper_registration_number=parts.tipper.registration_number,
            site_id=parts.site.id,
            site_name=parts.site.name,
            driver_name=parts.driver_name,
            driver_phone=(parts.driver_phone if parts.emergency is not None else None),
            supervisor_name=parts.supervisor_name,
            device_created_at=parts.event.device_created_at,
            server_received_at=parts.event.server_received_at,
            verification_status=parts.event.verification_status,
            reading_type=parts.km.reading_type.value if parts.km else None,
            reading_value=parts.km.reading_value if parts.km else None,
            litres=parts.diesel.litres if parts.diesel else None,
            emergency_category=(
                parts.emergency.category.value
                if parts.emergency is not None and parts.emergency.category is not None
                else None
            ),
            emergency_status=parts.emergency.status.value if parts.emergency else None,
            emergency_description=parts.emergency.description if parts.emergency else None,
            evidence_available=parts.evidence_available,
            verification_history=parts.history,
        )

    @staticmethod
    def _reading_value(events: list[_EventParts], reading_type: str) -> tuple[Decimal | None, bool]:
        approved_values = [
            parts.km.reading_value
            for parts in events
            if parts.km is not None
            and parts.km.reading_type.value == reading_type
            and parts.event.verification_status == VerificationStatus.APPROVED
        ]
        distinct_values = set(approved_values)
        if len(distinct_values) > 1:
            return None, True
        return (next(iter(distinct_values)) if distinct_values else None), False

    @staticmethod
    def _has_status(
        events: list[_EventParts], event_type: OperationalEventType, status: VerificationStatus
    ) -> bool:
        return any(
            parts.event.event_type == event_type and parts.event.verification_status == status
            for parts in events
        )

    def _tipper_report(
        self,
        assignment: Assignment,
        tipper: Tipper,
        site: Site,
        driver_name: str,
        supervisor_name: str,
        events: list[_EventParts],
    ) -> TipperDailyReport:
        approved_trips = [
            parts
            for parts in events
            if parts.event.event_type == OperationalEventType.TRIP_COMPLETE
            and parts.event.verification_status == VerificationStatus.APPROVED
        ]
        pending_trips = [
            parts
            for parts in events
            if parts.event.event_type == OperationalEventType.TRIP_COMPLETE
            and parts.event.verification_status == VerificationStatus.PENDING_VERIFICATION
        ]
        disputed_trips = [
            parts
            for parts in events
            if parts.event.event_type == OperationalEventType.TRIP_COMPLETE
            and parts.event.verification_status == VerificationStatus.DISPUTED
        ]
        rejected_trips = [
            parts
            for parts in events
            if parts.event.event_type == OperationalEventType.TRIP_COMPLETE
            and parts.event.verification_status == VerificationStatus.REJECTED
        ]
        (
            first_trip_completed_at,
            last_trip_completed_at,
            recorded_activity_span,
            avg_trip_completion_interval,
            median_trip_completion_interval,
            longest_trip_gap,
        ) = _trip_timing_metrics([parts.event.device_created_at for parts in approved_trips])
        reporting_zone = self._zone()
        if first_trip_completed_at is not None:
            first_trip_completed_at = first_trip_completed_at.astimezone(reporting_zone)
        if last_trip_completed_at is not None:
            last_trip_completed_at = last_trip_completed_at.astimezone(reporting_zone)
        start_km, conflicting_start = self._reading_value(events, "START_READING")
        end_km, conflicting_end = self._reading_value(events, "END_READING")
        exceptions: list[ReportException] = []

        def add_exception(code: str, description: str, event_id: UUID | None = None) -> None:
            exceptions.append(
                ReportException(
                    code=code,
                    description=description,
                    assignment_id=assignment.id,
                    tipper_id=tipper.id,
                    tipper_registration_number=tipper.registration_number,
                    site_id=site.id,
                    event_id=event_id,
                )
            )

        if conflicting_start:
            add_exception(
                "CONFLICTING_START_READING", "More than one approved START reading exists"
            )
        elif start_km is None:
            if self._has_status(
                events, OperationalEventType.KM_READING, VerificationStatus.PENDING_VERIFICATION
            ):
                add_exception("KM_PENDING", "A KM reading is pending verification")
            add_exception("MISSING_START_READING", "No approved START reading exists")
        if conflicting_end:
            add_exception("CONFLICTING_END_READING", "More than one approved END reading exists")
        elif end_km is None:
            if self._has_status(
                events, OperationalEventType.KM_READING, VerificationStatus.PENDING_VERIFICATION
            ):
                if not any(item.code == "KM_PENDING" for item in exceptions):
                    add_exception("KM_PENDING", "A KM reading is pending verification")
            add_exception("MISSING_END_READING", "No approved END reading exists")
        distance_km: Decimal | None = None
        if start_km is not None and end_km is not None:
            if end_km < start_km:
                add_exception("END_BELOW_START", "Approved END reading is lower than START reading")
            else:
                distance_km = end_km - start_km

        km_per_approved_trip = (
            distance_km / Decimal(len(approved_trips))
            if distance_km is not None and approved_trips
            else None
        )

        if pending_trips:
            add_exception("TRIP_PENDING", f"{len(pending_trips)} trip(s) pending verification")
        if disputed_trips:
            add_exception("TRIP_DISPUTED", f"{len(disputed_trips)} trip(s) are disputed")

        diesel_events = [
            parts for parts in events if parts.event.event_type == OperationalEventType.DIESEL
        ]
        approved_diesel = sum(
            (
                parts.diesel.litres
                for parts in diesel_events
                if parts.diesel is not None
                and parts.event.verification_status == VerificationStatus.APPROVED
            ),
            Decimal("0"),
        )
        pending_diesel = [
            parts
            for parts in diesel_events
            if parts.event.verification_status == VerificationStatus.PENDING_VERIFICATION
        ]
        disputed_diesel = [
            parts
            for parts in diesel_events
            if parts.event.verification_status == VerificationStatus.DISPUTED
        ]
        diesel_issued_per_approved_trip = (
            approved_diesel / Decimal(len(approved_trips)) if approved_trips else None
        )
        if pending_diesel:
            add_exception(
                "DIESEL_PENDING", f"{len(pending_diesel)} diesel record(s) pending verification"
            )

        unresolved_emergencies = [
            parts
            for parts in events
            if parts.emergency is not None
            and parts.emergency.status not in {EmergencyStatus.RESOLVED, EmergencyStatus.CLOSED}
        ]
        for emergency in unresolved_emergencies:
            emergency_status = emergency.emergency.status.value if emergency.emergency else "OPEN"
            add_exception(
                "UNRESOLVED_EMERGENCY",
                f"Emergency remains {emergency_status}",
                emergency.event.id,
            )

        review_codes = {
            "CONFLICTING_START_READING",
            "CONFLICTING_END_READING",
            "END_BELOW_START",
        }
        status = (
            "COMPLETE"
            if not exceptions
            else (
                "REVIEW_REQUIRED"
                if any(item.code in review_codes for item in exceptions)
                else "INCOMPLETE"
            )
        )
        return TipperDailyReport(
            assignment=assignment,
            tipper=tipper,
            site=site,
            driver_name=driver_name,
            supervisor_name=supervisor_name,
            approved_trip_count=len(approved_trips),
            pending_trip_count=len(pending_trips),
            disputed_trip_count=len(disputed_trips),
            rejected_trip_count=len(rejected_trips),
            start_km=start_km,
            end_km=end_km,
            distance_km=distance_km,
            km_per_approved_trip=km_per_approved_trip,
            verified_diesel_issued=approved_diesel,
            diesel_issued_per_approved_trip=diesel_issued_per_approved_trip,
            first_trip_completed_at=first_trip_completed_at,
            last_trip_completed_at=last_trip_completed_at,
            recorded_activity_span=recorded_activity_span,
            avg_trip_completion_interval=avg_trip_completion_interval,
            median_trip_completion_interval=median_trip_completion_interval,
            longest_trip_gap=longest_trip_gap,
            pending_diesel_count=len(pending_diesel),
            disputed_diesel_count=len(disputed_diesel),
            unresolved_emergency_count=len(unresolved_emergencies),
            missing_start_reading=start_km is None and not conflicting_start,
            missing_end_reading=end_km is None and not conflicting_end,
            completeness_status=status,
            closure_status=SiteClosureStatus.OPEN,
            exceptions=exceptions,
            events=[self._report_event(parts) for parts in events],
        )

    def _closure_snapshot(
        self,
        site: Site,
        day: OperationalDay,
        blockers: list[ReportException],
    ) -> ClosureSnapshot:
        snapshots = self._closure_snapshots(day, [site.id], {site.id: blockers})
        return snapshots[site.id]

    def _closure_snapshots(
        self,
        day: OperationalDay,
        site_ids: list[UUID],
        blockers_by_site: dict[UUID, list[ReportException]],
    ) -> dict[UUID, ClosureSnapshot]:
        if not site_ids:
            return {}
        closures = list(
            self.session.scalars(
                select(SiteDailyClosure).where(
                    SiteDailyClosure.company_id == self.company_id,
                    SiteDailyClosure.operational_date == day.operational_date,
                    SiteDailyClosure.site_id.in_(site_ids),
                )
            ).all()
        )
        closure_by_site = {closure.site_id: closure for closure in closures}
        history_by_closure: dict[UUID, list[ClosureHistory]] = defaultdict(list)
        if closures:
            history_rows = self.session.execute(
                select(SiteDailyClosureHistory, User.display_name)
                .join(
                    CompanyMembership,
                    CompanyMembership.id == SiteDailyClosureHistory.changed_by_membership_id,
                )
                .join(User, User.id == CompanyMembership.user_id)
                .where(
                    SiteDailyClosureHistory.company_id == self.company_id,
                    SiteDailyClosureHistory.closure_id.in_([closure.id for closure in closures]),
                )
                .order_by(SiteDailyClosureHistory.created_at, SiteDailyClosureHistory.id)
            )
            for item, actor_name in history_rows:
                history_by_closure[item.closure_id].append(
                    ClosureHistory(
                        status=item.status,
                        actor_name=actor_name,
                        reason=item.reason,
                        created_at=item.created_at,
                    )
                )
        snapshots: dict[UUID, ClosureSnapshot] = {}
        for site_id in site_ids:
            blockers = blockers_by_site.get(site_id, [])
            closure = closure_by_site.get(site_id)
            if closure is None:
                status = SiteClosureStatus.OPEN if blockers else SiteClosureStatus.READY_TO_CLOSE
                snapshots[site_id] = ClosureSnapshot(status=status, blockers=blockers, history=[])
                continue
            status = closure.status
            if status in {SiteClosureStatus.OPEN, SiteClosureStatus.REOPENED} and not blockers:
                status = SiteClosureStatus.READY_TO_CLOSE
            snapshots[site_id] = ClosureSnapshot(
                status=status,
                blockers=blockers,
                history=history_by_closure.get(closure.id, []),
            )
        return snapshots

    def _make_site_report(
        self,
        site: Site,
        day: OperationalDay,
        rows: list[TipperDailyReport],
        closure: ClosureSnapshot | None = None,
    ) -> SiteDailyReport:
        blockers = [item for row in rows for item in row.exceptions]
        distances = [row.distance_km for row in rows if row.distance_km is not None]
        closure = closure or self._closure_snapshot(site, day, blockers)
        rows = [replace(row, closure_status=closure.status) for row in rows]
        return SiteDailyReport(
            site=site,
            operational_day=day,
            rows=rows,
            assigned_tippers_count=len({row.tipper.id for row in rows}),
            approved_trip_count=sum(row.approved_trip_count for row in rows),
            pending_trip_count=sum(row.pending_trip_count for row in rows),
            disputed_trip_count=sum(row.disputed_trip_count for row in rows),
            total_km=sum(distances, Decimal("0")) if distances else None,
            verified_diesel_issued=sum((row.verified_diesel_issued for row in rows), Decimal("0")),
            missing_reading_count=sum(
                int(row.missing_start_reading) + int(row.missing_end_reading) for row in rows
            ),
            unresolved_emergency_count=sum(row.unresolved_emergency_count for row in rows),
            closure=closure,
        )

    def site_daily(self, site_id: UUID, requested_date: date | None = None) -> SiteDailyReport:
        site = self._site(site_id)
        day = self.operational_day(requested_date)
        rows = self._assignment_rows(day, site_id=site_id)
        assignments = [row[0] for row in rows]
        events = self._event_parts(day, [assignment.id for assignment in assignments])
        reports = [
            self._tipper_report(
                assignment, tipper, site_row, driver, supervisor, events.get(assignment.id, [])
            )
            for assignment, tipper, site_row, driver, supervisor in rows
        ]
        return self._make_site_report(site, day, reports)

    def tipper_daily(
        self, tipper_id: UUID, requested_date: date | None = None
    ) -> list[TipperDailyReport]:
        tipper = self._tipper(tipper_id)
        day = self.operational_day(requested_date)
        rows = self._assignment_rows(day, tipper_id=tipper.id)
        events = self._event_parts(day, [row[0].id for row in rows])
        reports = [
            self._tipper_report(
                assignment, tipper_row, site, driver, supervisor, events.get(assignment.id, [])
            )
            for assignment, tipper_row, site, driver, supervisor in rows
        ]
        blockers_by_site: dict[UUID, list[ReportException]] = defaultdict(list)
        for report in reports:
            blockers_by_site[report.site.id].extend(report.exceptions)
        closure_by_site = self._closure_snapshots(
            day,
            list(blockers_by_site),
            blockers_by_site,
        )
        return [
            replace(report, closure_status=closure_by_site[report.site.id].status)
            for report in reports
        ]

    def dashboard(self, requested_date: date | None = None) -> DashboardReport:
        day = self.operational_day(requested_date)
        sites = list(
            self.session.scalars(
                select(Site).where(Site.company_id == self.company_id).order_by(Site.name, Site.id)
            ).all()
        )
        assignment_rows = self._assignment_rows(day)
        events = self._event_parts(day, [row[0].id for row in assignment_rows])
        by_site: dict[UUID, list[TipperDailyReport]] = defaultdict(list)
        for assignment, tipper, site, driver, supervisor in assignment_rows:
            by_site[site.id].append(
                self._tipper_report(
                    assignment, tipper, site, driver, supervisor, events.get(assignment.id, [])
                )
            )
        blockers_by_site = {
            site.id: [item for row in by_site.get(site.id, []) for item in row.exceptions]
            for site in sites
        }
        closure_by_site = self._closure_snapshots(
            day,
            [site.id for site in sites],
            blockers_by_site,
        )
        site_reports = [
            self._make_site_report(
                site,
                day,
                by_site.get(site.id, []),
                closure=closure_by_site[site.id],
            )
            for site in sites
        ]
        rows = [row for report in site_reports for row in report.rows]
        exceptions = [item for row in rows for item in row.exceptions]
        for report in site_reports:
            if report.rows and report.closure.status != SiteClosureStatus.CLOSED:
                exceptions.append(
                    ReportException(
                        code="SITE_NOT_CLOSED",
                        description=f"{report.site.name} is {report.closure.status.value}",
                        assignment_id=report.rows[0].assignment.id,
                        tipper_id=report.rows[0].tipper.id,
                        tipper_registration_number=report.rows[0].tipper.registration_number,
                        site_id=report.site.id,
                    )
                )
        distances = [row.distance_km for row in rows if row.distance_km is not None]
        return DashboardReport(
            operational_day=day,
            assigned_tippers_count=len({row.tipper.id for row in rows}),
            approved_trip_count=sum(row.approved_trip_count for row in rows),
            pending_trip_count=sum(row.pending_trip_count for row in rows),
            total_km=sum(distances, Decimal("0")) if distances else None,
            verified_diesel_issued=sum((row.verified_diesel_issued for row in rows), Decimal("0")),
            pending_verification_count=sum(
                sum(
                    1
                    for event in row.events
                    if event.event_type != OperationalEventType.EMERGENCY
                    and event.verification_status == VerificationStatus.PENDING_VERIFICATION
                )
                for row in rows
            ),
            missing_reading_count=sum(
                int(row.missing_start_reading) + int(row.missing_end_reading) for row in rows
            ),
            unresolved_emergency_count=sum(row.unresolved_emergency_count for row in rows),
            sites_not_closed_count=sum(
                1
                for report in site_reports
                if report.rows and report.closure.status != SiteClosureStatus.CLOSED
            ),
            complete_tippers_count=sum(1 for row in rows if row.completeness_status == "COMPLETE"),
            sites=site_reports,
            exceptions=exceptions,
        )

    def exceptions(self, requested_date: date | None = None) -> list[ReportException]:
        return self.dashboard(requested_date).exceptions

    def closure(self, site_id: UUID, requested_date: date | None = None) -> ClosureSnapshot:
        return self.site_daily(site_id, requested_date).closure

    def close_site(
        self,
        site_id: UUID,
        requested_date: date | None = None,
        *,
        reason: str | None = None,
    ) -> ClosureSnapshot:
        site = self._authorize_site(site_id)
        day = self.operational_day(requested_date)
        report = self.site_daily(site.id, day.operational_date)
        if report.closure.blockers:
            blockers = [
                {
                    "code": blocker.code,
                    "description": blocker.description,
                    "tipper_registration_number": blocker.tipper_registration_number,
                }
                for blocker in report.closure.blockers
            ]
            raise ClosureBlockedError("site day has operational blockers", blockers)
        closure = self.session.scalar(
            select(SiteDailyClosure)
            .where(
                SiteDailyClosure.company_id == self.company_id,
                SiteDailyClosure.site_id == site.id,
                SiteDailyClosure.operational_date == day.operational_date,
            )
            .with_for_update()
        )
        if closure is None:
            closure = SiteDailyClosure(
                company_id=self.company_id,
                site_id=site.id,
                operational_date=day.operational_date,
                reporting_timezone=day.reporting_timezone,
                workday_start_minutes=day.workday_start_minutes,
                status=SiteClosureStatus.CLOSED,
                closed_by_membership_id=self.context.membership.id,
                closed_at=utc_now(),
                reason=reason.strip() if reason else None,
            )
            self.session.add(closure)
            self.session.flush()
        elif closure.status == SiteClosureStatus.CLOSED:
            raise ConflictError("site day is already closed")
        else:
            closure.status = SiteClosureStatus.CLOSED
            closure.closed_by_membership_id = self.context.membership.id
            closure.closed_at = utc_now()
            closure.reporting_timezone = day.reporting_timezone
            closure.workday_start_minutes = day.workday_start_minutes
            closure.reason = reason.strip() if reason else None
            self.session.flush()
        self.session.add(
            SiteDailyClosureHistory(
                company_id=self.company_id,
                closure_id=closure.id,
                status=SiteClosureStatus.CLOSED,
                changed_by_membership_id=self.context.membership.id,
                reason=reason.strip() if reason else None,
            )
        )
        write_audit_log(
            self.session,
            company_id=self.company_id,
            actor_membership_id=self.context.membership.id,
            action="SITE_DAILY_CLOSED",
            entity_type="SITE_DAILY_CLOSURE",
            entity_id=closure.id,
            new_values={
                "site_id": str(site.id),
                "operational_date": day.operational_date.isoformat(),
            },
            reason=reason.strip() if reason else None,
        )
        self.session.flush()
        return self.closure(site.id, day.operational_date)

    def reopen_site(
        self,
        site_id: UUID,
        requested_date: date | None = None,
        *,
        reason: str,
    ) -> ClosureSnapshot:
        site = self._site(site_id)
        if self.context.membership.role != MembershipRole.OWNER_ADMIN:
            raise RoleViolationError("only an owner/admin can reopen a site day")
        clean_reason = reason.strip()
        if not clean_reason:
            raise DomainError("a reopening reason is required")
        day = self.operational_day(requested_date)
        closure = self.session.scalar(
            select(SiteDailyClosure)
            .where(
                SiteDailyClosure.company_id == self.company_id,
                SiteDailyClosure.site_id == site.id,
                SiteDailyClosure.operational_date == day.operational_date,
            )
            .with_for_update()
        )
        if closure is None or closure.status != SiteClosureStatus.CLOSED:
            raise ConflictError("only a closed site day can be reopened")
        closure.status = SiteClosureStatus.REOPENED
        closure.reopened_by_membership_id = self.context.membership.id
        closure.reopened_at = utc_now()
        closure.reason = clean_reason
        self.session.add(
            SiteDailyClosureHistory(
                company_id=self.company_id,
                closure_id=closure.id,
                status=SiteClosureStatus.REOPENED,
                changed_by_membership_id=self.context.membership.id,
                reason=clean_reason,
            )
        )
        write_audit_log(
            self.session,
            company_id=self.company_id,
            actor_membership_id=self.context.membership.id,
            action="SITE_DAILY_REOPENED",
            entity_type="SITE_DAILY_CLOSURE",
            entity_id=closure.id,
            reason=clean_reason,
        )
        self.session.flush()
        return self.closure(site.id, day.operational_date)

    def evidence_for_event(self, event_id: UUID) -> EvidenceObject:
        return self.evidence_context_for_event(event_id).evidence

    def evidence_context_for_event(self, event_id: UUID) -> ReportEvidenceContext:
        event = self.session.scalar(
            select(OperationalEvent).where(
                OperationalEvent.id == event_id,
                OperationalEvent.company_id == self.company_id,
            )
        )
        if event is None:
            raise NotFoundError("event was not found")
        evidence = self.session.scalar(
            select(EvidenceObject).where(
                EvidenceObject.company_id == self.company_id,
                EvidenceObject.client_event_uuid == event.client_event_uuid,
            )
        )
        if evidence is None:
            raise NotFoundError("event evidence was not found")
        row = self.session.execute(
            select(OperationalEvent, Tipper, User.display_name)
            .join(Assignment, Assignment.id == OperationalEvent.assignment_id)
            .join(Tipper, Tipper.id == Assignment.tipper_id)
            .join(CompanyMembership, CompanyMembership.id == Assignment.driver_membership_id)
            .join(User, User.id == CompanyMembership.user_id)
            .where(
                OperationalEvent.id == event_id,
                OperationalEvent.company_id == self.company_id,
            )
        ).first()
        if row is None:
            raise NotFoundError("event was not found")
        _event, tipper, driver_name = row._tuple()
        return ReportEvidenceContext(
            event=event,
            tipper=tipper,
            driver_name=driver_name,
            evidence=evidence,
        )
