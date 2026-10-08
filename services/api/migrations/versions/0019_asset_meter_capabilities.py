"""Add per-asset meter capabilities, model year, and grouped captures."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_asset_meters"
down_revision: str | Sequence[str] | None = "0018_asset_contacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("fleet_assets", sa.Column("model_year", sa.Integer(), nullable=True))
    op.add_column(
        "fleet_assets",
        sa.Column(
            "is_wheeled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "fleet_assets",
        sa.Column(
            "supports_odometer_km",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "fleet_assets",
        sa.Column(
            "supports_hour_meter",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    # Preserve the meter model that existing records were created under. New
    # assets receive the richer defaults in the domain creation service, while
    # historical Tippers remain KM-only and historical machinery remains
    # HMR-only until an Owner explicitly edits the Asset.
    op.execute(
        "UPDATE fleet_assets "
        "SET supports_odometer_km = true, supports_hour_meter = false "
        "WHERE asset_type = 'TIPPER'"
    )
    op.execute(
        "UPDATE fleet_assets SET is_wheeled = true "
        "WHERE asset_type IN ('TIPPER', 'BACKHOE_LOADER', 'ROLLER', 'GRADER')"
    )
    op.create_check_constraint(
        "ck_fleet_assets_model_year_range",
        "fleet_assets",
        "model_year IS NULL OR model_year BETWEEN 1900 AND 2200",
    )
    op.create_check_constraint(
        "ck_fleet_assets_at_least_one_meter",
        "fleet_assets",
        "supports_odometer_km OR supports_hour_meter",
    )
    op.create_check_constraint(
        "ck_fleet_assets_non_wheeled_without_odometer",
        "fleet_assets",
        "is_wheeled OR NOT supports_odometer_km",
    )

    op.add_column(
        "operational_events",
        sa.Column("capture_group_uuid", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_operational_events_capture_group_uuid",
        "operational_events",
        ["capture_group_uuid"],
    )
    op.create_index(
        "uq_events_company_capture_group_type",
        "operational_events",
        ["company_id", "capture_group_uuid", "event_type"],
        unique=True,
        postgresql_where=sa.text("capture_group_uuid IS NOT NULL"),
    )
    op.drop_constraint("ck_duty_sessions_one_start_meter", "duty_sessions", type_="check")
    op.drop_constraint("ck_duty_sessions_one_end_meter", "duty_sessions", type_="check")
    op.drop_constraint("ck_duty_sessions_meter_type_consistent", "duty_sessions", type_="check")
    op.create_check_constraint(
        "ck_duty_sessions_start_meter_present",
        "duty_sessions",
        "start_km IS NOT NULL OR start_hmr IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_duty_sessions_start_meter_present", "duty_sessions", type_="check")
    op.create_check_constraint(
        "ck_duty_sessions_meter_type_consistent",
        "duty_sessions",
        "(start_km IS NULL OR end_hmr IS NULL) AND (start_hmr IS NULL OR end_km IS NULL)",
    )
    op.create_check_constraint(
        "ck_duty_sessions_one_end_meter",
        "duty_sessions",
        "NOT (end_km IS NOT NULL AND end_hmr IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_duty_sessions_one_start_meter",
        "duty_sessions",
        "(start_km IS NOT NULL AND start_hmr IS NULL) OR "
        "(start_km IS NULL AND start_hmr IS NOT NULL)",
    )
    op.drop_index("uq_events_company_capture_group_type", table_name="operational_events")
    op.drop_index("ix_operational_events_capture_group_uuid", table_name="operational_events")
    op.drop_column("operational_events", "capture_group_uuid")
    op.drop_constraint("ck_fleet_assets_at_least_one_meter", "fleet_assets", type_="check")
    op.drop_constraint(
        "ck_fleet_assets_non_wheeled_without_odometer", "fleet_assets", type_="check"
    )
    op.drop_constraint("ck_fleet_assets_model_year_range", "fleet_assets", type_="check")
    op.drop_column("fleet_assets", "supports_hour_meter")
    op.drop_column("fleet_assets", "supports_odometer_km")
    op.drop_column("fleet_assets", "model_year")
    op.drop_column("fleet_assets", "is_wheeled")
