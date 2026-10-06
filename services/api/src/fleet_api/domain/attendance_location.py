from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from fleet_api.auth.service import AuthContext, ensure_role
from fleet_api.db.models import (
    Assignment,
    AttendanceLocationSetting,
    AttendanceLocationSnapshot,
    DutySession,
    OperationalEvent,
    Site,
    SiteGeofence,
    TelematicsPosition,
)
from fleet_api.domain.audit import write_audit_log
from fleet_api.domain.enums import (
    AttendanceConfidence,
    DutySessionStatus,
    LocationSnapshotSource,
    LocationSnapshotStatus,
    MembershipRole,
)
from fleet_api.domain.errors import DomainError
from fleet_api.domain.telematics import haversine_distance_m


@dataclass(frozen=True)
class LocationSnapshotView:
    snapshot: AttendanceLocationSnapshot
    confidence: AttendanceConfidence
    site_distance_m: Decimal | None
    asset_distance_m: Decimal | None


def attendance_location_confidence(
    *,
    status: LocationSnapshotStatus,
    site_distance_m: Decimal | None,
    site_radius_m: Decimal | None,
    asset_distance_m: Decimal | None,
    asset_threshold_m: Decimal,
) -> AttendanceConfidence:
    """Explainable location evidence classification; never a payroll decision."""

    if status != LocationSnapshotStatus.AVAILABLE:
        return AttendanceConfidence.UNKNOWN
    site_match = (
        site_distance_m is not None
        and site_radius_m is not None
        and site_distance_m <= site_radius_m
    )
    asset_match = asset_distance_m is not None and asset_distance_m <= asset_threshold_m
    if site_match and asset_match:
        return AttendanceConfidence.STRONG_MATCH
    if site_match:
        return AttendanceConfidence.SITE_MATCH
    if asset_match:
        return AttendanceConfidence.ASSET_PROXIMITY_MATCH
    if site_distance_m is None and asset_distance_m is None:
        return AttendanceConfidence.UNKNOWN
    if site_distance_m is None or asset_distance_m is None:
        return AttendanceConfidence.PARTIAL_MATCH
    return AttendanceConfidence.MISMATCH


