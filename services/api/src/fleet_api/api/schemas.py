from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fleet_api.domain.enums import (
    AssetOwnershipType,
    DevicePlatform,
    EmergencyCategory,
    FleetAssetStatus,
    FleetAssetType,
    KmReadingType,
    MembershipRole,
    MembershipStatus,
    OperationalEventType,
    OwnerOperationAction,
    SiteClosureStatus,
    SiteStatus,
    VerificationStatus,
)


class OtpRequest(BaseModel):
    phone: str = Field(min_length=3, max_length=64)
    requested_role: MembershipRole | None = None


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
    short_name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=64)


class SiteUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    short_name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=64)
    status: SiteStatus | None = None


class SiteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    short_name: str
    code: str
    status: SiteStatus


class TipperCreateRequest(BaseModel):
    registration_number: str = Field(min_length=1, max_length=32)
    short_name: str | None = Field(default=None, max_length=100)


class TipperUpdateRequest(BaseModel):
    registration_number: str | None = Field(default=None, min_length=1, max_length=32)
    short_name: str | None = Field(default=None, max_length=100)
    status: FleetAssetStatus | None = None


class TipperResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    registration_number: str
    short_name: str | None
    status: FleetAssetStatus


class OwnerAssetCreateRequest(BaseModel):
    asset_code: str | None = Field(default=None, min_length=1, max_length=64)
    asset_type: FleetAssetType = FleetAssetType.TIPPER
    ownership_type: AssetOwnershipType
    registration_number: str | None = Field(default=None, min_length=1, max_length=32)
    short_name: str | None = Field(default=None, max_length=100)
    manufacturer: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    chassis_number: str | None = Field(default=None, max_length=100)
    engine_number: str | None = Field(default=None, max_length=100)
    rental_party_name: str | None = Field(default=None, max_length=200)
    rental_owner_phone_primary: str | None = Field(default=None, max_length=64)
    rental_owner_phone_secondary: str | None = Field(default=None, max_length=64)
    rental_start_date: date | None = None
    rental_end_date: date | None = None


class OwnerAssetUpdateRequest(BaseModel):
    asset_code: str | None = Field(default=None, min_length=1, max_length=64)
    ownership_type: AssetOwnershipType | None = None
    registration_number: str | None = Field(default=None, min_length=1, max_length=32)
    short_name: str | None = Field(default=None, max_length=100)
    manufacturer: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    chassis_number: str | None = Field(default=None, max_length=100)
    engine_number: str | None = Field(default=None, max_length=100)
    rental_party_name: str | None = Field(default=None, max_length=200)
    rental_owner_phone_primary: str | None = Field(default=None, max_length=64)
    rental_owner_phone_secondary: str | None = Field(default=None, max_length=64)
    rental_start_date: date | None = None
    rental_end_date: date | None = None


class OwnerAssetAssignmentResponse(BaseModel):
    assignment_id: UUID
    site_id: UUID
    site_name: str
    driver_membership_id: UUID
    driver_name: str
    driver_phone: str
    starts_at: datetime
    regular_duty_minutes: int


class DriverAssetAssignmentRequest(BaseModel):
    driver_membership_id: UUID
    regular_duty_minutes: int | None = Field(default=None, ge=1, le=1440)


class DriverCandidateResponse(BaseModel):
    membership_id: UUID
    display_name: str
    phone: str
    status: MembershipStatus


class DriverAssetAssignmentResponse(BaseModel):
    assignment_id: UUID
    asset_id: UUID
    asset_code: str
    registration_number: str | None
    driver_membership_id: UUID
    driver_name: str
    asset_site_deployment_id: UUID
    site_id: UUID
    site_name: str
    starts_at: datetime
    ends_at: datetime | None
    regular_duty_minutes: int


class AssetSiteDeploymentResponse(BaseModel):
    id: UUID
    asset_id: UUID
    site_id: UUID
    site_name: str
    starts_at: datetime
    ends_at: datetime | None


class AssetDeploymentRequest(BaseModel):
    site_id: UUID


class DeploymentRemovalRequest(BaseModel):
    expected_deployment_id: UUID
    expected_assignment_id: UUID | None
    expected_duty_status: Literal["UNASSIGNED", "OFF_DUTY", "ON_DUTY"]


class DeploymentRemovalPlanResponse(BaseModel):
    asset_id: UUID
    asset_code: str
    registration_number: str | None
    short_name: str | None
    deployment_id: UUID
    site_id: UUID
    site_name: str
    assignment_id: UUID | None
    driver_membership_id: UUID | None
    driver_name: str | None
    duty_status: Literal["UNASSIGNED", "OFF_DUTY", "ON_DUTY"]


class OwnerOperationAssetResolutionRequest(BaseModel):
    asset_id: UUID
    action: Literal["MOVE", "REMOVE"]
    target_site_id: UUID | None = None
    assignment_action: Literal["KEEP", "END"] | None = None


