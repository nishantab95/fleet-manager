from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fleet_api.db.models import Company, Site, Tipper
from fleet_api.domain.enums import SiteStatus, TipperStatus
from fleet_api.domain.errors import DomainError, TenantConsistencyError


def normalize_registration_number(value: str) -> str:
    """Normalize fleet registration values to uppercase without spaces or hyphens."""

    normalized = re.sub(r"[\s-]+", "", value).upper()
    if not normalized:
        raise DomainError("registration_number must contain a value")
    return normalized


def create_site(
    session: Session,
    *,
    company_id: UUID,
    name: str,
    code: str | None = None,
) -> Site:
    if session.get(Company, company_id) is None:
        raise TenantConsistencyError("company does not exist")
    site = Site(
        company_id=company_id,
        name=name.strip(),
        code=code.strip() if code else None,
        status=SiteStatus.ACTIVE,
    )
    session.add(site)
    session.flush()
    return site


def create_tipper(
    session: Session,
    *,
    company_id: UUID,
    registration_number: str,
    short_name: str | None = None,
) -> Tipper:
    if session.get(Company, company_id) is None:
        raise TenantConsistencyError("company does not exist")
    tipper = Tipper(
        company_id=company_id,
        registration_number=normalize_registration_number(registration_number),
        short_name=short_name.strip() if short_name else None,
        status=TipperStatus.ACTIVE,
    )
    session.add(tipper)
    try:
        session.flush()
    except IntegrityError as exc:
        raise DomainError("registration_number is already used by this company") from exc
    return tipper
