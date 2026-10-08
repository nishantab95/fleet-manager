"""Add explicit starter-template catalog metadata."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_maintenance_starter_catalog"
down_revision: str | Sequence[str] | None = "0021_maintenance_responsibility"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_enum(name: str, values: tuple[str, ...]) -> None:
    quoted = ", ".join(f"'{value}'" for value in values)
    op.execute(
        "DO $$ BEGIN "
        f"CREATE TYPE {name} AS ENUM ({quoted}); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )


def _enum(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    _create_enum("maintenance_template_type_enum", ("COMPANY_STARTER", "OEM_VERIFIED"))
    _create_enum("maintenance_template_confidence_enum", ("SUGGESTED", "VERIFIED"))
    _create_enum(
        "maintenance_template_category_enum",
        (
            "HEAVY_TIPPER_10_WHEEL",
            "TRACKED_EXCAVATOR",
            "BACKHOE_LOADER",
            "ROAD_ROLLER_COMPACTOR",
            "WHEEL_LOADER",
            "MOTOR_GRADER",
            "CUSTOM",
        ),
    )
    _create_enum("maintenance_template_applicability_enum", ("WHEELED", "NON_WHEELED"))

    op.add_column(
        "maintenance_templates",
        sa.Column(
            "template_type",
            _enum("maintenance_template_type_enum", "COMPANY_STARTER", "OEM_VERIFIED"),
            server_default=sa.text("'COMPANY_STARTER'"),
            nullable=False,
        ),
    )
    op.add_column(
        "maintenance_templates",
        sa.Column(
            "confidence",
            _enum("maintenance_template_confidence_enum", "SUGGESTED", "VERIFIED"),
            server_default=sa.text("'SUGGESTED'"),
            nullable=False,
        ),
    )
    op.add_column(
        "maintenance_templates",
        sa.Column(
            "category",
            _enum(
                "maintenance_template_category_enum",
                "HEAVY_TIPPER_10_WHEEL",
                "TRACKED_EXCAVATOR",
                "BACKHOE_LOADER",
                "ROAD_ROLLER_COMPACTOR",
                "WHEEL_LOADER",
                "MOTOR_GRADER",
                "CUSTOM",
            ),
            server_default=sa.text("'CUSTOM'"),
            nullable=False,
        ),
    )
    op.add_column(
        "maintenance_templates",
        sa.Column(
            "applicability",
            _enum("maintenance_template_applicability_enum", "WHEELED", "NON_WHEELED"),
            server_default=sa.text("'WHEELED'"),
            nullable=False,
        ),
    )
    op.add_column(
        "maintenance_templates",
        sa.Column(
            "source_name",
            sa.String(200),
            server_default=sa.text("'Company maintenance policy'"),
            nullable=False,
        ),
    )
    op.add_column("maintenance_templates", sa.Column("notes", sa.Text(), nullable=True))

    op.execute(
        "UPDATE maintenance_templates SET "
        "template_type = 'OEM_VERIFIED', confidence = 'VERIFIED', "
        "source_name = 'Verified manufacturer source' "
        "WHERE source_type = 'OEM' AND verification_status = 'VERIFIED' "
        "AND source_reference IS NOT NULL AND manufacturer IS NOT NULL AND model IS NOT NULL"
    )
    op.execute(
        "UPDATE maintenance_templates SET category = CASE asset_type::text "
        "WHEN 'TIPPER' THEN 'HEAVY_TIPPER_10_WHEEL'::maintenance_template_category_enum "
        "WHEN 'EXCAVATOR' THEN 'TRACKED_EXCAVATOR'::maintenance_template_category_enum "
        "WHEN 'BACKHOE_LOADER' THEN 'BACKHOE_LOADER'::maintenance_template_category_enum "
        "WHEN 'ROLLER' THEN 'ROAD_ROLLER_COMPACTOR'::maintenance_template_category_enum "
        "WHEN 'GRADER' THEN 'MOTOR_GRADER'::maintenance_template_category_enum "
        "ELSE 'CUSTOM'::maintenance_template_category_enum END"
    )
    op.execute(
        "UPDATE maintenance_templates SET applicability = CASE "
        "WHEN asset_type::text = 'EXCAVATOR' "
        "THEN 'NON_WHEELED'::maintenance_template_applicability_enum "
        "ELSE 'WHEELED'::maintenance_template_applicability_enum END"
    )

    op.create_check_constraint(
        "ck_maintenance_templates_source_name_required",
        "maintenance_templates",
        "length(btrim(source_name)) > 0",
    )
    op.create_check_constraint(
        "ck_maintenance_templates_verified_oem_metadata_required",
        "maintenance_templates",
        "template_type <> 'OEM_VERIFIED' OR "
        "(confidence = 'VERIFIED' AND source_type = 'OEM' "
        "AND verification_status = 'VERIFIED' AND source_reference IS NOT NULL "
        "AND manufacturer IS NOT NULL AND model IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_maintenance_templates_verified_oem_metadata_required",
        "maintenance_templates",
        type_="check",
    )
    op.drop_constraint(
        "ck_maintenance_templates_source_name_required",
        "maintenance_templates",
        type_="check",
    )
    for column in (
        "notes",
        "source_name",
        "applicability",
        "category",
        "confidence",
        "template_type",
    ):
        op.drop_column("maintenance_templates", column)
    for enum_name in (
        "maintenance_template_applicability_enum",
        "maintenance_template_category_enum",
        "maintenance_template_confidence_enum",
        "maintenance_template_type_enum",
    ):
        op.execute(f"DROP TYPE {enum_name}")
