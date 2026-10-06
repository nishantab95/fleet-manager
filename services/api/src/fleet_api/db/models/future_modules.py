from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.models.common import UpdatedTimestampModel, UUIDTimestampModel
from fleet_api.domain.enums import (
    FuelImportBatchStatus,
    FuelImportRowStatus,
    FuelReconciliationStatus,
    FuelSourceType,
    GeofenceTransitionType,
    MeterDiscrepancyStatus,
    NotificationCategory,
    NotificationState,
)


class InAppNotification(UUIDTimestampModel):
    __tablename__ = "in_app_notifications"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient_membership_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    category: Mapped[NotificationCategory] = mapped_column(
        SAEnum(NotificationCategory, name="notification_category_enum"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    deep_link: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
    state: Mapped[NotificationState] = mapped_column(
        SAEnum(NotificationState, name="notification_state_enum"), nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "recipient_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_notifications_company_recipient",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "company_id",
            "recipient_membership_id",
            "dedupe_key",
            name="uq_notifications_recipient_dedupe",
        ),
        Index(
            "ix_notifications_recipient_state_created",
            "company_id",
            "recipient_membership_id",
            "state",
            "created_at",
        ),
    )


class TelematicsVehicleMapping(UpdatedTimestampModel):
    __tablename__ = "telematics_vehicle_mappings"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_vehicle_id: Mapped[str] = mapped_column(String(160), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[UUID] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_telematics_mappings_company_id"),
        UniqueConstraint(
            "company_id",
            "provider",
            "provider_vehicle_id",
            name="uq_telematics_mappings_provider_vehicle",
        ),
        UniqueConstraint(
            "company_id", "asset_id", "provider", name="uq_telematics_mappings_asset_provider"
        ),
        ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_telematics_mappings_company_asset",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_telematics_mappings_company_creator",
            ondelete="RESTRICT",
        ),
    )


class SiteGeofence(UpdatedTimestampModel):
    __tablename__ = "site_geofences"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    site_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    radius_m: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[UUID] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_site_geofences_company_id"),
        UniqueConstraint("company_id", "site_id", name="uq_site_geofences_company_site"),
        ForeignKeyConstraint(
            ["company_id", "site_id"],
            ["sites.company_id", "sites.id"],
            name="fk_site_geofences_company_site",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_site_geofences_company_creator",
            ondelete="RESTRICT",
        ),
        CheckConstraint("radius_m > 0 AND radius_m <= 100000", name="site_geofence_radius_range"),
    )


class TelematicsPosition(UUIDTimestampModel):
    __tablename__ = "telematics_positions"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mapping_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    asset_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    provider_event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    speed_kph: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    heading: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    ignition_state: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    odometer_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    engine_hours: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    battery_voltage: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)

    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_telematics_positions_company_id"),
        UniqueConstraint(
            "company_id",
            "mapping_id",
            "provider_event_id",
            name="uq_telematics_positions_provider_event",
        ),
        ForeignKeyConstraint(
            ["company_id", "mapping_id"],
            ["telematics_vehicle_mappings.company_id", "telematics_vehicle_mappings.id"],
            name="fk_telematics_positions_company_mapping",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_telematics_positions_company_asset",
            ondelete="CASCADE",
        ),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="telematics_position_latitude_range"),
        CheckConstraint(
            "longitude BETWEEN -180 AND 180", name="telematics_position_longitude_range"
        ),
        CheckConstraint(
            "speed_kph IS NULL OR speed_kph >= 0", name="telematics_position_speed_non_negative"
        ),
        CheckConstraint(
            "heading IS NULL OR (heading >= 0 AND heading < 360)",
            name="telematics_position_heading_range",
        ),
        CheckConstraint(
            "odometer_km IS NULL OR odometer_km >= 0",
            name="telematics_position_odometer_non_negative",
        ),
        CheckConstraint(
            "engine_hours IS NULL OR engine_hours >= 0",
            name="telematics_position_engine_hours_non_negative",
        ),
        CheckConstraint(
            "battery_voltage IS NULL OR battery_voltage >= 0",
            name="telematics_position_voltage_non_negative",
        ),
        Index(
            "ix_telematics_positions_company_asset_recorded",
            "company_id",
            "asset_id",
            "recorded_at",
        ),
    )


class GeofenceTransition(UUIDTimestampModel):
    __tablename__ = "geofence_transitions"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    site_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    position_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    transition_type: Mapped[GeofenceTransitionType] = mapped_column(
        SAEnum(GeofenceTransitionType, name="geofence_transition_type_enum"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    distance_m: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_geofence_transitions_company_asset",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "site_id"],
            ["sites.company_id", "sites.id"],
            name="fk_geofence_transitions_company_site",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "position_id"],
            ["telematics_positions.company_id", "telematics_positions.id"],
            name="fk_geofence_transitions_company_position",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "company_id", "position_id", "site_id", name="uq_geofence_transitions_position_site"
        ),
        Index(
            "ix_geofence_transitions_company_asset_occurred",
            "company_id",
            "asset_id",
            "occurred_at",
        ),
    )


