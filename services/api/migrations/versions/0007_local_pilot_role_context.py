"""Support one local pilot identity with role-bound OTP challenges."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_local_pilot_role_context"
down_revision: str | Sequence[str] | None = "0006_pc_emergency_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _membership_role_enum() -> postgresql.ENUM:
    return postgresql.ENUM(
        "OWNER_ADMIN", "SUPERVISOR", "DRIVER", name="membership_role_enum", create_type=False
    )


def upgrade() -> None:
    op.add_column(
        "otp_challenges",
        sa.Column("requested_role", _membership_role_enum(), nullable=True),
    )
    op.drop_constraint("uq_memberships_company_user", "company_memberships", type_="unique")
    op.create_unique_constraint(
        "uq_memberships_company_user_role",
        "company_memberships",
        ["company_id", "user_id", "role"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_memberships_company_user_role", "company_memberships", type_="unique")
    op.create_unique_constraint(
        "uq_memberships_company_user", "company_memberships", ["company_id", "user_id"]
    )
    op.drop_column("otp_challenges", "requested_role")
