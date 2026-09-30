from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fleet_api.auth.phone import normalize_phone
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
from fleet_api.domain.audit import write_audit_log
from fleet_api.domain.enums import (
    DutySessionStatus,
    MembershipRole,
    MembershipStatus,
    SiteStatus,
    UserStatus,
)
from fleet_api.domain.errors import ConflictError, DomainError, NotFoundError


@dataclass(frozen=True)
class PersonSite:
    site_id: UUID
    site_name: str


@dataclass(frozen=True)
class PersonView:
    membership: CompanyMembership
    user: User
    sites: list[PersonSite]
    has_active_assignment: bool
    has_active_duty: bool
    current_asset_id: UUID | None
    current_asset_code: str | None
    current_site_id: UUID | None
    current_site_name: str | None


@dataclass(frozen=True)
class SiteSupervisor:
    access_id: UUID
    membership_id: UUID
    display_name: str


@dataclass(frozen=True)
class SiteView:
    site: Site
    supervisors: list[SiteSupervisor]
    asset_count: int


def _clean_required(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise DomainError(f"{field} must contain a value")
    return cleaned


def _clean_optional(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


class OwnerPeopleSiteService:
    """Owner-only tenant boundary for people, sites, and supervisor access."""

    def __init__(
        self,
        session: Session,
        context: AuthContext,
        *,
        request_id: str | None = None,
        phone_default_region: str | None = None,
    ) -> None:
        self.session = session
        self.company_id = context.company.id
        self.actor_membership_id = context.membership.id
        self.request_id = request_id
        self.phone_default_region = phone_default_region

    def _audit(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: UUID,
        old_values: Mapping[str, object] | None = None,
        new_values: Mapping[str, object] | None = None,
    ) -> None:
        write_audit_log(
            self.session,
            company_id=self.company_id,
            actor_membership_id=self.actor_membership_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_values=dict(old_values) if old_values is not None else None,
            new_values=dict(new_values) if new_values is not None else None,
            request_id=self.request_id,
        )

    def _membership(self, membership_id: UUID) -> CompanyMembership:
        membership = self.session.scalar(
            select(CompanyMembership).where(
                CompanyMembership.id == membership_id,
                CompanyMembership.company_id == self.company_id,
                CompanyMembership.role.in_(
                    (MembershipRole.DRIVER, MembershipRole.SUPERVISOR)
                ),
            )
        )
        if membership is None:
            raise NotFoundError("person was not found")
        return membership

    def _person_view(self, membership: CompanyMembership, user: User) -> PersonView:
        now = datetime.now(UTC)
        sites = [
            PersonSite(site_id=row.id, site_name=row.name)
            for row in self.session.execute(
                select(Site)
                .join(
                    SupervisorSiteAccess,
                    and_(
                        SupervisorSiteAccess.company_id == Site.company_id,
                        SupervisorSiteAccess.site_id == Site.id,
                    ),
                )
                .where(
                    SupervisorSiteAccess.company_id == self.company_id,
                    SupervisorSiteAccess.supervisor_membership_id == membership.id,
                )
                .order_by(Site.name, Site.id)
            ).scalars()
        ]
        current_asset_id: UUID | None = None
        current_asset_code: str | None = None
        current_site_id: UUID | None = None
        current_site_name: str | None = None
        has_assignment = False
        if membership.role == MembershipRole.DRIVER:
            current_assignment = self.session.execute(
                select(Assignment, FleetAsset, Site)
                .join(
                    FleetAsset,
                    and_(
                        FleetAsset.company_id == Assignment.company_id,
                        FleetAsset.id == Assignment.asset_id,
                    ),
                )
                .join(
                    Site,
                    and_(
                        Site.company_id == Assignment.company_id,
                        Site.id == Assignment.site_id,
                    ),
                )
                .where(
                    Assignment.company_id == self.company_id,
                    Assignment.driver_membership_id == membership.id,
                    Assignment.starts_at <= now,
                    or_(Assignment.ends_at.is_(None), Assignment.ends_at > now),
                )
                .limit(1)
            ).first()
            if current_assignment is not None:
                _assignment, asset, site = current_assignment._tuple()
                has_assignment = True
                current_asset_id = asset.id
                current_asset_code = asset.asset_code
                current_site_id = site.id
                current_site_name = site.name
        has_duty = (
            self.session.scalar(
                select(DutySession.id)
                .where(
                    DutySession.company_id == self.company_id,
                    DutySession.driver_membership_id == membership.id,
                    DutySession.status == DutySessionStatus.ACTIVE,
                )
                .limit(1)
            )
            is not None
        )
        return PersonView(
            membership,
            user,
            sites,
            has_assignment,
            has_duty,
            current_asset_id,
            current_asset_code,
            current_site_id,
            current_site_name,
        )

    def list_people(self) -> list[PersonView]:
        rows = self.session.execute(
            select(CompanyMembership, User)
            .join(User, User.id == CompanyMembership.user_id)
            .where(
                CompanyMembership.company_id == self.company_id,
                CompanyMembership.role.in_(
                    (MembershipRole.DRIVER, MembershipRole.SUPERVISOR)
                ),
            )
            .order_by(
                CompanyMembership.status,
                func.coalesce(CompanyMembership.display_name, User.display_name),
                CompanyMembership.id,
            )
        ).all()
        return [self._person_view(membership, user) for membership, user in rows]

    def get_person(self, membership_id: UUID) -> PersonView:
        membership = self._membership(membership_id)
        user = self.session.get(User, membership.user_id)
        if user is None:
            raise NotFoundError("person identity was not found")
        return self._person_view(membership, user)

    def invite_person(
        self, *, phone: str, display_name: str, role: MembershipRole
    ) -> PersonView:
        if role not in (MembershipRole.DRIVER, MembershipRole.SUPERVISOR):
            raise DomainError("role must be DRIVER or SUPERVISOR")
        normalized_phone = normalize_phone(phone, default_region=self.phone_default_region)
        clean_name = _clean_required(display_name, "display_name")
        user = self.session.scalar(select(User).where(User.phone_number == normalized_phone))
        if user is None:
            user = User(
                phone_number=normalized_phone,
                display_name=clean_name,
                status=UserStatus.ACTIVE,
            )
            self.session.add(user)
            self.session.flush()
        elif user.status != UserStatus.ACTIVE:
            raise ConflictError("phone belongs to an inactive identity")
        duplicate = self.session.scalar(
            select(CompanyMembership.id).where(
                CompanyMembership.company_id == self.company_id,
                CompanyMembership.user_id == user.id,
            )
        )
        if duplicate is not None:
            raise ConflictError("person already belongs to this company")
        membership = CompanyMembership(
            company_id=self.company_id,
            user_id=user.id,
            display_name=clean_name,
            role=role,
            status=MembershipStatus.INVITED,
        )
        self.session.add(membership)
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise ConflictError("membership already exists") from exc
        self._audit(
            action="OWNER_PERSON_INVITED",
            entity_type="COMPANY_MEMBERSHIP",
            entity_id=membership.id,
            new_values={
                "user_id": str(user.id),
                "phone": normalized_phone,
                "display_name": clean_name,
                "role": role.value,
                "status": MembershipStatus.INVITED.value,
            },
        )
        return self._person_view(membership, user)

    def update_person(
        self,
        membership_id: UUID,
        *,
        display_name: str | None,
        role: MembershipRole | None,
        fields_set: set[str],
    ) -> PersonView:
        view = self.get_person(membership_id)
        membership = view.membership
        old_values = {
            "display_name": membership.display_name,
            "role": membership.role.value,
        }
        if "display_name" in fields_set:
            if display_name is None:
                raise DomainError("display_name is required")
            membership.display_name = _clean_required(display_name, "display_name")
        if "role" in fields_set:
            if role not in (MembershipRole.DRIVER, MembershipRole.SUPERVISOR):
                raise DomainError("role must be DRIVER or SUPERVISOR")
            if membership.status != MembershipStatus.INVITED:
                raise ConflictError("role can only be changed before invitation acceptance")
            membership.role = role
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise ConflictError("person already has this role in the company") from exc
        self._audit(
            action="OWNER_PERSON_UPDATED",
            entity_type="COMPANY_MEMBERSHIP",
            entity_id=membership.id,
            old_values=old_values,
            new_values={
                "display_name": membership.display_name,
                "role": membership.role.value,
            },
        )
        return self.get_person(membership.id)

    def deactivate_person(self, membership_id: UUID) -> PersonView:
        view = self.get_person(membership_id)
        if view.membership.status == MembershipStatus.INACTIVE:
            return view
        if view.has_active_assignment or view.has_active_duty:
            raise ConflictError("person has an active assignment or duty session")
        if view.membership.role == MembershipRole.SUPERVISOR and view.sites:
            raise ConflictError("remove active supervisor site access before deactivation")
        old_status = view.membership.status
        view.membership.status = MembershipStatus.INACTIVE
        self.session.flush()
        self._audit(
            action="OWNER_PERSON_DEACTIVATED",
            entity_type="COMPANY_MEMBERSHIP",
            entity_id=view.membership.id,
            old_values={"status": old_status.value},
            new_values={"status": MembershipStatus.INACTIVE.value},
        )
        return self.get_person(view.membership.id)

    def reactivate_person(self, membership_id: UUID) -> PersonView:
        view = self.get_person(membership_id)
        if view.membership.status == MembershipStatus.ACTIVE:
            return view
        if view.membership.status != MembershipStatus.INACTIVE:
            raise ConflictError("invited person must accept the invitation through OTP")
        view.membership.status = MembershipStatus.ACTIVE
        self.session.flush()
        self._audit(
            action="OWNER_PERSON_REACTIVATED",
            entity_type="COMPANY_MEMBERSHIP",
            entity_id=view.membership.id,
            old_values={"status": MembershipStatus.INACTIVE.value},
            new_values={"status": MembershipStatus.ACTIVE.value},
        )
        return self.get_person(view.membership.id)

    def _site(self, site_id: UUID) -> Site:
        site = self.session.scalar(
            select(Site).where(Site.id == site_id, Site.company_id == self.company_id)
        )
        if site is None:
            raise NotFoundError("site was not found")
        return site

    def _site_view(self, site: Site) -> SiteView:
        supervisors = [
            SiteSupervisor(access.id, membership.id, membership.display_name or user.display_name)
            for access, membership, user in self.session.execute(
                select(SupervisorSiteAccess, CompanyMembership, User)
                .join(
                    CompanyMembership,
                    and_(
                        CompanyMembership.company_id == SupervisorSiteAccess.company_id,
                        CompanyMembership.id
                        == SupervisorSiteAccess.supervisor_membership_id,
                    ),
                )
                .join(User, User.id == CompanyMembership.user_id)
                .where(
                    SupervisorSiteAccess.company_id == self.company_id,
                    SupervisorSiteAccess.site_id == site.id,
                )
                .order_by(
                    func.coalesce(CompanyMembership.display_name, User.display_name),
                    CompanyMembership.id,
                )
            )
        ]
        asset_count = self.session.scalar(
            select(func.count(AssetSiteDeployment.id)).where(
                AssetSiteDeployment.company_id == self.company_id,
                AssetSiteDeployment.site_id == site.id,
                AssetSiteDeployment.ends_at.is_(None),
            )
        )
        return SiteView(site, supervisors, int(asset_count or 0))

    def list_sites(self) -> list[SiteView]:
        sites = self.session.scalars(
            select(Site)
            .where(Site.company_id == self.company_id)
            .order_by(Site.status, Site.name, Site.id)
        ).all()
        return [self._site_view(site) for site in sites]

    def get_site(self, site_id: UUID) -> SiteView:
        return self._site_view(self._site(site_id))

    def _ensure_unique_site(
        self, *, name: str, code: str | None, exclude_site_id: UUID | None = None
    ) -> None:
        collisions = [func.lower(Site.name) == name.lower()]
        if code is not None:
            collisions.append(func.lower(Site.code) == code.lower())
        duplicate = select(Site.id).where(
            Site.company_id == self.company_id,
            or_(*collisions),
        )
        if exclude_site_id is not None:
            duplicate = duplicate.where(Site.id != exclude_site_id)
        if self.session.scalar(duplicate.limit(1)) is not None:
            raise ConflictError("site name or code is already used")

    def create_site(
        self,
        *,
        name: str,
        code: str | None,
        location_description: str | None,
        latitude: Decimal | None,
        longitude: Decimal | None,
    ) -> SiteView:
        clean_name = _clean_required(name, "name")
        clean_code = _clean_optional(code)
        if clean_code:
            clean_code = clean_code.upper()
        self._ensure_unique_site(name=clean_name, code=clean_code)
        site = Site(
            company_id=self.company_id,
            name=clean_name,
            code=clean_code,
            location_description=_clean_optional(location_description),
            latitude=latitude,
            longitude=longitude,
            status=SiteStatus.ACTIVE,
        )
        self.session.add(site)
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise ConflictError("site name or code is already used") from exc
        self._audit(
            action="OWNER_SITE_CREATED",
            entity_type="SITE",
            entity_id=site.id,
            new_values=self._site_values(site),
        )
        return self._site_view(site)

    @staticmethod
    def _site_values(site: Site) -> dict[str, object]:
        return {
            "name": site.name,
            "code": site.code,
            "location_description": site.location_description,
            "latitude": str(site.latitude) if site.latitude is not None else None,
            "longitude": str(site.longitude) if site.longitude is not None else None,
            "status": site.status.value,
        }

    def update_site(
        self,
        site_id: UUID,
        *,
        name: str | None,
        code: str | None,
        location_description: str | None,
        latitude: Decimal | None,
        longitude: Decimal | None,
        fields_set: set[str],
    ) -> SiteView:
        site = self._site(site_id)
        old_values = self._site_values(site)
        if "name" in fields_set:
            if name is None:
                raise DomainError("name is required")
            site.name = _clean_required(name, "name")
        if "code" in fields_set:
            site.code = _clean_optional(code)
            if site.code:
                site.code = site.code.upper()
        if "location_description" in fields_set:
            site.location_description = _clean_optional(location_description)
        if "latitude" in fields_set:
            site.latitude = latitude
        if "longitude" in fields_set:
            site.longitude = longitude
        self._ensure_unique_site(name=site.name, code=site.code, exclude_site_id=site.id)
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise ConflictError("site name or code is already used") from exc
        self._audit(
            action="OWNER_SITE_UPDATED",
            entity_type="SITE",
            entity_id=site.id,
            old_values=old_values,
            new_values=self._site_values(site),
        )
        return self._site_view(site)

    def deactivate_site(self, site_id: UUID) -> SiteView:
        site = self._site(site_id)
        if site.status == SiteStatus.INACTIVE:
            return self._site_view(site)
        now = datetime.now(UTC)
        active_deployment = self.session.scalar(
            select(AssetSiteDeployment.id)
            .where(
                AssetSiteDeployment.company_id == self.company_id,
                AssetSiteDeployment.site_id == site.id,
                AssetSiteDeployment.ends_at.is_(None),
            )
            .limit(1)
        )
        if active_deployment is not None:
            raise ConflictError("Site cannot be deactivated while assets are deployed.")
        active_assignment = self.session.scalar(
            select(Assignment.id)
            .where(
                Assignment.company_id == self.company_id,
                Assignment.site_id == site.id,
                Assignment.starts_at <= now,
                or_(Assignment.ends_at.is_(None), Assignment.ends_at > now),
            )
            .limit(1)
        )
        active_duty = self.session.scalar(
            select(DutySession.id)
            .where(
                DutySession.company_id == self.company_id,
                DutySession.site_id == site.id,
                DutySession.status == DutySessionStatus.ACTIVE,
            )
            .limit(1)
        )
        if active_assignment is not None or active_duty is not None:
            raise ConflictError("site has an active assignment or duty session")
        site.status = SiteStatus.INACTIVE
        self.session.flush()
        self._audit(
            action="OWNER_SITE_DEACTIVATED",
            entity_type="SITE",
            entity_id=site.id,
            old_values={"status": SiteStatus.ACTIVE.value},
            new_values={"status": SiteStatus.INACTIVE.value},
        )
        return self._site_view(site)

    def reactivate_site(self, site_id: UUID) -> SiteView:
        site = self._site(site_id)
        if site.status == SiteStatus.ACTIVE:
            return self._site_view(site)
        site.status = SiteStatus.ACTIVE
        self.session.flush()
        self._audit(
            action="OWNER_SITE_REACTIVATED",
            entity_type="SITE",
            entity_id=site.id,
            old_values={"status": SiteStatus.INACTIVE.value},
            new_values={"status": SiteStatus.ACTIVE.value},
        )
        return self._site_view(site)

    def grant_supervisor(self, site_id: UUID, membership_id: UUID) -> SiteView:
        site = self._site(site_id)
        if site.status != SiteStatus.ACTIVE:
            raise ConflictError("supervisor access cannot be added to an inactive site")
        membership = self._membership(membership_id)
        if (
            membership.role != MembershipRole.SUPERVISOR
            or membership.status != MembershipStatus.ACTIVE
        ):
            raise ConflictError("site access requires an active supervisor")
        duplicate = self.session.scalar(
            select(SupervisorSiteAccess.id).where(
                SupervisorSiteAccess.company_id == self.company_id,
                SupervisorSiteAccess.site_id == site.id,
                SupervisorSiteAccess.supervisor_membership_id == membership.id,
            )
        )
        if duplicate is not None:
            raise ConflictError("supervisor already has access to this site")
        access = SupervisorSiteAccess(
            company_id=self.company_id,
            site_id=site.id,
            supervisor_membership_id=membership.id,
        )
        self.session.add(access)
        self.session.flush()
        self._audit(
            action="OWNER_SUPERVISOR_SITE_GRANTED",
            entity_type="SUPERVISOR_SITE_ACCESS",
            entity_id=access.id,
            new_values={
                "site_id": str(site.id),
                "supervisor_membership_id": str(membership.id),
            },
        )
        return self._site_view(site)

    def revoke_supervisor(self, site_id: UUID, membership_id: UUID) -> SiteView:
        site = self._site(site_id)
        access = self.session.scalar(
            select(SupervisorSiteAccess).where(
                SupervisorSiteAccess.company_id == self.company_id,
                SupervisorSiteAccess.site_id == site.id,
                SupervisorSiteAccess.supervisor_membership_id == membership_id,
            )
        )
        if access is None:
            raise NotFoundError("supervisor site access was not found")
        access_id = access.id
        self.session.delete(access)
        self.session.flush()
        self._audit(
            action="OWNER_SUPERVISOR_SITE_REVOKED",
            entity_type="SUPERVISOR_SITE_ACCESS",
            entity_id=access_id,
            old_values={
                "site_id": str(site.id),
                "supervisor_membership_id": str(membership_id),
            },
        )
        return self._site_view(site)
