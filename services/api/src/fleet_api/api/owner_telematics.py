from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_telematics_ingestion_service
from fleet_api.core.features import FutureFeature, require_feature
from fleet_api.db.models import (
    GeofenceTransition,
    TelematicsMeterDiscrepancy,
    TelematicsVehicleMapping,
)
from fleet_api.db.session import get_db
from fleet_api.domain.enums import GeofenceTransitionType, MeterDiscrepancyStatus
from fleet_api.domain.errors import ConflictError, DomainError, NotFoundError
from fleet_api.domain.telematics import LatestPositionView, TelematicsIngestionService

router = APIRouter(
    prefix="/api/v1/owner/telematics",
    tags=["owner-telematics"],
    dependencies=[Depends(require_feature(FutureFeature.TELEMATICS))],
)


def _fail(db: Session, exc: DomainError) -> NoReturn:
    db.rollback()
    if isinstance(exc, NotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, ConflictError):
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(status_code=code, detail={"code": "TELEMATICS_ERROR", "message": str(exc)})


class MappingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: UUID
    provider: str = Field(min_length=1, max_length=80)
    provider_vehicle_id: str = Field(min_length=1, max_length=160)


class MappingResponse(BaseModel):
    id: UUID
    asset_id: UUID
    provider: str
    provider_vehicle_id: str
    active: bool
    created_at: datetime
    updated_at: datetime


class GeofenceInput(BaseModel):
    site_id: UUID
    radius_m: Decimal = Field(gt=0, le=100000)


class PositionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_event_id: str = Field(min_length=1, max_length=200)
    recorded_at: datetime
    latitude: Decimal
    longitude: Decimal
    speed_kph: Decimal | None = None
    heading: Decimal | None = None
    ignition_state: bool | None = None
    odometer_km: Decimal | None = None
    engine_hours: Decimal | None = None
    battery_voltage: Decimal | None = None


class TransitionResponse(BaseModel):
    id: UUID
    asset_id: UUID
    site_id: UUID
    position_id: UUID
    transition_type: GeofenceTransitionType
    occurred_at: datetime
    distance_m: Decimal


class PositionResponse(BaseModel):
    id: UUID
    asset_id: UUID
    mapping_id: UUID
    provider_event_id: str
    recorded_at: datetime
    latitude: Decimal
    longitude: Decimal
    speed_kph: Decimal | None
    heading: Decimal | None
    ignition_state: bool | None
    odometer_km: Decimal | None
    engine_hours: Decimal | None
    battery_voltage: Decimal | None


class MeterDiscrepancyResponse(BaseModel):
    id: UUID
    asset_id: UUID
    position_id: UUID
    manual_event_id: UUID | None
    meter_type: str
    telemetry_value: Decimal
    manual_value: Decimal | None
    tolerance: Decimal
    difference: Decimal | None
    status: MeterDiscrepancyStatus
    created_at: datetime


class IngestionResponse(BaseModel):
    position: PositionResponse
    transitions: list[TransitionResponse]
    duplicate: bool
    out_of_order: bool
    discrepancies: list[MeterDiscrepancyResponse]


class LatestResponse(BaseModel):
    mapping: MappingResponse
    position: PositionResponse | None
    stale: bool


def _mapping(item: TelematicsVehicleMapping) -> MappingResponse:
    return MappingResponse.model_validate(item, from_attributes=True)


def _transition(item: GeofenceTransition) -> TransitionResponse:
    return TransitionResponse.model_validate(item, from_attributes=True)


def _latest(item: LatestPositionView) -> LatestResponse:
    return LatestResponse(
        mapping=_mapping(item.mapping),
        position=(
            PositionResponse.model_validate(item.position, from_attributes=True)
            if item.position
            else None
        ),
        stale=item.stale,
    )


@router.get("/mappings", response_model=list[MappingResponse])
def list_mappings(
    service: Annotated[TelematicsIngestionService, Depends(get_telematics_ingestion_service)],
) -> list[MappingResponse]:
    return [_mapping(item) for item in service.list_mappings()]


@router.post("/mappings", response_model=MappingResponse, status_code=status.HTTP_201_CREATED)
def create_mapping(
    payload: MappingInput,
    service: Annotated[TelematicsIngestionService, Depends(get_telematics_ingestion_service)],
    db: Annotated[Session, Depends(get_db)],
) -> MappingResponse:
    try:
        item = service.create_mapping(**payload.model_dump())
        db.commit()
        db.refresh(item)
        return _mapping(item)
    except DomainError as exc:
        _fail(db, exc)


@router.put("/geofences")
def set_geofence(
    payload: GeofenceInput,
    service: Annotated[TelematicsIngestionService, Depends(get_telematics_ingestion_service)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, bool]:
    try:
        service.set_geofence(**payload.model_dump())
        db.commit()
        return {"updated": True}
    except DomainError as exc:
        _fail(db, exc)


@router.post("/mappings/{mapping_id}/positions", response_model=IngestionResponse)
def ingest_position(
    mapping_id: UUID,
    payload: PositionInput,
    service: Annotated[TelematicsIngestionService, Depends(get_telematics_ingestion_service)],
    db: Annotated[Session, Depends(get_db)],
) -> IngestionResponse:
    try:
        result = service.ingest(mapping_id, **payload.model_dump())
        db.commit()
        return IngestionResponse(
            position=PositionResponse.model_validate(result.position, from_attributes=True),
            transitions=[_transition(item) for item in result.transitions],
            duplicate=result.duplicate,
            out_of_order=result.out_of_order,
            discrepancies=[
                MeterDiscrepancyResponse.model_validate(item, from_attributes=True)
                for item in result.discrepancies
            ],
        )
    except DomainError as exc:
        _fail(db, exc)


@router.get("/latest", response_model=list[LatestResponse])
def latest_positions(
    service: Annotated[TelematicsIngestionService, Depends(get_telematics_ingestion_service)],
    stale_after_seconds: int = Query(default=900, ge=0, le=86400),
) -> list[LatestResponse]:
    return [
        _latest(item) for item in service.latest_positions(stale_after_seconds=stale_after_seconds)
    ]


@router.get("/transitions", response_model=list[TransitionResponse])
def transitions(
    service: Annotated[TelematicsIngestionService, Depends(get_telematics_ingestion_service)],
    asset_id: UUID | None = None,
) -> list[TransitionResponse]:
    return [_transition(item) for item in service.transitions(asset_id=asset_id)]


@router.get("/meter-discrepancies", response_model=list[MeterDiscrepancyResponse])
def meter_discrepancies(
    service: Annotated[TelematicsIngestionService, Depends(get_telematics_ingestion_service)],
    asset_id: UUID | None = None,
) -> list[MeterDiscrepancyResponse]:
    return [
        MeterDiscrepancyResponse.model_validate(item, from_attributes=True)
        for item in service.meter_discrepancies(asset_id=asset_id)
        if isinstance(item, TelematicsMeterDiscrepancy)
    ]
