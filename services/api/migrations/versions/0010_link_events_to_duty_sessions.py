"""Link operational events to their server-authoritative duty session."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_event_duty_session"
down_revision: str | Sequence[str] | None = "0009_membership_display_names"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "operational_events",
        sa.Column("duty_session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_events_duty_session",
        "operational_events",
        "duty_sessions",
        ["duty_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_operational_events_duty_session_id",
        "operational_events",
        ["duty_session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_operational_events_duty_session_id", table_name="operational_events")
    op.drop_constraint("fk_events_duty_session", "operational_events", type_="foreignkey")
    op.drop_column("operational_events", "duty_session_id")