class OwnerOperationRequest(BaseModel):
    action: OwnerOperationAction
    asset_id: UUID | None = None
    person_membership_id: UUID | None = None
    site_id: UUID | None = None
    target_site_id: UUID | None = None
    driver_membership_id: UUID | None = None
    selected_site_ids: list[UUID] = Field(default_factory=list, max_length=200)
    selected_supervisor_ids: list[UUID] = Field(default_factory=list, max_length=200)
    selected_asset_ids: list[UUID] = Field(default_factory=list, max_length=500)
    asset_resolutions: list[OwnerOperationAssetResolutionRequest] = Field(
        default_factory=list,
        max_length=500,
    )
    assignment_action: Literal["KEEP", "END"] | None = None
    activate_membership: bool = False
    regular_duty_minutes: int = Field(default=600, ge=1, le=1440)
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_force_close_reason(self) -> OwnerOperationRequest:
        if self.reason is not None:
            self.reason = self.reason.strip()
        if (
            self.action == OwnerOperationAction.FORCE_CLOSE_DUTY_AND_DEACTIVATE_ASSET
            and not self.reason
        ):
            raise ValueError("reason is required for administrative duty closure")
        return self


class OwnerOperationExecuteRequest(OwnerOperationRequest):
    state_token: str = Field(min_length=64, max_length=64)


class OwnerOperationItemResponse(BaseModel):
    kind: str
    id: UUID
    label: str
    status: str
    details: dict[str, str | int | bool | None] = Field(default_factory=dict)


class OwnerOperationPlanResponse(BaseModel):
    action: OwnerOperationAction
    state_token: str
    title: str
    summary: str
    current_state: list[OwnerOperationItemResponse]
    dependencies: list[OwnerOperationItemResponse]
    warnings: list[str]
    allowed_resolutions: list[str]
    blocked_reasons: list[str]
    planned_changes: list[str]
    can_execute: bool


class OwnerOperationResultResponse(BaseModel):
    action: OwnerOperationAction
    completed_changes: list[str]
    message: str


class SiteDeployedAssetResponse(BaseModel):
    asset_id: UUID
    asset_code: str
    asset_type: FleetAssetType
    ownership_type: AssetOwnershipType
    registration_number: str | None
    short_name: str | None
    status: FleetAssetStatus
    current_deployment: AssetSiteDeploymentResponse
    driver_membership_id: UUID | None
    driver_name: str | None
    duty_status: str | None
    pending_review_count: int


class OwnerAssetResponse(BaseModel):
    id: UUID
    asset_code: str
    asset_type: FleetAssetType
    ownership_type: AssetOwnershipType
    registration_number: str | None
    short_name: str | None
    manufacturer: str | None
    model: str | None
    chassis_number: str | None
    engine_number: str | None
    status: FleetAssetStatus
    rental_party_name: str | None
    rental_owner_phone_primary: str | None
    rental_owner_phone_secondary: str | None
    rental_start_date: date | None
    rental_end_date: date | None
    current_deployment: AssetSiteDeploymentResponse | None
    has_active_assignment: bool
    active_assignment: OwnerAssetAssignmentResponse | None


class OwnerPersonInviteRequest(BaseModel):
    phone: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=1, max_length=200)
    role: Literal[MembershipRole.DRIVER, MembershipRole.SUPERVISOR]


class OwnerPersonUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    role: Literal[MembershipRole.DRIVER, MembershipRole.SUPERVISOR] | None = None


class OwnerPersonSiteResponse(BaseModel):
    site_id: UUID
    site_name: str


class OwnerPersonResponse(BaseModel):
    user_id: UUID
    membership_id: UUID
    phone: str
    display_name: str
    role: MembershipRole
    status: MembershipStatus
    sites: list[OwnerPersonSiteResponse]
    has_active_assignment: bool
    has_active_duty: bool
    current_asset_id: UUID | None
    current_asset_code: str | None
    current_site_id: UUID | None
    current_site_name: str | None


class OwnerSiteCreateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    short_name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=64)
    location_description: str | None = Field(default=None, max_length=500)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)


class OwnerSiteUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    short_name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=64)
    location_description: str | None = Field(default=None, max_length=500)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)


class OwnerSiteSupervisorRequest(BaseModel):
    supervisor_membership_id: UUID


class OwnerSiteSupervisorResponse(BaseModel):
    access_id: UUID
    membership_id: UUID
    display_name: str


class OwnerSiteResponse(BaseModel):
    id: UUID
    name: str
    short_name: str
    code: str
    location_description: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    status: SiteStatus
    supervisors: list[OwnerSiteSupervisorResponse]
    asset_count: int


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
    regular_duty_minutes: int = Field(default=600, ge=1, le=1440)


class AssignmentCloseRequest(BaseModel):
    ends_at: datetime


class AssignmentResponse(BaseModel):
    id: UUID
    driver_membership_id: UUID
    driver_name: str
    supervisor_membership_id: UUID | None
    supervisor_name: str
    tipper_id: UUID
    registration_number: str
    site_id: UUID
    site_name: str
    starts_at: datetime
    ends_at: datetime | None
    regular_duty_minutes: int


class DriverAssignmentResponse(BaseModel):
    assignment_id: UUID
    tipper_id: UUID
    asset_code: str
    asset_type: FleetAssetType
    tipper_registration_number: str | None
    tipper_short_name: str | None
    site_id: UUID
    site_name: str
    supervisor_name: str | None
    supervisor_names: list[str] = Field(default_factory=list)
    regular_duty_minutes: int


