from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from fleet_api.domain.enums import (
    DevicePlatform,
    EmergencyCategory,
    KmReadingType,
    MembershipRole,
    MembershipStatus,
    OperationalEventType,
    SiteClosureStatus,
    SiteStatus,
    TipperStatus,
    VerificationStatus,
)


class OtpRequest(BaseModel):
    phone: str = Field(min_length=3, max_length=64)


class OtpRequestResponse(BaseModel):
    status: Literal["accepted"] = "accepted"
    challenge_id: UUID


class OtpVerifyRequest(BaseModel):
    challenge_id: UUID
    otp: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


class OtpVerifyResponse(BaseModel):
    status: Literal["verified"] = "verified"
    pre_session_token: str
    expires_in: int


class MembershipOption(BaseModel):
    membership_id: UUID
    company_id: UUID
    company_name: str
    role: MembershipRole


class MembershipOptionsResponse(BaseModel):
    memberships: list[MembershipOption]


class MembershipOptionsRequest(BaseModel):
    pre_session_token: str = Field(min_length=1)


class SessionRequest(BaseModel):
    pre_session_token: str = Field(min_length=1)
    membership_id: UUID


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    membership_id: UUID
    company_id: UUID
    role: MembershipRole


class WebTokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    membership_id: UUID
    company_id: UUID
    role: MembershipRole


class MeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    display_name: str
    membership_id: UUID
    company_id: UUID
    company_name: str
    role: MembershipRole


class CompanySettingsResponse(BaseModel):
    company_id: UUID
    reporting_timezone: str
    operational_day_start_minutes: int


class CompanySettingsUpdateRequest(BaseModel):
    reporting_timezone: str | None = Field(default=None, min_length=1, max_length=64)
    operational_day_start_minutes: int | None = Field(default=None, ge=0, le=1439)


class SiteCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=64)


class SiteUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=64)
    status: SiteStatus | None = None


class SiteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    code: str | None
    status: SiteStatus


class TipperCreateRequest(BaseModel):
    registration_number: str = Field(min_length=1, max_length=32)
    short_name: str | None = Field(default=None, max_length=100)


class TipperUpdateRequest(BaseModel):
    registration_number: str | None = Field(default=None, min_length=1, max_length=32)
    short_name: str | None = Field(default=None, max_length=100)
    status: TipperStatus | None = None


class TipperResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    registration_number: str
    short_name: str | None
    status: TipperStatus


class PersonCreateRequest(BaseModel):
    phone: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=1, max_length=200)
    role: Literal[MembershipRole.DRIVER, MembershipRole.SUPERVISOR]


class PersonUpdateRequest(BaseModel):
    role: Literal[MembershipRole.DRIVER, MembershipRole.SUPERVISOR] | None = None
    status: MembershipStatus | None = None


class PersonResponse(BaseModel):
    user_id: UUID
    membership_id: UUID
    phone: str
    display_name: str
    role: MembershipRole
    status: MembershipStatus
    user_status: str


class SupervisorSiteAccessCreateRequest(BaseModel):
    supervisor_membership_id: UUID
    site_id: UUID


class SupervisorSiteAccessResponse(BaseModel):
    id: UUID
    supervisor_membership_id: UUID
    supervisor_name: str
    site_id: UUID
    site_name: str


class AssignmentCreateRequest(BaseModel):
    driver_membership_id: UUID
    supervisor_membership_id: UUID
    tipper_id: UUID
    site_id: UUID
    starts_at: datetime
    ends_at: datetime | None = None


class AssignmentCloseRequest(BaseModel):
    ends_at: datetime


class AssignmentResponse(BaseModel):
    id: UUID
    driver_membership_id: UUID
    driver_name: str
    supervisor_membership_id: UUID
    supervisor_name: str
    tipper_id: UUID
    registration_number: str
    site_id: UUID
    site_name: str
    starts_at: datetime
    ends_at: datetime | None


class DriverAssignmentResponse(BaseModel):
    assignment_id: UUID
    tipper_id: UUID
    tipper_registration_number: str
    tipper_short_name: str | None
    site_id: UUID
    site_name: str
    supervisor_name: str


class DriverDeviceRequest(BaseModel):
    installation_identifier: str = Field(min_length=1, max_length=200)
    platform: DevicePlatform


class DriverDeviceResponse(BaseModel):
    device_id: UUID
    installation_identifier: str
    platform: DevicePlatform


class DriverEventRequest(BaseModel):
    client_event_uuid: UUID
    event_type: OperationalEventType
    device_created_at: datetime
    installation_identifier: str = Field(min_length=1, max_length=200)
    platform: DevicePlatform
    reading_type: KmReadingType | None = None
    reading_value: Decimal | None = Field(default=None, ge=0)
    litres: Decimal | None = Field(default=None, gt=0)
    category: EmergencyCategory | None = None
    description: str | None = Field(default=None, max_length=500)
    object_reference: str | None = Field(default=None, max_length=500)


class DriverEventResponse(BaseModel):
    event_id: UUID
    client_event_uuid: UUID
    status: Literal["accepted", "already_accepted"]
    verification_status: str


class EvidenceUploadResponse(BaseModel):
    client_event_uuid: UUID
    object_reference: str
    content_type: str
    size_bytes: int


class SupervisorSiteResponse(BaseModel):
    id: UUID
    name: str
    code: str | None
    status: SiteStatus


