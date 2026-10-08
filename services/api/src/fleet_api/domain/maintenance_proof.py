from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, and_, select
from sqlalchemy.orm import Session

from fleet_api.auth.service import AuthContext, ensure_supervisor_site_access
from fleet_api.db.models import (
    CompanyMembership,
    DutySession,
    EvidenceObject,
    FleetAsset,
    MaintenanceProofEvidence,
    MaintenanceProofSubmission,
    MaintenanceSchedule,
    Site,
    SupervisorSiteAccess,
    User,
)
from fleet_api.domain.audit import write_audit_log
from fleet_api.domain.driver import get_current_assignment
from fleet_api.domain.enums import (
    DutySessionStatus,
    MaintenanceDueState,
    MaintenanceProofStatus,
    MaintenanceWorkOrderStatus,
    MembershipRole,
)
from fleet_api.domain.errors import ConflictError, DomainError, NotFoundError
from fleet_api.domain.maintenance import (
    MaintenanceService,
    ScheduleEvaluation,
    company_manages_maintenance,
    task_label,
)


@dataclass(frozen=True)
class MaintenanceProofView:
    submission: MaintenanceProofSubmission
    schedule: MaintenanceSchedule
    asset: FleetAsset
    site: Site
    driver_name: str
    evidence: list[EvidenceObject]


@dataclass(frozen=True)
class SubmissionResult:
    view: MaintenanceProofView
    duplicate: bool


