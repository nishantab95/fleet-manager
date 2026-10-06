from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from fastapi import HTTPException, Request, status

from fleet_api.core.config import Settings


class FutureFeature(StrEnum):
    MAINTENANCE = "maintenance"
    ASSET_DOCUMENTS = "asset_documents"
    NOTIFICATIONS = "notifications"
    TELEMATICS = "telematics"
    FUEL_INTEGRATIONS = "fuel_integrations"
    TOLL_EXPENSES = "toll_expenses"
    MULTI_METER = "multi_meter"
    PAYROLL = "payroll"
    ATTENDANCE_LOCATION = "attendance_location"


@dataclass(frozen=True)
class FeatureRegistry:
    """Typed, server-authoritative registry for dormant product modules."""

    maintenance_enabled: bool = False
    asset_documents_enabled: bool = False
    notifications_enabled: bool = False
    telematics_enabled: bool = False
    fuel_integrations_enabled: bool = False
    toll_expenses_enabled: bool = False
    multi_meter_enabled: bool = False
    payroll_enabled: bool = False
    attendance_location_enabled: bool = False

    @classmethod
    def from_settings(cls, settings: Settings) -> FeatureRegistry:
        return cls(
            maintenance_enabled=settings.maintenance_enabled,
            asset_documents_enabled=settings.asset_documents_enabled,
            notifications_enabled=settings.notifications_enabled,
            telematics_enabled=settings.telematics_enabled,
            fuel_integrations_enabled=settings.fuel_integrations_enabled,
            toll_expenses_enabled=settings.toll_expenses_enabled,
            multi_meter_enabled=settings.multi_meter_enabled,
            payroll_enabled=settings.payroll_enabled,
            attendance_location_enabled=settings.attendance_location_enabled,
        )

    def is_enabled(self, feature: FutureFeature) -> bool:
        return {
            FutureFeature.MAINTENANCE: self.maintenance_enabled,
            FutureFeature.ASSET_DOCUMENTS: self.asset_documents_enabled,
            FutureFeature.NOTIFICATIONS: self.notifications_enabled,
            FutureFeature.TELEMATICS: self.telematics_enabled,
            FutureFeature.FUEL_INTEGRATIONS: self.fuel_integrations_enabled,
            FutureFeature.TOLL_EXPENSES: self.toll_expenses_enabled,
            FutureFeature.MULTI_METER: self.multi_meter_enabled,
            FutureFeature.PAYROLL: self.payroll_enabled,
            FutureFeature.ATTENDANCE_LOCATION: self.attendance_location_enabled,
        }[feature]


def feature_registry(settings: Settings) -> FeatureRegistry:
    return FeatureRegistry.from_settings(settings)


def require_feature(feature: FutureFeature) -> Callable[..., None]:
    """Return a FastAPI dependency that fails closed with a stable 404."""

    def dependency(request: Request) -> None:
        settings = cast(Settings, request.app.state.settings)
        if not feature_registry(settings).is_enabled(feature):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "FEATURE_UNAVAILABLE",
                    "message": "feature is unavailable",
                },
            )

    return dependency
