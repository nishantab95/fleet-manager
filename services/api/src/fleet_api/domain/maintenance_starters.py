from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from fleet_api.domain.enums import (
    FleetAssetType,
    MaintenanceActionType,
    MaintenanceCriterionBasis,
    MaintenanceTaskCode,
    MaintenanceTemplateApplicability,
    MaintenanceTemplateCategory,
    MaintenanceTemplateConfidence,
    MaintenanceTemplateType,
)


@dataclass(frozen=True)
class StarterCriterion:
    basis: MaintenanceCriterionBasis
    interval: Decimal
    warning: Decimal = Decimal("0")


@dataclass(frozen=True)
class StarterItem:
    label: str
    action: MaintenanceActionType
    criteria: tuple[StarterCriterion, ...] = ()
    task_code: MaintenanceTaskCode = MaintenanceTaskCode.CUSTOM
    description: str | None = None


@dataclass(frozen=True)
class StarterTemplate:
    name: str
    version: str
    template_type: MaintenanceTemplateType
    confidence: MaintenanceTemplateConfidence
    category: MaintenanceTemplateCategory
    applicability: MaintenanceTemplateApplicability
    asset_type: FleetAssetType | None
    source_name: str
    source_reference: str | None
    notes: str
    items: tuple[StarterItem, ...]
    manufacturer: str | None = None
    model: str | None = None
    year_from: int | None = None
    year_to: int | None = None


def days(value: int, warning: int = 0) -> StarterCriterion:
    return StarterCriterion(
        MaintenanceCriterionBasis.CALENDAR_DAYS,
        Decimal(value),
        Decimal(warning),
    )


def hours(value: int, warning: int = 0) -> StarterCriterion:
    return StarterCriterion(
        MaintenanceCriterionBasis.HOUR_METER_HOURS,
        Decimal(value),
        Decimal(warning),
    )


def item(
    label: str,
    action: MaintenanceActionType,
    *criteria: StarterCriterion,
    description: str | None = None,
) -> StarterItem:
    return StarterItem(label, action, tuple(criteria), description=description)


SUGGESTED_NOTE = (
    "Editable company starter. Suggested intervals are not OEM requirements; "
    "verify them against the exact machine service manual and operating conditions."
)


