from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

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
    SupervisorSiteAccess,
    Tipper,
    TripEvent,
    User,
)
from fleet_api.domain.audit import write_audit_log
from fleet_api.domain.enums import EmergencyStatus, OperationalEventType, VerificationStatus
from fleet_api.domain.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    TenantConsistencyError,
)
from fleet_api.domain.events import record_verification


@dataclass(frozen=True)
class VerificationHistoryItem:
    status: VerificationStatus
    reason: str | None
    actor_name: str | None
    created_at: datetime


@dataclass(frozen=True)
class SupervisorEvent:
    event: OperationalEvent
    assignment: Assignment
    tipper: Tipper
    site: Site
    driver: User
    trip: TripEvent | None
    km: KmReading | None
    diesel: DieselEvent | None
    emergency: EmergencyEvent | None
    evidence: EvidenceObject | None
    history: list[VerificationHistoryItem]


@dataclass(frozen=True)
class SiteCompleteness:
    assignment: Assignment
    tipper: Tipper
    site: Site
    driver: User
    has_start_reading: bool
    has_end_reading: bool
    start_reading_value: Decimal | None
    end_reading_value: Decimal | None
    odometer_regression: bool
    pending_trip_verification: bool
    pending_diesel_verification: bool
    unresolved_emergency: bool


