"""Add machinery hour-meter events and duty readings."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_machinery_hmr"
down_revision: str | Sequence[str] | None = "0014_driver_asset_assignments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE operational_event_type_enum "
        "ADD VALUE IF NOT EXISTS 'HMR_READING'"
    )
    hour_meter_type = postgresql.ENUM(
        "START_READING",
        "END_READING",
        name="hour_meter_reading_type_enum",
        create_type=False,
    )
    hour_meter_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "hour_meter_readings",
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("operational_events.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("reading_type", hour_meter_type, nullable=False),
        sa.Column("reading_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("object_reference", sa.String(500), nullable=True),
        sa.CheckConstraint(
            "reading_value >= 0",
            name="ck_hour_meter_readings_non_negative",
        ),
    )
    op.create_index(
        "ix_hour_meter_readings_type",
        "hour_meter_readings",
        ["reading_type"],
    )

    op.alter_column(
        "duty_sessions",
        "start_km",
        existing_type=sa.Numeric(12, 2),
        nullable=True,
    )
    op.add_column(
        "duty_sessions", sa.Column("start_hmr", sa.Numeric(12, 2), nullable=True)
    )
    op.add_column(
        "duty_sessions", sa.Column("end_hmr", sa.Numeric(12, 2), nullable=True)
    )
    op.drop_constraint(
        "ck_duty_sessions_start_km_non_negative",
        "duty_sessions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_duty_sessions_start_km_non_negative",
        "duty_sessions",
        "start_km IS NULL OR start_km >= 0",
    )
    op.create_check_constraint(
        "ck_duty_sessions_start_hmr_non_negative",
        "duty_sessions",
        "start_hmr IS NULL OR start_hmr >= 0",
    )
    op.create_check_constraint(
        "ck_duty_sessions_end_hmr_non_negative",
        "duty_sessions",
        "end_hmr IS NULL OR end_hmr >= 0",
    )
    op.create_check_constraint(
        "ck_duty_sessions_one_start_meter",
        "duty_sessions",
        "(start_km IS NOT NULL AND start_hmr IS NULL) OR "
        "(start_km IS NULL AND start_hmr IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_duty_sessions_one_end_meter",
        "duty_sessions",
        "NOT (end_km IS NOT NULL AND end_hmr IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_duty_sessions_meter_type_consistent",
        "duty_sessions",
        "(start_km IS NULL OR end_hmr IS NULL) AND "
        "(start_hmr IS NULL OR end_km IS NULL)",
    )


def downgrade() -> None:
    machinery_sessions = op.get_bind().execute(
        sa.text("SELECT count(*) FROM duty_sessions WHERE start_hmr IS NOT NULL")
    ).scalar_one()
    if machinery_sessions:
        raise RuntimeError("cannot downgrade while machinery duty sessions exist")
    op.drop_constraint(
        "ck_duty_sessions_meter_type_consistent", "duty_sessions", type_="check"
    )
    op.drop_constraint(
        "ck_duty_sessions_one_end_meter", "duty_sessions", type_="check"
    )
    op.drop_constraint(
        "ck_duty_sessions_one_start_meter", "duty_sessions", type_="check"
    )
    op.drop_constraint(
        "ck_duty_sessions_end_hmr_non_negative", "duty_sessions", type_="check"
    )
    op.drop_constraint(
        "ck_duty_sessions_start_hmr_non_negative", "duty_sessions", type_="check"
    )
    op.drop_constraint(
        "ck_duty_sessions_start_km_non_negative", "duty_sessions", type_="check"
    )
    op.drop_column("duty_sessions", "end_hmr")
    op.drop_column("duty_sessions", "start_hmr")
    op.alter_column(
        "duty_sessions",
        "start_km",
        existing_type=sa.Numeric(12, 2),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_duty_sessions_start_km_non_negative",
        "duty_sessions",
        "start_km >= 0",
    )
    op.drop_index("ix_hour_meter_readings_type", table_name="hour_meter_readings")
    op.drop_table("hour_meter_readings")
    postgresql.ENUM(
        "START_READING",
        "END_READING",
        name="hour_meter_reading_type_enum",
    ).drop(op.get_bind(), checkfirst=True)
    # PostgreSQL enum values cannot be removed safely in-place. The retained
    # HMR_READING label is inert after the table/columns are removed.