MAINTENANCE_STARTER_CATALOG: tuple[StarterTemplate, ...] = (
    StarterTemplate(
        name="Heavy 10-Wheel Tipper Starter",
        version="1",
        template_type=MaintenanceTemplateType.COMPANY_STARTER,
        confidence=MaintenanceTemplateConfidence.SUGGESTED,
        category=MaintenanceTemplateCategory.HEAVY_TIPPER_10_WHEEL,
        applicability=MaintenanceTemplateApplicability.WHEELED,
        asset_type=FleetAssetType.TIPPER,
        source_name="Fleet Manager conservative heavy-tipper starter policy",
        source_reference="STARTER-HEAVY-TIPPER-10W-V1",
        notes=SUGGESTED_NOTE,
        items=(
            item("Engine oil level inspection", MaintenanceActionType.INSPECT, days(1)),
            item("Coolant inspection", MaintenanceActionType.INSPECT, days(1)),
            item("Fluid and leak inspection", MaintenanceActionType.INSPECT, days(1)),
            item("Air-filter restriction inspection", MaintenanceActionType.INSPECT, days(1)),
            item("Water separator check", MaintenanceActionType.INSPECT, days(1)),
            item("Brake inspection", MaintenanceActionType.INSPECT, days(1)),
            item("Lights and warnings inspection", MaintenanceActionType.INSPECT, days(1)),
            item("Tyre pressure", MaintenanceActionType.INSPECT, days(7, 1)),
            item("Tyre condition", MaintenanceActionType.INSPECT, days(7, 1)),
            item("Drive belt inspection", MaintenanceActionType.INSPECT, days(7, 1)),
            item("Greasing", MaintenanceActionType.LUBRICATE, days(30, 3)),
            item("Engine oil and filter", MaintenanceActionType.REPLACE, hours(500, 50)),
            item("Fuel filter", MaintenanceActionType.REPLACE, hours(500, 50)),
            item("Air filter", MaintenanceActionType.SERVICE),
            item("Hub inspection and grease", MaintenanceActionType.INSPECT, hours(1000, 100)),
            item("Hub service", MaintenanceActionType.SERVICE, hours(2000, 200)),
            item("Wheel bearing inspection", MaintenanceActionType.INSPECT),
            item("Brake service", MaintenanceActionType.SERVICE),
            item("Transmission / gearbox oil", MaintenanceActionType.REPLACE, hours(2000, 200)),
            item("Differential / rear axle oil", MaintenanceActionType.REPLACE, hours(3000, 300)),
            item("Coolant service", MaintenanceActionType.SERVICE),
            item("Battery inspection", MaintenanceActionType.INSPECT),
            item("Propeller shaft / U-joint inspection", MaintenanceActionType.INSPECT),
            item("General inspection", MaintenanceActionType.INSPECT),
        ),
    ),
    StarterTemplate(
        name="Tracked Excavator Starter",
        version="1",
        template_type=MaintenanceTemplateType.COMPANY_STARTER,
        confidence=MaintenanceTemplateConfidence.SUGGESTED,
        category=MaintenanceTemplateCategory.TRACKED_EXCAVATOR,
        applicability=MaintenanceTemplateApplicability.NON_WHEELED,
        asset_type=FleetAssetType.EXCAVATOR,
        source_name="Fleet Manager conservative tracked-excavator starter policy",
        source_reference="STARTER-TRACKED-EXCAVATOR-V1",
        notes=SUGGESTED_NOTE,
        items=(
            item("Engine oil and filter", MaintenanceActionType.REPLACE, hours(500, 50)),
            item("Fuel filter", MaintenanceActionType.REPLACE, hours(500, 50)),
            item("Air filter inspect / clean", MaintenanceActionType.CLEAN),
            item("Greasing", MaintenanceActionType.LUBRICATE, hours(50, 5)),
            item(
                "Boom / stick / bucket pin lubrication",
                MaintenanceActionType.LUBRICATE,
                hours(50, 5),
            ),
            item("Swing bearing lubrication", MaintenanceActionType.LUBRICATE, hours(250, 25)),
            item("Hydraulic filter", MaintenanceActionType.REPLACE, hours(1000, 100)),
            item("Hydraulic oil", MaintenanceActionType.REPLACE, hours(4000, 400)),
            item("Final drive oil", MaintenanceActionType.REPLACE),
            item("Coolant service", MaintenanceActionType.SERVICE),
            item("Track tension", MaintenanceActionType.INSPECT, hours(50, 5)),
            item("Undercarriage inspection", MaintenanceActionType.INSPECT, hours(50, 5)),
            item("Battery inspection", MaintenanceActionType.INSPECT),
            item("General inspection", MaintenanceActionType.INSPECT),
        ),
    ),
    StarterTemplate(
        name="Backhoe Loader Starter",
        version="1",
        template_type=MaintenanceTemplateType.COMPANY_STARTER,
        confidence=MaintenanceTemplateConfidence.SUGGESTED,
        category=MaintenanceTemplateCategory.BACKHOE_LOADER,
        applicability=MaintenanceTemplateApplicability.WHEELED,
        asset_type=FleetAssetType.BACKHOE_LOADER,
        source_name="Fleet Manager conservative backhoe-loader starter policy",
        source_reference="STARTER-BACKHOE-LOADER-V1",
        notes=SUGGESTED_NOTE,
        items=(
            item("Engine oil and filter", MaintenanceActionType.REPLACE, hours(500, 50)),
            item("Fuel filter", MaintenanceActionType.REPLACE, hours(1000, 100)),
            item("Air filter", MaintenanceActionType.SERVICE),
            item("Greasing", MaintenanceActionType.LUBRICATE, hours(50, 5)),
            item("Loader linkage", MaintenanceActionType.INSPECT),
            item("Backhoe pins and bushes", MaintenanceActionType.INSPECT),
            item("Hydraulic oil", MaintenanceActionType.REPLACE, hours(4000, 400)),
            item("Hydraulic filter", MaintenanceActionType.REPLACE),
            item("Transmission", MaintenanceActionType.SERVICE),
            item("Axles and differentials", MaintenanceActionType.SERVICE),
            item("Tyre pressure", MaintenanceActionType.INSPECT, days(7, 1)),
            item("Brake inspection", MaintenanceActionType.INSPECT),
            item("Coolant service", MaintenanceActionType.SERVICE),
            item("Battery inspection", MaintenanceActionType.INSPECT),
        ),
    ),
    StarterTemplate(
        name="Road Roller / Compactor Starter",
        version="1",
        template_type=MaintenanceTemplateType.COMPANY_STARTER,
        confidence=MaintenanceTemplateConfidence.SUGGESTED,
        category=MaintenanceTemplateCategory.ROAD_ROLLER_COMPACTOR,
        applicability=MaintenanceTemplateApplicability.WHEELED,
        asset_type=FleetAssetType.ROLLER,
        source_name="Fleet Manager conservative roller and compactor starter policy",
        source_reference="STARTER-ROAD-ROLLER-COMPACTOR-V1",
        notes=SUGGESTED_NOTE,
        items=(
            item("Engine oil and filter", MaintenanceActionType.REPLACE, hours(500, 50)),
            item("Fuel filter", MaintenanceActionType.REPLACE),
            item("Air filter", MaintenanceActionType.SERVICE),
            item("Hydraulic oil and filter", MaintenanceActionType.REPLACE, hours(3000, 300)),
            item(
                "Eccentric / vibration housing oil", MaintenanceActionType.REPLACE, hours(3000, 300)
            ),
            item("Drum condition", MaintenanceActionType.INSPECT),
            item("Scraper inspection", MaintenanceActionType.INSPECT),
            item("Greasing", MaintenanceActionType.LUBRICATE),
            item("Water spray system", MaintenanceActionType.INSPECT),
            item("Tyres where applicable", MaintenanceActionType.INSPECT),
            item("Brake inspection", MaintenanceActionType.INSPECT),
            item("Coolant service", MaintenanceActionType.SERVICE),
            item("Battery inspection", MaintenanceActionType.INSPECT),
        ),
    ),
    StarterTemplate(
        name="Wheel Loader Starter",
        version="1",
        template_type=MaintenanceTemplateType.COMPANY_STARTER,
        confidence=MaintenanceTemplateConfidence.SUGGESTED,
        category=MaintenanceTemplateCategory.WHEEL_LOADER,
        applicability=MaintenanceTemplateApplicability.WHEELED,
        asset_type=None,
        source_name="Fleet Manager conservative wheel-loader starter policy",
        source_reference="STARTER-WHEEL-LOADER-V1",
        notes=(
            f"{SUGGESTED_NOTE} Catalog reference only until WHEEL_LOADER becomes a supported "
            "operational Fleet asset type; it is never auto-matched to another asset type."
        ),
        items=(
            item("Engine oil and filter", MaintenanceActionType.REPLACE, hours(500, 50)),
            item("Fuel filter", MaintenanceActionType.REPLACE),
            item("Air filter", MaintenanceActionType.SERVICE),
            item("Greasing", MaintenanceActionType.LUBRICATE),
            item("Hydraulic filter", MaintenanceActionType.REPLACE),
            item("Hydraulic oil", MaintenanceActionType.REPLACE),
            item("Transmission filter", MaintenanceActionType.REPLACE, hours(500, 50)),
            item("Transmission oil", MaintenanceActionType.REPLACE, hours(1000, 100)),
            item("Differential / final drive", MaintenanceActionType.SERVICE),
            item("Loader linkage pins", MaintenanceActionType.LUBRICATE),
            item("Tyre pressure", MaintenanceActionType.INSPECT, days(7, 1)),
            item("Brake inspection", MaintenanceActionType.INSPECT),
            item("Coolant service", MaintenanceActionType.SERVICE),
            item("Battery inspection", MaintenanceActionType.INSPECT),
        ),
    ),
    StarterTemplate(
        name="Motor Grader Starter",
        version="1",
        template_type=MaintenanceTemplateType.COMPANY_STARTER,
        confidence=MaintenanceTemplateConfidence.SUGGESTED,
        category=MaintenanceTemplateCategory.MOTOR_GRADER,
        applicability=MaintenanceTemplateApplicability.WHEELED,
        asset_type=FleetAssetType.GRADER,
        source_name="Fleet Manager conservative motor-grader starter policy",
        source_reference="STARTER-MOTOR-GRADER-V1",
        notes=SUGGESTED_NOTE,
        items=(
            item("Engine oil and filter", MaintenanceActionType.REPLACE, hours(500, 50)),
            item("Fuel filter", MaintenanceActionType.REPLACE),
            item("Air filter", MaintenanceActionType.SERVICE),
            item("Greasing", MaintenanceActionType.LUBRICATE),
            item("Circle drive", MaintenanceActionType.SERVICE),
            item("Blade linkage", MaintenanceActionType.INSPECT),
            item("Tandem drive", MaintenanceActionType.SERVICE),
            item("Transmission", MaintenanceActionType.SERVICE),
            item("Differential", MaintenanceActionType.SERVICE),
            item("Hydraulic system", MaintenanceActionType.SERVICE),
            item("Articulation joint", MaintenanceActionType.INSPECT),
            item("Tyre pressure", MaintenanceActionType.INSPECT, days(7, 1)),
            item("Brake inspection", MaintenanceActionType.INSPECT),
            item("Coolant service", MaintenanceActionType.SERVICE),
            item("Battery inspection", MaintenanceActionType.INSPECT),
            item("General inspection", MaintenanceActionType.INSPECT),
        ),
    ),
    StarterTemplate(
        name="Tata Prima Lx 2825.K TC BS-IV 6X4 Reference",
        version="SC-2019-56",
        template_type=MaintenanceTemplateType.OEM_VERIFIED,
        confidence=MaintenanceTemplateConfidence.VERIFIED,
        category=MaintenanceTemplateCategory.HEAVY_TIPPER_10_WHEEL,
        applicability=MaintenanceTemplateApplicability.WHEELED,
        asset_type=FleetAssetType.TIPPER,
        manufacturer="TATA MOTORS",
        model="PRIMA Lx 2825.K TC BS-IV 6X4",
        year_from=2019,
        source_name="Tata Motors Service Circular SC / 2019 / 56",
        source_reference="TATA-SC-2019-56",
        notes=(
            "Exact-model reference only. Engine oil/filter has two initial 500-hour services "
            "followed by a 1,000-hour recurring interval; the recurring trigger is stored here."
        ),
        items=(
            item("Engine oil and coolant level", MaintenanceActionType.INSPECT, days(1)),
            item("Air / oil / fluid leak inspection", MaintenanceActionType.INSPECT, days(1)),
            item("Air-filter restriction indicator", MaintenanceActionType.INSPECT, days(1)),
            item("Fuel water separator", MaintenanceActionType.INSPECT, days(1)),
            item("Drain air tanks", MaintenanceActionType.SERVICE, days(1)),
            item("Brake operation", MaintenanceActionType.INSPECT, days(1)),
            item("Drive belts", MaintenanceActionType.INSPECT, days(7, 1)),
            item("Tyre pressure", MaintenanceActionType.INSPECT, days(7, 1)),
            item("Tyre condition", MaintenanceActionType.INSPECT, days(7, 1)),
            item("Greasing points", MaintenanceActionType.LUBRICATE, days(30, 3)),
            item("Engine oil and filter", MaintenanceActionType.REPLACE, hours(1000, 100)),
            item("Fuel filter", MaintenanceActionType.REPLACE, hours(1000, 100)),
            item("Front hub grease", MaintenanceActionType.LUBRICATE, hours(1000, 100)),
            item("Hub grease / service", MaintenanceActionType.SERVICE, hours(2000, 200)),
            item("Rear axle oil", MaintenanceActionType.REPLACE, hours(3000, 300)),
            item("GB-1150 gearbox oil", MaintenanceActionType.REPLACE, hours(4000, 400)),
            item("Tyre rotation", MaintenanceActionType.SERVICE, hours(1000, 100)),
        ),
    ),
    StarterTemplate(
        name="JCB NXT 205 Reference",
        version="2026-10",
        template_type=MaintenanceTemplateType.OEM_VERIFIED,
        confidence=MaintenanceTemplateConfidence.VERIFIED,
        category=MaintenanceTemplateCategory.TRACKED_EXCAVATOR,
        applicability=MaintenanceTemplateApplicability.NON_WHEELED,
        asset_type=FleetAssetType.EXCAVATOR,
        manufacturer="JCB",
        model="NXT 205",
        source_name="JCB 205 NXT official product page",
        source_reference="JCB-205-NXT-PRODUCT",
        notes="Exact-model reference only; verify serial-number and market applicability.",
        items=(
            item("Engine oil change", MaintenanceActionType.REPLACE, hours(500, 50)),
            item("Boom-end pivot grease", MaintenanceActionType.LUBRICATE, hours(50, 5)),
            item("Hydraulic main filter", MaintenanceActionType.REPLACE, hours(1000, 100)),
            item("Hydraulic oil", MaintenanceActionType.REPLACE, hours(5000, 500)),
        ),
    ),
    StarterTemplate(
        name="Volvo EC210 India Reference",
        version="20066457-B",
        template_type=MaintenanceTemplateType.OEM_VERIFIED,
        confidence=MaintenanceTemplateConfidence.VERIFIED,
        category=MaintenanceTemplateCategory.TRACKED_EXCAVATOR,
        applicability=MaintenanceTemplateApplicability.NON_WHEELED,
        asset_type=FleetAssetType.EXCAVATOR,
        manufacturer="VOLVO",
        model="EC210",
        source_name="Volvo EC210 T3 Product Guide for India 20066457-B",
        source_reference="VOLVO-EC210-INDIA-20066457-B",
        notes="Exact-model and market reference only; verify machine configuration.",
        items=(
            item("Engine oil and filter", MaintenanceActionType.REPLACE, hours(500, 50)),
            item("Fuel filters", MaintenanceActionType.REPLACE, hours(500, 50)),
            item("Swing gearbox oil", MaintenanceActionType.REPLACE, hours(1000, 100)),
            item("Hydraulic oil servo filter", MaintenanceActionType.REPLACE, hours(1000, 100)),
            item("Hydraulic oil return filter", MaintenanceActionType.REPLACE, hours(2000, 200)),
        ),
    ),
    StarterTemplate(
        name="Cat 320 ZBN Reference",
        version="2026-10",
        template_type=MaintenanceTemplateType.OEM_VERIFIED,
        confidence=MaintenanceTemplateConfidence.VERIFIED,
        category=MaintenanceTemplateCategory.TRACKED_EXCAVATOR,
        applicability=MaintenanceTemplateApplicability.NON_WHEELED,
        asset_type=FleetAssetType.EXCAVATOR,
        manufacturer="CATERPILLAR",
        model="320",
        source_name="Caterpillar 320 / 320 GC / 323 planned-maintenance page",
        source_reference="CAT-320-ZBN-PLANNED-MAINTENANCE",
        notes="Reference is limited to Cat 320 sales model with ZBN serial prefix.",
        items=(
            item("Engine oil and filter", MaintenanceActionType.REPLACE, hours(500, 50)),
            item("Fuel filter", MaintenanceActionType.REPLACE, hours(500, 50)),
            item("Machine lubrication", MaintenanceActionType.LUBRICATE, hours(500, 50)),
        ),
    ),
)
