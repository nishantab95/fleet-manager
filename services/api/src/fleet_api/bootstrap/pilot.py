from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from fleet_api.auth.phone import normalize_phone
from fleet_api.core.config import get_settings
from fleet_api.db.models import (
    Assignment,
    AuthSession,
    Company,
    CompanyMembership,
    Site,
    SupervisorSiteAccess,
    Tipper,
    User,
)
from fleet_api.db.models.common import utc_now
from fleet_api.db.session import SessionLocal
from fleet_api.domain.assets import (
    create_site,
    create_tipper,
    normalize_registration_number,
)
from fleet_api.domain.assignments import create_assignment, grant_supervisor_site_access
from fleet_api.domain.enums import (
    CompanyStatus,
    MembershipRole,
    MembershipStatus,
    SiteStatus,
    TipperStatus,
    UserStatus,
)

COMPANY_NAME = "Pilot Construction"
COMPANY_TIMEZONE = "Asia/Kolkata"
OWNER_PHONE = "+919876543210"
OWNER_NAME = "Pilot Owner"
SUPERVISOR_PHONE = "+919876543222"
SUPERVISOR_NAME = "Pilot Supervisor"
DRIVER_NAME = "Pilot Driver"
SITE_NAME = "Pilot Site"
SITE_CODE = "PILOT"
TIPPER_REGISTRATION = "PILOT-12"
TIPPER_SHORT_NAME = "Tipper 12"


def _single[T](session: Session, statement: Select[tuple[T]], label: str) -> T | None:
    rows = list(session.scalars(statement))
    if len(rows) > 1:
        raise RuntimeError(f"pilot bootstrap found duplicate {label} records")
    return rows[0] if rows else None


def _company(session: Session) -> Company:
    company = _single(
        session,
        select(Company).where(Company.name == COMPANY_NAME),
        "company",
    )
    if company is None:
        company = Company(
            name=COMPANY_NAME,
            status=CompanyStatus.ACTIVE,
            reporting_timezone=COMPANY_TIMEZONE,
        )
        session.add(company)
        session.flush()
    else:
        company.status = CompanyStatus.ACTIVE
        company.reporting_timezone = COMPANY_TIMEZONE
    return company


def _user(session: Session, *, phone: str, display_name: str) -> User:
    normalized_phone = normalize_phone(phone, default_region="IN")
    user = _single(
        session,
        select(User).where(User.phone_number == normalized_phone),
        f"user {normalized_phone}",
    )
    if user is None:
        user = User(
            phone_number=normalized_phone,
            display_name=display_name,
            status=UserStatus.ACTIVE,
        )
        session.add(user)
        session.flush()
    else:
        if user.display_name != display_name:
            raise RuntimeError(
                f"pilot phone {normalized_phone} belongs to {user.display_name!r}, "
                f"not {display_name!r}"
            )
        user.status = UserStatus.ACTIVE
    return user


def _membership(
    session: Session,
    *,
    company_id: UUID,
    user_id: UUID,
    role: MembershipRole,
    label: str,
) -> CompanyMembership:
    membership = _single(
        session,
        select(CompanyMembership).where(
            CompanyMembership.company_id == company_id,
            CompanyMembership.user_id == user_id,
        ),
        f"{label} membership",
    )
    if membership is None:
        membership = CompanyMembership(
            company_id=company_id,
            user_id=user_id,
            role=role,
            status=MembershipStatus.ACTIVE,
        )
        session.add(membership)
        session.flush()
    else:
        if membership.role != role:
            raise RuntimeError(f"existing {label} membership has role {membership.role.value}")
        membership.status = MembershipStatus.ACTIVE
    return membership


def _site(session: Session, *, company_id: UUID) -> Site:
    site = _single(
        session,
        select(Site).where(Site.company_id == company_id, Site.name == SITE_NAME),
        "site",
    )
    if site is None:
        site = create_site(session, company_id=company_id, name=SITE_NAME, code=SITE_CODE)
    else:
        site.code = SITE_CODE
        site.status = SiteStatus.ACTIVE
    return site


def _tipper(session: Session, *, company_id: UUID) -> Tipper:
    registration = normalize_registration_number(TIPPER_REGISTRATION)
    tipper = _single(
        session,
        select(Tipper).where(
            Tipper.company_id == company_id,
            Tipper.registration_number == registration,
        ),
        "tipper",
    )
    if tipper is None:
        tipper = create_tipper(
            session,
            company_id=company_id,
            registration_number=TIPPER_REGISTRATION,
            short_name=TIPPER_SHORT_NAME,
        )
    else:
        tipper.short_name = TIPPER_SHORT_NAME
        tipper.status = TipperStatus.ACTIVE
    return tipper


