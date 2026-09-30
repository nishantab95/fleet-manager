from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.models.common import UpdatedTimestampModel


class AssetSiteDeployment(UpdatedTimestampModel):
    """Effective-dated placement of a fleet asset at a site."""

    __tablename__ = "asset_site_deployments"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    site_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_asset_site_deployments_company_asset",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "site_id"],
            ["sites.company_id", "sites.id"],
            name="fk_asset_site_deployments_company_site",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id", "id", name="uq_asset_site_deployments_company_id"
        ),
        UniqueConstraint(
            "company_id",
            "id",
            "asset_id",
            "site_id",
            name="uq_asset_site_deployments_assignment_ref",
        ),
        CheckConstraint(
            "ends_at IS NULL OR ends_at > starts_at",
            name="ck_asset_site_deployments_end_after_start",
        ),
        Index(
            "uq_asset_site_deployments_current_asset",
            "company_id",
            "asset_id",
            unique=True,
            postgresql_where=text("ends_at IS NULL"),
        ),
        Index(
            "ix_asset_site_deployments_company_site_current",
            "company_id",
            "site_id",
            postgresql_where=text("ends_at IS NULL"),
        ),
    )
