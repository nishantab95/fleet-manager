"""Add Site short names and require stable internal Site codes."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_internal_ids"
down_revision: str | Sequence[str] | None = "0016_report_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sites", sa.Column("short_name", sa.String(length=200), nullable=True))
    op.execute(
        "UPDATE sites SET short_name = CASE "
        "WHEN length(btrim(name)) > 0 THEN name "
        "ELSE 'Legacy Site ' || upper(replace(id::text, '-', '')) END"
    )
    op.alter_column("sites", "short_name", nullable=False)
    op.create_unique_constraint(
        "uq_sites_company_short_name",
        "sites",
        ["company_id", "short_name"],
    )
    op.create_check_constraint(
        "ck_sites_short_name_non_empty",
        "sites",
        "length(btrim(short_name)) BETWEEN 1 AND 200",
    )

    op.execute(
        "UPDATE sites SET code = "
        "'SITE-' || upper(replace(id::text, '-', '')) "
        "WHERE code IS NULL OR length(btrim(code)) = 0"
    )
    op.alter_column("sites", "code", nullable=False)
    op.create_check_constraint(
        "ck_sites_code_non_empty",
        "sites",
        "length(btrim(code)) > 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_sites_code_non_empty", "sites", type_="check")
    op.alter_column("sites", "code", nullable=True)
    op.drop_constraint("ck_sites_short_name_non_empty", "sites", type_="check")
    op.drop_constraint("uq_sites_company_short_name", "sites", type_="unique")
    op.drop_column("sites", "short_name")
