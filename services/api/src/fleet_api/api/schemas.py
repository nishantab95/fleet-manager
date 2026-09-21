from __future__ import annotations

from datetime import datetime
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
    SiteStatus,
    TipperStatus,
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


class MeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    display_name: str
    membership_id: UUID
    company_id: UUID
    company_name: str
    role: MembershipRole


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
