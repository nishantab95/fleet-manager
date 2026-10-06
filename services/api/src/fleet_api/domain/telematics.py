from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from math import asin, cos, radians, sin, sqrt
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from fleet_api.auth.service import AuthContext, ensure_role
from fleet_api.core.features import FeatureRegistry, FutureFeature
from fleet_api.db.models import (
    Assignment,
    FleetAsset,
    GeofenceTransition,
    HourMeterReading,
    KmReading,
    OperationalEvent,
    Site,
    SiteGeofence,
    TelematicsMeterDiscrepancy,
    TelematicsPosition,
    TelematicsVehicleMapping,
)
from fleet_api.domain.audit import write_audit_log
from fleet_api.domain.enums import (
    GeofenceTransitionType,
    MembershipRole,
    MeterDiscrepancyStatus,
    VerificationStatus,
)
from fleet_api.domain.errors import (
    ConflictError,
    DomainError,
    FeatureUnavailableError,
    NotFoundError,
    TenantConsistencyError,
)


@dataclass(frozen=True)
class TelematicsVehicleReference:
    company_id: UUID
    asset_id: UUID
    provider: str
    provider_vehicle_id: str


@dataclass(frozen=True)
class ProviderPosition:
    timestamp: datetime
    latitude: Decimal
    longitude: Decimal
    speed_kph: Decimal | None = None
    heading: Decimal | None = None
    ignition_state: bool | None = None
    odometer_km: Decimal | None = None
    engine_hours: Decimal | None = None
    battery_voltage: Decimal | None = None
    raw_provider_reference: str | None = None


@dataclass(frozen=True)
class TelemetryPosition:
    company_id: UUID
    asset_id: UUID
    provider: str
    provider_vehicle_id: str
    timestamp: datetime
    latitude: Decimal
    longitude: Decimal
    speed_kph: Decimal | None
    heading: Decimal | None
    ignition_state: bool | None
    odometer_km: Decimal | None
    engine_hours: Decimal | None
    battery_voltage: Decimal | None
    raw_provider_reference: str | None


class TelematicsProvider(Protocol):
    def fetch_latest_position(self, provider_vehicle_id: str) -> ProviderPosition: ...

    def fetch_history(
        self,
        provider_vehicle_id: str,
        *,
        starts_at: datetime,
        ends_at: datetime,
    ) -> list[ProviderPosition]: ...

    def fetch_odometer(self, provider_vehicle_id: str) -> Decimal | None: ...

    def fetch_events(
        self,
        provider_vehicle_id: str,
        *,
        starts_at: datetime,
        ends_at: datetime,
    ) -> list[str]: ...


def normalize_position(
    mapping: TelematicsVehicleReference,
    position: ProviderPosition,
) -> TelemetryPosition:
    if position.timestamp.tzinfo is None or position.timestamp.utcoffset() is None:
        raise DomainError("telemetry timestamp must include a timezone")
    if not Decimal("-90") <= position.latitude <= Decimal("90"):
        raise DomainError("telemetry latitude is invalid")
    if not Decimal("-180") <= position.longitude <= Decimal("180"):
        raise DomainError("telemetry longitude is invalid")
    if position.speed_kph is not None and position.speed_kph < 0:
        raise DomainError("telemetry speed cannot be negative")
    if position.heading is not None and not Decimal("0") <= position.heading < Decimal("360"):
        raise DomainError("telemetry heading must be in [0, 360)")
    if position.odometer_km is not None and position.odometer_km < 0:
        raise DomainError("telemetry odometer cannot be negative")
    if position.engine_hours is not None and position.engine_hours < 0:
        raise DomainError("telemetry engine hours cannot be negative")
    if position.battery_voltage is not None and position.battery_voltage < 0:
        raise DomainError("telemetry battery voltage cannot be negative")
    return TelemetryPosition(
        company_id=mapping.company_id,
        asset_id=mapping.asset_id,
        provider=mapping.provider,
        provider_vehicle_id=mapping.provider_vehicle_id,
        timestamp=position.timestamp,
        latitude=position.latitude,
        longitude=position.longitude,
        speed_kph=position.speed_kph,
        heading=position.heading,
        ignition_state=position.ignition_state,
        odometer_km=position.odometer_km,
        engine_hours=position.engine_hours,
        battery_voltage=position.battery_voltage,
        raw_provider_reference=position.raw_provider_reference,
    )


