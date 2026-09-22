"""Add company reporting settings and site daily closure history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_phase6_reporting"
down_revision: str | Sequence[str] | None = "0004_evidence_objects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column(
            "reporting_timezone",
            sa.String(length=64),
            server_default="Asia/Kolkata",
            nullable=False,
        ),
    )
    op.add_column(
        "companies",
        sa.Column(
            "operational_day_start_minutes",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_companies_valid_operational_day_start",
        "companies",
        "operational_day_start_minutes >= 0 AND operational_day_start_minutes < 1440",
    )

    closure_status = postgresql.ENUM(
        "OPEN",
        "READY_TO_CLOSE",
        "CLOSED",
        "REOPENED",
        name="site_closure_status_enum",
    )
    closure_status.create(op.get_bind(), checkfirst=True)
    closure_status_column = postgresql.ENUM(
        "OPEN",
        "READY_TO_CLOSE",
        "CLOSED",
        "REOPENED",
        name="site_closure_status_enum",
        create_type=False,
    )

    op.create_table(
        "site_daily_closures",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operational_date", sa.Date(), nullable=False),
        sa.Column("reporting_timezone", sa.String(length=64), nullable=False),
        sa.Column("workday_start_minutes", sa.Integer(), nullable=False),
        sa.Column("status", closure_status_column, nullable=False),
        sa.Column("closed_by_membership_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopened_by_membership_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name="fk_closures_company_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "site_id"],
            ["sites.company_id", "sites.id"],
            name="fk_closures_company_site",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "closed_by_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_closures_company_closed_by",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "reopened_by_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_closures_company_reopened_by",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_site_daily_closures"),
        sa.UniqueConstraint(
            "company_id",
            "id",
            name="uq_closures_company_id_id",
        ),
        sa.UniqueConstraint(
            "company_id",
            "site_id",
            "operational_date",
            name="uq_closures_company_site_date",
        ),
    )
    op.create_index("ix_site_daily_closures_company_id", "site_daily_closures", ["company_id"])
    op.create_index("ix_site_daily_closures_site_id", "site_daily_closures", ["site_id"])
    op.create_index(
        "ix_closures_company_date", "site_daily_closures", ["company_id", "operational_date"]
    )
    op.create_index("ix_closures_site_date", "site_daily_closures", ["site_id", "operational_date"])
    op.create_index(
        "ix_site_daily_closures_closed_by_membership_id",
        "site_daily_closures",
        ["closed_by_membership_id"],
    )
    op.create_index(
        "ix_site_daily_closures_reopened_by_membership_id",
        "site_daily_closures",
        ["reopened_by_membership_id"],
    )

    op.create_table(
        "site_daily_closure_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("closure_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", closure_status_column, nullable=False),
        sa.Column("changed_by_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_closure_history_company_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "closure_id"],
            ["site_daily_closures.company_id", "site_daily_closures.id"],
            name="fk_closure_history_company_closure",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "changed_by_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_closure_history_company_actor",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_site_daily_closure_history"),
    )
    op.create_index(
        "ix_site_daily_closure_history_company_id",
        "site_daily_closure_history",
        ["company_id"],
    )
    op.create_index(
        "ix_site_daily_closure_history_closure_id",
        "site_daily_closure_history",
        ["closure_id"],
    )
    op.create_index(
        "ix_site_daily_closure_history_changed_by_membership_id",
        "site_daily_closure_history",
        ["changed_by_membership_id"],
    )
    op.create_index(
        "ix_closure_history_closure_time",
        "site_daily_closure_history",
        ["closure_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_closure_history_closure_time", table_name="site_daily_closure_history")
    op.drop_index(
        "ix_site_daily_closure_history_changed_by_membership_id",
        table_name="site_daily_closure_history",
    )
    op.drop_index(
        "ix_site_daily_closure_history_closure_id", table_name="site_daily_closure_history"
    )
    op.drop_index(
        "ix_site_daily_closure_history_company_id", table_name="site_daily_closure_history"
    )
    op.drop_table("site_daily_closure_history")

    op.drop_index(
        "ix_site_daily_closures_reopened_by_membership_id", table_name="site_daily_closures"
    )
    op.drop_index(
        "ix_site_daily_closures_closed_by_membership_id", table_name="site_daily_closures"
    )
    op.drop_index("ix_closures_site_date", table_name="site_daily_closures")
    op.drop_index("ix_closures_company_date", table_name="site_daily_closures")
    op.drop_index("ix_site_daily_closures_site_id", table_name="site_daily_closures")
    op.drop_index("ix_site_daily_closures_company_id", table_name="site_daily_closures")
    op.drop_table("site_daily_closures")
    sa.Enum(name="site_closure_status_enum").drop(op.get_bind(), checkfirst=True)

    op.drop_constraint("ck_companies_valid_operational_day_start", "companies", type_="check")
    op.drop_column("companies", "operational_day_start_minutes")
    op.drop_column("companies", "reporting_timezone")
