from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from fleet_api.domain.enums import MembershipRole


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
