from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from fleet_api.domain.enums import (
    FleetAssetType,
    MaintenanceActionType,
    MaintenanceCriterionBasis,
    MaintenanceDueState,
    MaintenancePlanSource,
    MaintenanceProofStatus,
    MaintenanceResponsibility,
    MaintenanceTaskCode,
    MaintenanceTemplateApplicability,
    MaintenanceTemplateCategory,
    MaintenanceTemplateConfidence,
    MaintenanceTemplateSourceType,
    MaintenanceTemplateType,
    MaintenanceTemplateVerificationStatus,
    MaintenanceWorkOrderStatus,
)


class MaintenanceCriterionRequest(BaseModel):
    basis: MaintenanceCriterionBasis
    enabled: bool = True
    interval_value: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    warning_value: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    baseline_value: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    baseline_date: date | None = None


class MaintenanceScheduleRequest(BaseModel):
    task_code: MaintenanceTaskCode
    custom_label: str | None = Field(default=None, max_length=200)
    action_type: MaintenanceActionType
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool = True
    criteria: list[MaintenanceCriterionRequest] = Field(default_factory=list, max_length=3)


class MaintenanceCriterionResponse(BaseModel):
    id: UUID
    basis: MaintenanceCriterionBasis
    enabled: bool
    interval_value: Decimal
    warning_value: Decimal
    baseline_value: Decimal | None
    baseline_date: date | None
    state: MaintenanceDueState
    current_value: Decimal | None
    due_value: Decimal | None
    current_date: date | None
    due_date: date | None


class MaintenanceScheduleResponse(BaseModel):
    id: UUID
    asset_id: UUID
    task_code: MaintenanceTaskCode
    task_label: str
    action_type: MaintenanceActionType
    description: str | None
    enabled: bool
    state: MaintenanceDueState
    triggered_by: list[MaintenanceCriterionBasis]
    criteria: list[MaintenanceCriterionResponse]


class MaintenancePlanResponse(BaseModel):
    id: UUID | None
    asset_id: UUID
    asset_code: str
    asset_type: FleetAssetType
    manufacturer: str | None
    model: str | None
    model_year: int | None
    is_wheeled: bool
    supports_odometer_km: bool
    supports_hour_meter: bool
    maintenance_responsibility: MaintenanceResponsibility
    managed_by_current_company: bool
    management_message: str | None = None
    source: MaintenancePlanSource | None
    source_template_id: UUID | None
    source_template_version: str | None
    items: list[MaintenanceScheduleResponse]


class MaintenanceDueItemResponse(MaintenanceScheduleResponse):
    asset_code: str
    site_name: str | None


class MaintenanceOverviewResponse(BaseModel):
    overdue: int
    due: int
    due_soon: int
    unknown: int
    open_work_orders: int
    items: list[MaintenanceDueItemResponse]


class MaintenanceTaskCatalogResponse(BaseModel):
    code: MaintenanceTaskCode
    label: str
    default_action: MaintenanceActionType
    suggested_for_asset: bool


class MaintenanceWorkOrderCreateRequest(BaseModel):
    asset_id: UUID
    schedule_id: UUID | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    scheduled_for: date | None = None


class MaintenanceWorkOrderTransitionRequest(BaseModel):
    status: MaintenanceWorkOrderStatus


class MaintenanceWorkOrderCompleteRequest(BaseModel):
    service_date: date
    odometer_km: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    hour_meter: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    vendor: str | None = Field(default=None, max_length=200)
    parts_cost: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    labor_cost: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    other_cost: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    notes: str | None = Field(default=None, max_length=4000)


class MaintenanceWorkOrderResponse(BaseModel):
    id: UUID
    asset_id: UUID
    schedule_id: UUID | None
    title: str
    description: str | None
    status: MaintenanceWorkOrderStatus
    scheduled_for: date | None
    started_at: datetime | None
    completed_at: datetime | None
    service_date: date | None
    completion_odometer_km: Decimal | None
    completion_hour_meter: Decimal | None
    vendor: str | None
    parts_cost: Decimal
    labor_cost: Decimal
    other_cost: Decimal
    total_cost: Decimal
    notes: str | None


class MaintenanceHistoryResponse(BaseModel):
    id: UUID
    work_order_id: UUID
    asset_id: UUID
    schedule_id: UUID | None
    task_code: MaintenanceTaskCode | None
    task_label: str
    service_date: date
    odometer_km: Decimal | None
    hour_meter: Decimal | None
    vendor: str | None
    parts_cost: Decimal
    labor_cost: Decimal
    other_cost: Decimal
    total_cost: Decimal
    notes: str | None
    actor_membership_id: UUID
    created_at: datetime


class MaintenanceTemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=40)
    template_type: MaintenanceTemplateType | None = None
    confidence: MaintenanceTemplateConfidence | None = None
    category: MaintenanceTemplateCategory | None = None
    applicability: MaintenanceTemplateApplicability | None = None
    source_name: str = Field(default="Company maintenance policy", min_length=1, max_length=200)
    source_type: MaintenanceTemplateSourceType
    source_reference: str | None = Field(default=None, max_length=500)
    verification_status: MaintenanceTemplateVerificationStatus
    asset_type: FleetAssetType | None = None
    manufacturer: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    model_year_min: int | None = Field(default=None, ge=1900, le=2200)
    model_year_max: int | None = Field(default=None, ge=1900, le=2200)
    notes: str | None = Field(default=None, max_length=4000)
    is_generic: bool = False

    @model_validator(mode="after")
    def validate_oem_metadata(self) -> MaintenanceTemplateCreateRequest:
        resolved_type = self.template_type or (
            MaintenanceTemplateType.OEM_VERIFIED
            if self.source_type == MaintenanceTemplateSourceType.OEM
            and self.verification_status == MaintenanceTemplateVerificationStatus.VERIFIED
            else MaintenanceTemplateType.COMPANY_STARTER
        )
        resolved_confidence = self.confidence or (
            MaintenanceTemplateConfidence.VERIFIED
            if resolved_type == MaintenanceTemplateType.OEM_VERIFIED
            else MaintenanceTemplateConfidence.SUGGESTED
        )
        if (
            resolved_type == MaintenanceTemplateType.COMPANY_STARTER
            and resolved_confidence != MaintenanceTemplateConfidence.SUGGESTED
        ):
            raise ValueError("company starter templates must be marked suggested")
        if resolved_type == MaintenanceTemplateType.OEM_VERIFIED and (
            resolved_confidence != MaintenanceTemplateConfidence.VERIFIED
            or self.source_type != MaintenanceTemplateSourceType.OEM
            or self.verification_status != MaintenanceTemplateVerificationStatus.VERIFIED
            or not self.source_reference
            or not self.manufacturer
            or not self.model
        ):
            raise ValueError(
                "OEM verified templates require verified confidence, source, "
                "manufacturer, and model"
            )
        return self


class MaintenanceTemplateResponse(BaseModel):
    id: UUID
    name: str
    version: str
    template_type: MaintenanceTemplateType
    confidence: MaintenanceTemplateConfidence
    category: MaintenanceTemplateCategory
    applicability: MaintenanceTemplateApplicability
    source_name: str
    source_type: MaintenanceTemplateSourceType
    source_reference: str | None
    verification_status: MaintenanceTemplateVerificationStatus
    asset_type: FleetAssetType | None
    manufacturer: str | None
    model: str | None
    model_year_min: int | None
    model_year_max: int | None
    notes: str | None
    is_generic: bool
    created_at: datetime
    updated_at: datetime


class MaintenanceTemplateItemRequest(BaseModel):
    task_code: MaintenanceTaskCode
    custom_label: str | None = Field(default=None, max_length=200)
    action_type: MaintenanceActionType
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool = True
    criteria: list[MaintenanceCriterionRequest] = Field(default_factory=list, max_length=3)


class MaintenanceTemplateCriterionResponse(BaseModel):
    basis: MaintenanceCriterionBasis
    interval_value: Decimal
    warning_value: Decimal


class MaintenanceTemplateItemResponse(BaseModel):
    id: UUID
    template_id: UUID
    task_code: MaintenanceTaskCode
    task_label: str
    action_type: MaintenanceActionType
    description: str | None
    enabled: bool
    criteria: list[MaintenanceTemplateCriterionResponse]


class MaintenanceTemplateApplyRequest(BaseModel):
    template_id: UUID


class MaintenancePlanCopyRequest(BaseModel):
    source_asset_id: UUID


class DriverMaintenanceDueItemResponse(BaseModel):
    schedule_id: UUID
    asset_id: UUID
    task_label: str
    status: MaintenanceDueState


class DriverMaintenanceProofRequest(BaseModel):
    client_submission_uuid: UUID
    schedule_id: UUID
    evidence_object_references: list[str] = Field(min_length=1, max_length=5)
    note: str | None = Field(default=None, max_length=500)


class MaintenanceProofEvidenceResponse(BaseModel):
    evidence_id: UUID
    content_type: str
    size_bytes: int


class MaintenanceProofResponse(BaseModel):
    id: UUID
    client_submission_uuid: UUID
    asset_id: UUID
    asset_code: str
    schedule_id: UUID
    task_label: str
    status: MaintenanceProofStatus
    driver_name: str
    site_id: UUID
    site_name: str
    assignment_id: UUID
    duty_session_id: UUID | None
    submitted_at: datetime
    note: str | None
    evidence: list[MaintenanceProofEvidenceResponse]
    reviewed_by_membership_id: UUID | None
    reviewed_at: datetime | None
    review_reason: str | None
    work_order_id: UUID | None
    duplicate: bool = False


class MaintenanceProofReviewRequest(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    reason: str | None = Field(default=None, max_length=500)