class MaintenanceProofService:
    """Driver submission and Site Supervisor verification boundary."""

    def __init__(
        self, session: Session, context: AuthContext, *, request_id: str | None = None
    ) -> None:
        self.session = session
        self.context = context
        self.company_id = context.company.id
        self.request_id = request_id

    def _audit(
        self,
        action: str,
        submission: MaintenanceProofSubmission,
        *,
        old_values: dict[str, object] | None = None,
        new_values: dict[str, object] | None = None,
    ) -> None:
        write_audit_log(
            self.session,
            company_id=self.company_id,
            actor_membership_id=self.context.membership.id,
            action=action,
            entity_type="MAINTENANCE_PROOF",
            entity_id=submission.id,
            old_values=old_values,
            new_values=new_values,
            request_id=self.request_id,
        )

    def driver_due_items(self) -> list[ScheduleEvaluation]:
        if self.context.membership.role != MembershipRole.DRIVER:
            raise DomainError("driver membership is required")
        current = get_current_assignment(self.session, self.context)
        if current is None or not company_manages_maintenance(current.asset):
            return []
        pending_schedule_ids = set(
            self.session.scalars(
                select(MaintenanceProofSubmission.schedule_id).where(
                    MaintenanceProofSubmission.company_id == self.company_id,
                    MaintenanceProofSubmission.asset_id == current.asset.id,
                    MaintenanceProofSubmission.status == MaintenanceProofStatus.PROOF_SUBMITTED,
                )
            ).all()
        )
        return [
            item
            for item in MaintenanceService(self.session, self.context).evaluations()
            if item.asset.id == current.asset.id
            and item.state in {MaintenanceDueState.DUE, MaintenanceDueState.OVERDUE}
            and item.schedule.id not in pending_schedule_ids
        ]

    def submit(
        self,
        *,
        client_submission_uuid: UUID,
        schedule_id: UUID,
        evidence_object_references: list[str],
        note: str | None,
    ) -> SubmissionResult:
        if self.context.membership.role != MembershipRole.DRIVER:
            raise DomainError("driver membership is required")
        existing = self.session.scalar(
            select(MaintenanceProofSubmission).where(
                MaintenanceProofSubmission.company_id == self.company_id,
                MaintenanceProofSubmission.driver_membership_id == self.context.membership.id,
                MaintenanceProofSubmission.client_submission_uuid == client_submission_uuid,
            )
        )
        clean_note = note.strip() if note else None
        if existing is not None:
            view = self._view(existing)
            existing_keys = [item.object_key for item in view.evidence]
            if (
                existing.schedule_id != schedule_id
                or existing.note != clean_note
                or existing_keys != evidence_object_references
            ):
                raise ConflictError("client submission UUID is already used by different proof")
            return SubmissionResult(view, True)

        current = get_current_assignment(self.session, self.context)
        if current is None:
            raise ConflictError("an active assignment is required")
        if not company_manages_maintenance(current.asset):
            raise DomainError("no company maintenance schedule applies to this asset")
        evaluation = next(
            (
                item
                for item in MaintenanceService(self.session, self.context).evaluations()
                if item.schedule.id == schedule_id and item.asset.id == current.asset.id
            ),
            None,
        )
        if evaluation is None:
            raise NotFoundError("maintenance item was not found")
        if evaluation.state not in {MaintenanceDueState.DUE, MaintenanceDueState.OVERDUE}:
            raise ConflictError("maintenance proof can be submitted only for due work")
        pending_id = self.session.scalar(
            select(MaintenanceProofSubmission.id).where(
                MaintenanceProofSubmission.company_id == self.company_id,
                MaintenanceProofSubmission.schedule_id == schedule_id,
                MaintenanceProofSubmission.status == MaintenanceProofStatus.PROOF_SUBMITTED,
            )
        )
        if pending_id is not None:
            raise ConflictError("maintenance proof is already awaiting Supervisor review")
        if not evidence_object_references:
            raise DomainError("at least one service photo is required")
        if len(evidence_object_references) != len(set(evidence_object_references)):
            raise DomainError("service photos must be unique")
        evidence = list(
            self.session.scalars(
                select(EvidenceObject).where(
                    EvidenceObject.company_id == self.company_id,
                    EvidenceObject.membership_id == self.context.membership.id,
                    EvidenceObject.object_key.in_(evidence_object_references),
                )
            ).all()
        )
        by_key = {item.object_key: item for item in evidence}
        if any(key not in by_key for key in evidence_object_references):
            raise DomainError("maintenance proof evidence is missing or unauthorized")
        duty = self.session.scalar(
            select(DutySession)
            .where(
                DutySession.company_id == self.company_id,
                DutySession.assignment_id == current.assignment.id,
                DutySession.driver_membership_id == self.context.membership.id,
                DutySession.status == DutySessionStatus.ACTIVE,
            )
            .order_by(DutySession.started_at.desc(), DutySession.id.desc())
        )
        submitted_at = datetime.now(UTC)
        submission = MaintenanceProofSubmission(
            company_id=self.company_id,
            asset_id=current.asset.id,
            schedule_id=evaluation.schedule.id,
            driver_membership_id=self.context.membership.id,
            assignment_id=current.assignment.id,
            site_id=current.site.id,
            duty_session_id=duty.id if duty else None,
            client_submission_uuid=client_submission_uuid,
            status=MaintenanceProofStatus.PROOF_SUBMITTED,
            note=clean_note,
            submitted_at=submitted_at,
        )
        self.session.add(submission)
        self.session.flush()
        for position, object_key in enumerate(evidence_object_references):
            self.session.add(
                MaintenanceProofEvidence(
                    company_id=self.company_id,
                    submission_id=submission.id,
                    evidence_id=by_key[object_key].id,
                    display_order=position,
                )
            )
        self.session.flush()
        self._audit(
            "MAINTENANCE_PROOF_SUBMITTED",
            submission,
            new_values={
                "asset_id": str(submission.asset_id),
                "schedule_id": str(submission.schedule_id),
                "assignment_id": str(submission.assignment_id),
                "site_id": str(submission.site_id),
                "evidence_count": len(evidence_object_references),
            },
        )
        return SubmissionResult(self._view(submission), False)

    def list_supervisor_submissions(
        self, *, site_id: UUID | None = None
    ) -> list[MaintenanceProofView]:
        if self.context.membership.role != MembershipRole.SUPERVISOR:
            raise DomainError("supervisor membership is required")
        if site_id is not None:
            ensure_supervisor_site_access(self.session, self.context, site_id=site_id)
        permitted_sites = select_site_ids_for_supervisor(
            self.company_id, self.context.membership.id
        )
        query = (
            select(MaintenanceProofSubmission)
            .where(
                MaintenanceProofSubmission.company_id == self.company_id,
                MaintenanceProofSubmission.site_id.in_(permitted_sites),
            )
            .order_by(
                MaintenanceProofSubmission.status,
                MaintenanceProofSubmission.submitted_at.desc(),
            )
        )
        if site_id is not None:
            query = query.where(MaintenanceProofSubmission.site_id == site_id)
        return [self._view(item) for item in self.session.scalars(query).all()]

    def _submission_for_review(
        self, submission_id: UUID, *, lock: bool = False
    ) -> MaintenanceProofSubmission:
        query = select(MaintenanceProofSubmission).where(
            MaintenanceProofSubmission.company_id == self.company_id,
            MaintenanceProofSubmission.id == submission_id,
        )
        if lock:
            query = query.with_for_update()
        submission = self.session.scalar(query)
        if submission is None:
            raise NotFoundError("maintenance proof was not found")
        ensure_supervisor_site_access(self.session, self.context, site_id=submission.site_id)
        return submission

    def approve(self, submission_id: UUID) -> MaintenanceProofView:
        if self.context.membership.role != MembershipRole.SUPERVISOR:
            raise DomainError("supervisor membership is required")
        submission = self._submission_for_review(submission_id, lock=True)
        if submission.status == MaintenanceProofStatus.COMPLETED:
            return self._view(submission)
        if submission.status != MaintenanceProofStatus.PROOF_SUBMITTED:
            raise ConflictError("only submitted maintenance proof can be approved")
        maintenance = MaintenanceService(self.session, self.context, request_id=self.request_id)
        schedule = maintenance._schedule(submission.schedule_id)
        km, hmr = maintenance.current_meters(submission.asset_id)
        order = maintenance.create_work_order(
            submission.asset_id,
            schedule_id=schedule.id,
            title=task_label(schedule.task_code, schedule.custom_label),
            description="Created from Driver service proof after Supervisor review.",
            scheduled_for=None,
        )
        order.status = MaintenanceWorkOrderStatus.IN_PROGRESS
        maintenance.complete_work_order(
            order.id,
            service_date=datetime.now(UTC).date(),
            odometer_km=km,
            hour_meter=hmr,
            vendor=None,
            parts_cost=Decimal("0"),
            labor_cost=Decimal("0"),
            other_cost=Decimal("0"),
            notes=submission.note,
        )
        now = datetime.now(UTC)
        submission.status = MaintenanceProofStatus.COMPLETED
        submission.reviewed_by_membership_id = self.context.membership.id
        submission.reviewed_at = now
        submission.review_reason = None
        submission.work_order_id = order.id
        self.session.flush()
        self._audit(
            "MAINTENANCE_PROOF_APPROVED",
            submission,
            old_values={"status": MaintenanceProofStatus.PROOF_SUBMITTED.value},
            new_values={
                "status": MaintenanceProofStatus.COMPLETED.value,
                "work_order_id": str(order.id),
                "odometer_km": str(km) if km is not None else None,
                "hour_meter": str(hmr) if hmr is not None else None,
            },
        )
        return self._view(submission)

    def reject(self, submission_id: UUID, *, reason: str) -> MaintenanceProofView:
        if self.context.membership.role != MembershipRole.SUPERVISOR:
            raise DomainError("supervisor membership is required")
        clean_reason = reason.strip()
        if not clean_reason:
            raise DomainError("a rejection reason is required")
        submission = self._submission_for_review(submission_id, lock=True)
        if submission.status != MaintenanceProofStatus.PROOF_SUBMITTED:
            raise ConflictError("only submitted maintenance proof can be rejected")
        submission.status = MaintenanceProofStatus.REJECTED
        submission.reviewed_by_membership_id = self.context.membership.id
        submission.reviewed_at = datetime.now(UTC)
        submission.review_reason = clean_reason
        self.session.flush()
        self._audit(
            "MAINTENANCE_PROOF_REJECTED",
            submission,
            old_values={"status": MaintenanceProofStatus.PROOF_SUBMITTED.value},
            new_values={
                "status": MaintenanceProofStatus.REJECTED.value,
                "reason": clean_reason,
            },
        )
        return self._view(submission)

    def evidence_for_supervisor(self, submission_id: UUID, evidence_id: UUID) -> EvidenceObject:
        submission = self._submission_for_review(submission_id)
        evidence = self.session.scalar(
            select(EvidenceObject)
            .join(
                MaintenanceProofEvidence,
                and_(
                    MaintenanceProofEvidence.company_id == EvidenceObject.company_id,
                    MaintenanceProofEvidence.evidence_id == EvidenceObject.id,
                ),
            )
            .where(
                MaintenanceProofEvidence.company_id == self.company_id,
                MaintenanceProofEvidence.submission_id == submission.id,
                EvidenceObject.id == evidence_id,
            )
        )
        if evidence is None:
            raise NotFoundError("maintenance proof evidence was not found")
        return evidence

    def _view(self, submission: MaintenanceProofSubmission) -> MaintenanceProofView:
        row = self.session.execute(
            select(MaintenanceSchedule, FleetAsset, Site, CompanyMembership, User)
            .join(
                FleetAsset,
                and_(
                    FleetAsset.company_id == MaintenanceSchedule.company_id,
                    FleetAsset.id == MaintenanceSchedule.asset_id,
                ),
            )
            .join(
                MaintenanceProofSubmission,
                and_(
                    MaintenanceProofSubmission.company_id == MaintenanceSchedule.company_id,
                    MaintenanceProofSubmission.schedule_id == MaintenanceSchedule.id,
                ),
            )
            .join(
                Site,
                and_(
                    Site.company_id == MaintenanceProofSubmission.company_id,
                    Site.id == MaintenanceProofSubmission.site_id,
                ),
            )
            .join(
                CompanyMembership,
                and_(
                    CompanyMembership.company_id == MaintenanceProofSubmission.company_id,
                    CompanyMembership.id == MaintenanceProofSubmission.driver_membership_id,
                ),
            )
            .join(User, User.id == CompanyMembership.user_id)
            .where(
                MaintenanceProofSubmission.company_id == self.company_id,
                MaintenanceProofSubmission.id == submission.id,
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("maintenance proof was not found")
        schedule, asset, site, membership, user = row._tuple()
        evidence = list(
            self.session.scalars(
                select(EvidenceObject)
                .join(
                    MaintenanceProofEvidence,
                    and_(
                        MaintenanceProofEvidence.company_id == EvidenceObject.company_id,
                        MaintenanceProofEvidence.evidence_id == EvidenceObject.id,
                    ),
                )
                .where(
                    MaintenanceProofEvidence.company_id == self.company_id,
                    MaintenanceProofEvidence.submission_id == submission.id,
                )
                .order_by(MaintenanceProofEvidence.display_order)
            ).all()
        )
        return MaintenanceProofView(
            submission=submission,
            schedule=schedule,
            asset=asset,
            site=site,
            driver_name=membership.display_name or user.display_name,
            evidence=evidence,
        )


def select_site_ids_for_supervisor(
    company_id: UUID, supervisor_membership_id: UUID
) -> Select[tuple[UUID]]:
    return select(SupervisorSiteAccess.site_id).where(
        SupervisorSiteAccess.company_id == company_id,
        SupervisorSiteAccess.supervisor_membership_id == supervisor_membership_id,
    )
