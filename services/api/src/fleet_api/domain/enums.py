from enum import StrEnum


class CompanyStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class MembershipRole(StrEnum):
    OWNER_ADMIN = "OWNER_ADMIN"
    SUPERVISOR = "SUPERVISOR"
    DRIVER = "DRIVER"


class MembershipStatus(StrEnum):
    INVITED = "INVITED"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class OtpChallengeStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CONSUMED = "CONSUMED"
    EXPIRED = "EXPIRED"
    EXHAUSTED = "EXHAUSTED"
    CANCELLED = "CANCELLED"


class SiteStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class FleetAssetType(StrEnum):
    TIPPER = "TIPPER"
    EXCAVATOR = "EXCAVATOR"
    BACKHOE_LOADER = "BACKHOE_LOADER"
    ROLLER = "ROLLER"
    GRADER = "GRADER"


class AssetOwnershipType(StrEnum):
    OWNED = "OWNED"
    RENTED = "RENTED"


class FleetAssetStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class DevicePlatform(StrEnum):
    ANDROID = "ANDROID"
    IOS = "IOS"
    WEB = "WEB"
    OTHER = "OTHER"


class DeviceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class OperationalEventType(StrEnum):
    TRIP_COMPLETE = "TRIP_COMPLETE"
    KM_READING = "KM_READING"
    HMR_READING = "HMR_READING"
    DIESEL = "DIESEL"
    EMERGENCY = "EMERGENCY"


class VerificationStatus(StrEnum):
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DISPUTED = "DISPUTED"
    AMENDED = "AMENDED"


class KmReadingType(StrEnum):
    START_READING = "START_READING"
    END_READING = "END_READING"


class HourMeterReadingType(StrEnum):
    START_READING = "START_READING"
    END_READING = "END_READING"


class DutySessionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class EmergencyCategory(StrEnum):
    BREAKDOWN = "BREAKDOWN"
    ACCIDENT = "ACCIDENT"
    TYRE_OR_VEHICLE_PROBLEM = "TYRE_OR_VEHICLE_PROBLEM"
    CONTACT_SUPERVISOR = "CONTACT_SUPERVISOR"


class EmergencyStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class SiteClosureStatus(StrEnum):
    OPEN = "OPEN"
    READY_TO_CLOSE = "READY_TO_CLOSE"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"


class MaintenanceBasis(StrEnum):
    KM = "KM"
    HMR = "HMR"
    DATE = "DATE"


class MaintenanceScheduleStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class MaintenanceDueStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    NOT_DUE = "NOT_DUE"
    DUE_SOON = "DUE_SOON"
    DUE = "DUE"
    OVERDUE = "OVERDUE"


class MaintenanceWorkOrderStatus(StrEnum):
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class MeterType(StrEnum):
    ODOMETER_KM = "ODOMETER_KM"
    HOUR_METER_HOURS = "HOUR_METER_HOURS"


class MaintenanceCriterionBasis(StrEnum):
    ODOMETER_KM = "ODOMETER_KM"
    HOUR_METER_HOURS = "HOUR_METER_HOURS"
    CALENDAR_TIME = "CALENDAR_TIME"


class AssetDocumentExpiryStatus(StrEnum):
    VALID = "VALID"
    EXPIRING_SOON = "EXPIRING_SOON"
    EXPIRED = "EXPIRED"
    NO_EXPIRY = "NO_EXPIRY"
    MISSING = "MISSING"
    NOT_REQUIRED = "NOT_REQUIRED"
    UNKNOWN = "UNKNOWN"


class NotificationState(StrEnum):
    UNREAD = "UNREAD"
    READ = "READ"
    ACKNOWLEDGED = "ACKNOWLEDGED"


class GeofenceTransitionType(StrEnum):
    ENTER = "ENTER"
    EXIT = "EXIT"


class FuelImportRowStatus(StrEnum):
    IMPORTED = "IMPORTED"
    DUPLICATE = "DUPLICATE"
    INVALID = "INVALID"
    UNMAPPED = "UNMAPPED"


class FuelImportBatchStatus(StrEnum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"


class PayBasis(StrEnum):
    MONTHLY = "MONTHLY"
    DAILY = "DAILY"
    HOURLY = "HOURLY"


class PayrollPeriodStatus(StrEnum):
    DRAFT = "DRAFT"
    REVIEWED = "REVIEWED"
    FINALIZED = "FINALIZED"


class AttendanceCalculationState(StrEnum):
    COMPLETE = "COMPLETE"
    OPEN_SESSION = "OPEN_SESSION"
    OVERLAP_EXCEPTION = "OVERLAP_EXCEPTION"
    MISSING_DATA = "MISSING_DATA"


class LocationSnapshotStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    DENIED = "DENIED"
    LOW_ACCURACY = "LOW_ACCURACY"


class LocationSnapshotSource(StrEnum):
    DUTY_START = "DUTY_START"
    DUTY_END = "DUTY_END"
    METER_SUBMISSION = "METER_SUBMISSION"
    DIESEL_SUBMISSION = "DIESEL_SUBMISSION"
    TRIP_COMPLETE = "TRIP_COMPLETE"
    EMERGENCY = "EMERGENCY"


class AttendanceConfidence(StrEnum):
    STRONG_MATCH = "STRONG_MATCH"
    SITE_MATCH = "SITE_MATCH"
    ASSET_PROXIMITY_MATCH = "ASSET_PROXIMITY_MATCH"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    MISMATCH = "MISMATCH"
    UNKNOWN = "UNKNOWN"


class MeterDiscrepancyStatus(StrEnum):
    WITHIN_TOLERANCE = "WITHIN_TOLERANCE"
    MISMATCH = "MISMATCH"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class NotificationChannel(StrEnum):
    IN_APP = "IN_APP"
    PUSH = "PUSH"
    SMS = "SMS"
    EMAIL = "EMAIL"


class NotificationCategory(StrEnum):
    EMERGENCY = "EMERGENCY"
    DIESEL_PENDING = "DIESEL_PENDING"
    TRIP_PENDING = "TRIP_PENDING"
    METER_PENDING = "METER_PENDING"
    MAINTENANCE_DUE = "MAINTENANCE_DUE"
    DOCUMENT_EXPIRY = "DOCUMENT_EXPIRY"
    ASSIGNMENT_CHANGED = "ASSIGNMENT_CHANGED"
    SYSTEM = "SYSTEM"


class DeliveryStatus(StrEnum):
    DISABLED = "DISABLED"
    ACCEPTED = "ACCEPTED"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


class FuelSourceType(StrEnum):
    DRIVER_ENTRY = "DRIVER_ENTRY"
    BUNK_DISPENSER = "BUNK_DISPENSER"
    FUEL_CARD = "FUEL_CARD"
    TANK_SENSOR = "TANK_SENSOR"
    SUPPLIER = "SUPPLIER"
    OTHER = "OTHER"


class FuelReconciliationStatus(StrEnum):
    MATCHED = "MATCHED"
    WITHIN_TOLERANCE = "WITHIN_TOLERANCE"
    MISMATCH = "MISMATCH"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    AMBIGUOUS = "AMBIGUOUS"


class ExpenseCategory(StrEnum):
    TOLL = "TOLL"
    PARKING = "PARKING"
    FUEL = "FUEL"
    REPAIR = "REPAIR"
    SITE_EXPENSE = "SITE_EXPENSE"
    OTHER = "OTHER"
