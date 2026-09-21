from __future__ import annotations

from uuid import UUID

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.models.common import UpdatedTimestampModel
from fleet_api.domain.enums import CompanyStatus, SiteStatus, TipperStatus, UserStatus


class Company(UpdatedTimestampModel):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[CompanyStatus] = mapped_column(
        SAEnum(CompanyStatus, name="company_status_enum"), nullable=False
    )


class User(UpdatedTimestampModel):
    __tablename__ = "users"

    phone_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="user_status_enum"), nullable=False
    )


class Site(UpdatedTimestampModel):
    __tablename__ = "sites"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[SiteStatus] = mapped_column(
        SAEnum(SiteStatus, name="site_status_enum"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_sites_company_name"),
        UniqueConstraint("company_id", "code", name="uq_sites_company_code"),
        UniqueConstraint("company_id", "id", name="uq_sites_company_id"),
    )


class Tipper(UpdatedTimestampModel):
    __tablename__ = "tippers"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    registration_number: Mapped[str] = mapped_column(String(32), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[TipperStatus] = mapped_column(
        SAEnum(TipperStatus, name="tipper_status_enum"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "company_id", "registration_number", name="uq_tippers_company_registration"
        ),
        UniqueConstraint("company_id", "id", name="uq_tippers_company_id"),
    )