class DriverDutyStateResponse(BaseModel):
    status: Literal["NONE", "ACTIVE", "CLOSED"]
    session_id: UUID | None = None
    assignment_id: UUID | None = None
    tipper_id: UUID | None = None
    site_id: UUID | None = None
    started_at: datetime | None = None
    start_km: Decimal | None = None
    ended_at: datetime | None = None
    end_km: Decimal | None = None
    start_hmr: Decimal | None = None
    end_hmr: Decimal | None = None
    machine_hours: Decimal | None = None
    regular_duty_minutes: int | None = None


class DriverDeviceRequest(BaseModel):
    installation_identifier: str = Field(min_length=1, max_length=200)
    platform: DevicePlatform
    allow_handover: bool = False
    local_state_clear: bool = False


class DriverDeviceResponse(BaseModel):
    device_id: UUID
    installation_identifier: str
    platform: DevicePlatform
    membership_id: UUID
    handed_over: bool = False


class DriverEventRequest(BaseModel):
    client_event_uuid: UUID
    event_type: OperationalEventType
    device_created_at: datetime
    installation_identifier: str = Field(min_length=1, max_length=200)
    platform: DevicePlatform
    reading_type: KmReadingType | None = None
    # KM bounds and finiteness are validated in the domain so every malformed,
    # negative, or excessive reading gets the same structured API error.
    reading_value: Decimal | str | None = Field(default=None)
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
    short_name: str
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
    duty_session_id: UUID | None
    driver_name: str
    driver_phone: str | None
    asset_code: str
    asset_short_name: str | None
    asset_type: FleetAssetType
    tipper_registration_number: str
    site_id: UUID
    site_name: str
    device_created_at: datetime
    server_received_at: datetime
    verification_status: VerificationStatus
    reading_type: str | None
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
    duty_session_id: UUID | None
    tipper_id: UUID
    tipper_registration_number: str
    asset_code: str
    asset_type: FleetAssetType
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
    asset_type: FleetAssetType
    site_id: UUID
    site_name: str
    driver_name: str
    supervisor_name: str
    assignment_starts_at: datetime
    assignment_ends_at: datetime | None
    approved_trip_count: int | None
    pending_trip_count: int | None
    disputed_trip_count: int | None
    rejected_trip_count: int | None
    trips_state: Literal["NOT_APPLICABLE", "MISSING", "ZERO", "VALUE"]
    start_km: Decimal | None
    end_km: Decimal | None
    start_hmr: Decimal | None = None
    end_hmr: Decimal | None = None
    machine_hours: Decimal | None = None
    distance_state: Literal["NOT_APPLICABLE", "MISSING", "ZERO", "VALUE"]
    machine_hours_state: Literal["NOT_APPLICABLE", "MISSING", "ZERO", "VALUE"]
    distance_km: Decimal | None
    km_per_approved_trip: Decimal | None
    verified_diesel_issued: Decimal
    pending_diesel_issued: Decimal
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
    drivers_on_duty: int = 0
    drivers_past_regular_duty: int = 0
    closed_duties_count: int = 0
    sites: list[SiteDailyReportResponse]
    exceptions: list[ReportExceptionResponse]


class DriverDutyReportResponse(BaseModel):
    operational_date: date
    session_id: UUID
    assignment_id: UUID
    driver_name: str
    asset_code: str
    tipper_registration_number: str
    site_name: str
    duty_start: datetime
    asset_type: FleetAssetType
    start_km: Decimal | None
    start_hmr: Decimal | None = None
    regular_duty_minutes: int
    regular_duty_ends_at: datetime
    actual_duty_end: datetime | None
    end_km: Decimal | None
    end_hmr: Decimal | None = None
    machine_hours: Decimal | None = None
    verified_diesel_issued: Decimal = Decimal("0")
    pending_diesel_issued: Decimal = Decimal("0")
    actual_duty_span_seconds: float | None
    overtime_minutes: int
    status: Literal["ACTIVE", "CLOSED"]


class ReportTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    builtin_key: str | None
    is_builtin: bool
    is_default: bool
    included_sheets: list[str]
    management_dashboard_columns: list[str]
    tipper_daily_columns: list[str]
    machinery_daily_columns: list[str]
    created_at: datetime
    updated_at: datetime


class ReportTemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    included_sheets: list[str] = Field(min_length=1, max_length=8)
    management_dashboard_columns: list[str] = Field(min_length=1)
    tipper_daily_columns: list[str] = Field(min_length=1)
    machinery_daily_columns: list[str] = Field(min_length=1)


class ReportTemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    included_sheets: list[str] | None = Field(default=None, min_length=1, max_length=8)
    management_dashboard_columns: list[str] | None = Field(default=None, min_length=1)
    tipper_daily_columns: list[str] | None = Field(default=None, min_length=1)
    machinery_daily_columns: list[str] | None = Field(default=None, min_length=1)


class ReportTemplateDuplicateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ClosureActionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)
