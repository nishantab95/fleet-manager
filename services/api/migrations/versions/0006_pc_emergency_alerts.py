"""Make emergency capture a one-tap, assignment-context signal."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_pc_emergency_alerts"
down_revision: str | Sequence[str] | None = "0005_phase6_reporting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "emergency_events",
        "category",
        existing_type=sa.Enum(name="emergency_category_enum"),
        nullable=True,
    )


def downgrade() -> None:
    op.execute("UPDATE emergency_events SET category = 'CONTACT_SUPERVISOR' WHERE category IS NULL")
    op.alter_column(
        "emergency_events",
        "category",
        existing_type=sa.Enum(name="emergency_category_enum"),
        nullable=False,
    )
