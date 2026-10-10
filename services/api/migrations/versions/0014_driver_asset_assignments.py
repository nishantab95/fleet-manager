"""Evolve assignments into deployment-backed Driver-to-asset history."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_driver_asset_assignments"
down_revision: str | Sequence[str] | None = "0013_asset_site_deployments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_asset_site_deployments_assignment_ref",
        "asset_site_deployments",
        ["company_id", "id", "asset_id", "site_id"],
    )
    op.add_column(
        "assignments",
        sa.Column(
            "asset_site_deployment_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE assignments AS a SET asset_site_deployment_id = ("
        "SELECT d.id FROM asset_site_deployments AS d "
        "WHERE d.company_id = a.company_id "
        "AND d.asset_id = a.asset_id "
        "AND d.site_id = a.site_id "
        "AND d.starts_at <= a.starts_at "
        "AND (d.ends_at IS NULL OR a.ends_at IS NULL OR d.ends_at >= a.ends_at) "
        "ORDER BY (d.starts_at = a.starts_at) DESC, d.starts_at DESC, d.id "
        "LIMIT 1)"
    )
    missing_query = "SELECT count(*) FROM assignments WHERE asset_site_deployment_id IS NULL"
    if op.get_context().as_sql:
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM assignments WHERE asset_site_deployment_id IS NULL
                ) THEN
                    RAISE EXCEPTION
                        'cannot link every historical assignment to an asset deployment';
                END IF;
            END $$;
            """
        )
    else:
        missing = op.get_bind().execute(sa.text(missing_query)).scalar_one()
        if missing:
            raise RuntimeError("cannot link every historical assignment to an asset deployment")
    op.alter_column(
        "assignments", "asset_site_deployment_id", existing_type=postgresql.UUID(), nullable=False
    )
    op.create_index(
        "ix_assignments_asset_site_deployment_id",
        "assignments",
        ["asset_site_deployment_id"],
    )
    op.create_foreign_key(
        "fk_assignments_deployment_asset_site",
        "assignments",
        "asset_site_deployments",
        ["company_id", "asset_site_deployment_id", "asset_id", "site_id"],
        ["company_id", "id", "asset_id", "site_id"],
        ondelete="RESTRICT",
    )
    op.alter_column(
        "assignments",
        "supervisor_membership_id",
        existing_type=postgresql.UUID(),
        nullable=True,
    )


def downgrade() -> None:
    legacy_nulls = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM assignments WHERE supervisor_membership_id IS NULL"))
        .scalar_one()
    )
    if legacy_nulls:
        raise RuntimeError(
            "cannot downgrade while deployment-backed assignments lack a legacy supervisor"
        )
    op.alter_column(
        "assignments",
        "supervisor_membership_id",
        existing_type=postgresql.UUID(),
        nullable=False,
    )
    op.drop_constraint("fk_assignments_deployment_asset_site", "assignments", type_="foreignkey")
    op.drop_index("ix_assignments_asset_site_deployment_id", table_name="assignments")
    op.drop_column("assignments", "asset_site_deployment_id")
    op.drop_constraint(
        "uq_asset_site_deployments_assignment_ref",
        "asset_site_deployments",
        type_="unique",
    )