class TelematicsService:
    def __init__(
        self,
        registry: FeatureRegistry,
        provider: TelematicsProvider,
        *,
        company_id: UUID,
    ) -> None:
        self.registry = registry
        self.provider = provider
        self.company_id = company_id

    def latest(self, mapping: TelematicsVehicleReference) -> TelemetryPosition:
        if not self.registry.is_enabled(FutureFeature.TELEMATICS):
            raise FeatureUnavailableError("telematics is disabled")
        if mapping.company_id != self.company_id:
            raise TenantConsistencyError("telematics mapping belongs to another company")
        return normalize_position(
            mapping,
            self.provider.fetch_latest_position(mapping.provider_vehicle_id),
        )


def haversine_distance_m(
    latitude_a: Decimal,
    longitude_a: Decimal,
    latitude_b: Decimal,
    longitude_b: Decimal,
) -> Decimal:
    """Great-circle distance in metres for circular site geofences."""

    radius = 6_371_000.0
    lat_a, lat_b = radians(float(latitude_a)), radians(float(latitude_b))
    delta_lat = lat_b - lat_a
    delta_lon = radians(float(longitude_b - longitude_a))
    term = sin(delta_lat / 2) ** 2 + cos(lat_a) * cos(lat_b) * sin(delta_lon / 2) ** 2
    return Decimal(str(2 * radius * asin(sqrt(term)))).quantize(Decimal("0.01"))


@dataclass(frozen=True)
class PositionIngestionResult:
    position: TelematicsPosition
    transitions: list[GeofenceTransition]
    duplicate: bool
    out_of_order: bool
    discrepancies: tuple[TelematicsMeterDiscrepancy, ...] = ()


@dataclass(frozen=True)
class LatestPositionView:
    mapping: TelematicsVehicleMapping
    position: TelematicsPosition | None
    stale: bool


