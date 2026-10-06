"""SQLAlchemy models for the core domain and authentication boundary."""

from fleet_api.db.models.asset_document import (
    AssetDocument,
    AssetDocumentPolicy,
    AssetDocumentRevision,
)
from fleet_api.db.models.assignment import Assignment
from fleet_api.db.models.audit import AuditLog
from fleet_api.db.models.auth import AuthSession, OtpChallenge
from fleet_api.db.models.closure import SiteDailyClosure, SiteDailyClosureHistory
from fleet_api.db.models.company import Company, Site, User
from fleet_api.db.models.deployment import AssetSiteDeployment
from fleet_api.db.models.device import Device
from fleet_api.db.models.duty import DutySession
from fleet_api.db.models.events import (
    DieselEvent,
    EmergencyEvent,
    EventVerification,
    HourMeterReading,
    KmReading,
    OperationalEvent,
    TripEvent,
)
from fleet_api.db.models.evidence import EvidenceObject
from fleet_api.db.models.fleet_asset import FleetAsset
from fleet_api.db.models.future_modules import (
    ExternalFuelTransaction,
    FuelImportBatch,
    FuelReconciliation,
    GeofenceTransition,
    InAppNotification,
    SiteGeofence,
    TelematicsMeterDiscrepancy,
    TelematicsPosition,
    TelematicsVehicleMapping,
)
from fleet_api.db.models.maintenance import (
    MaintenanceAttachment,
    MaintenanceCriterion,
    MaintenanceRecord,
    MaintenanceSchedule,
    MaintenanceWorkOrder,
)
from fleet_api.db.models.membership import CompanyMembership, SupervisorSiteAccess
from fleet_api.db.models.report_template import ReportTemplate
from fleet_api.db.models.workforce import (
    AttendanceLocationSetting,
    AttendanceLocationSnapshot,
    CompensationProfile,
    PayrollAdjustment,
    PayrollLine,
    PayrollPeriod,
)

__all__ = [
    "Assignment",
    "AssetDocument",
    "AssetDocumentPolicy",
    "AssetDocumentRevision",
    "AssetSiteDeployment",
    "AttendanceLocationSetting",
    "AttendanceLocationSnapshot",
    "AuditLog",
    "AuthSession",
    "Company",
    "CompanyMembership",
    "CompensationProfile",
    "Device",
    "DutySession",
    "DieselEvent",
    "EmergencyEvent",
    "EventVerification",
    "EvidenceObject",
    "ExternalFuelTransaction",
    "FleetAsset",
    "FuelImportBatch",
    "FuelReconciliation",
    "GeofenceTransition",
    "HourMeterReading",
    "KmReading",
    "InAppNotification",
    "MaintenanceAttachment",
    "MaintenanceCriterion",
    "MaintenanceRecord",
    "MaintenanceSchedule",
    "MaintenanceWorkOrder",
    "OperationalEvent",
    "OtpChallenge",
    "PayrollAdjustment",
    "PayrollLine",
    "PayrollPeriod",
    "ReportTemplate",
    "Site",
    "SiteGeofence",
    "SiteDailyClosure",
    "SiteDailyClosureHistory",
    "SupervisorSiteAccess",
    "TelematicsPosition",
    "TelematicsMeterDiscrepancy",
    "TelematicsVehicleMapping",
    "TripEvent",
    "User",
]