class TelematicsMeterDiscrepancy(UUIDTimestampModel):
    __tablename__ = "telematics_meter_discrepancies"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    position_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    manual_event_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    meter_type: Mapped[str] = mapped_column(String(40), nullable=False)
    telemetry_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    manual_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    tolerance: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    difference: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[MeterDiscrepancyStatus] = mapped_column(
        SAEnum(MeterDiscrepancyStatus, name="meter_discrepancy_status_enum"), nullable=False
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_telematics_discrepancies_company_asset",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "position_id"],
            ["telematics_positions.company_id", "telematics_positions.id"],
            name="fk_telematics_discrepancies_company_position",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "manual_event_id"],
            ["operational_events.company_id", "operational_events.id"],
            name="fk_telematics_discrepancies_company_event",
            ondelete="SET NULL",
        ),
        UniqueConstraint(
            "company_id",
            "position_id",
            "meter_type",
            name="uq_telematics_discrepancies_position_meter",
        ),
        CheckConstraint(
            "telemetry_value >= 0 AND tolerance >= 0",
            name="telematics_discrepancy_values_non_negative",
        ),
    )


class FuelImportBatch(UpdatedTimestampModel):
    __tablename__ = "fuel_import_batches"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[FuelImportBatchStatus] = mapped_column(
        SAEnum(FuelImportBatchStatus, name="fuel_import_batch_status_enum"), nullable=False
    )
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[UUID] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_fuel_import_batches_company_id"),
        ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_fuel_import_batches_company_creator",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "total_rows >= 0 AND imported_rows >= 0 AND rejected_rows >= 0",
            name="fuel_import_batch_counts_non_negative",
        ),
    )


class ExternalFuelTransaction(UUIDTimestampModel):
    __tablename__ = "external_fuel_transactions"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    row_status: Mapped[FuelImportRowStatus] = mapped_column(
        SAEnum(FuelImportRowStatus, name="fuel_import_row_status_enum"), nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    asset_identifier: Mapped[str] = mapped_column(String(160), nullable=False)
    source_type: Mapped[FuelSourceType] = mapped_column(
        SAEnum(FuelSourceType, name="fuel_source_type_enum"), nullable=False
    )
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    external_transaction_id: Mapped[str] = mapped_column(String(160), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    litres: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    raw_row: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_external_fuel_transactions_company_id"),
        Index(
            "uq_external_fuel_transactions_imported_source_external",
            "company_id",
            "source_name",
            "external_transaction_id",
            unique=True,
            postgresql_where=text("row_status = 'IMPORTED'::fuel_import_row_status_enum"),
        ),
        UniqueConstraint(
            "company_id", "batch_id", "row_number", name="uq_external_fuel_transactions_batch_row"
        ),
        ForeignKeyConstraint(
            ["company_id", "batch_id"],
            ["fuel_import_batches.company_id", "fuel_import_batches.id"],
            name="fk_external_fuel_transactions_company_batch",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_external_fuel_transactions_company_asset",
            ondelete="RESTRICT",
        ),
        CheckConstraint("row_number > 0", name="external_fuel_transaction_row_positive"),
        CheckConstraint(
            "litres IS NULL OR litres > 0", name="external_fuel_transaction_litres_positive"
        ),
    )


class FuelReconciliation(UpdatedTimestampModel):
    __tablename__ = "fuel_reconciliations"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_transaction_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    operational_event_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    status: Mapped[FuelReconciliationStatus] = mapped_column(
        SAEnum(FuelReconciliationStatus, name="fuel_reconciliation_status_enum"),
        nullable=False,
    )
    tolerance_litres: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    difference_litres: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    manually_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[UUID | None] = mapped_column(nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "company_id", "external_transaction_id", name="uq_fuel_reconciliations_transaction"
        ),
        ForeignKeyConstraint(
            ["company_id", "external_transaction_id"],
            ["external_fuel_transactions.company_id", "external_fuel_transactions.id"],
            name="fk_fuel_reconciliations_company_transaction",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "operational_event_id"],
            ["operational_events.company_id", "operational_events.id"],
            name="fk_fuel_reconciliations_company_event",
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["company_id", "resolved_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_fuel_reconciliations_company_resolver",
            ondelete="RESTRICT",
        ),
        CheckConstraint("tolerance_litres >= 0", name="fuel_reconciliation_tolerance_non_negative"),
        CheckConstraint(
            "difference_litres IS NULL OR difference_litres >= 0",
            name="fuel_reconciliation_difference_non_negative",
        ),
        CheckConstraint(
            "(manually_resolved = false AND resolution_reason IS NULL AND resolved_by IS NULL) OR "
            "(manually_resolved = true AND length(btrim(resolution_reason)) > 0 "
            "AND resolved_by IS NOT NULL)",
            name="fuel_reconciliation_resolution_complete",
        ),
    )
