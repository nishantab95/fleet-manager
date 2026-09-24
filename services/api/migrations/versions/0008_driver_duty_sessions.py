"""Add backend-authoritative driver duty sessions and assignment duty snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_driver_duty_sessions"
down_revision: str | Sequence[str] | None = "0007_local_pilot_role_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _duty_status_enum() -> postgresql.ENUM:
    return postgresql.ENUM("ACTIVE", "CLOSED", name="duty_session_status_enum", create_type=False)


def upgrade() -> None:
    op.add_column(
        "assignments",
        sa.Column("regular_duty_minutes", sa.Integer(), nullable=False, server_default="600"),
    )
    op.create_check_constraint(
        "ck_assignments_regular_duty_positive",
        "assignments",
        "regular_duty_minutes > 0",
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE duty_session_status_enum AS ENUM ('ACTIVE', 'CLOSED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )
    op.create_table(
        "duty_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("driver_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tipper_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operational_date", sa.Date(), nullable=False),
        sa.Column("start_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("start_km", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("configured_regular_duty_minutes", sa.Integer(), nullable=False),
        sa.Column("regular_duty_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("end_km", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", _duty_status_enum(), nullable=False, server_default="ACTIVE"),
        sa.Column("final_overtime_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("start_km >= 0", name="ck_duty_sessions_start_km_non_negative"),
        sa.CheckConstraint(
            "end_km IS NULL OR end_km >= 0", name="ck_duty_sessions_end_km_non_negative"
        ),
        sa.CheckConstraint(
            "configured_regular_duty_minutes > 0",
            name="ck_duty_sessions_regular_duty_positive",
        ),
        sa.CheckConstraint(
            "final_overtime_minutes IS NULL OR final_overtime_minutes >= 0",
            name="ck_duty_sessions_overtime_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name="fk_duty_sessions_company_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "assignment_id"],
            ["assignments.company_id", "assignments.id"],
            name="fk_duty_sessions_company_assignment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "driver_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_duty_sessions_company_driver_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "tipper_id"],
            ["tippers.company_id", "tippers.id"],
            name="fk_duty_sessions_company_tipper",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "site_id"],
            ["sites.company_id", "sites.id"],
            name="fk_duty_sessions_company_site",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "start_event_id"],
            ["operational_events.company_id", "operational_events.id"],
            name="fk_duty_sessions_company_start_event",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "end_event_id"],
            ["operational_events.company_id", "operational_events.id"],
            name="fk_duty_sessions_company_end_event",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_duty_sessions"),
        sa.UniqueConstraint("company_id", "id", name="uq_duty_sessions_company_id"),
    )
    op.create_index("ix_duty_sessions_company_id", "duty_sessions", ["company_id"])
    op.create_index("ix_duty_sessions_assignment_id", "duty_sessions", ["assignment_id"])
    op.create_index(
        "ix_duty_sessions_driver_membership_id", "duty_sessions", ["driver_membership_id"]
    )
    op.create_index("ix_duty_sessions_tipper_id", "duty_sessions", ["tipper_id"])
    op.create_index("ix_duty_sessions_site_id", "duty_sessions", ["site_id"])
    op.create_index("ix_duty_sessions_operational_date", "duty_sessions", ["operational_date"])
    op.create_index("ix_duty_sessions_start_event_id", "duty_sessions", ["start_event_id"])
    op.create_index("ix_duty_sessions_end_event_id", "duty_sessions", ["end_event_id"])
    op.create_index(
        "ix_duty_sessions_company_driver_date",
        "duty_sessions",
        ["company_id", "driver_membership_id", "operational_date"],
    )
    op.create_index(
        "ix_duty_sessions_company_assignment_status",
        "duty_sessions",
        ["company_id", "assignment_id", "status"],
    )
    op.create_index(
        "uq_duty_sessions_active_driver",
        "duty_sessions",
        ["company_id", "driver_membership_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )


def downgrade() -> None:
    op.drop_index("uq_duty_sessions_active_driver", table_name="duty_sessions")
    op.drop_index("ix_duty_sessions_company_assignment_status", table_name="duty_sessions")
    op.drop_index("ix_duty_sessions_company_driver_date", table_name="duty_sessions")
    op.drop_index("ix_duty_sessions_end_event_id", table_name="duty_sessions")
    op.drop_index("ix_duty_sessions_start_event_id", table_name="duty_sessions")
    op.drop_index("ix_duty_sessions_operational_date", table_name="duty_sessions")
    op.drop_index("ix_duty_sessions_site_id", table_name="duty_sessions")
    op.drop_index("ix_duty_sessions_tipper_id", table_name="duty_sessions")
    op.drop_index("ix_duty_sessions_driver_membership_id", table_name="duty_sessions")
    op.drop_index("ix_duty_sessions_assignment_id", table_name="duty_sessions")
    op.drop_index("ix_duty_sessions_company_id", table_name="duty_sessions")
    op.drop_table("duty_sessions")
    op.execute("DROP TYPE IF EXISTS duty_session_status_enum")
    op.drop_constraint("ck_assignments_regular_duty_positive", "assignments", type_="check")
    op.drop_column("assignments", "regular_duty_minutes")