def _site_access(
    session: Session,
    *,
    company_id: UUID,
    supervisor_membership_id: UUID,
    site_id: UUID,
) -> SupervisorSiteAccess:
    access = _single(
        session,
        select(SupervisorSiteAccess).where(
            SupervisorSiteAccess.company_id == company_id,
            SupervisorSiteAccess.supervisor_membership_id == supervisor_membership_id,
            SupervisorSiteAccess.site_id == site_id,
        ),
        "supervisor site access",
    )
    if access is None:
        access = grant_supervisor_site_access(
            session,
            company_id=company_id,
            supervisor_membership_id=supervisor_membership_id,
            site_id=site_id,
        )
    return access


def _assignment(
    session: Session,
    *,
    company_id: UUID,
    driver_membership_id: UUID,
    supervisor_membership_id: UUID,
    tipper_id: UUID,
    site_id: UUID,
) -> Assignment:
    now = utc_now()
    assignment = _single(
        session,
        select(Assignment)
        .where(
            Assignment.company_id == company_id,
            Assignment.driver_membership_id == driver_membership_id,
            Assignment.supervisor_membership_id == supervisor_membership_id,
            Assignment.tipper_id == tipper_id,
            Assignment.site_id == site_id,
        )
        .order_by(Assignment.starts_at.desc()),
        "pilot assignment",
    )
    if assignment is None:
        assignment = create_assignment(
            session,
            company_id=company_id,
            driver_membership_id=driver_membership_id,
            supervisor_membership_id=supervisor_membership_id,
            tipper_id=tipper_id,
            site_id=site_id,
            starts_at=now - timedelta(hours=1),
        )
    elif assignment.starts_at > now or assignment.ends_at is not None and assignment.ends_at <= now:
        assignment.starts_at = now - timedelta(hours=1)
        assignment.ends_at = None
        session.flush()
    return assignment


def bootstrap_pilot(session: Session) -> dict[str, UUID]:
    settings = get_settings()
    if settings.environment.lower() in {"production", "prod"}:
        raise RuntimeError("pilot bootstrap is forbidden in production")
    if not settings.pilot_driver_phone:
        raise RuntimeError("FLEET_PILOT_DRIVER_PHONE must be set for the pilot bootstrap")

    company = _company(session)
    owner = _user(session, phone=OWNER_PHONE, display_name=OWNER_NAME)
    supervisor = _user(session, phone=SUPERVISOR_PHONE, display_name=SUPERVISOR_NAME)
    driver_phone = normalize_phone(settings.pilot_driver_phone, default_region="IN")
    driver = _single(
        session,
        select(User).where(User.phone_number == driver_phone),
        f"user {driver_phone}",
    )
    existing_driver = _single(
        session,
        select(User)
        .join(CompanyMembership, CompanyMembership.user_id == User.id)
        .where(
            CompanyMembership.company_id == company.id,
            User.display_name == DRIVER_NAME,
        ),
        "pilot driver",
    )
    if driver is None and existing_driver is not None:
        existing_driver.phone_number = driver_phone
        driver = existing_driver
        for auth_session in session.scalars(
            select(AuthSession).where(
                AuthSession.user_id == driver.id,
                AuthSession.revoked_at.is_(None),
            )
        ):
            auth_session.revoked_at = utc_now()
            auth_session.revocation_reason = "pilot phone corrected"
        session.flush()
    if driver is None:
        driver = _user(session, phone=driver_phone, display_name=DRIVER_NAME)
    elif driver.display_name != DRIVER_NAME:
        raise RuntimeError(
            f"pilot phone {driver_phone} belongs to {driver.display_name!r}, not {DRIVER_NAME!r}"
        )
    else:
        driver.status = UserStatus.ACTIVE
    owner_membership = _membership(
        session,
        company_id=company.id,
        user_id=owner.id,
        role=MembershipRole.OWNER_ADMIN,
        label="owner",
    )
    supervisor_membership = _membership(
        session,
        company_id=company.id,
        user_id=supervisor.id,
        role=MembershipRole.SUPERVISOR,
        label="supervisor",
    )
    driver_membership = _membership(
        session,
        company_id=company.id,
        user_id=driver.id,
        role=MembershipRole.DRIVER,
        label="driver",
    )
    site = _site(session, company_id=company.id)
    tipper = _tipper(session, company_id=company.id)
    _site_access(
        session,
        company_id=company.id,
        supervisor_membership_id=supervisor_membership.id,
        site_id=site.id,
    )
    assignment = _assignment(
        session,
        company_id=company.id,
        driver_membership_id=driver_membership.id,
        supervisor_membership_id=supervisor_membership.id,
        tipper_id=tipper.id,
        site_id=site.id,
    )
    session.flush()
    return {
        "company_id": company.id,
        "owner_user_id": owner.id,
        "owner_membership_id": owner_membership.id,
        "supervisor_user_id": supervisor.id,
        "supervisor_membership_id": supervisor_membership.id,
        "driver_user_id": driver.id,
        "driver_membership_id": driver_membership.id,
        "site_id": site.id,
        "tipper_id": tipper.id,
        "assignment_id": assignment.id,
    }


def main() -> None:
    with SessionLocal.begin() as session:
        records = bootstrap_pilot(session)
    print("PILOT_BOOTSTRAP_SUCCEEDED")
    for key, value in records.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
