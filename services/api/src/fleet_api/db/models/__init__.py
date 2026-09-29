"""SQLAlchemy models for the core domain and authentication boundary."""

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
    KmReading,
    OperationalEvent,
    TripEvent,
)
from fleet_api.db.models.evidence import EvidenceObject
from fleet_api.db.models.fleet_asset import FleetAsset
from fleet_api.db.models.membership import CompanyMembership, SupervisorSiteAccess

__all__ = [
    "Assignment",
    "AssetSiteDeployment",
    "AuditLog",
    "AuthSession",
    "Company",
    "CompanyMembership",
    "Device",
    "DutySession",
    "DieselEvent",
    "EmergencyEvent",
    "EventVerification",
    "EvidenceObject",
    "FleetAsset",
    "KmReading",
    "OperationalEvent",
    "OtpChallenge",
    "Site",
    "SiteDailyClosure",
    "SiteDailyClosureHistory",
    "SupervisorSiteAccess",
    "TripEvent",
    "User",
]
