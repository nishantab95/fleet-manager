"""Add effective-dated fleet asset to site deployments."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_asset_site_deployments"
down_revision: str | Sequence[str] | None = "0012_owner_people_sites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "asset_site_deployments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "ends_at IS NULL OR ends_at > starts_at",
            name="ck_asset_site_deployments_end_after_start",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_asset_site_deployments_company_asset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "site_id"],
            ["sites.company_id", "sites.id"],
            name="fk_asset_site_deployments_company_site",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_asset_site_deployments_company_id"
        ),
    )
    op.create_index(
        "ix_asset_site_deployments_company_id",
        "asset_site_deployments",
        ["company_id"],
    )
    op.create_index(
        "ix_asset_site_deployments_asset_id",
        "asset_site_deployments",
        ["asset_id"],
    )
    op.create_index(
        "ix_asset_site_deployments_site_id",
        "asset_site_deployments",
        ["site_id"],
    )
    op.create_index(
        "uq_asset_site_deployments_current_asset",
        "asset_site_deployments",
        ["company_id", "asset_id"],
        unique=True,
        postgresql_where=sa.text("ends_at IS NULL"),
    )
    op.create_index(
        "ix_asset_site_deployments_company_site_current",
        "asset_site_deployments",
        ["company_id", "site_id"],
        postgresql_where=sa.text("ends_at IS NULL"),
    )
    op.execute(
        "ALTER TABLE asset_site_deployments ADD CONSTRAINT "
        "excl_asset_site_deployments_asset_time EXCLUDE USING gist "
        "(company_id WITH =, asset_id WITH =, "
        "tstzrange(starts_at, COALESCE(ends_at, 'infinity'::timestamptz), '[)') WITH &&)"
    )

    # Existing assignments are authoritative migration evidence. Assignment's
    # exclusion constraint already guarantees non-overlapping asset intervals.
    op.execute(
        "INSERT INTO asset_site_deployments "
        "(id, company_id, asset_id, site_id, starts_at, ends_at, created_at, updated_at) "
        "SELECT gen_random_uuid(), a.company_id, a.asset_id, a.site_id, "
        "a.starts_at, a.ends_at, a.created_at, a.updated_at "
        "FROM assignments a "
        "WHERE NOT EXISTS ("
        "SELECT 1 FROM asset_site_deployments d "
        "WHERE d.company_id = a.company_id AND d.asset_id = a.asset_id "
        "AND d.site_id = a.site_id AND d.starts_at = a.starts_at "
        "AND d.ends_at IS NOT DISTINCT FROM a.ends_at)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE asset_site_deployments DROP CONSTRAINT IF EXISTS "
        "excl_asset_site_deployments_asset_time"
    )
    op.drop_index(
        "ix_asset_site_deployments_company_site_current",
        table_name="asset_site_deployments",
    )
    op.drop_index(
        "uq_asset_site_deployments_current_asset",
        table_name="asset_site_deployments",
    )
    op.drop_index("ix_asset_site_deployments_site_id", table_name="asset_site_deployments")
    op.drop_index("ix_asset_site_deployments_asset_id", table_name="asset_site_deployments")
    op.drop_index(
        "ix_asset_site_deployments_company_id", table_name="asset_site_deployments"
    )
    op.drop_table("asset_site_deployments")
