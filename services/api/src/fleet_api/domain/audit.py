from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from fleet_api.db.models import AuditLog, CompanyMembership
from fleet_api.domain.errors import TenantConsistencyError


def write_audit_log(
    session: Session,
    *,
    company_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID,
    actor_membership_id: UUID | None = None,
    old_values: dict[str, object] | None = None,
    new_values: dict[str, object] | None = None,
    reason: str | None = None,
    request_id: str | None = None,
) -> AuditLog:
    if actor_membership_id is not None:
        actor = session.get(CompanyMembership, actor_membership_id)
        if actor is None or actor.company_id != company_id:
            raise TenantConsistencyError("audit actor does not belong to this company")
    audit = AuditLog(
        company_id=company_id,
        actor_membership_id=actor_membership_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values=old_values,
        new_values=new_values,
        reason=reason,
        request_id=request_id,
    )
    session.add(audit)
    session.flush()
    return audit
