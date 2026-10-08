"""Add fleet asset rental contacts and technical identifiers."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_asset_contacts"
down_revision: str | Sequence[str] | None = "0017_internal_ids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fleet_assets",
        sa.Column("chassis_number", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "fleet_assets",
        sa.Column("engine_number", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "fleet_assets",
        sa.Column("rental_owner_phone_primary", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "fleet_assets",
        sa.Column("rental_owner_phone_secondary", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fleet_assets", "rental_owner_phone_secondary")
    op.drop_column("fleet_assets", "rental_owner_phone_primary")
    op.drop_column("fleet_assets", "engine_number")
    op.drop_column("fleet_assets", "chassis_number")
