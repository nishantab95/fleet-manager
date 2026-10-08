from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from fleet_api.auth.service import AuthContext
from fleet_api.db.models import (
    AssetSiteDeployment,
    Assignment,
    CompanyMembership,
    DutySession,
    FleetAsset,
    Site,
    SupervisorSiteAccess,
    User,
)
from fleet_api.domain.assets import capabilities_for_asset
from fleet_api.domain.audit import write_audit_log
from fleet_api.domain.enums import (
    DutySessionStatus,
    FleetAssetStatus,
    MembershipRole,
    MembershipStatus,
    OwnerOperationAction,
    SiteStatus,
    UserStatus,
)
from fleet_api.domain.errors import ConflictError, DomainError, NotFoundError

AssignmentResolution = Literal["KEEP", "END"]
SiteAssetAction = Literal["MOVE", "REMOVE"]


@dataclass(frozen=True)
class SiteAssetResolution:
    asset_id: UUID
    action: SiteAssetAction
    target_site_id: UUID | None = None
    assignment_action: AssignmentResolution | None = None


@dataclass(frozen=True)
class OwnerOperationIntent:
    action: OwnerOperationAction
    asset_id: UUID | None = None
    person_membership_id: UUID | None = None
    site_id: UUID | None = None
    target_site_id: UUID | None = None
    driver_membership_id: UUID | None = None
    selected_site_ids: tuple[UUID, ...] = ()
    selected_supervisor_ids: tuple[UUID, ...] = ()
    selected_asset_ids: tuple[UUID, ...] = ()
    asset_resolutions: tuple[SiteAssetResolution, ...] = ()
    assignment_action: AssignmentResolution | None = None
    activate_membership: bool = False
    regular_duty_minutes: int = 600
    reason: str | None = None


OperationDetailValue = str | int | bool | None


@dataclass(frozen=True)
class OperationItem:
    kind: str
    id: UUID
    label: str
    status: str
    details: dict[str, OperationDetailValue] = field(default_factory=dict)


@dataclass(frozen=True)
class OwnerOperationPlan:
    action: OwnerOperationAction
    state_token: str
    title: str
    summary: str
    current_state: list[OperationItem]
    dependencies: list[OperationItem]
    warnings: list[str]
    allowed_resolutions: list[str]
    blocked_reasons: list[str]
    planned_changes: list[str]

    @property
    def can_execute(self) -> bool:
        return not self.blocked_reasons


@dataclass(frozen=True)
class OwnerOperationResult:
    action: OwnerOperationAction
    completed_changes: list[str]
    message: str


def _effective_assignment_clause(
    now: datetime,
) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    return (
        Assignment.starts_at <= now,
        or_(Assignment.ends_at.is_(None), Assignment.ends_at > now),
    )


