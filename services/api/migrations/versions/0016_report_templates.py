"""Add company-scoped report templates and deterministic built-ins."""

# ruff: noqa: S608 -- dynamic SQL contains only fixed, checked-in migration values.

from __future__ import annotations

import json
from collections.abc import Sequence
from uuid import NAMESPACE_URL, UUID, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_report_templates"
down_revision: str | Sequence[str] | None = "0015_machinery_hmr"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SHEETS = [
    "management_dashboard",
    "tipper_daily",
    "machinery_daily",
    "trip_register",
    "meter_readings",
    "diesel_register",
    "duty_register",
    "exceptions",
]
MANAGEMENT_COLUMNS = [
    "asset",
    "asset_type",
    "site",
    "operator",
    "duty_status",
    "trips",
    "distance_km",
    "machine_hours",
    "verified_diesel_l",
    "pending_status",
]
TIPPER_COLUMNS = [
    "asset",
    "site",
    "registration",
    "driver",
    "start_km",
    "end_km",
    "distance_km",
    "approved_trips",
    "diesel_l",
    "status",
]
MACHINERY_COLUMNS = [
    "asset",
    "asset_type",
    "site",
    "operator",
    "start_hmr",
    "end_hmr",
    "machine_hours",
    "diesel_l",
    "status",
]


def _builtin_id(company_id: UUID, key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"fleet-manager:{company_id}:report-template:{key}")


def _insert_builtins_offline() -> None:
    definitions = (
        (
            "management_summary",
            "Management Summary",
            ["management_dashboard", "tipper_daily", "machinery_daily", "exceptions"],
            MANAGEMENT_COLUMNS,
            True,
        ),
        (
            "detailed_operations",
            "Detailed Operations",
            SHEETS,
            MANAGEMENT_COLUMNS,
            False,
        ),
        (
            "diesel_report",
            "Diesel Report",
            ["management_dashboard", "diesel_register", "exceptions"],
            [
                "asset",
                "asset_type",
                "site",
                "operator",
                "verified_diesel_l",
                "pending_status",
            ],
            False,
        ),
    )
    values = ",\n".join(
        "("
        + ", ".join(
            (
                f"'{key}'",
                f"'{name}'",
                f"'{json.dumps(sheets)}'::jsonb",
                f"'{json.dumps(management)}'::jsonb",
                "TRUE" if is_default else "FALSE",
            )
        )
        + ")"
        for key, name, sheets, management, is_default in definitions
    )
    tipper_columns = json.dumps(TIPPER_COLUMNS)
    machinery_columns = json.dumps(MACHINERY_COLUMNS)
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    statement = f"""
        WITH definitions (
            builtin_key,
            name,
            included_sheets,
            management_dashboard_columns,
            is_default
        ) AS (VALUES {values})
        INSERT INTO report_templates (
            id,
            company_id,
            name,
            builtin_key,
            is_builtin,
            is_default,
            included_sheets,
            management_dashboard_columns,
            tipper_daily_columns,
            machinery_daily_columns
        )
        SELECT
            uuid_generate_v5(
                '6ba7b811-9dad-11d1-80b4-00c04fd430c8'::uuid,
                'fleet-manager:' || companies.id::text || ':report-template:'
                    || definitions.builtin_key
            ),
            companies.id,
            definitions.name,
            definitions.builtin_key,
            TRUE,
            definitions.is_default,
            definitions.included_sheets,
            definitions.management_dashboard_columns,
            '{tipper_columns}'::jsonb,
            '{machinery_columns}'::jsonb
        FROM companies
        CROSS JOIN definitions;
        """
    op.execute(statement)


def upgrade() -> None:
    op.create_table(
        "report_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("builtin_key", sa.String(64), nullable=True),
        sa.Column("is_builtin", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("included_sheets", postgresql.JSONB(), nullable=False),
        sa.Column("management_dashboard_columns", postgresql.JSONB(), nullable=False),
        sa.Column("tipper_daily_columns", postgresql.JSONB(), nullable=False),
        sa.Column("machinery_daily_columns", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "builtin_key",
            name="uq_report_templates_company_builtin_key",
        ),
    )
    op.create_index(
        "ix_report_templates_company_id",
        "report_templates",
        ["company_id"],
    )
    op.create_index(
        "uq_report_templates_company_name_ci",
        "report_templates",
        ["company_id", sa.text("lower(name)")],
        unique=True,
    )
    op.create_index(
        "uq_report_templates_company_default",
        "report_templates",
        ["company_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    table = sa.table(
        "report_templates",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("company_id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String()),
        sa.column("builtin_key", sa.String()),
        sa.column("is_builtin", sa.Boolean()),
        sa.column("is_default", sa.Boolean()),
        sa.column("included_sheets", postgresql.JSONB()),
        sa.column("management_dashboard_columns", postgresql.JSONB()),
        sa.column("tipper_daily_columns", postgresql.JSONB()),
        sa.column("machinery_daily_columns", postgresql.JSONB()),
    )
    if op.get_context().as_sql:
        _insert_builtins_offline()
        return
    company_ids = [
        row[0] for row in op.get_bind().execute(sa.text("SELECT id FROM companies ORDER BY id"))
    ]
    for company_id in company_ids:
        definitions = (
            (
                "management_summary",
                "Management Summary",
                [
                    "management_dashboard",
                    "tipper_daily",
                    "machinery_daily",
                    "exceptions",
                ],
                MANAGEMENT_COLUMNS,
                True,
            ),
            (
                "detailed_operations",
                "Detailed Operations",
                SHEETS,
                MANAGEMENT_COLUMNS,
                False,
            ),
            (
                "diesel_report",
                "Diesel Report",
                ["management_dashboard", "diesel_register", "exceptions"],
                [
                    "asset",
                    "asset_type",
                    "site",
                    "operator",
                    "verified_diesel_l",
                    "pending_status",
                ],
                False,
            ),
        )
        for key, name, sheets, management, is_default in definitions:
            op.get_bind().execute(
                table.insert().values(
                    id=_builtin_id(company_id, key),
                    company_id=company_id,
                    name=name,
                    builtin_key=key,
                    is_builtin=True,
                    is_default=is_default,
                    included_sheets=list(sheets),
                    management_dashboard_columns=list(management),
                    tipper_daily_columns=list(TIPPER_COLUMNS),
                    machinery_daily_columns=list(MACHINERY_COLUMNS),
                )
            )


def downgrade() -> None:
    op.drop_index("uq_report_templates_company_default", table_name="report_templates")
    op.drop_index("uq_report_templates_company_name_ci", table_name="report_templates")
    op.drop_index("ix_report_templates_company_id", table_name="report_templates")
    op.drop_table("report_templates")