class TelematicsIngestionService:
    """Owner-scoped persisted mapping, ingestion, and circular geofence engine."""

    def __init__(
        self,
        session: Session,
        context: AuthContext,
        *,
        request_id: str | None = None,
    ) -> None:
        ensure_role(context, MembershipRole.OWNER_ADMIN)
        self.session = session
        self.company_id = context.company.id
        self.actor_id = context.membership.id
        self.request_id = request_id

    def _asset(self, asset_id: UUID) -> FleetAsset:
        asset = self.session.scalar(
            select(FleetAsset).where(
                FleetAsset.company_id == self.company_id, FleetAsset.id == asset_id
            )
        )
        if asset is None:
            raise NotFoundError("asset not found")
        return asset

    def _mapping(self, mapping_id: UUID) -> TelematicsVehicleMapping:
        mapping = self.session.scalar(
            select(TelematicsVehicleMapping).where(
                TelematicsVehicleMapping.company_id == self.company_id,
                TelematicsVehicleMapping.id == mapping_id,
            )
        )
        if mapping is None:
            raise NotFoundError("telematics mapping not found")
        return mapping

    def create_mapping(
        self, *, asset_id: UUID, provider: str, provider_vehicle_id: str
    ) -> TelematicsVehicleMapping:
        self._asset(asset_id)
        clean_provider = provider.strip().upper()
        clean_vehicle = provider_vehicle_id.strip()
        if not clean_provider or not clean_vehicle:
            raise DomainError("provider and provider_vehicle_id are required")
        existing = self.session.scalar(
            select(TelematicsVehicleMapping.id).where(
                TelematicsVehicleMapping.company_id == self.company_id,
                (
                    (
                        (TelematicsVehicleMapping.provider == clean_provider)
                        & (TelematicsVehicleMapping.provider_vehicle_id == clean_vehicle)
                    )
                    | (
                        (TelematicsVehicleMapping.asset_id == asset_id)
                        & (TelematicsVehicleMapping.provider == clean_provider)
                    )
                ),
            )
        )
        if existing is not None:
            raise ConflictError("telematics mapping already exists")
        mapping = TelematicsVehicleMapping(
            company_id=self.company_id,
            asset_id=asset_id,
            provider=clean_provider,
            provider_vehicle_id=clean_vehicle,
            active=True,
            created_by=self.actor_id,
        )
        self.session.add(mapping)
        self.session.flush()
        write_audit_log(
            self.session,
            company_id=self.company_id,
            actor_membership_id=self.actor_id,
            action="TELEMATICS_MAPPING_CREATED",
            entity_type="TELEMATICS_MAPPING",
            entity_id=mapping.id,
            new_values={
                "asset_id": str(asset_id),
                "provider": clean_provider,
                "provider_vehicle_id": clean_vehicle,
            },
            request_id=self.request_id,
        )
        return mapping

    def list_mappings(self) -> list[TelematicsVehicleMapping]:
        return list(
            self.session.scalars(
                select(TelematicsVehicleMapping)
                .where(TelematicsVehicleMapping.company_id == self.company_id)
                .order_by(TelematicsVehicleMapping.created_at, TelematicsVehicleMapping.id)
            )
        )

    def set_geofence(self, *, site_id: UUID, radius_m: Decimal) -> SiteGeofence:
        if not radius_m.is_finite() or radius_m <= 0 or radius_m > Decimal("100000"):
            raise DomainError("radius_m must be between zero and 100000")
        site = self.session.scalar(
            select(Site).where(Site.company_id == self.company_id, Site.id == site_id)
        )
        if site is None:
            raise NotFoundError("site not found")
        if site.latitude is None or site.longitude is None:
            raise DomainError("site latitude and longitude are required for a geofence")
        geofence = self.session.scalar(
            select(SiteGeofence)
            .where(SiteGeofence.company_id == self.company_id, SiteGeofence.site_id == site_id)
            .with_for_update()
        )
        if geofence is None:
            geofence = SiteGeofence(
                company_id=self.company_id,
                site_id=site_id,
                radius_m=radius_m,
                active=True,
                created_by=self.actor_id,
            )
            self.session.add(geofence)
        else:
            geofence.radius_m = radius_m
            geofence.active = True
        self.session.flush()
        return geofence

    def ingest(
        self,
        mapping_id: UUID,
        *,
        provider_event_id: str,
        recorded_at: datetime,
        latitude: Decimal,
        longitude: Decimal,
        speed_kph: Decimal | None,
        heading: Decimal | None,
        ignition_state: bool | None,
        odometer_km: Decimal | None,
        engine_hours: Decimal | None = None,
        battery_voltage: Decimal | None = None,
    ) -> PositionIngestionResult:
        mapping = self._mapping(mapping_id)
        if not mapping.active:
            raise DomainError("telematics mapping is inactive")
        event_id = provider_event_id.strip()
        if not event_id:
            raise DomainError("provider_event_id is required")
        normalized = normalize_position(
            TelematicsVehicleReference(
                self.company_id, mapping.asset_id, mapping.provider, mapping.provider_vehicle_id
            ),
            ProviderPosition(
                timestamp=recorded_at,
                latitude=latitude,
                longitude=longitude,
                speed_kph=speed_kph,
                heading=heading,
                ignition_state=ignition_state,
                odometer_km=odometer_km,
                engine_hours=engine_hours,
                battery_voltage=battery_voltage,
                raw_provider_reference=event_id,
            ),
        )
        duplicate = self.session.scalar(
            select(TelematicsPosition).where(
                TelematicsPosition.company_id == self.company_id,
                TelematicsPosition.mapping_id == mapping.id,
                TelematicsPosition.provider_event_id == event_id,
            )
        )
        if duplicate is not None:
            duplicate_transitions = list(
                self.session.scalars(
                    select(GeofenceTransition).where(
                        GeofenceTransition.company_id == self.company_id,
                        GeofenceTransition.position_id == duplicate.id,
                    )
                )
            )
            duplicate_discrepancies = tuple(
                self.session.scalars(
                    select(TelematicsMeterDiscrepancy).where(
                        TelematicsMeterDiscrepancy.company_id == self.company_id,
                        TelematicsMeterDiscrepancy.position_id == duplicate.id,
                    )
                )
            )
            return PositionIngestionResult(
                duplicate, duplicate_transitions, True, False, duplicate_discrepancies
            )
        latest = self.session.scalar(
            select(TelematicsPosition)
            .where(
                TelematicsPosition.company_id == self.company_id,
                TelematicsPosition.asset_id == mapping.asset_id,
            )
            .order_by(TelematicsPosition.recorded_at.desc(), TelematicsPosition.created_at.desc())
            .limit(1)
        )
        out_of_order = latest is not None and recorded_at <= latest.recorded_at
        position = TelematicsPosition(
            company_id=self.company_id,
            mapping_id=mapping.id,
            asset_id=mapping.asset_id,
            provider_event_id=event_id,
            recorded_at=normalized.timestamp,
            latitude=normalized.latitude,
            longitude=normalized.longitude,
            speed_kph=normalized.speed_kph,
            heading=normalized.heading,
            ignition_state=normalized.ignition_state,
            odometer_km=normalized.odometer_km,
            engine_hours=normalized.engine_hours,
            battery_voltage=normalized.battery_voltage,
        )
        self.session.add(position)
        self.session.flush()
        transitions: list[GeofenceTransition] = []
        if not out_of_order:
            geofences = self.session.execute(
                select(SiteGeofence, Site)
                .join(
                    Site,
                    (Site.company_id == SiteGeofence.company_id)
                    & (Site.id == SiteGeofence.site_id),
                )
                .where(
                    SiteGeofence.company_id == self.company_id,
                    SiteGeofence.active.is_(True),
                    Site.latitude.is_not(None),
                    Site.longitude.is_not(None),
                )
            ).all()
            for geofence, site in geofences:
                assert site.latitude is not None and site.longitude is not None
                current_distance = haversine_distance_m(
                    latitude, longitude, site.latitude, site.longitude
                )
                current_inside = current_distance <= geofence.radius_m
                previous_inside = False
                if latest is not None:
                    previous_distance = haversine_distance_m(
                        latest.latitude, latest.longitude, site.latitude, site.longitude
                    )
                    previous_inside = previous_distance <= geofence.radius_m
                if current_inside == previous_inside:
                    continue
                transition = GeofenceTransition(
                    company_id=self.company_id,
                    asset_id=mapping.asset_id,
                    site_id=site.id,
                    position_id=position.id,
                    transition_type=(
                        GeofenceTransitionType.ENTER
                        if current_inside
                        else GeofenceTransitionType.EXIT
                    ),
                    occurred_at=recorded_at,
                    distance_m=current_distance,
                )
                self.session.add(transition)
                transitions.append(transition)
            self.session.flush()
        recorded_discrepancies = self._record_meter_discrepancies(position)
        return PositionIngestionResult(
            position, transitions, False, out_of_order, tuple(recorded_discrepancies)
        )

    def _latest_manual_meter(
        self, asset_id: UUID, reading: type[KmReading] | type[HourMeterReading]
    ) -> tuple[UUID, Decimal] | None:
        row = self.session.execute(
            select(OperationalEvent.id, reading.reading_value)
            .join(reading, reading.event_id == OperationalEvent.id)
            .join(Assignment, Assignment.id == OperationalEvent.assignment_id)
            .where(
                OperationalEvent.company_id == self.company_id,
                Assignment.company_id == self.company_id,
                Assignment.asset_id == asset_id,
                OperationalEvent.verification_status.in_(
                    [VerificationStatus.APPROVED, VerificationStatus.AMENDED]
                ),
            )
            .order_by(OperationalEvent.device_created_at.desc(), OperationalEvent.id.desc())
            .limit(1)
        ).first()
        return (row[0], row[1]) if row is not None else None

    def _record_meter_discrepancies(
        self, position: TelematicsPosition
    ) -> list[TelematicsMeterDiscrepancy]:
        result: list[TelematicsMeterDiscrepancy] = []
        readings: tuple[
            tuple[str, Decimal | None, type[KmReading] | type[HourMeterReading], Decimal], ...
        ] = (
            ("ODOMETER_KM", position.odometer_km, KmReading, Decimal("5.00")),
            ("HOUR_METER_HOURS", position.engine_hours, HourMeterReading, Decimal("1.00")),
        )
        for meter_type, telemetry_value, reading_model, tolerance in readings:
            if telemetry_value is None:
                continue
            manual = self._latest_manual_meter(position.asset_id, reading_model)
            manual_event_id = manual[0] if manual else None
            manual_value = manual[1] if manual else None
            difference = abs(telemetry_value - manual_value) if manual_value is not None else None
            if difference is None:
                discrepancy_status = MeterDiscrepancyStatus.INSUFFICIENT_DATA
            elif difference <= tolerance:
                discrepancy_status = MeterDiscrepancyStatus.WITHIN_TOLERANCE
            else:
                discrepancy_status = MeterDiscrepancyStatus.MISMATCH
            item = TelematicsMeterDiscrepancy(
                company_id=self.company_id,
                asset_id=position.asset_id,
                position_id=position.id,
                manual_event_id=manual_event_id,
                meter_type=meter_type,
                telemetry_value=telemetry_value,
                manual_value=manual_value,
                tolerance=tolerance,
                difference=difference,
                status=discrepancy_status,
            )
            self.session.add(item)
            result.append(item)
        self.session.flush()
        return result

    def meter_discrepancies(
        self, *, asset_id: UUID | None = None
    ) -> list[TelematicsMeterDiscrepancy]:
        query = select(TelematicsMeterDiscrepancy).where(
            TelematicsMeterDiscrepancy.company_id == self.company_id
        )
        if asset_id is not None:
            self._asset(asset_id)
            query = query.where(TelematicsMeterDiscrepancy.asset_id == asset_id)
        return list(
            self.session.scalars(
                query.order_by(
                    TelematicsMeterDiscrepancy.created_at.desc(),
                    TelematicsMeterDiscrepancy.id,
                )
            )
        )

    def latest_positions(
        self, *, stale_after_seconds: int = 900, now: datetime | None = None
    ) -> list[LatestPositionView]:
        if stale_after_seconds < 0:
            raise DomainError("stale_after_seconds cannot be negative")
        current_time = now or datetime.now(UTC)
        result: list[LatestPositionView] = []
        for mapping in self.list_mappings():
            position = self.session.scalar(
                select(TelematicsPosition)
                .where(
                    TelematicsPosition.company_id == self.company_id,
                    TelematicsPosition.mapping_id == mapping.id,
                )
                .order_by(TelematicsPosition.recorded_at.desc())
                .limit(1)
            )
            stale = position is None or current_time - position.recorded_at > timedelta(
                seconds=stale_after_seconds
            )
            result.append(LatestPositionView(mapping, position, stale))
        return result

    def transitions(self, *, asset_id: UUID | None = None) -> list[GeofenceTransition]:
        query = select(GeofenceTransition).where(GeofenceTransition.company_id == self.company_id)
        if asset_id is not None:
            self._asset(asset_id)
            query = query.where(GeofenceTransition.asset_id == asset_id)
        return list(
            self.session.scalars(
                query.order_by(
                    GeofenceTransition.occurred_at.desc(), GeofenceTransition.created_at.desc()
                )
            )
        )
