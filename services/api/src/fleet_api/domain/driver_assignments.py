from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fleet_api.auth.service import AuthContext, ensure_supervisor_site_access
from fleet_api.db.models import (
    AssetSiteDeployment,
    Assignment,
    CompanyMembership,
    DutySession,
    FleetAsset,
    Site,
    User,
)
from fleet_api.domain.assets import capabilities_for
from fleet_api.domain.audit import write_audit_log
from fleet_api.domain.enums import (
    DutySessionStatus,
    FleetAssetStatus,
    MembershipRole,
    MembershipStatus,
    SiteStatus,
    UserStatus,
)
from fleet_api.domain.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    RoleViolationError,
    TenantConsistencyError,
)


@dataclass(frozen=True)
class DriverCandidate:
    membership: CompanyMembership
    user: User


@dataclass(frozen=True)
class DriverAssetAssignmentView:
    assignment: Assignment
    asset: FleetAsset
    deployment: AssetSiteDeployment
    site: Site
    driver_membership: CompanyMembership
    driver: User


class DriverAssetAssignmentService:
    """Effective-dated Driver-to-asset scheduling over canonical deployments."""

    def __init__(
        self,
        session: Session,
        context: AuthContext,
        *,
        request_id: str | None = None,
    ) -> None:
        if context.membership.role not in {
            MembershipRole.OWNER_ADMIN,
            MembershipRole.SUPERVISOR,
        }:
            raise RoleViolationError("owner or supervisor membership is required")
        self.session = session
        self.context = context
        self.company_id = context.company.id
        self.actor_membership_id = context.membership.id
        self.request_id = request_id

    def _asset(self, asset_id: UUID, *, lock: bool = False) -> FleetAsset:
        statement = select(FleetAsset).where(
            FleetAsset.id == asset_id,
            FleetAsset.company_id == self.company_id,
        )
        if lock:
            statement = statement.with_for_update()
        asset = self.session.scalar(statement)
        if asset is None:
            raise NotFoundError("asset was not found")
        return asset

    def _deployment(
        self, asset_id: UUID, *, lock: bool = False
    ) -> tuple[AssetSiteDeployment, Site]:
        statement = (
            select(AssetSiteDeployment, Site)
            .join(
                Site,
                (Site.company_id == AssetSiteDeployment.company_id)
                & (Site.id == AssetSiteDeployment.site_id),
            )
            .where(
                AssetSiteDeployment.company_id == self.company_id,
                AssetSiteDeployment.asset_id == asset_id,
                AssetSiteDeployment.ends_at.is_(None),
            )
        )
        if lock:
            statement = statement.with_for_update(of=AssetSiteDeployment)
        row = self.session.execute(statement).first()
        if row is None:
            raise ConflictError("Asset must be deployed to an active Site before assignment.")
        deployment, site = row._tuple()
        if site.status != SiteStatus.ACTIVE:
            raise ConflictError("Asset must be deployed to an active Site before assignment.")
        if self.context.membership.role == MembershipRole.SUPERVISOR:
            try:
                ensure_supervisor_site_access(self.session, self.context, site_id=site.id)
            except DomainError as exc:
                raise TenantConsistencyError(
                    "supervisor is not authorized for the asset's Site"
                ) from exc
        return deployment, site

    def _driver(self, membership_id: UUID, *, lock: bool = False) -> DriverCandidate:
        statement = (
            select(CompanyMembership, User)
            .join(User, User.id == CompanyMembership.user_id)
            .where(CompanyMembership.id == membership_id)
        )
        if lock:
            statement = statement.with_for_update(of=CompanyMembership)
        row = self.session.execute(statement).first()
        if row is None:
            raise NotFoundError("Driver / Operator was not found.")
        membership, user = row._tuple()
        if membership.company_id != self.company_id:
            raise TenantConsistencyError("Driver / Operator belongs to another company.")
        if membership.role != MembershipRole.DRIVER:
            raise RoleViolationError("assignment requires a Driver / Operator membership")
        if (
            membership.status not in (MembershipStatus.INVITED, MembershipStatus.ACTIVE)
            or user.status != UserStatus.ACTIVE
        ):
            raise ConflictError("Driver / Operator must be invited or active before assignment.")
        return DriverCandidate(membership, user)

    def _current_for_asset(self, asset_id: UUID, *, lock: bool = False) -> Assignment | None:
        now = datetime.now(UTC)
        statement = (
            select(Assignment)
            .where(
                Assignment.company_id == self.company_id,
                Assignment.asset_id == asset_id,
                Assignment.starts_at <= now,
                or_(Assignment.ends_at.is_(None), Assignment.ends_at > now),
            )
            .order_by(Assignment.starts_at.desc(), Assignment.id.desc())
            .limit(1)
        )
        if lock:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def _current_for_driver(self, membership_id: UUID, *, lock: bool = False) -> Assignment | None:
        now = datetime.now(UTC)
        statement = (
            select(Assignment)
            .where(
                Assignment.company_id == self.company_id,
                Assignment.driver_membership_id == membership_id,
                Assignment.starts_at <= now,
                or_(Assignment.ends_at.is_(None), Assignment.ends_at > now),
            )
            .order_by(Assignment.starts_at.desc(), Assignment.id.desc())
            .limit(1)
        )
        if lock:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def _view(self, assignment: Assignment) -> DriverAssetAssignmentView:
        asset = self.session.get(FleetAsset, assignment.asset_id)
        deployment = self.session.get(AssetSiteDeployment, assignment.asset_site_deployment_id)
        site = self.session.get(Site, assignment.site_id)
        membership = self.session.get(CompanyMembership, assignment.driver_membership_id)
        driver = self.session.get(User, membership.user_id) if membership else None
        if any(value is None for value in (asset, deployment, site, membership, driver)):
            raise TenantConsistencyError("assignment references are incomplete")
        assert asset is not None
        assert deployment is not None
        assert site is not None
        assert membership is not None
        assert driver is not None
        return DriverAssetAssignmentView(assignment, asset, deployment, site, membership, driver)

    def current(self, asset_id: UUID) -> DriverAssetAssignmentView | None:
        self._asset(asset_id)
        self._deployment(asset_id)
        assignment = self._current_for_asset(asset_id)
        return self._view(assignment) if assignment is not None else None

    def ensure_asset_site(self, asset_id: UUID, site_id: UUID) -> None:
        self._asset(asset_id)
        _deployment, site = self._deployment(asset_id)
        if site.id != site_id:
            raise TenantConsistencyError("asset is not deployed to the requested Site")

    def history(self, asset_id: UUID) -> list[DriverAssetAssignmentView]:
        self._asset(asset_id)
        if self.context.membership.role == MembershipRole.SUPERVISOR:
            self._deployment(asset_id)
        assignments = self.session.scalars(
            select(Assignment)
            .where(
                Assignment.company_id == self.company_id,
                Assignment.asset_id == asset_id,
            )
            .order_by(Assignment.starts_at.desc(), Assignment.id.desc())
        ).all()
        return [self._view(assignment) for assignment in assignments]

    def eligible_drivers(self, asset_id: UUID) -> list[DriverCandidate]:
        asset = self._asset(asset_id)
        self._deployment(asset_id)
        if asset.status != FleetAssetStatus.ACTIVE:
            raise ConflictError("Only an active asset can receive a Driver / Operator.")
        if not capabilities_for(asset.asset_type).supports_duty_session:
            raise ConflictError("This asset type is not supported by the current Driver workflow.")
        now = datetime.now(UTC)
        assigned_driver_ids = select(Assignment.driver_membership_id).where(
            Assignment.company_id == self.company_id,
            Assignment.starts_at <= now,
            or_(Assignment.ends_at.is_(None), Assignment.ends_at > now),
        )
        rows = self.session.execute(
            select(CompanyMembership, User)
            .join(User, User.id == CompanyMembership.user_id)
            .where(
                CompanyMembership.company_id == self.company_id,
                CompanyMembership.role == MembershipRole.DRIVER,
                CompanyMembership.status.in_((MembershipStatus.INVITED, MembershipStatus.ACTIVE)),
                User.status == UserStatus.ACTIVE,
                CompanyMembership.id.not_in(assigned_driver_ids),
            )
            .order_by(
                CompanyMembership.display_name,
                User.display_name,
                CompanyMembership.id,
            )
        ).all()
        return [DriverCandidate(membership, user) for membership, user in rows]

    def _ensure_assignable_asset(self, asset: FleetAsset) -> None:
        if asset.status != FleetAssetStatus.ACTIVE:
            raise ConflictError("Only an active asset can receive a Driver / Operator.")
        if not capabilities_for(asset.asset_type).supports_duty_session:
            raise ConflictError("This asset type is not supported by the current Driver workflow.")

    def _create(
        self,
        *,
        asset: FleetAsset,
        deployment: AssetSiteDeployment,
        driver: DriverCandidate,
        starts_at: datetime,
        regular_duty_minutes: int,
    ) -> Assignment:
        if regular_duty_minutes <= 0 or regular_duty_minutes > 1440:
            raise DomainError("regular_duty_minutes must be between 1 and 1440")
        assignment = Assignment(
            company_id=self.company_id,
            driver_membership_id=driver.membership.id,
            supervisor_membership_id=None,
            asset_id=asset.id,
            site_id=deployment.site_id,
            asset_site_deployment_id=deployment.id,
            starts_at=starts_at,
            regular_duty_minutes=regular_duty_minutes,
        )
        self.session.add(assignment)
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "Driver / Operator or asset assignment changed; reload and try again."
            ) from exc
        return assignment

    def _audit(
        self,
        *,
        action: str,
        assignment: Assignment,
        old_driver_id: UUID | None,
        new_driver_id: UUID | None,
    ) -> None:
        old_values: dict[str, object] | None = None
        if old_driver_id is not None:
            old_values = {
                "driver_membership_id": str(old_driver_id),
                "site_id": str(assignment.site_id),
                "asset_site_deployment_id": str(assignment.asset_site_deployment_id),
            }
        new_values: dict[str, object] | None = None
        if new_driver_id is not None:
            new_values = {
                "driver_membership_id": str(new_driver_id),
                "site_id": str(assignment.site_id),
                "asset_site_deployment_id": str(assignment.asset_site_deployment_id),
                "assignment_id": str(assignment.id),
            }
        write_audit_log(
            self.session,
            company_id=self.company_id,
            actor_membership_id=self.actor_membership_id,
            action=action,
            entity_type="FLEET_ASSET",
            entity_id=assignment.asset_id,
            old_values=old_values,
            new_values=new_values,
            request_id=self.request_id,
        )

    def assign(
        self,
        asset_id: UUID,
        driver_membership_id: UUID,
        *,
        regular_duty_minutes: int = 600,
    ) -> DriverAssetAssignmentView:
        asset = self._asset(asset_id, lock=True)
        self._ensure_assignable_asset(asset)
        deployment, _site = self._deployment(asset.id, lock=True)
        driver = self._driver(driver_membership_id, lock=True)
        if self._current_for_asset(asset.id, lock=True) is not None:
            raise ConflictError("Asset already has a current Driver / Operator.")
        if self._current_for_driver(driver.membership.id, lock=True) is not None:
            raise ConflictError("Driver / Operator already has a current asset.")
        assignment = self._create(
            asset=asset,
            deployment=deployment,
            driver=driver,
            starts_at=datetime.now(UTC),
            regular_duty_minutes=regular_duty_minutes,
        )
        self._audit(
            action="DRIVER_ASSIGNED_TO_ASSET",
            assignment=assignment,
            old_driver_id=None,
            new_driver_id=driver.membership.id,
        )
        return self._view(assignment)

    def _ensure_no_active_duty(self, assignment: Assignment) -> None:
        duty = self.session.scalar(
            select(DutySession.id)
            .where(
                DutySession.company_id == self.company_id,
                DutySession.assignment_id == assignment.id,
                DutySession.status == DutySessionStatus.ACTIVE,
            )
            .limit(1)
        )
        if duty is not None:
            raise ConflictError("Driver must end the active duty before assignment can change.")

    def unassign(self, asset_id: UUID) -> DriverAssetAssignmentView:
        self._asset(asset_id, lock=True)
        self._deployment(asset_id, lock=True)
        assignment = self._current_for_asset(asset_id, lock=True)
        if assignment is None:
            raise ConflictError("Asset has no current Driver / Operator assignment.")
        self._ensure_no_active_duty(assignment)
        assignment.ends_at = datetime.now(UTC)
        self.session.flush()
        self._audit(
            action="DRIVER_UNASSIGNED_FROM_ASSET",
            assignment=assignment,
            old_driver_id=assignment.driver_membership_id,
            new_driver_id=None,
        )
        return self._view(assignment)

    def reassign(
        self,
        asset_id: UUID,
        driver_membership_id: UUID,
        *,
        regular_duty_minutes: int | None = None,
    ) -> DriverAssetAssignmentView:
        asset = self._asset(asset_id, lock=True)
        self._ensure_assignable_asset(asset)
        deployment, _site = self._deployment(asset.id, lock=True)
        current = self._current_for_asset(asset.id, lock=True)
        if current is None:
            raise ConflictError("Asset has no current Driver / Operator assignment.")
        if current.driver_membership_id == driver_membership_id:
            raise ConflictError("Driver / Operator is already assigned to this asset.")
        self._ensure_no_active_duty(current)
        driver = self._driver(driver_membership_id, lock=True)
        if self._current_for_driver(driver.membership.id, lock=True) is not None:
            raise ConflictError("Driver / Operator already has a current asset.")
        now = datetime.now(UTC)
        current.ends_at = now
        self.session.flush()
        replacement = self._create(
            asset=asset,
            deployment=deployment,
            driver=driver,
            starts_at=now,
            regular_duty_minutes=(
                regular_duty_minutes
                if regular_duty_minutes is not None
                else current.regular_duty_minutes
            ),
        )
        self._audit(
            action="DRIVER_REASSIGNED_ON_ASSET",
            assignment=replacement,
            old_driver_id=current.driver_membership_id,
            new_driver_id=driver.membership.id,
        )
        return self._view(replacement)
