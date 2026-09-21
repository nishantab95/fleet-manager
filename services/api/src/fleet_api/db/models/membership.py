from __future__ import annotations

from uuid import UUID

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.models.common import UpdatedTimestampModel
from fleet_api.domain.enums import MembershipRole, MembershipStatus


class CompanyMembership(UpdatedTimestampModel):
    __tablename__ = "company_memberships"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    role: Mapped[MembershipRole] = mapped_column(
        SAEnum(MembershipRole, name="membership_role_enum"), nullable=False
    )
    status: Mapped[MembershipStatus] = mapped_column(
        SAEnum(MembershipStatus, name="membership_status_enum"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("company_id", "user_id", name="uq_memberships_company_user"),
        UniqueConstraint("company_id", "id", name="uq_memberships_company_id"),
    )


class SupervisorSiteAccess(UpdatedTimestampModel):
    __tablename__ = "supervisor_site_access"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supervisor_membership_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    site_id: Mapped[UUID] = mapped_column(nullable=False, index=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "supervisor_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_access_company_supervisor_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "site_id"],
            ["sites.company_id", "sites.id"],
            name="fk_access_company_site",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "company_id",
            "supervisor_membership_id",
            "site_id",
            name="uq_access_company_supervisor_site",
        ),
    )
