from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql.elements import ColumnElement

from fleet_api.auth.service import AuthContext
from fleet_api.db.models import (
    AssetSiteDeployment,
    Assignment,
    CompanyMembership,
    DutySession,
    FleetAsset,
    OperationalEvent,
    Site,
    User,
)
from fleet_api.domain.audit import write_audit_log
from fleet_api.domain.enums import (
    DutySessionStatus,
    FleetAssetStatus,
    SiteStatus,
    VerificationStatus,
)
from fleet_api.domain.errors import ConflictError, NotFoundError


@dataclass(frozen=True)
class DeploymentView:
    deployment: AssetSiteDeployment
    site: Site


@dataclass(frozen=True)
class DeployedAssetView:
    deployment: AssetSiteDeployment
    asset: FleetAsset
    site_name: str
    driver_membership_id: UUID | None
    driver_name: str | None
    duty_status: str | None
    pending_review_count: int


def _effective_assignment_clause(
    now: datetime,
) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    return (
        Assignment.starts_at <= now,
        or_(Assignment.ends_at.is_(None), Assignment.ends_at > now),
    )


def ensure_deployment_for_assignment(
    session: Session,
    *,
    company_id: UUID,
    asset_id: UUID,
    site_id: UUID,
    starts_at: datetime,
    ends_at: datetime | None,
) -> AssetSiteDeployment:
    """Keep legacy assignment creation compatible with canonical deployment.

    New owner flows create deployments directly. Legacy bootstrap/tests may still
    create an operational assignment first; this bridge creates the independent
    placement row once and refuses a cross-site mismatch.
    """

    overlap = session.scalar(
        select(AssetSiteDeployment)
        .where(
            AssetSiteDeployment.company_id == company_id,
            AssetSiteDeployment.asset_id == asset_id,
            AssetSiteDeployment.starts_at < (ends_at or datetime.max.replace(tzinfo=UTC)),
            or_(
                AssetSiteDeployment.ends_at.is_(None),
                AssetSiteDeployment.ends_at > starts_at,
            ),
        )
        .order_by(AssetSiteDeployment.starts_at.desc())
        .limit(1)
    )
    if overlap is not None:
        if overlap.site_id != site_id:
            raise ConflictError("Driver assignment site must match the asset's current deployment.")
        return overlap
    deployment = AssetSiteDeployment(
        company_id=company_id,
        asset_id=asset_id,
        site_id=site_id,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    session.add(deployment)
    session.flush()
    return deployment


def list_current_site_assets(
    session: Session,
    *,
    company_id: UUID,
    site_id: UUID,
) -> list[DeployedAssetView]:
    now = datetime.now(UTC)
    site_name = session.scalar(
        select(Site.name).where(Site.company_id == company_id, Site.id == site_id)
    )
    if site_name is None:
        raise NotFoundError("site was not found")
    driver_membership = aliased(CompanyMembership)
    driver_user = aliased(User)
    rows = session.execute(
        select(
            AssetSiteDeployment,
            FleetAsset,
            Assignment,
            driver_membership,
            driver_user,
        )
        .join(
            FleetAsset,
            and_(
                FleetAsset.company_id == AssetSiteDeployment.company_id,
                FleetAsset.id == AssetSiteDeployment.asset_id,
            ),
        )
        .outerjoin(
            Assignment,
            and_(
                Assignment.company_id == AssetSiteDeployment.company_id,
                Assignment.asset_id == AssetSiteDeployment.asset_id,
                Assignment.site_id == AssetSiteDeployment.site_id,
                *_effective_assignment_clause(now),
            ),
        )
        .outerjoin(
            driver_membership,
            and_(
                driver_membership.company_id == Assignment.company_id,
                driver_membership.id == Assignment.driver_membership_id,
            ),
        )
        .outerjoin(driver_user, driver_user.id == driver_membership.user_id)
        .where(
            AssetSiteDeployment.company_id == company_id,
            AssetSiteDeployment.site_id == site_id,
            AssetSiteDeployment.ends_at.is_(None),
            FleetAsset.status == FleetAssetStatus.ACTIVE,
        )
        .order_by(FleetAsset.asset_code, FleetAsset.id)
    ).all()
    result: list[DeployedAssetView] = []
    for deployment, asset, assignment, membership, user in rows:
        duty_status = None
        pending = 0
        driver_membership_id = None
        driver_name = None
        if assignment is not None:
            driver_membership_id = assignment.driver_membership_id
            if membership is not None and user is not None:
                driver_name = membership.display_name or user.display_name
            active_duty = session.scalar(
                select(DutySession.status).where(
                    DutySession.company_id == company_id,
                    DutySession.assignment_id == assignment.id,
                    DutySession.status == DutySessionStatus.ACTIVE,
                )
            )
            duty_status = active_duty.value if active_duty is not None else None
            pending = int(
                session.scalar(
                    select(func.count(OperationalEvent.id)).where(
                        OperationalEvent.company_id == company_id,
                        OperationalEvent.assignment_id == assignment.id,
                        OperationalEvent.verification_status
                        == VerificationStatus.PENDING_VERIFICATION,
                    )
                )
                or 0
            )
        result.append(
            DeployedAssetView(
                deployment=deployment,
                asset=asset,
                site_name=site_name,
                driver_membership_id=driver_membership_id,
                driver_name=driver_name,
                duty_status=duty_status,
                pending_review_count=pending,
            )
        )
    return result


class OwnerDeploymentService:
    """Owner-only deployment lifecycle, independent of Driver assignment."""

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
        query = select(FleetAsset).where(
            FleetAsset.id == asset_id,
            FleetAsset.company_id == self.company_id,
        )
        if lock:
            query = query.with_for_update()
        asset = self.session.scalar(query)
        if asset is None:
            raise NotFoundError("asset was not found")
        return asset

    def _site(self, site_id: UUID) -> Site:
        site = self.session.scalar(
            select(Site).where(
                Site.id == site_id,
                Site.company_id == self.company_id,
            )
        )
        if site is None:
            raise NotFoundError("site was not found")
        return site

    def _current(self, asset_id: UUID, *, lock: bool = False) -> AssetSiteDeployment | None:
        query = select(AssetSiteDeployment).where(
            AssetSiteDeployment.company_id == self.company_id,
            AssetSiteDeployment.asset_id == asset_id,
            AssetSiteDeployment.ends_at.is_(None),
        )
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def current(self, asset_id: UUID) -> DeploymentView | None:
        self._asset(asset_id)
        deployment = self._current(asset_id)
        if deployment is None:
            return None
        return DeploymentView(deployment, self._site(deployment.site_id))

    def history(self, asset_id: UUID) -> list[DeploymentView]:
        self._asset(asset_id)
        rows = self.session.execute(
            select(AssetSiteDeployment, Site)
            .join(
                Site,
                and_(
                    Site.company_id == AssetSiteDeployment.company_id,
                    Site.id == AssetSiteDeployment.site_id,
                ),
            )
            .where(
                AssetSiteDeployment.company_id == self.company_id,
                AssetSiteDeployment.asset_id == asset_id,
            )
            .order_by(
                AssetSiteDeployment.starts_at.desc(),
                AssetSiteDeployment.id.desc(),
            )
        ).all()
        return [DeploymentView(deployment, site) for deployment, site in rows]

    def site_assets(self, site_id: UUID) -> list[DeployedAssetView]:
        site = self._site(site_id)
        views = list_current_site_assets(self.session, company_id=self.company_id, site_id=site_id)
        return [replace(view, site_name=site.short_name) for view in views]

    def _ensure_no_operational_dependency(self, asset_id: UUID, action: str) -> None:
        active_duty = self.session.scalar(
            select(DutySession.id)
            .where(
                DutySession.company_id == self.company_id,
                DutySession.asset_id == asset_id,
                DutySession.status == DutySessionStatus.ACTIVE,
            )
            .limit(1)
        )
        if active_duty is not None:
            raise ConflictError(f"Asset cannot be {action} while an active duty is in progress.")
        now = datetime.now(UTC)
        active_assignment = self.session.scalar(
            select(Assignment.id)
            .where(
                Assignment.company_id == self.company_id,
                Assignment.asset_id == asset_id,
                *_effective_assignment_clause(now),
            )
            .limit(1)
        )
        if active_assignment is not None:
            raise ConflictError(f"Asset cannot be {action} while a Driver is actively assigned.")

    def _audit(
        self,
        *,
        action: str,
        asset_id: UUID,
        old_site_id: UUID | None,
        new_site_id: UUID | None,
    ) -> None:
        write_audit_log(
            self.session,
            company_id=self.company_id,
            actor_membership_id=self.actor_membership_id,
            action=action,
            entity_type="FLEET_ASSET",
            entity_id=asset_id,
            old_values={"site_id": str(old_site_id)} if old_site_id else None,
            new_values={"site_id": str(new_site_id)} if new_site_id else None,
            request_id=self.request_id,
        )

    def deploy(self, asset_id: UUID, site_id: UUID) -> DeploymentView:
        asset = self._asset(asset_id, lock=True)
        site = self._site(site_id)
        if asset.status != FleetAssetStatus.ACTIVE:
            raise ConflictError("Only an active asset can be deployed.")
        if site.status != SiteStatus.ACTIVE:
            raise ConflictError("An asset can be deployed only to an active site.")
        current = self._current(asset.id, lock=True)
        if current is not None and current.site_id == site.id:
            raise ConflictError("Asset is already deployed to this site.")
        now = datetime.now(UTC)
        action = "ASSET_DEPLOYED_TO_SITE"
        old_site_id = None
        if current is not None:
            self._ensure_no_operational_dependency(asset.id, "moved")
            current.ends_at = now
            old_site_id = current.site_id
            action = "ASSET_MOVED_SITE"
        else:
            active_assignment_site = self.session.scalar(
                select(Assignment.site_id)
                .where(
                    Assignment.company_id == self.company_id,
                    Assignment.asset_id == asset.id,
                    *_effective_assignment_clause(now),
                )
                .limit(1)
            )
            if active_assignment_site is not None and active_assignment_site != site.id:
                raise ConflictError(
                    "Asset deployment site must match its active Driver assignment."
                )
        deployment = AssetSiteDeployment(
            company_id=self.company_id,
            asset_id=asset.id,
            site_id=site.id,
            starts_at=now,
        )
        self.session.add(deployment)
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise ConflictError("Asset deployment changed; reload and try again.") from exc
        self._audit(
            action=action,
            asset_id=asset.id,
            old_site_id=old_site_id,
            new_site_id=site.id,
        )
        return DeploymentView(deployment, site)

    def remove(self, asset_id: UUID) -> DeploymentView:
        asset = self._asset(asset_id, lock=True)
        current = self._current(asset.id, lock=True)
        if current is None:
            raise ConflictError("Asset is not currently deployed to a site.")
        self._ensure_no_operational_dependency(asset.id, "removed")
        site = self._site(current.site_id)
        current.ends_at = datetime.now(UTC)
        self.session.flush()
        self._audit(
            action="ASSET_REMOVED_FROM_SITE",
            asset_id=asset.id,
            old_site_id=site.id,
            new_site_id=None,
        )
        return DeploymentView(current, site)