class SupervisorVerificationHistoryResponse(BaseModel):
    status: VerificationStatus
    reason: str | None
    actor_name: str | None
    created_at: datetime


class SupervisorEventResponse(BaseModel):
    event_id: UUID
    event_type: OperationalEventType
    assignment_id: UUID
    driver_name: str
    driver_phone: str | None
    tipper_registration_number: str
    site_id: UUID
    site_name: str
    device_created_at: datetime
    server_received_at: datetime
    verification_status: VerificationStatus
    reading_type: KmReadingType | None
    reading_value: Decimal | None
    litres: Decimal | None
    emergency_category: EmergencyCategory | None
    emergency_status: str | None
    emergency_description: str | None
    evidence_id: UUID | None
    evidence_available: bool
    verification_history: list[SupervisorVerificationHistoryResponse]


class SupervisorVerificationRequest(BaseModel):
    decision: Literal["APPROVED", "REJECTED", "DISPUTED"]
    reason: str | None = Field(default=None, max_length=1000)
    expected_status: VerificationStatus = VerificationStatus.PENDING_VERIFICATION


class SupervisorBatchVerificationRequest(SupervisorVerificationRequest):
    event_ids: list[UUID] = Field(min_length=1, max_length=100)


class SupervisorBatchVerificationResponse(BaseModel):
    events: list[SupervisorEventResponse]


class SupervisorCompletenessResponse(BaseModel):
    assignment_id: UUID
    driver_name: str
    tipper_registration_number: str
    site_id: UUID
    site_name: str
    has_start_reading: bool
    has_end_reading: bool
    start_reading_value: Decimal | None
    end_reading_value: Decimal | None
    odometer_regression: bool
    pending_trip_verification: bool
    pending_diesel_verification: bool
    unresolved_emergency: bool


class ReportHistoryResponse(BaseModel):
    status: VerificationStatus
    actor_name: str | None
    reason: str | None
    created_at: datetime


class ReportEventResponse(BaseModel):
    event_id: UUID
    event_type: OperationalEventType
    assignment_id: UUID
    tipper_id: UUID
    tipper_registration_number: str
    site_id: UUID
    site_name: str
    driver_name: str
    driver_phone: str | None
    supervisor_name: str
    device_created_at: datetime
    server_received_at: datetime
    verification_status: VerificationStatus
    reading_type: str | None
    reading_value: Decimal | None
    litres: Decimal | None
    emergency_category: str | None
    emergency_status: str | None
    emergency_description: str | None
    evidence_available: bool
    verification_history: list[ReportHistoryResponse]


class ReportExceptionResponse(BaseModel):
    code: str
    description: str
    assignment_id: UUID
    tipper_id: UUID
    tipper_registration_number: str
    site_id: UUID
    event_id: UUID | None


class TipperDailyReportResponse(BaseModel):
    assignment_id: UUID
    tipper_id: UUID
    registration_number: str
    short_name: str | None
    site_id: UUID
    site_name: str
    driver_name: str
    supervisor_name: str
    assignment_starts_at: datetime
    assignment_ends_at: datetime | None
    approved_trip_count: int
    pending_trip_count: int
    disputed_trip_count: int
    rejected_trip_count: int
    start_km: Decimal | None
    end_km: Decimal | None
    distance_km: Decimal | None
    km_per_approved_trip: Decimal | None
    verified_diesel_issued: Decimal
    diesel_issued_per_approved_trip: Decimal | None
    first_trip_completed_at: datetime | None
    last_trip_completed_at: datetime | None
    recorded_activity_span_seconds: float | None
    avg_trip_completion_interval_seconds: float | None
    median_trip_completion_interval_seconds: float | None
    longest_trip_gap_seconds: float | None
    pending_diesel_count: int
    disputed_diesel_count: int
    unresolved_emergency_count: int
    missing_start_reading: bool
    missing_end_reading: bool
    completeness_status: str
    closure_status: SiteClosureStatus
    exceptions: list[ReportExceptionResponse]
    events: list[ReportEventResponse]


class ClosureHistoryResponse(BaseModel):
    status: SiteClosureStatus
    actor_name: str | None
    reason: str | None
    created_at: datetime


class ClosureResponse(BaseModel):
    site_id: UUID
    site_name: str
    operational_date: date
    reporting_timezone: str
    workday_start_minutes: int
    status: SiteClosureStatus
    blockers: list[ReportExceptionResponse]
    history: list[ClosureHistoryResponse]


class SiteDailyReportResponse(BaseModel):
    site_id: UUID
    site_name: str
    operational_date: date
    reporting_timezone: str
    assigned_tippers_count: int
    approved_trip_count: int
    pending_trip_count: int
    disputed_trip_count: int
    total_km: Decimal | None
    verified_diesel_issued: Decimal
    missing_reading_count: int
    unresolved_emergency_count: int
    closure: ClosureResponse
    tippers: list[TipperDailyReportResponse]


class DashboardResponse(BaseModel):
    operational_date: date
    reporting_timezone: str
    workday_start_minutes: int
    assigned_tippers_count: int
    approved_trip_count: int
    pending_trip_count: int
    total_km: Decimal | None
    verified_diesel_issued: Decimal
    pending_verification_count: int
    missing_reading_count: int
    unresolved_emergency_count: int
    sites_not_closed_count: int
    complete_tippers_count: int
    sites: list[SiteDailyReportResponse]
    exceptions: list[ReportExceptionResponse]


class ClosureActionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)
