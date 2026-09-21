"""Create the Phase 1 core fleet domain schema.

The assignment exclusion constraints are deliberately expressed as PostgreSQL
DDL: they are the concurrency-safe part of the effective-dated assignment
invariant and must not be reduced to an application-only check.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_core_domain"
down_revision: str | Sequence[str] | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def _create_enum(name: str, values: tuple[str, ...]) -> None:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    op.execute(
        "DO $$ BEGIN "
        f"CREATE TYPE {name} AS ENUM ({quoted_values}); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    _create_enum("company_status_enum", ("ACTIVE", "INACTIVE"))
    _create_enum("user_status_enum", ("ACTIVE", "INACTIVE"))
    _create_enum("membership_role_enum", ("OWNER_ADMIN", "SUPERVISOR", "DRIVER"))
    _create_enum("membership_status_enum", ("ACTIVE", "INACTIVE"))
    _create_enum("site_status_enum", ("ACTIVE", "INACTIVE"))
    _create_enum("tipper_status_enum", ("ACTIVE", "INACTIVE"))
    _create_enum("device_platform_enum", ("ANDROID", "IOS", "WEB", "OTHER"))
    _create_enum("device_status_enum", ("ACTIVE", "REVOKED"))
    _create_enum(
        "operational_event_type_enum", ("TRIP_COMPLETE", "KM_READING", "DIESEL", "EMERGENCY")
    )
    _create_enum(
        "verification_status_enum",
        ("PENDING_VERIFICATION", "APPROVED", "REJECTED", "DISPUTED", "AMENDED"),
    )
    _create_enum("km_reading_type_enum", ("START_READING", "END_READING"))
    _create_enum(
        "emergency_category_enum",
        ("BREAKDOWN", "ACCIDENT", "TYRE_OR_VEHICLE_PROBLEM", "CONTACT_SUPERVISOR"),
    )
    _create_enum("emergency_status_enum", ("OPEN", "ACKNOWLEDGED", "RESOLVED", "CLOSED"))

    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", _enum("company_status_enum", "ACTIVE", "INACTIVE"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_companies"),
    )
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phone_number", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("status", _enum("user_status_enum", "ACTIVE", "INACTIVE"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("phone_number", name="uq_users_phone_number"),
    )
    op.create_table(
        "company_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            _enum("membership_role_enum", "OWNER_ADMIN", "SUPERVISOR", "DRIVER"),
            nullable=False,
        ),
        sa.Column("status", _enum("membership_status_enum", "ACTIVE", "INACTIVE"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name="fk_memberships_company_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_memberships_user_id", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_company_memberships"),
        sa.UniqueConstraint("company_id", "user_id", name="uq_memberships_company_user"),
        sa.UniqueConstraint("company_id", "id", name="uq_memberships_company_id"),
    )
    op.create_index("ix_company_memberships_company_id", "company_memberships", ["company_id"])
    op.create_index("ix_company_memberships_user_id", "company_memberships", ["user_id"])
    op.create_table(
        "sites",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("status", _enum("site_status_enum", "ACTIVE", "INACTIVE"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name="fk_sites_company_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sites"),
        sa.UniqueConstraint("company_id", "name", name="uq_sites_company_name"),
        sa.UniqueConstraint("company_id", "code", name="uq_sites_company_code"),
        sa.UniqueConstraint("company_id", "id", name="uq_sites_company_id"),
    )
    op.create_index("ix_sites_company_id", "sites", ["company_id"])
    op.create_table(
        "tippers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("registration_number", sa.String(length=32), nullable=False),
        sa.Column("short_name", sa.String(length=100), nullable=True),
        sa.Column("status", _enum("tipper_status_enum", "ACTIVE", "INACTIVE"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name="fk_tippers_company_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tippers"),
        sa.UniqueConstraint(
            "company_id", "registration_number", name="uq_tippers_company_registration"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_tippers_company_id"),
    )
    op.create_index("ix_tippers_company_id", "tippers", ["company_id"])
    op.create_table(
        "supervisor_site_access",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supervisor_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name="fk_access_company_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "supervisor_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_access_company_supervisor_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "site_id"],
            ["sites.company_id", "sites.id"],
            name="fk_access_company_site",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_supervisor_site_access"),
        sa.UniqueConstraint(
            "company_id",
            "supervisor_membership_id",
            "site_id",
            name="uq_access_company_supervisor_site",
        ),
    )
    op.create_index(
        "ix_supervisor_site_access_company_id", "supervisor_site_access", ["company_id"]
    )
    op.create_index(
        "ix_supervisor_site_access_supervisor_membership_id",
        "supervisor_site_access",
        ["supervisor_membership_id"],
    )
    op.create_index("ix_supervisor_site_access_site_id", "supervisor_site_access", ["site_id"])
    op.create_table(
        "devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("installation_identifier", sa.String(length=200), nullable=False),
        sa.Column(
            "platform",
            _enum("device_platform_enum", "ANDROID", "IOS", "WEB", "OTHER"),
            nullable=False,
        ),
        sa.Column("status", _enum("device_status_enum", "ACTIVE", "REVOKED"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name="fk_devices_company_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_devices_company_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_devices"),
        sa.UniqueConstraint(
            "company_id", "installation_identifier", name="uq_devices_company_installation"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_devices_company_id"),
    )
    op.create_index("ix_devices_company_id", "devices", ["company_id"])
    op.create_index("ix_devices_membership_id", "devices", ["membership_id"])
    op.create_table(
        "assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("driver_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supervisor_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tipper_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="end_after_start"),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name="fk_assignments_company_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "driver_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_assignments_company_driver_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "supervisor_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_assignments_company_supervisor_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "tipper_id"],
            ["tippers.company_id", "tippers.id"],
            name="fk_assignments_company_tipper",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "site_id"],
            ["sites.company_id", "sites.id"],
            name="fk_assignments_company_site",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_assignments_company_id"),
        sa.PrimaryKeyConstraint("id", name="pk_assignments"),
    )
    op.create_index("ix_assignments_company_id", "assignments", ["company_id"])
    op.create_index("ix_assignments_driver_membership_id", "assignments", ["driver_membership_id"])
    op.create_index(
        "ix_assignments_supervisor_membership_id", "assignments", ["supervisor_membership_id"]
    )
    op.create_index("ix_assignments_tipper_id", "assignments", ["tipper_id"])
    op.create_index("ix_assignments_site_id", "assignments", ["site_id"])
    op.create_index(
        "ix_assignments_company_active", "assignments", ["company_id", "starts_at", "ends_at"]
    )
    op.execute(
        "ALTER TABLE assignments ADD CONSTRAINT excl_assignments_driver_time "
        "EXCLUDE USING gist (company_id WITH =, driver_membership_id WITH =, "
        "tstzrange(starts_at, COALESCE(ends_at, 'infinity'::timestamptz), '[)') WITH &&)"
    )
    op.execute(
        "ALTER TABLE assignments ADD CONSTRAINT excl_assignments_tipper_time "
        "EXCLUDE USING gist (company_id WITH =, tipper_id WITH =, "
        "tstzrange(starts_at, COALESCE(ends_at, 'infinity'::timestamptz), '[)') WITH &&)"
    )
    op.create_table(
        "operational_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_event_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("device_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "server_received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            _enum(
                "operational_event_type_enum", "TRIP_COMPLETE", "KM_READING", "DIESEL", "EMERGENCY"
            ),
            nullable=False,
        ),
        sa.Column(
            "verification_status",
            _enum(
                "verification_status_enum",
                "PENDING_VERIFICATION",
                "APPROVED",
                "REJECTED",
                "DISPUTED",
                "AMENDED",
            ),
            server_default="PENDING_VERIFICATION",
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name="fk_events_company_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "assignment_id"],
            ["assignments.company_id", "assignments.id"],
            name="fk_events_company_assignment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "device_id"],
            ["devices.company_id", "devices.id"],
            name="fk_events_company_device",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_operational_events"),
        sa.UniqueConstraint(
            "company_id", "client_event_uuid", name="uq_events_company_client_uuid"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_events_company_id"),
    )
    op.create_index(
        "ix_events_company_verification",
        "operational_events",
        ["company_id", "verification_status", "server_received_at"],
    )
    op.create_index(
        "ix_events_assignment_time", "operational_events", ["assignment_id", "device_created_at"]
    )
    op.create_index("ix_operational_events_company_id", "operational_events", ["company_id"])
    op.create_index("ix_operational_events_assignment_id", "operational_events", ["assignment_id"])
    op.create_index("ix_operational_events_device_id", "operational_events", ["device_id"])
    op.create_table(
        "trip_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["operational_events.id"],
            name="fk_trip_events_event_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("event_id", name="pk_trip_events"),
    )
    op.create_table(
        "km_readings",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "reading_type",
            _enum("km_reading_type_enum", "START_READING", "END_READING"),
            nullable=False,
        ),
        sa.Column("reading_value", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("object_reference", sa.String(length=500), nullable=True),
        sa.CheckConstraint("reading_value >= 0", name="non_negative"),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["operational_events.id"],
            name="fk_km_readings_event_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("event_id", name="pk_km_readings"),
    )
    op.create_index("ix_km_readings_type", "km_readings", ["reading_type"])
    op.create_table(
        "diesel_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("litres", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("object_reference", sa.String(length=500), nullable=True),
        sa.CheckConstraint("litres > 0", name="positive_litres"),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["operational_events.id"],
            name="fk_diesel_events_event_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("event_id", name="pk_diesel_events"),
    )
    op.create_table(
        "emergency_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "category",
            _enum(
                "emergency_category_enum",
                "BREAKDOWN",
                "ACCIDENT",
                "TYRE_OR_VEHICLE_PROBLEM",
                "CONTACT_SUPERVISOR",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            _enum("emergency_status_enum", "OPEN", "ACKNOWLEDGED", "RESOLVED", "CLOSED"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["operational_events.id"],
            name="fk_emergency_events_event_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("event_id", name="pk_emergency_events"),
    )
    op.create_table(
        "event_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("changed_by_membership_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            _enum(
                "verification_status_enum",
                "PENDING_VERIFICATION",
                "APPROVED",
                "REJECTED",
                "DISPUTED",
                "AMENDED",
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name="fk_verifications_company_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "event_id"],
            ["operational_events.company_id", "operational_events.id"],
            name="fk_verifications_company_event",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "changed_by_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_verifications_company_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_event_verifications"),
    )
    op.create_index("ix_event_verifications_company_id", "event_verifications", ["company_id"])
    op.create_index("ix_event_verifications_event_id", "event_verifications", ["event_id"])
    op.create_index(
        "ix_verifications_event_time", "event_verifications", ["event_id", "created_at"]
    )
    op.create_index(
        "ix_event_verifications_changed_by_membership_id",
        "event_verifications",
        ["changed_by_membership_id"],
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_membership_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("old_values", postgresql.JSONB(), nullable=True),
        sa.Column("new_values", postgresql.JSONB(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name="fk_audit_logs_company_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "actor_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_audit_company_actor_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
    )
    op.create_index("ix_audit_logs_company_id", "audit_logs", ["company_id"])
    op.create_index("ix_audit_logs_actor_membership_id", "audit_logs", ["actor_membership_id"])
    op.create_index("ix_audit_logs_company_created", "audit_logs", ["company_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_company_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_membership_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_company_id", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.execute("DROP INDEX IF EXISTS ix_event_verifications_changed_by_membership_id")
    op.execute("DROP INDEX IF EXISTS ix_verifications_changed_by_membership_id")
    op.drop_index("ix_verifications_event_time", table_name="event_verifications")
    op.execute("DROP INDEX IF EXISTS ix_event_verifications_event_id")
    op.execute("DROP INDEX IF EXISTS ix_verifications_event_id")
    op.execute("DROP INDEX IF EXISTS ix_event_verifications_company_id")
    op.execute("DROP INDEX IF EXISTS ix_verifications_company_id")
    op.drop_table("event_verifications")
    op.drop_table("emergency_events")
    op.drop_table("diesel_events")
    op.drop_index("ix_km_readings_type", table_name="km_readings")
    op.drop_table("km_readings")
    op.drop_table("trip_events")
    op.drop_index("ix_events_assignment_time", table_name="operational_events")
    op.drop_index("ix_events_company_verification", table_name="operational_events")
    op.drop_index("ix_operational_events_device_id", table_name="operational_events")
    op.drop_index("ix_operational_events_assignment_id", table_name="operational_events")
    op.drop_index("ix_operational_events_company_id", table_name="operational_events")
    op.drop_table("operational_events")
    op.execute("ALTER TABLE assignments DROP CONSTRAINT IF EXISTS excl_assignments_tipper_time")
    op.execute("ALTER TABLE assignments DROP CONSTRAINT IF EXISTS excl_assignments_driver_time")
    op.drop_index("ix_assignments_company_active", table_name="assignments")
    op.drop_index("ix_assignments_site_id", table_name="assignments")
    op.drop_index("ix_assignments_tipper_id", table_name="assignments")
    op.drop_index("ix_assignments_supervisor_membership_id", table_name="assignments")
    op.drop_index("ix_assignments_driver_membership_id", table_name="assignments")
    op.drop_index("ix_assignments_company_id", table_name="assignments")
    op.drop_table("assignments")
    op.drop_index("ix_devices_membership_id", table_name="devices")
    op.drop_index("ix_devices_company_id", table_name="devices")
    op.drop_table("devices")
    op.drop_index("ix_supervisor_site_access_site_id", table_name="supervisor_site_access")
    op.drop_index(
        "ix_supervisor_site_access_supervisor_membership_id", table_name="supervisor_site_access"
    )
    op.drop_index("ix_supervisor_site_access_company_id", table_name="supervisor_site_access")
    op.drop_table("supervisor_site_access")
    op.drop_index("ix_tippers_company_id", table_name="tippers")
    op.drop_table("tippers")
    op.drop_index("ix_sites_company_id", table_name="sites")
    op.drop_table("sites")
    op.drop_index("ix_company_memberships_user_id", table_name="company_memberships")
    op.drop_index("ix_company_memberships_company_id", table_name="company_memberships")
    op.drop_table("company_memberships")
    op.drop_table("users")
    op.drop_table("companies")
    for name in (
        "emergency_status_enum",
        "emergency_category_enum",
        "km_reading_type_enum",
        "verification_status_enum",
        "operational_event_type_enum",
        "device_status_enum",
        "device_platform_enum",
        "tipper_status_enum",
        "site_status_enum",
        "membership_status_enum",
        "membership_role_enum",
        "user_status_enum",
        "company_status_enum",
    ):
        op.execute(f"DROP TYPE IF EXISTS {name}")
