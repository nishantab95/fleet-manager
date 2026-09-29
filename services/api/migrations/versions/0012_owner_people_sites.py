"""Add invited memberships and optional site location metadata."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_owner_people_sites"
down_revision: str | Sequence[str] | None = "0011_fleet_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE membership_status_enum ADD VALUE IF NOT EXISTS 'INVITED'")
    op.add_column(
        "sites", sa.Column("location_description", sa.String(length=500), nullable=True)
    )
    op.add_column("sites", sa.Column("latitude", sa.Numeric(9, 6), nullable=True))
    op.add_column("sites", sa.Column("longitude", sa.Numeric(9, 6), nullable=True))
    op.create_check_constraint(
        "ck_sites_latitude_range",
        "sites",
        "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
    )
    op.create_check_constraint(
        "ck_sites_longitude_range",
        "sites",
        "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
    )


def downgrade() -> None:
    invited_count = op.get_bind().execute(
        sa.text("SELECT count(*) FROM company_memberships WHERE status = 'INVITED'")
    ).scalar_one()
    if invited_count:
        raise RuntimeError("cannot downgrade while invited memberships exist")
    op.drop_constraint("ck_sites_longitude_range", "sites", type_="check")
    op.drop_constraint("ck_sites_latitude_range", "sites", type_="check")
    op.drop_column("sites", "longitude")
    op.drop_column("sites", "latitude")
    op.drop_column("sites", "location_description")
    op.execute("ALTER TABLE company_memberships ALTER COLUMN status TYPE text USING status::text")
    op.execute("DROP TYPE membership_status_enum")
    op.execute("CREATE TYPE membership_status_enum AS ENUM ('ACTIVE', 'INACTIVE')")
    op.execute(
        "ALTER TABLE company_memberships ALTER COLUMN status "
        "TYPE membership_status_enum USING status::membership_status_enum"
    )
