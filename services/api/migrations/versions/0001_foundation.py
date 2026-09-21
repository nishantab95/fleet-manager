"""Create the initial migration boundary.

The domain tables are intentionally deferred until Phase 1. Keeping a real,
empty migration establishes the migration workflow without pretending that
the future domain schema has already been implemented.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_foundation"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

