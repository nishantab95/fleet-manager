"""Replace the tipper-specific core with canonical fleet assets.

Existing UUIDs and all referencing rows are preserved. Public API compatibility
is handled by the application layer; this migration changes only canonical
database names and adds future-safe asset attributes.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_fleet_assets"
down_revision: str | Sequence[str] | None = "0010_event_duty_session"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_enum(name: str, values: tuple[str, ...]) -> None:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    op.execute(
        "DO $$ BEGIN "
        f"CREATE TYPE {name} AS ENUM ({quoted_values}); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )


def _enum(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def _normalized_legacy_code(short_name: str | None, registration: str) -> str:
    source = short_name.strip() if short_name and short_name.strip() else registration
    code = re.sub(r"[^A-Z0-9]+", "-", source.upper()).strip("-")
    return (code or "ASSET")[:64]


def _backfill_asset_codes() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, company_id, short_name, registration_number "
            "FROM fleet_assets ORDER BY company_id, id"
        )
    ).mappings()
    used_by_company: dict[Any, set[str]] = {}
    for row in rows:
        used = used_by_company.setdefault(row["company_id"], set())
        base = _normalized_legacy_code(row["short_name"], row["registration_number"])
        candidate = base
        counter = 0
        while candidate in used:
            counter += 1
            suffix = f"-LEGACY-{row['id'].hex}"
            if counter > 1:
                suffix += f"-{counter}"
            candidate = f"{base[: 64 - len(suffix)]}{suffix}"
        used.add(candidate)
        connection.execute(
            sa.text("UPDATE fleet_assets SET asset_code = :asset_code WHERE id = :id"),
            {"asset_code": candidate, "id": row["id"]},
        )


def upgrade() -> None:
    _create_enum(
        "fleet_asset_type_enum",
        ("TIPPER", "EXCAVATOR", "BACKHOE_LOADER", "ROLLER", "GRADER"),
    )
    _create_enum("asset_ownership_type_enum", ("OWNED", "RENTED"))
    _create_enum("fleet_asset_status_enum", ("ACTIVE", "INACTIVE"))

    op.rename_table("tippers", "fleet_assets")
    op.execute("ALTER TABLE fleet_assets RENAME CONSTRAINT pk_tippers TO pk_fleet_assets")
    op.execute(
        "ALTER TABLE fleet_assets RENAME CONSTRAINT fk_tippers_company_id "
        "TO fk_fleet_assets_company_id"
    )
    op.execute(
        "ALTER TABLE fleet_assets RENAME CONSTRAINT uq_tippers_company_id "
        "TO uq_fleet_assets_company_id"
    )
    op.execute("ALTER INDEX ix_tippers_company_id RENAME TO ix_fleet_assets_company_id")

    op.add_column(
        "fleet_assets",
        sa.Column(
            "asset_type",
            _enum(
                "fleet_asset_type_enum",
                "TIPPER",
                "EXCAVATOR",
                "BACKHOE_LOADER",
                "ROLLER",
                "GRADER",
            ),
            nullable=False,
            server_default="TIPPER",
        ),
    )
    op.add_column(
        "fleet_assets",
        sa.Column(
            "ownership_type",
            _enum("asset_ownership_type_enum", "OWNED", "RENTED"),
            nullable=False,
            server_default="OWNED",
        ),
    )
    op.add_column("fleet_assets", sa.Column("asset_code", sa.String(length=64), nullable=True))
    op.add_column("fleet_assets", sa.Column("manufacturer", sa.String(length=100), nullable=True))
    op.add_column("fleet_assets", sa.Column("model", sa.String(length=100), nullable=True))
    op.add_column(
        "fleet_assets", sa.Column("rental_party_name", sa.String(length=200), nullable=True)
    )
    op.add_column("fleet_assets", sa.Column("rental_start_date", sa.Date(), nullable=True))
    op.add_column("fleet_assets", sa.Column("rental_end_date", sa.Date(), nullable=True))

    _backfill_asset_codes()
    op.alter_column("fleet_assets", "asset_code", nullable=False)
    op.alter_column("fleet_assets", "asset_type", server_default=None)
    op.alter_column("fleet_assets", "ownership_type", server_default=None)
    op.alter_column("fleet_assets", "registration_number", nullable=True)
    op.execute(
        "ALTER TABLE fleet_assets ALTER COLUMN status TYPE fleet_asset_status_enum "
        "USING status::text::fleet_asset_status_enum"
    )

    op.drop_constraint("uq_tippers_company_registration", "fleet_assets", type_="unique")
    op.create_unique_constraint(
        "uq_fleet_assets_company_asset_code", "fleet_assets", ["company_id", "asset_code"]
    )
    op.create_index(
        "uq_fleet_assets_company_registration",
        "fleet_assets",
        ["company_id", "registration_number"],
        unique=True,
        postgresql_where=sa.text("registration_number IS NOT NULL"),
    )
    op.create_check_constraint(
        "asset_code_non_empty", "fleet_assets", "length(btrim(asset_code)) > 0"
    )
    op.create_check_constraint(
        "short_name_length",
        "fleet_assets",
        "short_name IS NULL OR length(btrim(short_name)) BETWEEN 1 AND 100",
    )
    op.create_check_constraint(
        "rental_dates_ordered",
        "fleet_assets",
        "rental_end_date IS NULL OR rental_start_date IS NULL "
        "OR rental_end_date >= rental_start_date",
    )

    op.alter_column("assignments", "tipper_id", new_column_name="asset_id")
    op.execute(
        "ALTER TABLE assignments RENAME CONSTRAINT fk_assignments_company_tipper "
        "TO fk_assignments_company_asset"
    )
    op.execute(
        "ALTER TABLE assignments RENAME CONSTRAINT excl_assignments_tipper_time "
        "TO excl_assignments_asset_time"
    )
    op.execute("ALTER INDEX ix_assignments_tipper_id RENAME TO ix_assignments_asset_id")

    op.alter_column("duty_sessions", "tipper_id", new_column_name="asset_id")
    op.execute(
        "ALTER TABLE duty_sessions RENAME CONSTRAINT fk_duty_sessions_company_tipper "
        "TO fk_duty_sessions_company_asset"
    )
    op.execute("ALTER INDEX ix_duty_sessions_tipper_id RENAME TO ix_duty_sessions_asset_id")
    op.execute("DROP TYPE tipper_status_enum")


def downgrade() -> None:
    incompatible = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM fleet_assets "
                "WHERE asset_type <> 'TIPPER' OR ownership_type <> 'OWNED' "
                "OR registration_number IS NULL OR manufacturer IS NOT NULL OR model IS NOT NULL "
                "OR rental_party_name IS NOT NULL OR rental_start_date IS NOT NULL "
                "OR rental_end_date IS NOT NULL"
            )
        )
        .scalar_one()
    )
    if incompatible:
        raise RuntimeError(
            "cannot downgrade fleet assets while generic or rental-only asset data exists"
        )

    _create_enum("tipper_status_enum", ("ACTIVE", "INACTIVE"))
    op.execute(
        "ALTER TABLE fleet_assets ALTER COLUMN status TYPE tipper_status_enum "
        "USING status::text::tipper_status_enum"
    )
    op.drop_constraint("rental_dates_ordered", "fleet_assets", type_="check")
    op.drop_constraint("short_name_length", "fleet_assets", type_="check")
    op.drop_constraint("asset_code_non_empty", "fleet_assets", type_="check")
    op.drop_index("uq_fleet_assets_company_registration", table_name="fleet_assets")
    op.drop_constraint("uq_fleet_assets_company_asset_code", "fleet_assets", type_="unique")
    op.alter_column("fleet_assets", "registration_number", nullable=False)
    op.create_unique_constraint(
        "uq_tippers_company_registration",
        "fleet_assets",
        ["company_id", "registration_number"],
    )
    for column in (
        "rental_end_date",
        "rental_start_date",
        "rental_party_name",
        "model",
        "manufacturer",
        "asset_code",
        "ownership_type",
        "asset_type",
    ):
        op.drop_column("fleet_assets", column)

    op.execute("ALTER INDEX ix_duty_sessions_asset_id RENAME TO ix_duty_sessions_tipper_id")
    op.execute(
        "ALTER TABLE duty_sessions RENAME CONSTRAINT fk_duty_sessions_company_asset "
        "TO fk_duty_sessions_company_tipper"
    )
    op.alter_column("duty_sessions", "asset_id", new_column_name="tipper_id")

    op.execute("ALTER INDEX ix_assignments_asset_id RENAME TO ix_assignments_tipper_id")
    op.execute(
        "ALTER TABLE assignments RENAME CONSTRAINT excl_assignments_asset_time "
        "TO excl_assignments_tipper_time"
    )
    op.execute(
        "ALTER TABLE assignments RENAME CONSTRAINT fk_assignments_company_asset "
        "TO fk_assignments_company_tipper"
    )
    op.alter_column("assignments", "asset_id", new_column_name="tipper_id")

    op.execute("ALTER INDEX ix_fleet_assets_company_id RENAME TO ix_tippers_company_id")
    op.execute(
        "ALTER TABLE fleet_assets RENAME CONSTRAINT uq_fleet_assets_company_id "
        "TO uq_tippers_company_id"
    )
    op.execute(
        "ALTER TABLE fleet_assets RENAME CONSTRAINT fk_fleet_assets_company_id "
        "TO fk_tippers_company_id"
    )
    op.execute("ALTER TABLE fleet_assets RENAME CONSTRAINT pk_fleet_assets TO pk_tippers")
    op.rename_table("fleet_assets", "tippers")

    op.execute("DROP TYPE fleet_asset_status_enum")
    op.execute("DROP TYPE asset_ownership_type_enum")
    op.execute("DROP TYPE fleet_asset_type_enum")