class SupervisorService:
    """Site-scoped verification and operational completeness operations."""

    def __init__(self, session: Session, context: AuthContext) -> None:
        self.session = session
        self.context = context
        if context.membership.role.value != "SUPERVISOR":
            raise TenantConsistencyError("supervisor membership is required")

    def _site(self, site_id: UUID) -> Site:
        try:
            ensure_supervisor_site_access(self.session, self.context, site_id=site_id)
        except DomainError as exc:
            raise TenantConsistencyError("supervisor is not authorized for this site") from exc
        site = self.session.scalar(
            select(Site).where(Site.id == site_id, Site.company_id == self.context.company.id)
        )
        if site is None:
            raise NotFoundError("site was not found")
        return site

    def list_sites(self) -> list[Site]:
        return list(
            self.session.scalars(
                select(Site)
                .join(
                    SupervisorSiteAccess,
                    and_(
                        SupervisorSiteAccess.site_id == Site.id,
                        SupervisorSiteAccess.company_id == Site.company_id,
                    ),
                )
                .where(
                    Site.company_id == self.context.company.id,
                    SupervisorSiteAccess.supervisor_membership_id == self.context.membership.id,
                )
                .order_by(Site.name, Site.id)
            ).all()
        )

    def _event_query(
        self,
    ) -> Select[tuple[OperationalEvent, Assignment, Tipper, Site, CompanyMembership, User]]:
        return (
            select(OperationalEvent, Assignment, Tipper, Site, CompanyMembership, User)
            .join(Assignment, Assignment.id == OperationalEvent.assignment_id)
            .join(Tipper, Tipper.id == Assignment.tipper_id)
            .join(Site, Site.id == Assignment.site_id)
            .join(CompanyMembership, CompanyMembership.id == Assignment.driver_membership_id)
            .join(User, User.id == CompanyMembership.user_id)
            .where(OperationalEvent.company_id == self.context.company.id)
        )

    def _event_row(
        self,
        event_id: UUID,
        *,
        lock: bool = False,
    ) -> tuple[OperationalEvent, Assignment, Tipper, Site, CompanyMembership, User]:
        statement = self._event_query().where(OperationalEvent.id == event_id)
        if lock:
            statement = statement.with_for_update()
        row = self.session.execute(statement).first()
        if row is None:
            raise NotFoundError("event was not found")
        event, assignment, tipper, site, driver_membership, driver = row._tuple()
        self._site(site.id)
        return event, assignment, tipper, site, driver_membership, driver

    def _history(self, event_id: UUID) -> list[VerificationHistoryItem]:
        rows = self.session.execute(
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
                EventVerification.company_id == self.context.company.id,
                EventVerification.event_id == event_id,
            )
            .order_by(EventVerification.created_at.asc(), EventVerification.id.asc())
        )
        return [
            VerificationHistoryItem(
                status=verification.status,
                reason=verification.reason,
                actor_name=actor_name,
                created_at=verification.created_at,
            )
            for verification, actor_name in rows
        ]

    def _event_view(
        self,
        row: tuple[OperationalEvent, Assignment, Tipper, Site, CompanyMembership, User],
    ) -> SupervisorEvent:
        event, assignment, tipper, site, _driver_membership, _driver = row
        trip = self.session.get(TripEvent, event.id)
        km = self.session.get(KmReading, event.id)
        diesel = self.session.get(DieselEvent, event.id)
        emergency = self.session.get(EmergencyEvent, event.id)
        object_reference = None
        if km is not None:
            object_reference = km.object_reference
        elif diesel is not None:
            object_reference = diesel.object_reference
        evidence = None
        if object_reference is not None:
            evidence = self.session.scalar(
                select(EvidenceObject).where(
                    EvidenceObject.company_id == self.context.company.id,
                    EvidenceObject.membership_id == assignment.driver_membership_id,
                    EvidenceObject.client_event_uuid == event.client_event_uuid,
                    EvidenceObject.object_key == object_reference,
                )
            )
        return SupervisorEvent(
            event=event,
            assignment=assignment,
            tipper=tipper,
            site=site,
            driver=_driver,
            trip=trip,
            km=km,
            diesel=diesel,
            emergency=emergency,
            evidence=evidence,
            history=self._history(event.id),
        )

    def list_events(
        self,
        site_id: UUID,
        *,
        verification_status: VerificationStatus | None = None,
        review_date: date | None = None,
        limit: int = 200,
    ) -> list[SupervisorEvent]:
        self._site(site_id)
        statement = (
            self._event_query()
            .where(Site.id == site_id)
            .order_by(OperationalEvent.device_created_at.desc(), OperationalEvent.id.desc())
        )
        if verification_status is not None:
            statement = statement.where(OperationalEvent.verification_status == verification_status)
        if review_date is not None:
            start = datetime.combine(review_date, time.min, tzinfo=UTC)
            end = start + timedelta(days=1)
            statement = statement.where(
                OperationalEvent.device_created_at >= start,
                OperationalEvent.device_created_at < end,
            )
        rows = self.session.execute(statement.limit(limit)).all()
        return [self._event_view(row._tuple()) for row in rows]

    def verify_event(
        self,
        event_id: UUID,
        *,
        decision: VerificationStatus,
        reason: str | None,
        expected_status: VerificationStatus,
    ) -> SupervisorEvent:
        if decision not in {
            VerificationStatus.APPROVED,
            VerificationStatus.REJECTED,
            VerificationStatus.DISPUTED,
        }:
            raise DomainError("verification decision is unsupported")
        clean_reason = reason.strip() if reason else None
        if (
            decision in {VerificationStatus.REJECTED, VerificationStatus.DISPUTED}
            and not clean_reason
        ):
            raise DomainError("a reason is required for rejection or dispute")
        row = self._event_row(event_id, lock=True)
        event = row[0]
        if event.event_type == OperationalEventType.EMERGENCY:
            raise DomainError("emergency uses acknowledge and resolve, not verification")
        if event.verification_status != expected_status:
            raise ConflictError("event verification changed; reload before deciding")
        record_verification(
            self.session,
            company_id=self.context.company.id,
            event_id=event.id,
            status=decision,
            changed_by_membership_id=self.context.membership.id,
            reason=clean_reason,
        )
        return self._event_view(row)

    def verify_batch(
        self,
        event_ids: list[UUID],
        *,
        decision: VerificationStatus,
        reason: str | None,
        expected_status: VerificationStatus,
    ) -> list[SupervisorEvent]:
        if len(set(event_ids)) != len(event_ids):
            raise DomainError("batch contains duplicate event IDs")
        return [
            self.verify_event(
                event_id,
                decision=decision,
                reason=reason,
                expected_status=expected_status,
            )
            for event_id in event_ids
        ]

    def acknowledge_emergency(self, event_id: UUID) -> SupervisorEvent:
        row = self._event_row(event_id, lock=True)
        event, _assignment, _tipper, _site, _membership, _driver = row
        emergency = self.session.get(EmergencyEvent, event.id)
        if emergency is None or event.event_type != OperationalEventType.EMERGENCY:
            raise DomainError("event is not an emergency")
        if emergency.status == EmergencyStatus.OPEN:
            emergency.status = EmergencyStatus.ACKNOWLEDGED
            write_audit_log(
                self.session,
                company_id=self.context.company.id,
                actor_membership_id=self.context.membership.id,
                action="SUPERVISOR_EMERGENCY_ACKNOWLEDGED",
                entity_type="EMERGENCY_EVENT",
                entity_id=event.id,
                new_values={"status": emergency.status.value},
            )
            self.session.flush()
        return self._event_view(row)

    def resolve_emergency(self, event_id: UUID) -> SupervisorEvent:
        row = self._event_row(event_id, lock=True)
        event, _assignment, _tipper, _site, _membership, _driver = row
        emergency = self.session.get(EmergencyEvent, event.id)
        if emergency is None or event.event_type != OperationalEventType.EMERGENCY:
            raise DomainError("event is not an emergency")
        if emergency.status == EmergencyStatus.OPEN:
            raise DomainError("emergency must be acknowledged before it can be resolved")
        if emergency.status == EmergencyStatus.ACKNOWLEDGED:
            emergency.status = EmergencyStatus.RESOLVED
            write_audit_log(
                self.session,
                company_id=self.context.company.id,
                actor_membership_id=self.context.membership.id,
                action="SUPERVISOR_EMERGENCY_RESOLVED",
                entity_type="EMERGENCY_EVENT",
                entity_id=event.id,
                new_values={"status": emergency.status.value},
            )
            self.session.flush()
        return self._event_view(row)

    def evidence_for_event(self, event_id: UUID) -> EvidenceObject:
        view = self.evidence_view_for_event(event_id)
        if view.evidence is None:
            raise NotFoundError("event evidence was not found")
        return view.evidence

    def evidence_view_for_event(self, event_id: UUID) -> SupervisorEvent:
        view = self._event_view(self._event_row(event_id))
        if view.evidence is None:
            raise NotFoundError("event evidence was not found")
        return view

    def completeness(self, site_id: UUID, review_date: date) -> list[SiteCompleteness]:
        site = self._site(site_id)
        start = datetime.combine(review_date, time.min, tzinfo=UTC)
        end = start + timedelta(days=1)
        assignments = self.session.execute(
            select(Assignment, Tipper, CompanyMembership, User)
            .join(Tipper, Tipper.id == Assignment.tipper_id)
            .join(CompanyMembership, CompanyMembership.id == Assignment.driver_membership_id)
            .join(User, User.id == CompanyMembership.user_id)
            .where(
                Assignment.company_id == self.context.company.id,
                Assignment.site_id == site_id,
                Assignment.starts_at < end,
                (Assignment.ends_at.is_(None) | (Assignment.ends_at > start)),
            )
            .order_by(Assignment.starts_at.asc(), Assignment.id.asc())
        ).all()
        result: list[SiteCompleteness] = []
        for assignment, tipper, _membership, driver in assignments:
            events = list(
                self.session.scalars(
                    select(OperationalEvent).where(
                        OperationalEvent.company_id == self.context.company.id,
                        OperationalEvent.assignment_id == assignment.id,
                        OperationalEvent.device_created_at >= start,
                        OperationalEvent.device_created_at < end,
                    )
                ).all()
            )
            km_events = [self.session.get(KmReading, event.id) for event in events]
            emergencies = [self.session.get(EmergencyEvent, event.id) for event in events]
            start_values = [
                reading.reading_value
                for reading in km_events
                if reading is not None and reading.reading_type.value == "START_READING"
            ]
            end_values = [
                reading.reading_value
                for reading in km_events
                if reading is not None and reading.reading_type.value == "END_READING"
            ]
            start_reading_value = max(start_values) if start_values else None
            end_reading_value = min(end_values) if end_values else None
            result.append(
                SiteCompleteness(
                    assignment=assignment,
                    tipper=tipper,
                    site=site,
                    driver=driver,
                    has_start_reading=any(
                        reading is not None and reading.reading_type.value == "START_READING"
                        for reading in km_events
                    ),
                    has_end_reading=any(
                        reading is not None and reading.reading_type.value == "END_READING"
                        for reading in km_events
                    ),
                    start_reading_value=start_reading_value,
                    end_reading_value=end_reading_value,
                    odometer_regression=(
                        start_reading_value is not None
                        and end_reading_value is not None
                        and end_reading_value < start_reading_value
                    ),
                    pending_trip_verification=any(
                        event.event_type == OperationalEventType.TRIP_COMPLETE
                        and event.verification_status == VerificationStatus.PENDING_VERIFICATION
                        for event in events
                    ),
                    pending_diesel_verification=any(
                        event.event_type == OperationalEventType.DIESEL
                        and event.verification_status == VerificationStatus.PENDING_VERIFICATION
                        for event in events
                    ),
                    unresolved_emergency=any(
                        emergency is not None
                        and emergency.status
                        not in {EmergencyStatus.RESOLVED, EmergencyStatus.CLOSED}
                        for emergency in emergencies
                    ),
                )
            )
        return result
