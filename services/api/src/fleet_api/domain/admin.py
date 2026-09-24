from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from fleet_api.auth.phone import normalize_phone
from fleet_api.auth.service import AuthContext
from fleet_api.db.models import (
    Assignment,
    Company,
    CompanyMembership,
    Site,
    SupervisorSiteAccess,
    Tipper,
    User,
)
from fleet_api.domain.assets import create_site, create_tipper, normalize_registration_number
from fleet_api.domain.assignments import (
    close_assignment,
    create_assignment,
    grant_supervisor_site_access,
)
from fleet_api.domain.audit import write_audit_log
from fleet_api.domain.enums import (
    MembershipRole,
    MembershipStatus,
    SiteStatus,
    TipperStatus,
    UserStatus,
)
from fleet_api.domain.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    RoleViolationError,
)


class AdminService:
    """Tenant-scoped owner/admin operations over the existing domain services."""

    def __init__(
        self,
        session: Session,
        context: AuthContext,
        *,
        request_id: str | None = None,
        phone_default_region: str | None = None,
    ) -> None:
        self.session = session
        self.context = context
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
        reason: str | None = None,
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
            reason=reason,
            request_id=self.request_id,
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

    def _membership(self, membership_id: UUID) -> CompanyMembership:
        membership = self.session.scalar(
            select(CompanyMembership).where(
                CompanyMembership.id == membership_id,
                CompanyMembership.company_id == self.company_id,
            )
        )
        if membership is None:
            raise NotFoundError("membership was not found")
        return membership

    def get_company_settings(self) -> Company:
        return self.context.company

    def update_company_settings(
        self,
        *,
        reporting_timezone: str | None,
        operational_day_start_minutes: int | None,
    ) -> Company:
        company = self.context.company
        old_values = {
            "reporting_timezone": company.reporting_timezone,
            "operational_day_start_minutes": company.operational_day_start_minutes,
        }
        if reporting_timezone is not None:
            clean_timezone = reporting_timezone.strip()
            try:
                ZoneInfo(clean_timezone)
            except ZoneInfoNotFoundError as exc:
                raise DomainError("reporting timezone is invalid") from exc
            company.reporting_timezone = clean_timezone
        if operational_day_start_minutes is not None:
            company.operational_day_start_minutes = operational_day_start_minutes
        self.session.flush()
        self._audit(
            action="ADMIN_COMPANY_SETTINGS_UPDATED",
            entity_type="COMPANY",
            entity_id=company.id,
            old_values=old_values,
            new_values={
                "reporting_timezone": company.reporting_timezone,
                "operational_day_start_minutes": company.operational_day_start_minutes,
            },
        )
        return company

    def list_sites(self) -> list[Site]:
        return list(
            self.session.scalars(
                select(Site)
                .where(Site.company_id == self.company_id)
                .order_by(Site.status, Site.name, Site.id)
            ).all()
        )

    def get_site(self, site_id: UUID) -> Site:
        return self._site(site_id)

    def create_site(self, *, name: str, code: str | None) -> Site:
        try:
            site = create_site(
                self.session,
                company_id=self.company_id,
                name=name,
                code=code,
            )
        except IntegrityError as exc:
            raise ConflictError("site name or code is already used") from exc
        self._audit(
            action="ADMIN_SITE_CREATED",
            entity_type="SITE",
            entity_id=site.id,
            new_values={"name": site.name, "code": site.code, "status": site.status.value},
        )
        return site

    def update_site(
        self,
        site_id: UUID,
        *,
        name: str | None,
        code: str | None,
        status: SiteStatus | None,
        code_was_sent: bool,
    ) -> Site:
        site = self._site(site_id)
        old_values = {"name": site.name, "code": site.code, "status": site.status.value}
        if name is not None:
            if not name.strip():
                raise DomainError("site name must contain a value")
            site.name = name.strip()
        if code_was_sent:
            site.code = code.strip() if code else None
        if status is not None:
            site.status = status
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise ConflictError("site name or code is already used") from exc
        self._audit(
            action="ADMIN_SITE_UPDATED",
            entity_type="SITE",
            entity_id=site.id,
            old_values=old_values,
            new_values={"name": site.name, "code": site.code, "status": site.status.value},
        )
        return site

    def list_tippers(self) -> list[Tipper]:
        return list(
            self.session.scalars(
                select(Tipper)
                .where(Tipper.company_id == self.company_id)
                .order_by(Tipper.status, Tipper.registration_number, Tipper.id)
            ).all()
        )

    def get_tipper(self, tipper_id: UUID) -> Tipper:
        return self._tipper(tipper_id)

    def create_tipper(self, *, registration_number: str, short_name: str | None) -> Tipper:
        try:
            tipper = create_tipper(
                self.session,
                company_id=self.company_id,
                registration_number=registration_number,
                short_name=short_name,
            )
        except (DomainError, IntegrityError) as exc:
            raise ConflictError("registration number is already used or invalid") from exc
        self._audit(
            action="ADMIN_TIPPER_CREATED",
            entity_type="TIPPER",
            entity_id=tipper.id,
            new_values={
                "registration_number": tipper.registration_number,
                "short_name": tipper.short_name,
                "status": tipper.status.value,
            },
        )
        return tipper

    def update_tipper(
        self,
        tipper_id: UUID,
        *,
        registration_number: str | None,
        short_name: str | None,
        status: TipperStatus | None,
        registration_was_sent: bool,
        short_name_was_sent: bool,
    ) -> Tipper:
        tipper = self._tipper(tipper_id)
        old_values = {
            "registration_number": tipper.registration_number,
            "short_name": tipper.short_name,
            "status": tipper.status.value,
        }
        if registration_was_sent:
            tipper.registration_number = normalize_registration_number(registration_number or "")
        if short_name_was_sent:
            tipper.short_name = (short_name or "").strip() or None
        if status is not None:
            tipper.status = status
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise ConflictError("registration number is already used") from exc
        self._audit(
            action="ADMIN_TIPPER_UPDATED",
            entity_type="TIPPER",
            entity_id=tipper.id,
            old_values=old_values,
            new_values={
                "registration_number": tipper.registration_number,
                "short_name": tipper.short_name,
                "status": tipper.status.value,
            },
        )
        return tipper

    def list_people(self) -> list[tuple[CompanyMembership, User]]:
        return [
            row._tuple()
            for row in self.session.execute(
                select(CompanyMembership, User)
                .join(User, User.id == CompanyMembership.user_id)
                .where(CompanyMembership.company_id == self.company_id)
                .order_by(User.display_name, CompanyMembership.id)
            ).all()
        ]

    def create_person(
        self,
        *,
        phone: str,
        display_name: str,
        role: MembershipRole,
    ) -> tuple[CompanyMembership, User]:
        if role == MembershipRole.OWNER_ADMIN:
            raise RoleViolationError("owner/admin membership creation is not available here")
        normalized_phone = normalize_phone(phone, default_region=self.phone_default_region)
        clean_name = display_name.strip()
        if not clean_name:
            raise DomainError("display_name must contain a value")
        user = self.session.scalar(select(User).where(User.phone_number == normalized_phone))
        if user is None:
            user = User(
                phone_number=normalized_phone,
                display_name=clean_name,
                status=UserStatus.ACTIVE,
            )
            self.session.add(user)
            self.session.flush()
        else:
            existing = self.session.scalar(
                select(CompanyMembership).where(
                    CompanyMembership.company_id == self.company_id,
                    CompanyMembership.user_id == user.id,
                )
            )
            if existing is not None:
                raise ConflictError("user already has a membership in this company")
            user.status = UserStatus.ACTIVE
            user.display_name = clean_name
        membership = CompanyMembership(
            company_id=self.company_id,
            user_id=user.id,
            role=role,
            status=MembershipStatus.ACTIVE,
        )
        self.session.add(membership)
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise ConflictError("membership already exists") from exc
        self._audit(
            action="ADMIN_MEMBERSHIP_CREATED",
            entity_type="COMPANY_MEMBERSHIP",
            entity_id=membership.id,
            new_values={
                "user_id": str(user.id),
                "role": role.value,
                "status": membership.status.value,
            },
        )
        return membership, user

    def update_person(
        self,
        membership_id: UUID,
        *,
        role: MembershipRole | None,
        status: MembershipStatus | None,
    ) -> tuple[CompanyMembership, User]:
        membership = self._membership(membership_id)
        if role == MembershipRole.OWNER_ADMIN:
            raise RoleViolationError("owner/admin membership changes are not available here")
        user = self.session.get(User, membership.user_id)
        if user is None:
            raise NotFoundError("membership user was not found")
        old_values = {"role": membership.role.value, "status": membership.status.value}
        if role is not None:
            membership.role = role
        if status is not None:
            membership.status = status
        self.session.flush()
        self._audit(
            action="ADMIN_MEMBERSHIP_UPDATED",
            entity_type="COMPANY_MEMBERSHIP",
            entity_id=membership.id,
            old_values=old_values,
            new_values={"role": membership.role.value, "status": membership.status.value},
        )
        return membership, user

    def list_supervisor_access(self) -> list[tuple[SupervisorSiteAccess, str, str]]:
        return [
            row._tuple()
            for row in self.session.execute(
                select(SupervisorSiteAccess, User.display_name, Site.name)
                .join(
                    CompanyMembership,
                    CompanyMembership.id == SupervisorSiteAccess.supervisor_membership_id,
                )
                .join(User, User.id == CompanyMembership.user_id)
                .join(Site, Site.id == SupervisorSiteAccess.site_id)
                .where(SupervisorSiteAccess.company_id == self.company_id)
                .order_by(User.display_name, Site.name, SupervisorSiteAccess.id)
            ).all()
        ]

    def grant_supervisor_access(
        self, *, supervisor_membership_id: UUID, site_id: UUID
    ) -> SupervisorSiteAccess:
        try:
            access = grant_supervisor_site_access(
                self.session,
                company_id=self.company_id,
                supervisor_membership_id=supervisor_membership_id,
                site_id=site_id,
            )
        except IntegrityError as exc:
            raise ConflictError("supervisor already has access to this site") from exc
        self._audit(
            action="ADMIN_SUPERVISOR_SITE_GRANTED",
            entity_type="SUPERVISOR_SITE_ACCESS",
            entity_id=access.id,
            new_values={
                "supervisor_membership_id": str(supervisor_membership_id),
                "site_id": str(site_id),
            },
        )
        return access

    def revoke_supervisor_access(self, access_id: UUID) -> None:
        access = self.session.scalar(
            select(SupervisorSiteAccess).where(
                SupervisorSiteAccess.id == access_id,
                SupervisorSiteAccess.company_id == self.company_id,
            )
        )
        if access is None:
            raise NotFoundError("supervisor site access was not found")
        old_values = {
            "supervisor_membership_id": str(access.supervisor_membership_id),
            "site_id": str(access.site_id),
        }
        self.session.delete(access)
        self.session.flush()
        self._audit(
            action="ADMIN_SUPERVISOR_SITE_REVOKED",
            entity_type="SUPERVISOR_SITE_ACCESS",
            entity_id=access_id,
            old_values=old_values,
        )

    def list_assignments(
        self,
    ) -> list[tuple[Assignment, str, str, str, str]]:
        driver_membership = aliased(CompanyMembership)
        supervisor_membership = aliased(CompanyMembership)
        driver_user = aliased(User)
        supervisor_user = aliased(User)
        return [
            row._tuple()
            for row in self.session.execute(
                select(
                    Assignment,
                    Tipper.registration_number,
                    Site.name,
                    driver_user.display_name,
                    supervisor_user.display_name,
                )
                .join(Tipper, Tipper.id == Assignment.tipper_id)
                .join(Site, Site.id == Assignment.site_id)
                .join(
                    driver_membership,
                    driver_membership.id == Assignment.driver_membership_id,
                )
                .join(driver_user, driver_user.id == driver_membership.user_id)
                .join(
                    supervisor_membership,
                    supervisor_membership.id == Assignment.supervisor_membership_id,
                )
                .join(supervisor_user, supervisor_user.id == supervisor_membership.user_id)
                .where(Assignment.company_id == self.company_id)
                .order_by(Assignment.starts_at.desc(), Assignment.id)
            ).all()
        ]

    def create_admin_assignment(
        self,
        *,
        driver_membership_id: UUID,
        supervisor_membership_id: UUID,
        tipper_id: UUID,
        site_id: UUID,
        starts_at: datetime,
        ends_at: datetime | None,
        regular_duty_minutes: int = 600,
    ) -> Assignment:
        driver = self._membership(driver_membership_id)
        supervisor = self._membership(supervisor_membership_id)
        tipper = self._tipper(tipper_id)
        site = self._site(site_id)
        if driver.status != MembershipStatus.ACTIVE or supervisor.status != MembershipStatus.ACTIVE:
            raise DomainError("driver and supervisor memberships must be active")
        if tipper.status != TipperStatus.ACTIVE or site.status != SiteStatus.ACTIVE:
            raise DomainError("tipper and site must be active")
        assignment = create_assignment(
            self.session,
            company_id=self.company_id,
            driver_membership_id=driver_membership_id,
            supervisor_membership_id=supervisor_membership_id,
            tipper_id=tipper_id,
            site_id=site_id,
            starts_at=starts_at,
            ends_at=ends_at,
            regular_duty_minutes=regular_duty_minutes,
        )
        self._audit(
            action="ADMIN_ASSIGNMENT_CREATED",
            entity_type="ASSIGNMENT",
            entity_id=assignment.id,
            new_values={
                "driver_membership_id": str(driver_membership_id),
                "supervisor_membership_id": str(supervisor_membership_id),
                "tipper_id": str(tipper_id),
                "site_id": str(site_id),
                "starts_at": starts_at.isoformat(),
                "ends_at": ends_at.isoformat() if ends_at else None,
                "regular_duty_minutes": regular_duty_minutes,
            },
        )
        return assignment

    def get_assignment(self, assignment_id: UUID) -> tuple[Assignment, str, str, str, str]:
        for row in self.list_assignments():
            if row[0].id == assignment_id:
                return row
        raise NotFoundError("assignment was not found")

    def close_admin_assignment(self, assignment_id: UUID, *, ends_at: datetime) -> Assignment:
        assignment = close_assignment(
            self.session,
            company_id=self.company_id,
            assignment_id=assignment_id,
            ends_at=ends_at,
        )
        self._audit(
            action="ADMIN_ASSIGNMENT_CLOSED",
            entity_type="ASSIGNMENT",
            entity_id=assignment.id,
            new_values={"ends_at": ends_at.isoformat()},
        )
        return assignment
