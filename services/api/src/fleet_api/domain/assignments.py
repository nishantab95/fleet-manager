from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fleet_api.db.models import (
    Assignment,
    Company,
    CompanyMembership,
    FleetAsset,
    Site,
    SupervisorSiteAccess,
)
from fleet_api.domain.assets import capabilities_for
from fleet_api.domain.deployments import ensure_deployment_for_assignment
from fleet_api.domain.enums import MembershipRole
from fleet_api.domain.errors import (
    AssignmentConflictError,
    DomainError,
    DuplicateAccessError,
    RoleViolationError,
    TenantConsistencyError,
)


class _CompanyOwned(Protocol):
    company_id: UUID


def _require_company(session: Session, company_id: UUID) -> None:
    if session.get(Company, company_id) is None:
        raise TenantConsistencyError("company does not exist")


def _require_membership(
    session: Session, *, company_id: UUID, membership_id: UUID, role: MembershipRole
) -> CompanyMembership:
    membership = session.get(CompanyMembership, membership_id)
    if membership is None:
        raise TenantConsistencyError("membership does not exist")
    if membership.company_id != company_id:
        raise TenantConsistencyError("membership belongs to another company")
    if membership.role != role:
        raise RoleViolationError(f"membership must have role {role}")
    return membership


def _require_owned_record[CompanyOwned: _CompanyOwned](
    session: Session,
    *,
    company_id: UUID,
    record_id: UUID,
    model: type[CompanyOwned],
) -> CompanyOwned:
    record = session.get(model, record_id)
    if record is None:
        raise TenantConsistencyError("record does not exist")
    if record.company_id != company_id:
        raise TenantConsistencyError("record belongs to another company")
    return record


def create_assignment(
    session: Session,
    *,
    company_id: UUID,
    driver_membership_id: UUID,
    supervisor_membership_id: UUID,
    asset_id: UUID,
    site_id: UUID,
    starts_at: datetime,
    ends_at: datetime | None = None,
    regular_duty_minutes: int = 600,
) -> Assignment:
    _require_company(session, company_id)
    if ends_at is not None and ends_at <= starts_at:
        raise DomainError("ends_at must be greater than starts_at")
    if regular_duty_minutes <= 0 or regular_duty_minutes > 1440:
        raise DomainError("regular_duty_minutes must be between 1 and 1440")
    _require_membership(
        session,
        company_id=company_id,
        membership_id=driver_membership_id,
        role=MembershipRole.DRIVER,
    )
    _require_membership(
        session,
        company_id=company_id,
        membership_id=supervisor_membership_id,
        role=MembershipRole.SUPERVISOR,
    )
    asset = _require_owned_record(
        session, company_id=company_id, record_id=asset_id, model=FleetAsset
    )
    if not capabilities_for(asset.asset_type).supports_duty_session:
        raise DomainError("asset type does not support the current duty workflow")
    _require_owned_record(session, company_id=company_id, record_id=site_id, model=Site)

    deployment = ensure_deployment_for_assignment(
        session,
        company_id=company_id,
        asset_id=asset_id,
        site_id=site_id,
        starts_at=starts_at,
        ends_at=ends_at,
    )

    assignment = Assignment(
        company_id=company_id,
        driver_membership_id=driver_membership_id,
        supervisor_membership_id=supervisor_membership_id,
        asset_id=asset_id,
        site_id=site_id,
        asset_site_deployment_id=deployment.id,
        starts_at=starts_at,
        ends_at=ends_at,
        regular_duty_minutes=regular_duty_minutes,
    )
    session.add(assignment)
    try:
        session.flush()
    except IntegrityError as exc:
        raise AssignmentConflictError(
            "driver or asset has an overlapping assignment; transaction must be rolled back"
        ) from exc
    return assignment


def close_assignment(
    session: Session, *, company_id: UUID, assignment_id: UUID, ends_at: datetime
) -> Assignment:
    assignment = session.get(Assignment, assignment_id)
    if assignment is None or assignment.company_id != company_id:
        raise TenantConsistencyError("assignment does not belong to this company")
    if ends_at <= assignment.starts_at:
        raise DomainError("ends_at must be greater than starts_at")
    assignment.ends_at = ends_at
    session.flush()
    return assignment


def grant_supervisor_site_access(
    session: Session,
    *,
    company_id: UUID,
    supervisor_membership_id: UUID,
    site_id: UUID,
) -> SupervisorSiteAccess:
    _require_company(session, company_id)
    _require_membership(
        session,
        company_id=company_id,
        membership_id=supervisor_membership_id,
        role=MembershipRole.SUPERVISOR,
    )
    _require_owned_record(session, company_id=company_id, record_id=site_id, model=Site)
    access = SupervisorSiteAccess(
        company_id=company_id,
        supervisor_membership_id=supervisor_membership_id,
        site_id=site_id,
    )
    session.add(access)
    try:
        session.flush()
    except IntegrityError as exc:
        raise DuplicateAccessError("supervisor already has access to this site") from exc
    return access