class OwnerOperationPlanner:
    """Server-authoritative preview and atomic execution for Owner relationships.

    The browser submits only business intent and resolution choices. Every preview
    derives dependencies from the database. Execute repeats the same reads under
    row locks and compares a scoped state token before changing anything.
    """

    def __init__(
        self,
        session: Session,
        context: AuthContext,
        *,
        request_id: str | None = None,
    ) -> None:
        self.session = session
        self.company_id = context.company.id
        self.actor_membership_id = context.membership.id
        self.request_id = request_id

    def _asset(self, asset_id: UUID, *, lock: bool = False) -> FleetAsset:
        statement = select(FleetAsset).where(
            FleetAsset.company_id == self.company_id,
            FleetAsset.id == asset_id,
        )
        if lock:
            statement = statement.with_for_update()
        asset = self.session.scalar(statement)
        if asset is None:
            raise NotFoundError("asset was not found")
        return asset

    def _site(self, site_id: UUID, *, lock: bool = False) -> Site:
        statement = select(Site).where(
            Site.company_id == self.company_id,
            Site.id == site_id,
        )
        if lock:
            statement = statement.with_for_update()
        site = self.session.scalar(statement)
        if site is None:
            raise NotFoundError("site was not found")
        return site

    def _membership(
        self, membership_id: UUID, *, lock: bool = False
    ) -> tuple[CompanyMembership, User]:
        statement = (
            select(CompanyMembership, User)
            .join(User, User.id == CompanyMembership.user_id)
            .where(
                CompanyMembership.company_id == self.company_id,
                CompanyMembership.id == membership_id,
            )
        )
        if lock:
            statement = statement.with_for_update(of=CompanyMembership)
        row = self.session.execute(statement).first()
        if row is None:
            raise NotFoundError("person was not found")
        membership, user = row._tuple()
        return membership, user

    def _deployment(self, asset_id: UUID, *, lock: bool = False) -> AssetSiteDeployment | None:
        statement = select(AssetSiteDeployment).where(
            AssetSiteDeployment.company_id == self.company_id,
            AssetSiteDeployment.asset_id == asset_id,
            AssetSiteDeployment.ends_at.is_(None),
        )
        if lock:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def _assignment(self, asset_id: UUID, *, at: datetime, lock: bool = False) -> Assignment | None:
        statement = (
            select(Assignment)
            .where(
                Assignment.company_id == self.company_id,
                Assignment.asset_id == asset_id,
                *_effective_assignment_clause(at),
            )
            .order_by(Assignment.starts_at.desc(), Assignment.id.desc())
            .limit(1)
        )
        if lock:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def _driver_assignment(
        self, membership_id: UUID, *, at: datetime, lock: bool = False
    ) -> Assignment | None:
        statement = (
            select(Assignment)
            .where(
                Assignment.company_id == self.company_id,
                Assignment.driver_membership_id == membership_id,
                *_effective_assignment_clause(at),
            )
            .order_by(Assignment.starts_at.desc(), Assignment.id.desc())
            .limit(1)
        )
        if lock:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def _duty(self, asset_id: UUID, *, lock: bool = False) -> DutySession | None:
        statement = (
            select(DutySession)
            .where(
                DutySession.company_id == self.company_id,
                DutySession.asset_id == asset_id,
                DutySession.status == DutySessionStatus.ACTIVE,
            )
            .order_by(DutySession.started_at.desc(), DutySession.id.desc())
            .limit(1)
        )
        if lock:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    @staticmethod
    def _asset_label(asset: FleetAsset) -> str:
        return asset.short_name or asset.registration_number or asset.asset_code

    @staticmethod
    def _person_label(membership: CompanyMembership, user: User) -> str:
        return membership.display_name or user.display_name

    @staticmethod
    def _snapshot_row(kind: str, row: object | None, **values: object) -> dict[str, object]:
        result: dict[str, object] = {"kind": kind, **values}
        if row is None:
            result["present"] = False
            return result
        result["present"] = True
        row_id = getattr(row, "id", None)
        updated_at = getattr(row, "updated_at", None)
        if row_id is not None:
            result["id"] = str(row_id)
        if isinstance(updated_at, datetime):
            result["updated_at"] = updated_at.isoformat()
        return result

    @staticmethod
    def _intent_values(intent: OwnerOperationIntent) -> dict[str, object]:
        return {
            "action": intent.action.value,
            "asset_id": str(intent.asset_id) if intent.asset_id else None,
            "person_membership_id": (
                str(intent.person_membership_id) if intent.person_membership_id else None
            ),
            "site_id": str(intent.site_id) if intent.site_id else None,
            "target_site_id": str(intent.target_site_id) if intent.target_site_id else None,
            "driver_membership_id": (
                str(intent.driver_membership_id) if intent.driver_membership_id else None
            ),
            "selected_site_ids": sorted(str(value) for value in intent.selected_site_ids),
            "selected_supervisor_ids": sorted(
                str(value) for value in intent.selected_supervisor_ids
            ),
            "selected_asset_ids": sorted(str(value) for value in intent.selected_asset_ids),
            "asset_resolutions": sorted(
                (
                    {
                        "asset_id": str(item.asset_id),
                        "action": item.action,
                        "target_site_id": (
                            str(item.target_site_id) if item.target_site_id else None
                        ),
                        "assignment_action": item.assignment_action,
                    }
                    for item in intent.asset_resolutions
                ),
                key=lambda item: str(item["asset_id"]),
            ),
            "assignment_action": intent.assignment_action,
            "activate_membership": intent.activate_membership,
            "regular_duty_minutes": intent.regular_duty_minutes,
            "reason": intent.reason,
        }

    def _token(self, intent: OwnerOperationIntent, snapshot: list[dict[str, object]]) -> str:
        encoded = json.dumps(
            {"intent": self._intent_values(intent), "state": snapshot},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _plan(
        self,
        intent: OwnerOperationIntent,
        *,
        title: str,
        summary: str,
        current_state: list[OperationItem],
        dependencies: list[OperationItem],
        warnings: list[str],
        allowed_resolutions: list[str],
        blocked_reasons: list[str],
        planned_changes: list[str],
        snapshot: list[dict[str, object]],
    ) -> OwnerOperationPlan:
        return OwnerOperationPlan(
            action=intent.action,
            state_token=self._token(intent, snapshot),
            title=title,
            summary=summary,
            current_state=current_state,
            dependencies=dependencies,
            warnings=warnings,
            allowed_resolutions=allowed_resolutions,
            blocked_reasons=blocked_reasons,
            planned_changes=planned_changes,
        )

    def preview(self, intent: OwnerOperationIntent, *, lock: bool = False) -> OwnerOperationPlan:
        if intent.regular_duty_minutes <= 0 or intent.regular_duty_minutes > 1440:
            raise DomainError("regular_duty_minutes must be between 1 and 1440")
        handlers = {
            OwnerOperationAction.ACTIVATE_PERSON: self._preview_activate_person,
            OwnerOperationAction.SET_SUPERVISOR_SITES: self._preview_supervisor_sites,
            OwnerOperationAction.DEACTIVATE_PERSON: self._preview_deactivate_person,
            OwnerOperationAction.DEPLOY_ASSET: self._preview_deploy_asset,
            OwnerOperationAction.MOVE_DEPLOYMENT: self._preview_move_deployment,
            OwnerOperationAction.REMOVE_DEPLOYMENT: self._preview_remove_deployment,
            OwnerOperationAction.ASSIGN_DRIVER: self._preview_assign_driver,
            OwnerOperationAction.REASSIGN_DRIVER: self._preview_reassign_driver,
            OwnerOperationAction.END_ASSIGNMENT: self._preview_end_assignment,
            OwnerOperationAction.DEACTIVATE_ASSET: self._preview_deactivate_asset,
            OwnerOperationAction.FORCE_CLOSE_DUTY_AND_DEACTIVATE_ASSET: (
                self._preview_force_close_duty_and_deactivate_asset
            ),
            OwnerOperationAction.REACTIVATE_ASSET: self._preview_reactivate_asset,
            OwnerOperationAction.DEACTIVATE_SITE: self._preview_deactivate_site,
            OwnerOperationAction.REACTIVATE_SITE: self._preview_reactivate_site,
        }
        return handlers[intent.action](intent, lock)

    def _asset_relationship_state(
        self,
        asset_id: UUID,
        *,
        lock: bool,
    ) -> tuple[
        FleetAsset,
        AssetSiteDeployment | None,
        Site | None,
        Assignment | None,
        CompanyMembership | None,
        User | None,
        DutySession | None,
        list[dict[str, object]],
    ]:
        now = datetime.now(UTC)
        asset = self._asset(asset_id, lock=lock)
        deployment = self._deployment(asset.id, lock=lock)
        site = self._site(deployment.site_id, lock=lock) if deployment is not None else None
        assignment = self._assignment(asset.id, at=now, lock=lock)
        membership: CompanyMembership | None = None
        user: User | None = None
        if assignment is not None:
            membership, user = self._membership(
                assignment.driver_membership_id,
                lock=lock,
            )
        duty = self._duty(asset.id, lock=lock)
        snapshot = [
            self._snapshot_row(
                "asset",
                asset,
                status=asset.status.value,
            ),
            self._snapshot_row(
                "deployment",
                deployment,
                site_id=str(deployment.site_id) if deployment else None,
                starts_at=deployment.starts_at.isoformat() if deployment else None,
                ends_at=deployment.ends_at.isoformat()
                if deployment and deployment.ends_at
                else None,
            ),
            self._snapshot_row(
                "assignment",
                assignment,
                driver_membership_id=(str(assignment.driver_membership_id) if assignment else None),
                deployment_id=(str(assignment.asset_site_deployment_id) if assignment else None),
                starts_at=assignment.starts_at.isoformat() if assignment else None,
                ends_at=assignment.ends_at.isoformat()
                if assignment and assignment.ends_at
                else None,
            ),
            self._snapshot_row(
                "duty",
                duty,
                assignment_id=str(duty.assignment_id) if duty else None,
                status=duty.status.value if duty else None,
                started_at=duty.started_at.isoformat() if duty else None,
                end_event_id=(str(duty.end_event_id) if duty and duty.end_event_id else None),
                end_km=(str(duty.end_km) if duty and duty.end_km is not None else None),
                end_hmr=(str(duty.end_hmr) if duty and duty.end_hmr is not None else None),
                ended_at=(
                    duty.ended_at.isoformat() if duty and duty.ended_at is not None else None
                ),
            ),
        ]
        if site is not None:
            snapshot.append(self._snapshot_row("site", site, status=site.status.value))
        if membership is not None:
            snapshot.append(
                self._snapshot_row(
                    "driver",
                    membership,
                    status=membership.status.value,
                )
            )
        return asset, deployment, site, assignment, membership, user, duty, snapshot

    def _asset_items(
        self,
        asset: FleetAsset,
        deployment: AssetSiteDeployment | None,
        site: Site | None,
        assignment: Assignment | None,
        membership: CompanyMembership | None,
        user: User | None,
        duty: DutySession | None,
    ) -> tuple[list[OperationItem], list[OperationItem]]:
        current = [
            OperationItem(
                "ASSET",
                asset.id,
                self._asset_label(asset),
                asset.status.value,
                {
                    "asset_code": asset.asset_code,
                    "registration": asset.registration_number,
                    "type": asset.asset_type.value,
                    "ownership": asset.ownership_type.value,
                },
            )
        ]
        dependencies: list[OperationItem] = []
        if deployment is not None and site is not None:
            dependencies.append(
                OperationItem(
                    "DEPLOYMENT",
                    deployment.id,
                    site.short_name,
                    "ACTIVE",
                    {"site_id": str(site.id), "asset_id": str(asset.id)},
                )
            )
        if assignment is not None and membership is not None and user is not None:
            dependencies.append(
                OperationItem(
                    "ASSIGNMENT",
                    assignment.id,
                    self._person_label(membership, user),
                    "ON_DUTY" if duty is not None else "OFF_DUTY",
                    {
                        "driver_membership_id": str(membership.id),
                        "asset_id": str(asset.id),
                        "site_id": str(assignment.site_id),
                    },
                )
            )
        if duty is not None:
            dependencies.append(
                OperationItem(
                    "DUTY",
                    duty.id,
                    "Active duty",
                    duty.status.value,
                    {
                        "asset_id": str(asset.id),
                        "assignment_id": str(duty.assignment_id),
                        "driver_membership_id": str(duty.driver_membership_id),
                        "site_id": str(duty.site_id),
                        "started_at": duty.started_at.isoformat(),
                    },
                )
            )
        return current, dependencies

    def _previous_asset_relationships(
        self,
        asset_id: UUID,
        *,
        lock: bool,
    ) -> tuple[
        AssetSiteDeployment | None,
        Site | None,
        Assignment | None,
        CompanyMembership | None,
        User | None,
        list[dict[str, object]],
    ]:
        deployment_statement = (
            select(AssetSiteDeployment)
            .where(
                AssetSiteDeployment.company_id == self.company_id,
                AssetSiteDeployment.asset_id == asset_id,
                AssetSiteDeployment.ends_at.is_not(None),
            )
            .order_by(
                AssetSiteDeployment.ends_at.desc(),
                AssetSiteDeployment.starts_at.desc(),
                AssetSiteDeployment.id.desc(),
            )
            .limit(1)
        )
        assignment_statement = (
            select(Assignment)
            .where(
                Assignment.company_id == self.company_id,
                Assignment.asset_id == asset_id,
                Assignment.ends_at.is_not(None),
            )
            .order_by(
                Assignment.ends_at.desc(),
                Assignment.starts_at.desc(),
                Assignment.id.desc(),
            )
            .limit(1)
        )
        if lock:
            deployment_statement = deployment_statement.with_for_update()
            assignment_statement = assignment_statement.with_for_update()
        deployment = self.session.scalar(deployment_statement)
        assignment = self.session.scalar(assignment_statement)
        site = self._site(deployment.site_id, lock=lock) if deployment is not None else None
        membership: CompanyMembership | None = None
        user: User | None = None
        if assignment is not None:
            membership, user = self._membership(
                assignment.driver_membership_id,
                lock=lock,
            )
        snapshot = [
            self._snapshot_row(
                "previous_deployment",
                deployment,
                site_id=str(deployment.site_id) if deployment else None,
                starts_at=deployment.starts_at.isoformat() if deployment else None,
                ends_at=(
                    deployment.ends_at.isoformat()
                    if deployment is not None and deployment.ends_at is not None
                    else None
                ),
            ),
            self._snapshot_row(
                "previous_assignment",
                assignment,
                driver_membership_id=(str(assignment.driver_membership_id) if assignment else None),
                site_id=str(assignment.site_id) if assignment else None,
                starts_at=assignment.starts_at.isoformat() if assignment else None,
                ends_at=(
                    assignment.ends_at.isoformat()
                    if assignment is not None and assignment.ends_at is not None
                    else None
                ),
            ),
        ]
        if site is not None:
            snapshot.append(self._snapshot_row("previous_site", site, status=site.status.value))
        if membership is not None:
            snapshot.append(
                self._snapshot_row(
                    "previous_driver",
                    membership,
                    status=membership.status.value,
                )
            )
        return deployment, site, assignment, membership, user, snapshot

    def _preview_remove_deployment(
        self, intent: OwnerOperationIntent, lock: bool
    ) -> OwnerOperationPlan:
        if intent.asset_id is None:
            raise DomainError("asset_id is required")
        (
            asset,
            deployment,
            site,
            assignment,
            membership,
            user,
            duty,
            snapshot,
        ) = self._asset_relationship_state(intent.asset_id, lock=lock)
        current, dependencies = self._asset_items(
            asset, deployment, site, assignment, membership, user, duty
        )
        blocked: list[str] = []
        changes: list[str] = []
        if deployment is None or site is None:
            blocked.append("Deployment no longer exists. Refresh the page.")
        if duty is not None:
            blocked.append("The active duty must be resolved before deployment can be removed.")
        if assignment is not None and membership is not None and user is not None:
            changes.append(
                f"End {self._person_label(membership, user)}'s assignment to "
                f"{self._asset_label(asset)}"
            )
        if deployment is not None and site is not None:
            changes.append(f"Remove {self._asset_label(asset)} from {site.short_name}")
        changes.append("Preserve deployment, assignment, and operational history")
        return self._plan(
            intent,
            title=f"Remove {self._asset_label(asset)} from Site",
            summary=(
                "Fleet Manager will end the current Site deployment"
                if assignment is None
                else "Fleet Manager will end the assignment and Site deployment together"
            ),
            current_state=current,
            dependencies=dependencies,
            warnings=[],
            allowed_resolutions=["REMOVE"],
            blocked_reasons=blocked,
            planned_changes=changes,
            snapshot=snapshot,
        )

    def _preview_move_deployment(
        self, intent: OwnerOperationIntent, lock: bool
    ) -> OwnerOperationPlan:
        if intent.asset_id is None:
            raise DomainError("asset_id is required")
        (
            asset,
            deployment,
            site,
            assignment,
            membership,
            user,
            duty,
            snapshot,
        ) = self._asset_relationship_state(intent.asset_id, lock=lock)
        target = (
            self._site(intent.target_site_id, lock=lock)
            if intent.target_site_id is not None
            else None
        )
        if target is not None:
            snapshot.append(self._snapshot_row("target_site", target, status=target.status.value))
        current, dependencies = self._asset_items(
            asset, deployment, site, assignment, membership, user, duty
        )
        if target is not None:
            dependencies.append(
                OperationItem("TARGET_SITE", target.id, target.short_name, target.status.value)
            )
        blocked: list[str] = []
        changes: list[str] = []
        if target is None:
            blocked.append("Choose a destination Site.")
        if deployment is None or site is None:
            blocked.append("Asset is not currently deployed. Review the operation again.")
        elif target is not None and deployment.site_id == target.id:
            blocked.append("Asset is already deployed to the selected Site.")
        if target is not None and target.status != SiteStatus.ACTIVE:
            blocked.append("The destination Site must be active.")
        if duty is not None:
            blocked.append("The active duty must be resolved before the asset can move.")
        if assignment is not None and intent.assignment_action is None:
            blocked.append(
                "Choose whether to keep or end the current Driver / Operator assignment."
            )
        if assignment is None and intent.assignment_action is not None:
            blocked.append("This asset has no current assignment to reconcile.")
        if deployment is not None and site is not None and target is not None:
            changes.append(f"End {self._asset_label(asset)} deployment from {site.short_name}")
            changes.append(f"Deploy {self._asset_label(asset)} to {target.short_name}")
        if (
            assignment is not None
            and membership is not None
            and user is not None
            and target is not None
        ):
            name = self._person_label(membership, user)
            changes.insert(
                0, f"End {name}'s assignment at {site.short_name if site else 'the Site'}"
            )
            if intent.assignment_action == "KEEP":
                changes.append(
                    f"Continue {name} with {self._asset_label(asset)} at {target.short_name}"
                )
        return self._plan(
            intent,
            title=f"Move {self._asset_label(asset)}",
            summary=(
                f"Move the asset to {target.short_name} without rewriting history."
                if target is not None
                else "Choose a destination while preserving the current relationship history."
            ),
            current_state=current,
            dependencies=dependencies,
            warnings=[],
            allowed_resolutions=(
                ["KEEP_DRIVER", "END_ASSIGNMENT"] if assignment is not None else ["MOVE"]
            ),
            blocked_reasons=blocked,
            planned_changes=changes,
            snapshot=snapshot,
        )

    def _preview_deploy_asset(self, intent: OwnerOperationIntent, lock: bool) -> OwnerOperationPlan:
        if intent.asset_id is None:
            raise DomainError("asset_id is required")
        asset, deployment, current_site, assignment, membership, user, duty, snapshot = (
            self._asset_relationship_state(intent.asset_id, lock=lock)
        )
        target = self._site(intent.site_id, lock=lock) if intent.site_id is not None else None
        if target is not None:
            snapshot.append(self._snapshot_row("target_site", target, status=target.status.value))
        current, dependencies = self._asset_items(
            asset, deployment, current_site, assignment, membership, user, duty
        )
        blocked: list[str] = []
        if target is None:
            blocked.append("Choose an active Site for this asset.")
        if asset.status != FleetAssetStatus.ACTIVE:
            blocked.append("Only an active asset can be deployed.")
        if target is not None and target.status != SiteStatus.ACTIVE:
            blocked.append("The destination Site must be active.")
        if deployment is not None:
            blocked.append("Asset already has a current Site deployment.")
        if assignment is not None or duty is not None:
            blocked.append("Resolve the current assignment or duty before deploying the asset.")
        return self._plan(
            intent,
            title=f"Deploy {self._asset_label(asset)}",
            summary=(
                f"Place {self._asset_label(asset)} at {target.short_name}."
                if target is not None
                else "Choose the Site where this asset will operate."
            ),
            current_state=current,
            dependencies=dependencies,
            warnings=[],
            allowed_resolutions=["DEPLOY"],
            blocked_reasons=blocked,
            planned_changes=(
                [f"Deploy {self._asset_label(asset)} to {target.short_name}"]
                if target is not None
                else []
            ),
            snapshot=snapshot,
        )

    def _preview_assign_driver(
        self, intent: OwnerOperationIntent, lock: bool
    ) -> OwnerOperationPlan:
        if intent.asset_id is None and intent.driver_membership_id is None:
            raise DomainError("asset_id or driver_membership_id is required")
        if intent.asset_id is None:
            assert intent.driver_membership_id is not None
            driver, driver_user = self._membership(intent.driver_membership_id, lock=lock)
            current_driver_assignment = self._driver_assignment(
                driver.id,
                at=datetime.now(UTC),
                lock=lock,
            )
            name = self._person_label(driver, driver_user)
            partial_blocked = ["Choose an available asset for this Driver / Operator."]
            partial_changes: list[str] = []
            if driver.role != MembershipRole.DRIVER or driver_user.status != UserStatus.ACTIVE:
                partial_blocked.append("The selected person is not an eligible Driver / Operator.")
            if driver.status == MembershipStatus.INACTIVE and not intent.activate_membership:
                partial_blocked.append(
                    "Choose the activation option before assigning this Driver / Operator."
                )
            if driver.status == MembershipStatus.INVITED and intent.activate_membership:
                partial_blocked.append(
                    "Invited people become active through their first OTP login."
                )
            if current_driver_assignment is not None:
                partial_blocked.append("Driver / Operator already has a current asset.")
            if driver.status == MembershipStatus.INACTIVE and intent.activate_membership:
                partial_changes.append(f"Reactivate {name} as Driver / Operator")
            return self._plan(
                intent,
                title=f"Assign {name}",
                summary="Choose an available asset, then review its Site relationship.",
                current_state=[
                    OperationItem(
                        "PERSON",
                        driver.id,
                        name,
                        driver.status.value,
                        {"role": driver.role.value},
                    )
                ],
                dependencies=[],
                warnings=[],
                allowed_resolutions=["ASSIGN"],
                blocked_reasons=partial_blocked,
                planned_changes=partial_changes,
                snapshot=[
                    self._snapshot_row(
                        "selected_driver",
                        driver,
                        status=driver.status.value,
                        role=driver.role.value,
                    ),
                    self._snapshot_row(
                        "selected_driver_assignment",
                        current_driver_assignment,
                        asset_id=(
                            str(current_driver_assignment.asset_id)
                            if current_driver_assignment
                            else None
                        ),
                    ),
                ],
            )
        if intent.driver_membership_id is None:
            assert intent.asset_id is not None
            asset, deployment, site, assignment, membership, user, duty, snapshot = (
                self._asset_relationship_state(intent.asset_id, lock=lock)
            )
            current, dependencies = self._asset_items(
                asset, deployment, site, assignment, membership, user, duty
            )
            selected_site = site
            if deployment is None and intent.site_id is not None:
                selected_site = self._site(intent.site_id, lock=lock)
                snapshot.append(
                    self._snapshot_row(
                        "selected_site", selected_site, status=selected_site.status.value
                    )
                )
            partial_blocked = ["Choose a Driver / Operator for this asset."]
            partial_changes = []
            if asset.status != FleetAssetStatus.ACTIVE:
                partial_blocked.append("Only an active asset can receive a Driver / Operator.")
            if not capabilities_for_asset(asset).supports_duty_session:
                partial_blocked.append(
                    "This asset type is not supported by the current Driver workflow."
                )
            if assignment is not None:
                partial_blocked.append("Asset already has a current Driver / Operator.")
            if duty is not None:
                partial_blocked.append("Asset currently has an active duty.")
            if deployment is None:
                if selected_site is None:
                    partial_blocked.append("Choose an active Site for the undeployed asset.")
                elif selected_site.status != SiteStatus.ACTIVE:
                    partial_blocked.append("The selected Site must be active.")
                else:
                    partial_changes.append(
                        f"Deploy {self._asset_label(asset)} to {selected_site.short_name}"
                    )
            return self._plan(
                intent,
                title=f"Assign an operator to {self._asset_label(asset)}",
                summary="Choose a Driver / Operator, then review the complete relationship.",
                current_state=current,
                dependencies=dependencies,
                warnings=[],
                allowed_resolutions=["ASSIGN"],
                blocked_reasons=partial_blocked,
                planned_changes=partial_changes,
                snapshot=snapshot,
            )
        assert intent.asset_id is not None
        asset, deployment, site, assignment, assigned_membership, assigned_user, duty, snapshot = (
            self._asset_relationship_state(intent.asset_id, lock=lock)
        )
        driver, driver_user = self._membership(intent.driver_membership_id, lock=lock)
        current_driver_assignment = self._driver_assignment(
            driver.id,
            at=datetime.now(UTC),
            lock=lock,
        )
        target_site: Site | None = site
        if deployment is None and intent.site_id is not None:
            target_site = self._site(intent.site_id, lock=lock)
        snapshot.extend(
            [
                self._snapshot_row(
                    "selected_driver",
                    driver,
                    status=driver.status.value,
                    role=driver.role.value,
                ),
                self._snapshot_row(
                    "selected_driver_assignment",
                    current_driver_assignment,
                    asset_id=(
                        str(current_driver_assignment.asset_id)
                        if current_driver_assignment
                        else None
                    ),
                ),
            ]
        )
        if target_site is not None and (site is None or target_site.id != site.id):
            snapshot.append(
                self._snapshot_row(
                    "selected_site",
                    target_site,
                    status=target_site.status.value,
                )
            )
        current, dependencies = self._asset_items(
            asset,
            deployment,
            site,
            assignment,
            assigned_membership,
            assigned_user,
            duty,
        )
        dependencies.append(
            OperationItem(
                "DRIVER",
                driver.id,
                self._person_label(driver, driver_user),
                driver.status.value,
            )
        )
        blocked: list[str] = []
        changes: list[str] = []
        if asset.status != FleetAssetStatus.ACTIVE:
            blocked.append("Only an active asset can receive a Driver / Operator.")
        if not capabilities_for_asset(asset).supports_duty_session:
            blocked.append("This asset type is not supported by the current Driver workflow.")
        if assignment is not None:
            blocked.append("Asset already has a current Driver / Operator.")
        if duty is not None:
            blocked.append("Asset currently has an active duty.")
        if driver.role != MembershipRole.DRIVER or driver_user.status != UserStatus.ACTIVE:
            blocked.append("The selected person is not an eligible Driver / Operator.")
        if driver.status == MembershipStatus.INACTIVE and not intent.activate_membership:
            blocked.append("Choose the activation option before assigning this Driver / Operator.")
        if driver.status == MembershipStatus.INVITED and intent.activate_membership:
            blocked.append("Invited people become active through their first OTP login.")
        if current_driver_assignment is not None:
            blocked.append("Driver / Operator already has a current asset.")
        if deployment is None:
            if target_site is None:
                blocked.append("Choose an active Site for the undeployed asset.")
            elif target_site.status != SiteStatus.ACTIVE:
                blocked.append("The selected Site must be active.")
            else:
                changes.append(f"Deploy {self._asset_label(asset)} to {target_site.short_name}")
        elif intent.site_id is not None and intent.site_id != deployment.site_id:
            blocked.append("The assignment Site is derived from the current deployment.")
        if driver.status == MembershipStatus.INACTIVE and intent.activate_membership:
            changes.insert(
                0, f"Reactivate {self._person_label(driver, driver_user)} as Driver / Operator"
            )
        if target_site is not None:
            changes.append(
                f"Assign {self._person_label(driver, driver_user)} to "
                f"{self._asset_label(asset)} at {target_site.short_name}"
            )
        return self._plan(
            intent,
            title=f"Assign {self._person_label(driver, driver_user)}",
            summary="Review the Driver, asset, and server-derived Site relationship.",
            current_state=current,
            dependencies=dependencies,
            warnings=[],
            allowed_resolutions=(
                ["ACTIVATE_ONLY", "ACTIVATE_DEPLOY_ASSIGN"]
                if driver.status == MembershipStatus.INACTIVE and deployment is None
                else ["ASSIGN"]
            ),
            blocked_reasons=blocked,
            planned_changes=changes,
            snapshot=snapshot,
        )

    def _preview_end_assignment(
        self, intent: OwnerOperationIntent, lock: bool
    ) -> OwnerOperationPlan:
        if intent.asset_id is None:
            raise DomainError("asset_id is required")
        asset, deployment, site, assignment, membership, user, duty, snapshot = (
            self._asset_relationship_state(intent.asset_id, lock=lock)
        )
        current, dependencies = self._asset_items(
            asset, deployment, site, assignment, membership, user, duty
        )
        blocked: list[str] = []
        if assignment is None or membership is None or user is None:
            blocked.append("Assignment no longer exists. Refresh the page.")
            name = "Driver / Operator"
        else:
            name = self._person_label(membership, user)
        if duty is not None:
            blocked.append("The active duty must be resolved before the assignment can end.")
        return self._plan(
            intent,
            title=f"End {name}'s assignment",
            summary=(
                f"End the current assignment to {self._asset_label(asset)} and preserve history."
            ),
            current_state=current,
            dependencies=dependencies,
            warnings=[],
            allowed_resolutions=["END_ASSIGNMENT"],
            blocked_reasons=blocked,
            planned_changes=[f"End {name}'s assignment to {self._asset_label(asset)}"],
            snapshot=snapshot,
        )

    def _preview_reassign_driver(
        self, intent: OwnerOperationIntent, lock: bool
    ) -> OwnerOperationPlan:
        if intent.asset_id is None:
            raise DomainError("asset_id is required")
        asset, deployment, site, assignment, current_driver, current_user, duty, snapshot = (
            self._asset_relationship_state(intent.asset_id, lock=lock)
        )
        current, dependencies = self._asset_items(
            asset,
            deployment,
            site,
            assignment,
            current_driver,
            current_user,
            duty,
        )
        blocked: list[str] = []
        changes: list[str] = []
        if assignment is None or current_driver is None or current_user is None:
            blocked.append("The current assignment no longer exists. Review the operation again.")
            current_name = "the current Driver / Operator"
        else:
            current_name = self._person_label(current_driver, current_user)
        if deployment is None or site is None:
            blocked.append("The asset must have a current Site deployment.")
        if duty is not None:
            blocked.append(
                "The active duty must be resolved before changing the Driver / Operator."
            )

        replacement_name = "a new Driver / Operator"
        if intent.driver_membership_id is None:
            blocked.append("Choose a new Driver / Operator.")
        else:
            replacement, replacement_user = self._membership(
                intent.driver_membership_id,
                lock=lock,
            )
            replacement_name = self._person_label(replacement, replacement_user)
            replacement_assignment = self._driver_assignment(
                replacement.id,
                at=datetime.now(UTC),
                lock=lock,
            )
            snapshot.extend(
                [
                    self._snapshot_row(
                        "replacement_driver",
                        replacement,
                        status=replacement.status.value,
                        role=replacement.role.value,
                    ),
                    self._snapshot_row(
                        "replacement_driver_assignment",
                        replacement_assignment,
                        asset_id=(
                            str(replacement_assignment.asset_id) if replacement_assignment else None
                        ),
                    ),
                ]
            )
            dependencies.append(
                OperationItem(
                    "REPLACEMENT_DRIVER",
                    replacement.id,
                    replacement_name,
                    replacement.status.value,
                )
            )
            if assignment is not None and replacement.id == assignment.driver_membership_id:
                blocked.append("Choose a different Driver / Operator.")
            elif replacement_assignment is not None:
                blocked.append("The selected Driver / Operator already has a current asset.")
            if (
                replacement.role != MembershipRole.DRIVER
                or replacement_user.status != UserStatus.ACTIVE
            ):
                blocked.append("The selected person is not an eligible Driver / Operator.")
            if replacement.status == MembershipStatus.INACTIVE:
                if intent.activate_membership:
                    changes.append(f"Reactivate {replacement_name} as Driver / Operator")
                else:
                    blocked.append(
                        "Choose the activation option before assigning this Driver / Operator."
                    )
            if replacement.status == MembershipStatus.INVITED and intent.activate_membership:
                blocked.append("Invited people become active through their first OTP login.")

        if assignment is not None:
            changes.append(f"End {current_name}'s assignment to {self._asset_label(asset)}")
        if deployment is not None and site is not None and intent.driver_membership_id is not None:
            changes.append(
                f"Assign {replacement_name} to {self._asset_label(asset)} at {site.short_name}"
            )
        return self._plan(
            intent,
            title=f"Change Driver / Operator on {self._asset_label(asset)}",
            summary="Replace the current assignment without rewriting its history.",
            current_state=current,
            dependencies=dependencies,
            warnings=[],
            allowed_resolutions=["REASSIGN"],
            blocked_reasons=blocked,
            planned_changes=changes,
            snapshot=snapshot,
        )

    def _preview_activate_person(
        self, intent: OwnerOperationIntent, lock: bool
    ) -> OwnerOperationPlan:
        if intent.person_membership_id is None:
            raise DomainError("person_membership_id is required")
        membership, user = self._membership(intent.person_membership_id, lock=lock)
        name = self._person_label(membership, user)
        snapshot = [
            self._snapshot_row(
                "membership",
                membership,
                status=membership.status.value,
                role=membership.role.value,
            )
        ]
        current = [
            OperationItem(
                "PERSON",
                membership.id,
                name,
                membership.status.value,
                {"role": membership.role.value},
            )
        ]
        dependencies: list[OperationItem] = []
        blocked: list[str] = []
        changes: list[str] = []
        if membership.status == MembershipStatus.INVITED:
            blocked.append("Invited people become active through their first OTP login.")
        elif membership.status == MembershipStatus.INACTIVE:
            role_label = (
                "Driver / Operator"
                if membership.role == MembershipRole.DRIVER
                else membership.role.value.replace("_", " ").title()
            )
            changes.append(f"Reactivate {name} as {role_label}")
        if membership.role == MembershipRole.SUPERVISOR:
            for site_id in sorted(set(intent.selected_site_ids), key=str):
                site = self._site(site_id, lock=lock)
                snapshot.append(self._snapshot_row("selected_site", site, status=site.status.value))
                dependencies.append(
                    OperationItem("SITE", site.id, site.short_name, site.status.value)
                )
                if site.status != SiteStatus.ACTIVE:
                    blocked.append(f"{site.short_name} is not active.")
                else:
                    changes.append(f"Give {name} access to {site.short_name}")
        elif membership.role == MembershipRole.DRIVER and intent.asset_id is not None:
            nested_intent = OwnerOperationIntent(
                action=OwnerOperationAction.ASSIGN_DRIVER,
                asset_id=intent.asset_id,
                site_id=intent.site_id,
                driver_membership_id=membership.id,
                activate_membership=True,
                regular_duty_minutes=intent.regular_duty_minutes,
            )
            nested = self._preview_assign_driver(nested_intent, lock)
            dependencies.extend(nested.dependencies)
            blocked.extend(nested.blocked_reasons)
            changes.extend(change for change in nested.planned_changes if change not in changes)
            snapshot.append({"nested_state_token": nested.state_token})
        elif membership.role not in (MembershipRole.DRIVER, MembershipRole.SUPERVISOR):
            blocked.append("Only Driver / Operator and Supervisor roles use this setup workflow.")
        if not changes and membership.status == MembershipStatus.ACTIVE:
            changes.append(f"Keep {name}'s role active without additional setup")
        return self._plan(
            intent,
            title=f"Activate {name}",
            summary="Activation can be completed with or without operational setup.",
            current_state=current,
            dependencies=dependencies,
            warnings=[],
            allowed_resolutions=["ACTIVATE_ONLY", "ACTIVATE_AND_SET_UP"],
            blocked_reasons=blocked,
            planned_changes=changes,
            snapshot=snapshot,
        )

    def _supervisor_accesses(
        self, membership_id: UUID, *, lock: bool
    ) -> list[tuple[SupervisorSiteAccess, Site]]:
        statement = (
            select(SupervisorSiteAccess, Site)
            .join(
                Site,
                and_(
                    Site.company_id == SupervisorSiteAccess.company_id,
                    Site.id == SupervisorSiteAccess.site_id,
                ),
            )
            .where(
                SupervisorSiteAccess.company_id == self.company_id,
                SupervisorSiteAccess.supervisor_membership_id == membership_id,
            )
            .order_by(SupervisorSiteAccess.site_id, SupervisorSiteAccess.id)
        )
        if lock:
            statement = statement.with_for_update(of=SupervisorSiteAccess)
        return [row._tuple() for row in self.session.execute(statement)]

    def _preview_supervisor_sites(
        self, intent: OwnerOperationIntent, lock: bool
    ) -> OwnerOperationPlan:
        if intent.person_membership_id is None:
            raise DomainError("person_membership_id is required")
        membership, user = self._membership(intent.person_membership_id, lock=lock)
        if membership.role != MembershipRole.SUPERVISOR:
            raise DomainError("Site access requires a Supervisor membership.")
        accesses = self._supervisor_accesses(membership.id, lock=lock)
        selected: list[Site] = []
        for site_id in sorted(set(intent.selected_site_ids), key=str):
            selected.append(self._site(site_id, lock=lock))
        snapshot = [
            self._snapshot_row(
                "membership",
                membership,
                status=membership.status.value,
                role=membership.role.value,
            ),
            *[
                self._snapshot_row("access", access, site_id=str(site.id))
                for access, site in accesses
            ],
            *[
                self._snapshot_row("selected_site", site, status=site.status.value)
                for site in selected
            ],
        ]
        name = self._person_label(membership, user)
        current_ids = {site.id for _access, site in accesses}
        selected_ids = {site.id for site in selected}
        blocked: list[str] = []
        if membership.status == MembershipStatus.INACTIVE and not intent.activate_membership:
            blocked.append("Reactivate the Supervisor before saving Site access.")
        if membership.status == MembershipStatus.INVITED and intent.activate_membership:
            blocked.append("Invited people become active through their first OTP login.")
        for site in selected:
            if site.status != SiteStatus.ACTIVE:
                blocked.append(f"{site.short_name} is not active.")
        changes = [
            f"Give {name} access to {site.short_name}"
            for site in selected
            if site.id not in current_ids
        ]
        changes.extend(
            f"End {name}'s access to {site.short_name}"
            for _access, site in accesses
            if site.id not in selected_ids
        )
        if membership.status == MembershipStatus.INACTIVE and intent.activate_membership:
            changes.insert(0, f"Reactivate {name} as Supervisor")
        if not changes:
            changes.append("Keep the current Supervisor Site access")
        return self._plan(
            intent,
            title=f"Manage {name}'s Site access",
            summary=(
                f"{len(selected_ids)} active Site{'s' if len(selected_ids) != 1 else ''} selected."
            ),
            current_state=[
                OperationItem(
                    "PERSON",
                    membership.id,
                    name,
                    membership.status.value,
                    {"role": membership.role.value},
                )
            ],
            dependencies=[
                OperationItem("SITE_ACCESS", access.id, site.short_name, "ACTIVE")
                for access, site in accesses
            ],
            warnings=[],
            allowed_resolutions=["SAVE_SITE_ACCESS"],
            blocked_reasons=blocked,
            planned_changes=changes,
            snapshot=snapshot,
        )

    def _preview_deactivate_person(
        self, intent: OwnerOperationIntent, lock: bool
    ) -> OwnerOperationPlan:
        if intent.person_membership_id is None:
            raise DomainError("person_membership_id is required")
        membership, user = self._membership(intent.person_membership_id, lock=lock)
        name = self._person_label(membership, user)
        snapshot = [
            self._snapshot_row(
                "membership",
                membership,
                status=membership.status.value,
                role=membership.role.value,
            )
        ]
        dependencies: list[OperationItem] = []
        changes: list[str] = []
        blocked: list[str] = []
        if membership.role == MembershipRole.OWNER_ADMIN:
            blocked.append("Owner/Admin roles cannot be removed through the person workflow.")
        if membership.role == MembershipRole.SUPERVISOR:
            accesses = self._supervisor_accesses(membership.id, lock=lock)
            for access, site in accesses:
                snapshot.append(self._snapshot_row("access", access, site_id=str(site.id)))
                dependencies.append(
                    OperationItem("SITE_ACCESS", access.id, site.short_name, "ACTIVE")
                )
                changes.append(f"End {name}'s access to {site.short_name}")
        if membership.role == MembershipRole.DRIVER:
            assignment = self._driver_assignment(
                membership.id,
                at=datetime.now(UTC),
                lock=lock,
            )
            duty: DutySession | None = None
            if assignment is not None:
                asset = self._asset(assignment.asset_id, lock=lock)
                duty = self._duty(asset.id, lock=lock)
                site = self._site(assignment.site_id, lock=lock)
                snapshot.extend(
                    [
                        self._snapshot_row("assignment", assignment, asset_id=str(asset.id)),
                        self._snapshot_row(
                            "duty",
                            duty,
                            assignment_id=str(duty.assignment_id) if duty else None,
                        ),
                    ]
                )
                dependencies.append(
                    OperationItem(
                        "ASSIGNMENT",
                        assignment.id,
                        self._asset_label(asset),
                        "ON_DUTY" if duty else "OFF_DUTY",
                        {"site": site.short_name, "asset_id": str(asset.id)},
                    )
                )
                if duty is not None:
                    blocked.append(
                        "The active duty must be resolved before this role can be deactivated."
                    )
                changes.append(f"End {name}'s assignment to {self._asset_label(asset)}")
        changes.append(
            f"Deactivate {name}'s {membership.role.value.replace('_', ' ').title()} role"
        )
        return self._plan(
            intent,
            title=f"Deactivate {name}",
            summary="Dependent operational relationships will be ended safely first.",
            current_state=[
                OperationItem(
                    "PERSON",
                    membership.id,
                    name,
                    membership.status.value,
                    {"role": membership.role.value},
                )
            ],
            dependencies=dependencies,
            warnings=[],
            allowed_resolutions=["DEACTIVATE_AND_END_RELATIONSHIPS"],
            blocked_reasons=blocked,
            planned_changes=changes,
            snapshot=snapshot,
        )

    def _preview_deactivate_asset(
        self, intent: OwnerOperationIntent, lock: bool
    ) -> OwnerOperationPlan:
        if intent.asset_id is None:
            raise DomainError("asset_id is required")
        asset, deployment, site, assignment, membership, user, duty, snapshot = (
            self._asset_relationship_state(intent.asset_id, lock=lock)
        )
        current, dependencies = self._asset_items(
            asset, deployment, site, assignment, membership, user, duty
        )
        blocked = (
            ["The active duty must be resolved before the asset can be deactivated."]
            if duty is not None
            else []
        )
        changes: list[str] = []
        if assignment is not None and membership is not None and user is not None:
            changes.append(
                f"End {self._person_label(membership, user)}'s assignment to "
                f"{self._asset_label(asset)}"
            )
        if deployment is not None and site is not None:
            changes.append(f"Remove {self._asset_label(asset)} from {site.short_name}")
        changes.append(f"Deactivate {self._asset_label(asset)}")
        return self._plan(
            intent,
            title=f"Deactivate {self._asset_label(asset)}",
            summary="Assignment and deployment dependencies will be reconciled first.",
            current_state=current,
            dependencies=dependencies,
            warnings=[],
            allowed_resolutions=["DEACTIVATE_AND_END_RELATIONSHIPS"],
            blocked_reasons=blocked,
            planned_changes=changes,
            snapshot=snapshot,
        )

    def _preview_force_close_duty_and_deactivate_asset(
        self, intent: OwnerOperationIntent, lock: bool
    ) -> OwnerOperationPlan:
        if intent.asset_id is None:
            raise DomainError("asset_id is required")
        reason = (intent.reason or "").strip()
        if not reason:
            raise DomainError("reason is required for administrative duty closure")
        asset, deployment, site, assignment, membership, user, duty, snapshot = (
            self._asset_relationship_state(intent.asset_id, lock=lock)
        )
        current, dependencies = self._asset_items(
            asset, deployment, site, assignment, membership, user, duty
        )
        capabilities = capabilities_for_asset(asset)
        if capabilities.supports_odometer:
            missing_meter_label = "END KM"
            missing_exception_code = "MISSING_END_READING"
        elif capabilities.supports_hour_meter:
            missing_meter_label = "END HMR"
            missing_exception_code = "MISSING_END_HMR"
        else:
            missing_meter_label = "END meter"
            missing_exception_code = "MISSING_END_READING"

        blocked: list[str] = []
        warnings: list[str] = []
        changes: list[str] = []
        if duty is not None:
            changes.extend(
                [
                    "Administratively close the active duty without fabricating "
                    f"{missing_meter_label}",
                    "Preserve the duty start, operational events, and evidence",
                    f"Leave reporting to record {missing_exception_code}",
                ]
            )
        else:
            warnings.append(
                "The active duty has already closed. Safe asset deactivation will continue."
            )
            if asset.status == FleetAssetStatus.INACTIVE:
                blocked.append("Asset is already inactive and has no active duty to close.")
        if assignment is not None and membership is not None and user is not None:
            changes.append(
                f"End {self._person_label(membership, user)}'s assignment to "
                f"{self._asset_label(asset)}"
            )
        if deployment is not None and site is not None:
            changes.append(f"Remove {self._asset_label(asset)} from {site.short_name}")
        if asset.status != FleetAssetStatus.INACTIVE:
            changes.append(f"Deactivate {self._asset_label(asset)}")
        changes.append("Preserve assignment, deployment, event, and evidence history")
        return self._plan(
            intent,
            title=f"Force close duty and deactivate {self._asset_label(asset)}",
            summary=(
                "This restricted Owner action closes the stuck duty without an END meter "
                "reading, then ends its relationships and deactivates the asset atomically."
            ),
            current_state=current,
            dependencies=dependencies,
            warnings=warnings,
            allowed_resolutions=["FORCE_CLOSE_DUTY_AND_DEACTIVATE"],
            blocked_reasons=blocked,
            planned_changes=changes,
            snapshot=snapshot,
        )

    def _preview_reactivate_asset(
        self, intent: OwnerOperationIntent, lock: bool
    ) -> OwnerOperationPlan:
        if intent.asset_id is None:
            raise DomainError("asset_id is required")
        asset, deployment, site, assignment, membership, user, duty, snapshot = (
            self._asset_relationship_state(intent.asset_id, lock=lock)
        )
        current, dependencies = self._asset_items(
            asset,
            deployment,
            site,
            assignment,
            membership,
            user,
            duty,
        )
        (
            previous_deployment,
            previous_site,
            previous_assignment,
            previous_driver,
            previous_driver_user,
            previous_snapshot,
        ) = self._previous_asset_relationships(asset.id, lock=lock)
        snapshot.extend(previous_snapshot)
        if previous_deployment is not None and previous_site is not None:
            current.append(
                OperationItem(
                    "PREVIOUS_SITE",
                    previous_deployment.id,
                    previous_site.short_name,
                    "PREVIOUS",
                    {
                        "site_id": str(previous_site.id),
                        "ended_at": (
                            previous_deployment.ends_at.isoformat()
                            if previous_deployment.ends_at is not None
                            else None
                        ),
                    },
                )
            )
        if (
            previous_assignment is not None
            and previous_driver is not None
            and previous_driver_user is not None
        ):
            current.append(
                OperationItem(
                    "PREVIOUS_DRIVER",
                    previous_assignment.id,
                    self._person_label(previous_driver, previous_driver_user),
                    "PREVIOUS",
                    {
                        "driver_membership_id": str(previous_driver.id),
                        "site_id": str(previous_assignment.site_id),
                        "ended_at": (
                            previous_assignment.ends_at.isoformat()
                            if previous_assignment.ends_at is not None
                            else None
                        ),
                    },
                )
            )

        target_site = self._site(intent.site_id, lock=lock) if intent.site_id is not None else None
        if target_site is not None:
            snapshot.append(
                self._snapshot_row(
                    "target_site",
                    target_site,
                    status=target_site.status.value,
                )
            )
            dependencies.append(
                OperationItem(
                    "TARGET_SITE",
                    target_site.id,
                    target_site.short_name,
                    target_site.status.value,
                )
            )

        selected_driver: CompanyMembership | None = None
        selected_driver_user: User | None = None
        selected_driver_assignment: Assignment | None = None
        if intent.driver_membership_id is not None:
            selected_driver, selected_driver_user = self._membership(
                intent.driver_membership_id,
                lock=lock,
            )
            selected_driver_assignment = self._driver_assignment(
                selected_driver.id,
                at=datetime.now(UTC),
                lock=lock,
            )
            snapshot.extend(
                [
                    self._snapshot_row(
                        "selected_driver",
                        selected_driver,
                        status=selected_driver.status.value,
                        role=selected_driver.role.value,
                    ),
                    self._snapshot_row(
                        "selected_driver_assignment",
                        selected_driver_assignment,
                        asset_id=(
                            str(selected_driver_assignment.asset_id)
                            if selected_driver_assignment is not None
                            else None
                        ),
                    ),
                ]
            )
            dependencies.append(
                OperationItem(
                    "DRIVER",
                    selected_driver.id,
                    self._person_label(selected_driver, selected_driver_user),
                    selected_driver.status.value,
                    {
                        "role": selected_driver.role.value,
                        "assignment_state": (
                            "ASSIGNED" if selected_driver_assignment is not None else "UNASSIGNED"
                        ),
                    },
                )
            )

        blocked: list[str] = []
        if asset.status != FleetAssetStatus.INACTIVE:
            blocked.append("Asset is already active.")
        if deployment is not None or assignment is not None or duty is not None:
            blocked.append(
                "Resolve the asset's current deployment, assignment, or duty before reactivation."
            )
        if target_site is not None and target_site.status != SiteStatus.ACTIVE:
            blocked.append("The selected Site must be active.")
        if selected_driver is not None:
            assert selected_driver_user is not None
            if target_site is None:
                blocked.append("Choose a Site before assigning a Driver / Operator.")
            if not capabilities_for_asset(asset).supports_duty_session:
                blocked.append("This asset type is not supported by the current Driver workflow.")
            if (
                selected_driver.role != MembershipRole.DRIVER
                or selected_driver_user.status != UserStatus.ACTIVE
            ):
                blocked.append("The selected person is not an eligible Driver / Operator.")
            if selected_driver.status == MembershipStatus.INACTIVE:
                if not intent.activate_membership:
                    blocked.append(
                        "Select ‘Reactivate role as part of this setup’ for this inactive "
                        "Driver / Operator."
                    )
            elif selected_driver.status == MembershipStatus.INVITED and intent.activate_membership:
                blocked.append("Invited people become active through their first OTP login.")
            if selected_driver_assignment is not None:
                blocked.append("Driver / Operator already has a current asset.")
        elif intent.activate_membership:
            blocked.append("Choose a Driver / Operator before selecting role reactivation.")

        asset_label = self._asset_label(asset)
        changes = [f"Set {asset_label} lifecycle to Active"]
        if target_site is not None:
            changes.append(f"Set Site to {target_site.short_name}")
        if selected_driver is not None and selected_driver_user is not None:
            driver_name = self._person_label(selected_driver, selected_driver_user)
            if selected_driver.status == MembershipStatus.INACTIVE and intent.activate_membership:
                changes.append(f"Reactivate {driver_name}'s Driver / Operator role")
            changes.append(f"Set Driver / Operator to {driver_name}")

        if target_site is None:
            summary = f"Reactivate {asset_label} and leave it undeployed."
        elif selected_driver is None:
            summary = (
                f"Reactivate {asset_label}, deploy it to {target_site.short_name}, "
                "and leave it unassigned."
            )
        else:
            summary = f"Reactivate {asset_label} with its Site and Driver / Operator setup."
        return self._plan(
            intent,
            title=f"Reactivate {asset_label}",
            summary=summary,
            current_state=current,
            dependencies=dependencies,
            warnings=[],
            allowed_resolutions=[
                "REACTIVATE_ONLY",
                "REACTIVATE_AND_DEPLOY",
                "REACTIVATE_DEPLOY_ASSIGN",
            ],
            blocked_reasons=blocked,
            planned_changes=changes,
            snapshot=snapshot,
        )

    def _site_dependencies(
        self,
        site: Site,
        *,
        lock: bool,
    ) -> tuple[
        list[
            tuple[
                AssetSiteDeployment,
                FleetAsset,
                Assignment | None,
                CompanyMembership | None,
                User | None,
                DutySession | None,
            ]
        ],
        list[tuple[SupervisorSiteAccess, CompanyMembership, User]],
    ]:
        deployment_statement = (
            select(AssetSiteDeployment, FleetAsset)
            .join(
                FleetAsset,
                and_(
                    FleetAsset.company_id == AssetSiteDeployment.company_id,
                    FleetAsset.id == AssetSiteDeployment.asset_id,
                ),
            )
            .where(
                AssetSiteDeployment.company_id == self.company_id,
                AssetSiteDeployment.site_id == site.id,
                AssetSiteDeployment.ends_at.is_(None),
            )
            .order_by(AssetSiteDeployment.asset_id, AssetSiteDeployment.id)
        )
        if lock:
            deployment_statement = deployment_statement.with_for_update(of=AssetSiteDeployment)
        assets: list[
            tuple[
                AssetSiteDeployment,
                FleetAsset,
                Assignment | None,
                CompanyMembership | None,
                User | None,
                DutySession | None,
            ]
        ] = []
        now = datetime.now(UTC)
        for deployment, asset in self.session.execute(deployment_statement):
            assignment = self._assignment(asset.id, at=now, lock=lock)
            membership: CompanyMembership | None = None
            user: User | None = None
            if assignment is not None:
                membership, user = self._membership(
                    assignment.driver_membership_id,
                    lock=lock,
                )
            duty = self._duty(asset.id, lock=lock)
            assets.append((deployment, asset, assignment, membership, user, duty))
        access_statement = (
            select(SupervisorSiteAccess, CompanyMembership, User)
            .join(
                CompanyMembership,
                and_(
                    CompanyMembership.company_id == SupervisorSiteAccess.company_id,
                    CompanyMembership.id == SupervisorSiteAccess.supervisor_membership_id,
                ),
            )
            .join(User, User.id == CompanyMembership.user_id)
            .where(
                SupervisorSiteAccess.company_id == self.company_id,
                SupervisorSiteAccess.site_id == site.id,
            )
            .order_by(SupervisorSiteAccess.supervisor_membership_id)
        )
        if lock:
            access_statement = access_statement.with_for_update(of=SupervisorSiteAccess)
        accesses = [row._tuple() for row in self.session.execute(access_statement)]
        return assets, accesses

    def _preview_deactivate_site(
        self, intent: OwnerOperationIntent, lock: bool
    ) -> OwnerOperationPlan:
        if intent.site_id is None:
            raise DomainError("site_id is required")
        site = self._site(intent.site_id, lock=lock)
        assets, accesses = self._site_dependencies(site, lock=lock)
        snapshot: list[dict[str, object]] = [
            self._snapshot_row("site", site, status=site.status.value)
        ]
        dependencies: list[OperationItem] = []
        blocked: list[str] = []
        changes: list[str] = []
        decisions = {item.asset_id: item for item in intent.asset_resolutions}
        if len(decisions) != len(intent.asset_resolutions):
            blocked.append("Each deployed asset must have one resolution.")
        deployed_asset_ids = {asset.id for _deployment, asset, *_rest in assets}
        if set(decisions) - deployed_asset_ids:
            blocked.append("A selected asset is not currently deployed to this Site.")
        for deployment, asset, assignment, membership, user, duty in assets:
            snapshot.extend(
                [
                    self._snapshot_row(
                        "deployment",
                        deployment,
                        asset_id=str(asset.id),
                        site_id=str(site.id),
                    ),
                    self._snapshot_row(
                        "assignment",
                        assignment,
                        driver_membership_id=(
                            str(assignment.driver_membership_id) if assignment else None
                        ),
                    ),
                    self._snapshot_row(
                        "duty",
                        duty,
                        assignment_id=str(duty.assignment_id) if duty else None,
                    ),
                ]
            )
            status = "ON_DUTY" if duty else "OFF_DUTY" if assignment else "UNASSIGNED"
            details: dict[str, OperationDetailValue] = {
                "asset_id": str(asset.id),
                "asset_code": asset.asset_code,
                "driver": (
                    self._person_label(membership, user)
                    if membership is not None and user is not None
                    else None
                ),
            }
            dependencies.append(
                OperationItem(
                    "DEPLOYED_ASSET", deployment.id, self._asset_label(asset), status, details
                )
            )
            if duty is not None:
                driver_name = (
                    self._person_label(membership, user)
                    if membership is not None and user is not None
                    else "the assigned Driver / Operator"
                )
                blocked.append(
                    f"{self._asset_label(asset)} is on duty with {driver_name}. "
                    "Resolve the duty first."
                )
            decision = decisions.get(asset.id)
            if decision is None:
                blocked.append(f"Choose how to resolve {self._asset_label(asset)}.")
                continue
            if decision.action == "REMOVE":
                if assignment is not None and membership is not None and user is not None:
                    changes.append(
                        f"End {self._person_label(membership, user)}'s assignment to "
                        f"{self._asset_label(asset)}"
                    )
                changes.append(f"Remove {self._asset_label(asset)} from {site.short_name}")
                continue
            if decision.target_site_id is None:
                blocked.append(f"Choose a destination Site for {self._asset_label(asset)}.")
                continue
            target = self._site(decision.target_site_id, lock=lock)
            snapshot.append(
                self._snapshot_row(
                    "target_site",
                    target,
                    asset_id=str(asset.id),
                    status=target.status.value,
                )
            )
            if target.id == site.id or target.status != SiteStatus.ACTIVE:
                blocked.append(f"Choose another active Site for {self._asset_label(asset)}.")
            if assignment is not None and decision.assignment_action is None:
                blocked.append(
                    f"Choose whether to keep or end the Driver / Operator for "
                    f"{self._asset_label(asset)}."
                )
            changes.append(
                f"Move {self._asset_label(asset)} from {site.short_name} to {target.short_name}"
            )
            if (
                assignment is not None
                and decision.assignment_action == "KEEP"
                and membership is not None
                and user is not None
            ):
                changes.append(
                    f"Continue {self._person_label(membership, user)} with "
                    f"{self._asset_label(asset)} at {target.short_name}"
                )
            elif assignment is not None and membership is not None and user is not None:
                changes.insert(
                    max(0, len(changes) - 1),
                    f"End {self._person_label(membership, user)}'s assignment to "
                    f"{self._asset_label(asset)}",
                )
        for access, membership, user in accesses:
            snapshot.append(
                self._snapshot_row(
                    "supervisor_access",
                    access,
                    membership_id=str(membership.id),
                )
            )
            name = self._person_label(membership, user)
            dependencies.append(OperationItem("SUPERVISOR_ACCESS", access.id, name, "ACTIVE"))
            changes.append(f"End {name}'s access to {site.short_name}")
        changes.append(f"Deactivate {site.short_name}")
        return self._plan(
            intent,
            title=f"Deactivate {site.short_name}",
            summary=(
                f"{len(assets)} deployed asset{'s' if len(assets) != 1 else ''}, "
                f"{len(accesses)} Supervisor access relationship"
                f"{'s' if len(accesses) != 1 else ''}, "
                f"{sum(1 for *_, duty in assets if duty is not None)} active "
                "duty relationship"
                f"{'s' if sum(1 for *_, duty in assets if duty is not None) != 1 else ''}."
            ),
            current_state=[
                OperationItem(
                    "SITE",
                    site.id,
                    site.short_name,
                    site.status.value,
                    {
                        "deployed_assets": len(assets),
                        "supervisors": len(accesses),
                        "active_duties": sum(1 for *_, duty in assets if duty is not None),
                    },
                )
            ],
            dependencies=dependencies,
            warnings=[],
            allowed_resolutions=["MOVE", "REMOVE", "KEEP_DRIVER", "END_ASSIGNMENT"],
            blocked_reasons=blocked,
            planned_changes=changes,
            snapshot=snapshot,
        )

    def _preview_reactivate_site(
        self, intent: OwnerOperationIntent, lock: bool
    ) -> OwnerOperationPlan:
        if intent.site_id is None:
            raise DomainError("site_id is required")
        site = self._site(intent.site_id, lock=lock)
        snapshot = [self._snapshot_row("site", site, status=site.status.value)]
        dependencies: list[OperationItem] = []
        blocked: list[str] = []
        changes = [f"Reactivate {site.short_name}"]
        for membership_id in sorted(set(intent.selected_supervisor_ids), key=str):
            membership, user = self._membership(membership_id, lock=lock)
            snapshot.append(
                self._snapshot_row(
                    "selected_supervisor",
                    membership,
                    status=membership.status.value,
                    role=membership.role.value,
                )
            )
            name = self._person_label(membership, user)
            dependencies.append(
                OperationItem("SUPERVISOR", membership.id, name, membership.status.value)
            )
            if (
                membership.role != MembershipRole.SUPERVISOR
                or membership.status != MembershipStatus.ACTIVE
            ):
                blocked.append(f"{name} must be an active Supervisor.")
            else:
                changes.append(f"Give {name} access to {site.short_name}")
        for asset_id in sorted(set(intent.selected_asset_ids), key=str):
            asset = self._asset(asset_id, lock=lock)
            deployment = self._deployment(asset.id, lock=lock)
            assignment = self._assignment(asset.id, at=datetime.now(UTC), lock=lock)
            snapshot.extend(
                [
                    self._snapshot_row("selected_asset", asset, status=asset.status.value),
                    self._snapshot_row("deployment", deployment),
                    self._snapshot_row("assignment", assignment),
                ]
            )
            dependencies.append(
                OperationItem("ASSET", asset.id, self._asset_label(asset), asset.status.value)
            )
            if asset.status != FleetAssetStatus.ACTIVE or deployment is not None:
                blocked.append(f"{self._asset_label(asset)} must be active and undeployed.")
            elif assignment is not None:
                blocked.append(f"{self._asset_label(asset)} has a current assignment.")
            else:
                changes.append(f"Deploy {self._asset_label(asset)} to {site.short_name}")
        return self._plan(
            intent,
            title=f"Reactivate {site.short_name}",
            summary="The Site can be reactivated alone or with optional setup.",
            current_state=[OperationItem("SITE", site.id, site.short_name, site.status.value)],
            dependencies=dependencies,
            warnings=[],
            allowed_resolutions=["REACTIVATE_ONLY", "REACTIVATE_AND_SET_UP"],
            blocked_reasons=blocked,
            planned_changes=changes,
            snapshot=snapshot,
        )

    def execute(
        self,
        intent: OwnerOperationIntent,
        *,
        expected_state_token: str,
    ) -> OwnerOperationResult:
        plan = self.preview(intent, lock=True)
        if plan.state_token != expected_state_token:
            raise ConflictError("State changed. Review the operation again.")
        if not plan.can_execute:
            raise ConflictError(plan.blocked_reasons[0])
        handlers = {
            OwnerOperationAction.ACTIVATE_PERSON: self._execute_activate_person,
            OwnerOperationAction.SET_SUPERVISOR_SITES: self._execute_supervisor_sites,
            OwnerOperationAction.DEACTIVATE_PERSON: self._execute_deactivate_person,
            OwnerOperationAction.DEPLOY_ASSET: self._execute_deploy_asset,
            OwnerOperationAction.MOVE_DEPLOYMENT: self._execute_move_deployment,
            OwnerOperationAction.REMOVE_DEPLOYMENT: self._execute_remove_deployment,
            OwnerOperationAction.ASSIGN_DRIVER: self._execute_assign_driver,
            OwnerOperationAction.REASSIGN_DRIVER: self._execute_reassign_driver,
            OwnerOperationAction.END_ASSIGNMENT: self._execute_end_assignment,
            OwnerOperationAction.DEACTIVATE_ASSET: self._execute_deactivate_asset,
            OwnerOperationAction.FORCE_CLOSE_DUTY_AND_DEACTIVATE_ASSET: (
                self._execute_force_close_duty_and_deactivate_asset
            ),
            OwnerOperationAction.REACTIVATE_ASSET: self._execute_reactivate_asset,
            OwnerOperationAction.DEACTIVATE_SITE: self._execute_deactivate_site,
            OwnerOperationAction.REACTIVATE_SITE: self._execute_reactivate_site,
        }
        try:
            handlers[intent.action](intent)
            self.session.flush()
        except IntegrityError as exc:
            raise ConflictError("State changed. Review the operation again.") from exc
        return OwnerOperationResult(
            action=intent.action,
            completed_changes=plan.planned_changes,
            message="Operation completed successfully.",
        )

    def _audit(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: UUID,
        old_values: dict[str, object] | None = None,
        new_values: dict[str, object] | None = None,
        reason: str | None = None,
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
            reason=reason,
            request_id=self.request_id,
        )

    def _end_assignment(self, assignment: Assignment, at: datetime) -> None:
        assignment.ends_at = at
        self._audit(
            action="DRIVER_UNASSIGNED_FROM_ASSET",
            entity_type="FLEET_ASSET",
            entity_id=assignment.asset_id,
            old_values={
                "assignment_id": str(assignment.id),
                "driver_membership_id": str(assignment.driver_membership_id),
                "site_id": str(assignment.site_id),
                "asset_site_deployment_id": str(assignment.asset_site_deployment_id),
            },
        )

    def _end_deployment(self, deployment: AssetSiteDeployment, at: datetime) -> None:
        deployment.ends_at = at
        self._audit(
            action="ASSET_REMOVED_FROM_SITE",
            entity_type="FLEET_ASSET",
            entity_id=deployment.asset_id,
            old_values={"site_id": str(deployment.site_id), "deployment_id": str(deployment.id)},
        )

    def _create_deployment(
        self,
        *,
        asset_id: UUID,
        site_id: UUID,
        starts_at: datetime,
        old_site_id: UUID | None = None,
    ) -> AssetSiteDeployment:
        deployment = AssetSiteDeployment(
            company_id=self.company_id,
            asset_id=asset_id,
            site_id=site_id,
            starts_at=starts_at,
        )
        self.session.add(deployment)
        self.session.flush()
        self._audit(
            action="ASSET_MOVED_SITE" if old_site_id is not None else "ASSET_DEPLOYED_TO_SITE",
            entity_type="FLEET_ASSET",
            entity_id=asset_id,
            old_values={"site_id": str(old_site_id)} if old_site_id else None,
            new_values={"site_id": str(site_id), "deployment_id": str(deployment.id)},
        )
        return deployment

    def _create_assignment(
        self,
        *,
        asset: FleetAsset,
        deployment: AssetSiteDeployment,
        driver_membership_id: UUID,
        starts_at: datetime,
        regular_duty_minutes: int,
        action: str = "DRIVER_ASSIGNED_TO_ASSET",
        old_driver_id: UUID | None = None,
    ) -> Assignment:
        assignment = Assignment(
            company_id=self.company_id,
            driver_membership_id=driver_membership_id,
            supervisor_membership_id=None,
            asset_id=asset.id,
            site_id=deployment.site_id,
            asset_site_deployment_id=deployment.id,
            starts_at=starts_at,
            regular_duty_minutes=regular_duty_minutes,
        )
        self.session.add(assignment)
        self.session.flush()
        self._audit(
            action=action,
            entity_type="FLEET_ASSET",
            entity_id=asset.id,
            old_values=({"driver_membership_id": str(old_driver_id)} if old_driver_id else None),
            new_values={
                "assignment_id": str(assignment.id),
                "driver_membership_id": str(driver_membership_id),
                "site_id": str(deployment.site_id),
                "asset_site_deployment_id": str(deployment.id),
            },
        )
        return assignment

    def _execute_remove_deployment(self, intent: OwnerOperationIntent) -> None:
        assert intent.asset_id is not None
        deployment = self._deployment(intent.asset_id, lock=True)
        assert deployment is not None
        assignment = self._assignment(intent.asset_id, at=datetime.now(UTC), lock=True)
        now = datetime.now(UTC)
        if assignment is not None:
            self._end_assignment(assignment, now)
        self._end_deployment(deployment, now)

    def _execute_move_deployment(self, intent: OwnerOperationIntent) -> None:
        assert intent.asset_id is not None and intent.target_site_id is not None
        asset = self._asset(intent.asset_id, lock=True)
        deployment = self._deployment(asset.id, lock=True)
        assert deployment is not None
        assignment = self._assignment(asset.id, at=datetime.now(UTC), lock=True)
        now = datetime.now(UTC)
        old_site_id = deployment.site_id
        old_driver_id: UUID | None = None
        duty_minutes = intent.regular_duty_minutes
        if assignment is not None:
            old_driver_id = assignment.driver_membership_id
            duty_minutes = assignment.regular_duty_minutes
            self._end_assignment(assignment, now)
        deployment.ends_at = now
        replacement = self._create_deployment(
            asset_id=asset.id,
            site_id=intent.target_site_id,
            starts_at=now,
            old_site_id=old_site_id,
        )
        if assignment is not None and intent.assignment_action == "KEEP":
            self._create_assignment(
                asset=asset,
                deployment=replacement,
                driver_membership_id=assignment.driver_membership_id,
                starts_at=now,
                regular_duty_minutes=duty_minutes,
                action="DRIVER_ASSIGNMENT_CONTINUED_AFTER_SITE_MOVE",
                old_driver_id=old_driver_id,
            )

    def _execute_deploy_asset(self, intent: OwnerOperationIntent) -> None:
        assert intent.asset_id is not None and intent.site_id is not None
        self._create_deployment(
            asset_id=intent.asset_id,
            site_id=intent.site_id,
            starts_at=datetime.now(UTC),
        )

    def _activate_membership(self, membership: CompanyMembership) -> None:
        if membership.status != MembershipStatus.INACTIVE:
            return
        membership.status = MembershipStatus.ACTIVE
        self._audit(
            action="OWNER_PERSON_REACTIVATED",
            entity_type="COMPANY_MEMBERSHIP",
            entity_id=membership.id,
            old_values={"status": MembershipStatus.INACTIVE.value},
            new_values={"status": MembershipStatus.ACTIVE.value},
        )

    def _execute_assign_driver(self, intent: OwnerOperationIntent) -> None:
        assert intent.asset_id is not None and intent.driver_membership_id is not None
        asset = self._asset(intent.asset_id, lock=True)
        driver, _user = self._membership(intent.driver_membership_id, lock=True)
        if intent.activate_membership:
            self._activate_membership(driver)
        deployment = self._deployment(asset.id, lock=True)
        now = datetime.now(UTC)
        if deployment is None:
            assert intent.site_id is not None
            deployment = self._create_deployment(
                asset_id=asset.id,
                site_id=intent.site_id,
                starts_at=now,
            )
        self._create_assignment(
            asset=asset,
            deployment=deployment,
            driver_membership_id=driver.id,
            starts_at=now,
            regular_duty_minutes=intent.regular_duty_minutes,
        )

    def _execute_reassign_driver(self, intent: OwnerOperationIntent) -> None:
        assert intent.asset_id is not None and intent.driver_membership_id is not None
        asset = self._asset(intent.asset_id, lock=True)
        deployment = self._deployment(asset.id, lock=True)
        assignment = self._assignment(asset.id, at=datetime.now(UTC), lock=True)
        replacement, _user = self._membership(intent.driver_membership_id, lock=True)
        assert deployment is not None and assignment is not None
        if intent.activate_membership:
            self._activate_membership(replacement)
        now = datetime.now(UTC)
        old_driver_id = assignment.driver_membership_id
        self._end_assignment(assignment, now)
        self._create_assignment(
            asset=asset,
            deployment=deployment,
            driver_membership_id=replacement.id,
            starts_at=now,
            regular_duty_minutes=intent.regular_duty_minutes,
            action="DRIVER_REASSIGNED_ON_ASSET",
            old_driver_id=old_driver_id,
        )

    def _execute_end_assignment(self, intent: OwnerOperationIntent) -> None:
        assert intent.asset_id is not None
        assignment = self._assignment(intent.asset_id, at=datetime.now(UTC), lock=True)
        assert assignment is not None
        self._end_assignment(assignment, datetime.now(UTC))

    def _grant_access(self, membership_id: UUID, site_id: UUID) -> None:
        existing = self.session.scalar(
            select(SupervisorSiteAccess).where(
                SupervisorSiteAccess.company_id == self.company_id,
                SupervisorSiteAccess.supervisor_membership_id == membership_id,
                SupervisorSiteAccess.site_id == site_id,
            )
        )
        if existing is not None:
            return
        access = SupervisorSiteAccess(
            company_id=self.company_id,
            supervisor_membership_id=membership_id,
            site_id=site_id,
        )
        self.session.add(access)
        self.session.flush()
        self._audit(
            action="OWNER_SUPERVISOR_SITE_GRANTED",
            entity_type="SUPERVISOR_SITE_ACCESS",
            entity_id=access.id,
            new_values={
                "supervisor_membership_id": str(membership_id),
                "site_id": str(site_id),
            },
        )

    def _revoke_access(self, access: SupervisorSiteAccess) -> None:
        access_id = access.id
        membership_id = access.supervisor_membership_id
        site_id = access.site_id
        self.session.delete(access)
        self._audit(
            action="OWNER_SUPERVISOR_SITE_REVOKED",
            entity_type="SUPERVISOR_SITE_ACCESS",
            entity_id=access_id,
            old_values={
                "supervisor_membership_id": str(membership_id),
                "site_id": str(site_id),
            },
        )

    def _execute_activate_person(self, intent: OwnerOperationIntent) -> None:
        assert intent.person_membership_id is not None
        membership, _user = self._membership(intent.person_membership_id, lock=True)
        self._activate_membership(membership)
        if membership.role == MembershipRole.SUPERVISOR:
            for site_id in sorted(set(intent.selected_site_ids), key=str):
                self._grant_access(membership.id, site_id)
        elif membership.role == MembershipRole.DRIVER and intent.asset_id is not None:
            assignment_intent = OwnerOperationIntent(
                action=OwnerOperationAction.ASSIGN_DRIVER,
                asset_id=intent.asset_id,
                site_id=intent.site_id,
                driver_membership_id=membership.id,
                activate_membership=False,
                regular_duty_minutes=intent.regular_duty_minutes,
            )
            self._execute_assign_driver(assignment_intent)

    def _execute_supervisor_sites(self, intent: OwnerOperationIntent) -> None:
        assert intent.person_membership_id is not None
        membership, _user = self._membership(intent.person_membership_id, lock=True)
        if intent.activate_membership:
            self._activate_membership(membership)
        selected = set(intent.selected_site_ids)
        for access, _site in self._supervisor_accesses(membership.id, lock=True):
            if access.site_id not in selected:
                self._revoke_access(access)
        for site_id in sorted(selected, key=str):
            self._grant_access(membership.id, site_id)

    def _execute_deactivate_person(self, intent: OwnerOperationIntent) -> None:
        assert intent.person_membership_id is not None
        membership, _user = self._membership(intent.person_membership_id, lock=True)
        if membership.role == MembershipRole.SUPERVISOR:
            for access, _site in self._supervisor_accesses(membership.id, lock=True):
                self._revoke_access(access)
        elif membership.role == MembershipRole.DRIVER:
            assignment = self._driver_assignment(
                membership.id,
                at=datetime.now(UTC),
                lock=True,
            )
            if assignment is not None:
                self._end_assignment(assignment, datetime.now(UTC))
        if membership.status != MembershipStatus.INACTIVE:
            old_status = membership.status
            membership.status = MembershipStatus.INACTIVE
            self._audit(
                action="OWNER_PERSON_DEACTIVATED",
                entity_type="COMPANY_MEMBERSHIP",
                entity_id=membership.id,
                old_values={"status": old_status.value},
                new_values={"status": MembershipStatus.INACTIVE.value},
            )

    def _execute_deactivate_asset(self, intent: OwnerOperationIntent) -> None:
        assert intent.asset_id is not None
        asset = self._asset(intent.asset_id, lock=True)
        now = datetime.now(UTC)
        assignment = self._assignment(asset.id, at=now, lock=True)
        deployment = self._deployment(asset.id, lock=True)
        if assignment is not None:
            self._end_assignment(assignment, now)
        if deployment is not None:
            self._end_deployment(deployment, now)
        if asset.status != FleetAssetStatus.INACTIVE:
            asset.status = FleetAssetStatus.INACTIVE
            self._audit(
                action="OWNER_ASSET_DEACTIVATED",
                entity_type="FLEET_ASSET",
                entity_id=asset.id,
                old_values={"status": FleetAssetStatus.ACTIVE.value},
                new_values={"status": FleetAssetStatus.INACTIVE.value},
            )

    def _execute_force_close_duty_and_deactivate_asset(self, intent: OwnerOperationIntent) -> None:
        assert intent.asset_id is not None
        reason = (intent.reason or "").strip()
        if not reason:
            raise DomainError("reason is required for administrative duty closure")

        asset = self._asset(intent.asset_id, lock=True)
        now = datetime.now(UTC)
        duty = self._duty(asset.id, lock=True)
        assignment = self._assignment(asset.id, at=now, lock=True)
        deployment = self._deployment(asset.id, lock=True)
        capabilities = capabilities_for_asset(asset)

        duty_id = duty.id if duty is not None else None
        driver_membership_id = (
            duty.driver_membership_id
            if duty is not None
            else assignment.driver_membership_id
            if assignment is not None
            else None
        )
        site_id = (
            duty.site_id
            if duty is not None
            else deployment.site_id
            if deployment is not None
            else None
        )
        duty_started_at = duty.started_at if duty is not None else None
        old_duty_status = duty.status.value if duty is not None else None
        old_end_event_id = duty.end_event_id if duty is not None else None
        old_end_km = duty.end_km if duty is not None else None
        old_end_hmr = duty.end_hmr if duty is not None else None
        missing_end_meter = bool(
            duty is not None
            and (
                (capabilities.supports_odometer and duty.end_km is None)
                or (capabilities.supports_hour_meter and duty.end_hmr is None)
            )
        )
        missing_end_meter_type = (
            "KM"
            if duty is not None and capabilities.supports_odometer
            else "HMR"
            if duty is not None and capabilities.supports_hour_meter
            else None
        )
        lifecycle_effects: list[str] = []

        if duty is not None:
            duty.status = DutySessionStatus.CLOSED
            duty.ended_at = now
            duty.final_overtime_minutes = max(
                0,
                int((now - duty.regular_duty_ends_at).total_seconds() // 60),
            )
            lifecycle_effects.append("DUTY_ADMINISTRATIVELY_CLOSED")
        if assignment is not None:
            self._end_assignment(assignment, now)
            lifecycle_effects.append("ASSIGNMENT_ENDED")
        if deployment is not None:
            self._end_deployment(deployment, now)
            lifecycle_effects.append("DEPLOYMENT_ENDED")
        old_asset_status = asset.status
        if asset.status != FleetAssetStatus.INACTIVE:
            asset.status = FleetAssetStatus.INACTIVE
            self._audit(
                action="OWNER_ASSET_DEACTIVATED",
                entity_type="FLEET_ASSET",
                entity_id=asset.id,
                old_values={"status": old_asset_status.value},
                new_values={"status": FleetAssetStatus.INACTIVE.value},
            )
            lifecycle_effects.append("ASSET_DEACTIVATED")

        self._audit(
            action="OWNER_DUTY_FORCE_CLOSED_AND_ASSET_DEACTIVATED",
            entity_type="FLEET_ASSET",
            entity_id=asset.id,
            old_values={
                "asset_id": str(asset.id),
                "asset_status": old_asset_status.value,
                "duty_session_id": str(duty_id) if duty_id is not None else None,
                "duty_status": old_duty_status,
                "duty_started_at": (
                    duty_started_at.isoformat() if duty_started_at is not None else None
                ),
                "driver_membership_id": (
                    str(driver_membership_id) if driver_membership_id is not None else None
                ),
                "site_id": str(site_id) if site_id is not None else None,
                "assignment_id": str(assignment.id) if assignment is not None else None,
                "deployment_id": str(deployment.id) if deployment is not None else None,
                "end_event_id": (str(old_end_event_id) if old_end_event_id is not None else None),
                "end_km": str(old_end_km) if old_end_km is not None else None,
                "end_hmr": str(old_end_hmr) if old_end_hmr is not None else None,
                "missing_end_meter": missing_end_meter,
                "missing_end_meter_type": missing_end_meter_type,
            },
            new_values={
                "asset_status": FleetAssetStatus.INACTIVE.value,
                "duty_status": (
                    DutySessionStatus.CLOSED.value if duty is not None else "NO_ACTIVE_DUTY"
                ),
                "duty_ended_at": now.isoformat() if duty is not None else None,
                "end_event_fabricated": False,
                "end_meter_fabricated": False,
                "history_preserved": True,
                "lifecycle_effects": lifecycle_effects,
            },
            reason=reason,
        )

    def _execute_reactivate_asset(self, intent: OwnerOperationIntent) -> None:
        assert intent.asset_id is not None
        asset = self._asset(intent.asset_id, lock=True)
        old_status = asset.status
        asset.status = FleetAssetStatus.ACTIVE
        self._audit(
            action="OWNER_ASSET_REACTIVATED",
            entity_type="FLEET_ASSET",
            entity_id=asset.id,
            old_values={"status": old_status.value},
            new_values={"status": FleetAssetStatus.ACTIVE.value},
        )

        if intent.site_id is None:
            return
        now = datetime.now(UTC)
        deployment = self._create_deployment(
            asset_id=asset.id,
            site_id=intent.site_id,
            starts_at=now,
        )
        if intent.driver_membership_id is None:
            return
        driver, _user = self._membership(intent.driver_membership_id, lock=True)
        if intent.activate_membership:
            self._activate_membership(driver)
        self._create_assignment(
            asset=asset,
            deployment=deployment,
            driver_membership_id=driver.id,
            starts_at=now,
            regular_duty_minutes=intent.regular_duty_minutes,
        )

    def _move_site_asset(
        self,
        *,
        asset: FleetAsset,
        deployment: AssetSiteDeployment,
        assignment: Assignment | None,
        target_site_id: UUID,
        assignment_action: AssignmentResolution | None,
        now: datetime,
    ) -> None:
        old_driver_id = assignment.driver_membership_id if assignment else None
        duty_minutes = assignment.regular_duty_minutes if assignment else 600
        if assignment is not None:
            self._end_assignment(assignment, now)
        old_site_id = deployment.site_id
        deployment.ends_at = now
        replacement = self._create_deployment(
            asset_id=asset.id,
            site_id=target_site_id,
            starts_at=now,
            old_site_id=old_site_id,
        )
        if assignment is not None and assignment_action == "KEEP":
            self._create_assignment(
                asset=asset,
                deployment=replacement,
                driver_membership_id=assignment.driver_membership_id,
                starts_at=now,
                regular_duty_minutes=duty_minutes,
                action="DRIVER_ASSIGNMENT_CONTINUED_AFTER_SITE_MOVE",
                old_driver_id=old_driver_id,
            )

    def _execute_deactivate_site(self, intent: OwnerOperationIntent) -> None:
        assert intent.site_id is not None
        site = self._site(intent.site_id, lock=True)
        assets, accesses = self._site_dependencies(site, lock=True)
        decisions = {item.asset_id: item for item in intent.asset_resolutions}
        now = datetime.now(UTC)
        for deployment, asset, assignment, _membership, _user, _duty in assets:
            decision = decisions[asset.id]
            if decision.action == "REMOVE":
                if assignment is not None:
                    self._end_assignment(assignment, now)
                self._end_deployment(deployment, now)
            else:
                assert decision.target_site_id is not None
                self._move_site_asset(
                    asset=asset,
                    deployment=deployment,
                    assignment=assignment,
                    target_site_id=decision.target_site_id,
                    assignment_action=decision.assignment_action,
                    now=now,
                )
        for access, _membership, _user in accesses:
            self._revoke_access(access)
        if site.status != SiteStatus.INACTIVE:
            site.status = SiteStatus.INACTIVE
            self._audit(
                action="OWNER_SITE_DEACTIVATED",
                entity_type="SITE",
                entity_id=site.id,
                old_values={"status": SiteStatus.ACTIVE.value},
                new_values={"status": SiteStatus.INACTIVE.value},
            )

    def _execute_reactivate_site(self, intent: OwnerOperationIntent) -> None:
        assert intent.site_id is not None
        site = self._site(intent.site_id, lock=True)
        if site.status != SiteStatus.ACTIVE:
            site.status = SiteStatus.ACTIVE
            self._audit(
                action="OWNER_SITE_REACTIVATED",
                entity_type="SITE",
                entity_id=site.id,
                old_values={"status": SiteStatus.INACTIVE.value},
                new_values={"status": SiteStatus.ACTIVE.value},
            )
        for membership_id in sorted(set(intent.selected_supervisor_ids), key=str):
            self._grant_access(membership_id, site.id)
        now = datetime.now(UTC)
        for asset_id in sorted(set(intent.selected_asset_ids), key=str):
            self._create_deployment(asset_id=asset_id, site_id=site.id, starts_at=now)
