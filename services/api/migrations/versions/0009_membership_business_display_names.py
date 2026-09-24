"""Keep role-specific business display names separate from shared auth users."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_membership_display_names"
down_revision: str | Sequence[str] | None = "0008_driver_duty_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "company_memberships",
        sa.Column("display_name", sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("company_memberships", "display_name")
