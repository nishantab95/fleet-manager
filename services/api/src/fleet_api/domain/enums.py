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


class TipperStatus(StrEnum):
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
