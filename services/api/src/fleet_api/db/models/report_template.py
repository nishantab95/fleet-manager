from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.models.common import UpdatedTimestampModel


class ReportTemplate(UpdatedTimestampModel):
    __tablename__ = "report_templates"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    builtin_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    included_sheets: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    management_dashboard_columns: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    tipper_daily_columns: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    machinery_daily_columns: Mapped[list[str]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "company_id", "builtin_key", name="uq_report_templates_company_builtin_key"
        ),
        Index(
            "uq_report_templates_company_name_ci",
            "company_id",
            func.lower(name),
            unique=True,
        ),
        Index(
            "uq_report_templates_company_default",
            "company_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )
