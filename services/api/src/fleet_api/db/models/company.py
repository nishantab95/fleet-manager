from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.models.common import UpdatedTimestampModel
from fleet_api.domain.enums import CompanyStatus, SiteStatus, UserStatus


class Company(UpdatedTimestampModel):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[CompanyStatus] = mapped_column(
        SAEnum(CompanyStatus, name="company_status_enum"), nullable=False
    )
    reporting_timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Asia/Kolkata", server_default="Asia/Kolkata"
    )
    operational_day_start_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    __table_args__ = (
        CheckConstraint(
            "operational_day_start_minutes >= 0 AND operational_day_start_minutes < 1440",
            name="ck_companies_valid_operational_day_start",
        ),
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
    location_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    status: Mapped[SiteStatus] = mapped_column(
        SAEnum(SiteStatus, name="site_status_enum"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_sites_company_name"),
        UniqueConstraint("company_id", "code", name="uq_sites_company_code"),
        UniqueConstraint("company_id", "id", name="uq_sites_company_id"),
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="ck_sites_latitude_range",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="ck_sites_longitude_range",
        ),
    )