class AttendanceLocationService:
    def __init__(
        self,
        session: Session,
        context: AuthContext,
        *,
        request_id: str | None = None,
    ) -> None:
        self.session = session
        self.context = context
        self.company_id = context.company.id
        self.actor_id = context.membership.id
        self.request_id = request_id

    def get_settings(self) -> AttendanceLocationSetting | None:
        ensure_role(self.context, MembershipRole.OWNER_ADMIN)
        return self.session.scalar(
            select(AttendanceLocationSetting).where(
                AttendanceLocationSetting.company_id == self.company_id
            )
        )

    def put_settings(
        self,
        *,
        site_match_required: bool,
        asset_proximity_threshold_m: Decimal,
        gps_freshness_seconds: int,
        max_accuracy_m: Decimal,
        retention_days: int,
    ) -> AttendanceLocationSetting:
        ensure_role(self.context, MembershipRole.OWNER_ADMIN)
        if (
            asset_proximity_threshold_m <= 0
            or gps_freshness_seconds <= 0
            or max_accuracy_m <= 0
            or retention_days <= 0
        ):
            raise DomainError("attendance location settings must be positive")
        item = self.session.scalar(
            select(AttendanceLocationSetting)
            .where(AttendanceLocationSetting.company_id == self.company_id)
            .with_for_update()
        )
        if item is None:
            item = AttendanceLocationSetting(
                company_id=self.company_id,
                site_match_required=site_match_required,
                asset_proximity_threshold_m=asset_proximity_threshold_m,
                gps_freshness_seconds=gps_freshness_seconds,
                max_accuracy_m=max_accuracy_m,
                retention_days=retention_days,
                updated_by=self.actor_id,
            )
            self.session.add(item)
        else:
            item.site_match_required = site_match_required
            item.asset_proximity_threshold_m = asset_proximity_threshold_m
            item.gps_freshness_seconds = gps_freshness_seconds
            item.max_accuracy_m = max_accuracy_m
            item.retention_days = retention_days
            item.updated_by = self.actor_id
        self.session.flush()
        return item

    def _effective_settings(self) -> tuple[Decimal, int, Decimal]:
        item = self.session.scalar(
            select(AttendanceLocationSetting).where(
                AttendanceLocationSetting.company_id == self.company_id
            )
        )
        if item is None:
            return Decimal("100"), 900, Decimal("100")
        return item.asset_proximity_threshold_m, item.gps_freshness_seconds, item.max_accuracy_m

    def capture(
        self,
        *,
        source: LocationSnapshotSource,
        status: LocationSnapshotStatus,
        captured_at_device: datetime,
        latitude: Decimal | None,
        longitude: Decimal | None,
        accuracy_m: Decimal | None,
        permission_state: str | None,
        operational_event_id: UUID | None = None,
    ) -> AttendanceLocationSnapshot:
        ensure_role(self.context, MembershipRole.DRIVER)
        if captured_at_device.tzinfo is None or captured_at_device.utcoffset() is None:
            raise DomainError("captured_at_device must include a timezone")
        threshold, _, max_accuracy = self._effective_settings()
        del threshold
        if status == LocationSnapshotStatus.AVAILABLE:
            if latitude is None or longitude is None or accuracy_m is None:
                raise DomainError("available location requires coordinates and accuracy")
            if accuracy_m > max_accuracy:
                status = LocationSnapshotStatus.LOW_ACCURACY
        if latitude is not None and not Decimal("-90") <= latitude <= Decimal("90"):
            raise DomainError("latitude is invalid")
        if longitude is not None and not Decimal("-180") <= longitude <= Decimal("180"):
            raise DomainError("longitude is invalid")
        active_duty = self.session.scalar(
            select(DutySession).where(
                DutySession.company_id == self.company_id,
                DutySession.driver_membership_id == self.actor_id,
                DutySession.status == DutySessionStatus.ACTIVE,
            )
        )
        assignment: Assignment | None = None
        event: OperationalEvent | None = None
        if active_duty is not None:
            assignment = self.session.scalar(
                select(Assignment).where(
                    Assignment.company_id == self.company_id,
                    Assignment.id == active_duty.assignment_id,
                    Assignment.driver_membership_id == self.actor_id,
                )
            )
        elif operational_event_id is not None:
            event = self.session.scalar(
                select(OperationalEvent).where(
                    OperationalEvent.company_id == self.company_id,
                    OperationalEvent.id == operational_event_id,
                )
            )
            if event is not None:
                assignment = self.session.scalar(
                    select(Assignment).where(
                        Assignment.company_id == self.company_id,
                        Assignment.id == event.assignment_id,
                        Assignment.driver_membership_id == self.actor_id,
                    )
                )
        if assignment is None:
            raise DomainError("location capture requires active duty or the driver's event")
        snapshot = AttendanceLocationSnapshot(
            company_id=self.company_id,
            membership_id=self.actor_id,
            duty_session_id=active_duty.id if active_duty is not None else None,
            assignment_id=assignment.id,
            asset_id=assignment.asset_id,
            site_id=assignment.site_id,
            operational_event_id=event.id if event is not None else operational_event_id,
            captured_at_device=captured_at_device,
            received_at_server=datetime.now(UTC),
            latitude=latitude,
            longitude=longitude,
            accuracy_m=accuracy_m,
            source=source,
            status=status,
            permission_state=permission_state.strip() if permission_state else None,
        )
        self.session.add(snapshot)
        self.session.flush()
        return snapshot

    def _view(self, snapshot: AttendanceLocationSnapshot) -> LocationSnapshotView:
        threshold, freshness, _ = self._effective_settings()
        site = self.session.scalar(
            select(Site).where(Site.company_id == self.company_id, Site.id == snapshot.site_id)
        )
        geofence = self.session.scalar(
            select(SiteGeofence).where(
                SiteGeofence.company_id == self.company_id,
                SiteGeofence.site_id == snapshot.site_id,
                SiteGeofence.active.is_(True),
            )
        )
        latest = self.session.scalar(
            select(TelematicsPosition)
            .where(
                TelematicsPosition.company_id == self.company_id,
                TelematicsPosition.asset_id == snapshot.asset_id,
                TelematicsPosition.recorded_at
                >= snapshot.captured_at_device - timedelta(seconds=freshness),
                TelematicsPosition.recorded_at
                <= snapshot.captured_at_device + timedelta(seconds=freshness),
            )
            .order_by(TelematicsPosition.recorded_at.desc())
            .limit(1)
        )
        site_distance = None
        asset_distance = None
        if snapshot.latitude is not None and snapshot.longitude is not None:
            if site is not None and site.latitude is not None and site.longitude is not None:
                site_distance = haversine_distance_m(
                    snapshot.latitude, snapshot.longitude, site.latitude, site.longitude
                )
            if latest is not None:
                asset_distance = haversine_distance_m(
                    snapshot.latitude,
                    snapshot.longitude,
                    latest.latitude,
                    latest.longitude,
                )
        return LocationSnapshotView(
            snapshot,
            attendance_location_confidence(
                status=snapshot.status,
                site_distance_m=site_distance,
                site_radius_m=geofence.radius_m if geofence is not None else None,
                asset_distance_m=asset_distance,
                asset_threshold_m=threshold,
            ),
            site_distance,
            asset_distance,
        )

    def list_snapshots(self, *, membership_id: UUID | None = None) -> list[LocationSnapshotView]:
        ensure_role(self.context, MembershipRole.OWNER_ADMIN)
        query = select(AttendanceLocationSnapshot).where(
            AttendanceLocationSnapshot.company_id == self.company_id
        )
        if membership_id is not None:
            query = query.where(AttendanceLocationSnapshot.membership_id == membership_id)
        return [
            self._view(item)
            for item in self.session.scalars(
                query.order_by(
                    AttendanceLocationSnapshot.captured_at_device.desc(),
                    AttendanceLocationSnapshot.id,
                )
            )
        ]

    def purge_expired(self, *, now: datetime | None = None) -> int:
        ensure_role(self.context, MembershipRole.OWNER_ADMIN)
        settings = self.get_settings()
        retention_days = settings.retention_days if settings is not None else 30
        cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
        rows = list(
            self.session.scalars(
                select(AttendanceLocationSnapshot).where(
                    AttendanceLocationSnapshot.company_id == self.company_id,
                    AttendanceLocationSnapshot.captured_at_device < cutoff,
                )
            )
        )
        for item in rows:
            self.session.delete(item)
        self.session.flush()
        if rows:
            write_audit_log(
                self.session,
                company_id=self.company_id,
                actor_membership_id=self.actor_id,
                action="ATTENDANCE_LOCATION_RETENTION_APPLIED",
                entity_type="ATTENDANCE_LOCATION_SETTING",
                entity_id=settings.id if settings is not None else self.company_id,
                new_values={"deleted": len(rows)},
                request_id=self.request_id,
            )
        return len(rows)
