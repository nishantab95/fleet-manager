from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from fleet_api.auth.service import AuthContext
from fleet_api.db.models import (
    AuthSession,
    Company,
    CompanyMembership,
    EvidenceObject,
    FleetAsset,
    MaintenanceCriterion,
    MaintenanceProofSubmission,
    MaintenanceRecord,
    MaintenanceTemplateCriterion,
    Site,
    User,
)
from fleet_api.domain.assets import create_fleet_asset
from fleet_api.domain.assignments import create_assignment, grant_supervisor_site_access
from fleet_api.domain.enums import (
    AssetOwnershipType,
    FleetAssetType,
    MaintenanceActionType,
    MaintenanceCriterionBasis,
    MaintenanceDueState,
    MaintenanceProofStatus,
    MaintenanceTaskCode,
    MaintenanceTemplateSourceType,
    MaintenanceTemplateVerificationStatus,
    MaintenanceWorkOrderStatus,
    MembershipRole,
)
from fleet_api.domain.errors import DomainError, NotFoundError
from fleet_api.domain.maintenance import (
    CriterionInput,
    MaintenanceService,
    evaluate_criterion,
    overall_due_state,
)
from fleet_api.domain.maintenance_proof import MaintenanceProofService
from test_asset_site_deployments_api import client_for


def value[T](records: dict[str, object], key: str, expected_type: type[T]) -> T:
    item = records[key]
    assert isinstance(item, expected_type)
    return item


def criterion(
    basis: MaintenanceCriterionBasis,
    *,
    interval: str,
    warning: str,
    baseline_value: str | None = None,
    baseline_date: date | None = None,
) -> MaintenanceCriterion:
    return MaintenanceCriterion(
        company_id=uuid4(),
        schedule_id=uuid4(),
        basis=basis,
        enabled=True,
        interval_value=Decimal(interval),
        warning_value=Decimal(warning),
        baseline_value=Decimal(baseline_value) if baseline_value is not None else None,
        baseline_date=baseline_date,
    )


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (Decimal("89"), MaintenanceDueState.NOT_DUE),
        (Decimal("90"), MaintenanceDueState.DUE_SOON),
        (Decimal("100"), MaintenanceDueState.DUE),
        (Decimal("101"), MaintenanceDueState.OVERDUE),
        (None, MaintenanceDueState.UNKNOWN),
    ],
)
def test_meter_due_states_are_deterministic(
    current: Decimal | None,
    expected: MaintenanceDueState,
) -> None:
    result = evaluate_criterion(
        criterion(
            MaintenanceCriterionBasis.ODOMETER_KM,
            interval="100",
            warning="10",
            baseline_value="0",
        ),
        current_odometer_km=current,
        current_hour_meter=None,
        as_of=date(2026, 10, 8),
    )
    assert result.state == expected


@pytest.mark.parametrize(
    ("bases", "current_km", "current_hours", "as_of", "expected", "trigger"),
    [
        (
            (MaintenanceCriterionBasis.CALENDAR_DAYS,),
            None,
            None,
            date(2026, 6, 30),
            MaintenanceDueState.OVERDUE,
            MaintenanceCriterionBasis.CALENDAR_DAYS,
        ),
        (
            (MaintenanceCriterionBasis.ODOMETER_KM,),
            Decimal("101"),
            None,
            date(2026, 6, 1),
            MaintenanceDueState.OVERDUE,
            MaintenanceCriterionBasis.ODOMETER_KM,
        ),
        (
            (MaintenanceCriterionBasis.HOUR_METER_HOURS,),
            None,
            Decimal("101"),
            date(2026, 6, 1),
            MaintenanceDueState.OVERDUE,
            MaintenanceCriterionBasis.HOUR_METER_HOURS,
        ),
        (
            (MaintenanceCriterionBasis.CALENDAR_DAYS, MaintenanceCriterionBasis.ODOMETER_KM),
            Decimal("101"),
            None,
            date(2026, 6, 1),
            MaintenanceDueState.OVERDUE,
            MaintenanceCriterionBasis.ODOMETER_KM,
        ),
        (
            (MaintenanceCriterionBasis.CALENDAR_DAYS, MaintenanceCriterionBasis.HOUR_METER_HOURS),
            None,
            Decimal("101"),
            date(2026, 6, 1),
            MaintenanceDueState.OVERDUE,
            MaintenanceCriterionBasis.HOUR_METER_HOURS,
        ),
        (
            (MaintenanceCriterionBasis.ODOMETER_KM, MaintenanceCriterionBasis.HOUR_METER_HOURS),
            Decimal("80"),
            Decimal("101"),
            date(2026, 6, 1),
            MaintenanceDueState.OVERDUE,
            MaintenanceCriterionBasis.HOUR_METER_HOURS,
        ),
        (
            (
                MaintenanceCriterionBasis.CALENDAR_DAYS,
                MaintenanceCriterionBasis.ODOMETER_KM,
                MaintenanceCriterionBasis.HOUR_METER_HOURS,
            ),
            Decimal("95"),
            Decimal("80"),
            date(2026, 6, 30),
            MaintenanceDueState.OVERDUE,
            MaintenanceCriterionBasis.CALENDAR_DAYS,
        ),
    ],
)
def test_every_supported_trigger_combination_uses_whichever_comes_first(
    bases: tuple[MaintenanceCriterionBasis, ...],
    current_km: Decimal | None,
    current_hours: Decimal | None,
    as_of: date,
    expected: MaintenanceDueState,
    trigger: MaintenanceCriterionBasis,
) -> None:
    inputs = {
        MaintenanceCriterionBasis.CALENDAR_DAYS: criterion(
            MaintenanceCriterionBasis.CALENDAR_DAYS,
            interval="28",
            warning="5",
            baseline_date=date(2026, 6, 1),
        ),
        MaintenanceCriterionBasis.ODOMETER_KM: criterion(
            MaintenanceCriterionBasis.ODOMETER_KM,
            interval="100",
            warning="10",
            baseline_value="0",
        ),
        MaintenanceCriterionBasis.HOUR_METER_HOURS: criterion(
            MaintenanceCriterionBasis.HOUR_METER_HOURS,
            interval="100",
            warning="10",
            baseline_value="0",
        ),
    }
    evaluations = tuple(
        evaluate_criterion(
            inputs[basis],
            current_odometer_km=current_km,
            current_hour_meter=current_hours,
            as_of=as_of,
        )
        for basis in bases
    )
    state, triggered_by = overall_due_state(evaluations)
    assert state == expected
    assert trigger in triggered_by


def test_unknown_meter_does_not_hide_overdue_calendar() -> None:
    calendar = evaluate_criterion(
        criterion(
            MaintenanceCriterionBasis.CALENDAR_DAYS,
            interval="30",
            warning="5",
            baseline_date=date(2026, 1, 1),
        ),
        current_odometer_km=None,
        current_hour_meter=None,
        as_of=date(2026, 3, 1),
    )
    hours = evaluate_criterion(
        criterion(
            MaintenanceCriterionBasis.HOUR_METER_HOURS,
            interval="100",
            warning="10",
            baseline_value="0",
        ),
        current_odometer_km=None,
        current_hour_meter=None,
        as_of=date(2026, 3, 1),
    )
    assert overall_due_state((calendar, hours)) == (
        MaintenanceDueState.OVERDUE,
        (MaintenanceCriterionBasis.CALENDAR_DAYS,),
    )


def test_all_unknown_criteria_keep_the_item_unknown() -> None:
    unknown = tuple(
        evaluate_criterion(
            criterion(basis, interval="100", warning="10"),
            current_odometer_km=None,
            current_hour_meter=None,
            as_of=date(2026, 3, 1),
        )
        for basis in (
            MaintenanceCriterionBasis.ODOMETER_KM,
            MaintenanceCriterionBasis.HOUR_METER_HOURS,
        )
    )
    assert overall_due_state(unknown) == (MaintenanceDueState.UNKNOWN, ())


pytestmark = pytest.mark.postgres


def owner_context(records: dict[str, object]) -> AuthContext:
    return AuthContext(
        auth_session=cast(AuthSession, object()),
        user=value(records, "owner_a_user", User),
        membership=value(records, "owner_a_membership", CompanyMembership),
        company=value(records, "company_a", Company),
    )


def membership_context(
    db_session: Session,
    records: dict[str, object],
    membership_key: str,
) -> AuthContext:
    membership = value(records, membership_key, CompanyMembership)
    user = db_session.get(User, membership.user_id)
    company = db_session.get(Company, membership.company_id)
    assert user is not None and company is not None
    return AuthContext(
        auth_session=cast(AuthSession, object()),
        user=user,
        membership=membership,
        company=company,
    )


def test_plan_completion_history_costs_tenant_boundary_and_tracked_km_rejection(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    owner = owner_context(tenant_records)
    wheeled = create_fleet_asset(
        db_session,
        company_id=company.id,
        asset_type=FleetAssetType.TIPPER,
        ownership_type=AssetOwnershipType.OWNED,
        asset_code="MAINT-DUAL",
        registration_number="KA09AA9999",
        short_name="Maintenance Dual",
        model_year=2024,
    )
    tracked = create_fleet_asset(
        db_session,
        company_id=company.id,
        asset_type=FleetAssetType.EXCAVATOR,
        ownership_type=AssetOwnershipType.OWNED,
        asset_code="MAINT-TRACKED",
        registration_number=None,
        short_name="Maintenance Tracked",
    )
    service = MaintenanceService(db_session, owner)
    schedule = service.save_schedule(
        wheeled.id,
        task_code=MaintenanceTaskCode.ENGINE_SERVICE,
        custom_label=None,
        action_type=MaintenanceActionType.SERVICE,
        description=None,
        enabled=True,
        criteria=[
            CriterionInput(
                MaintenanceCriterionBasis.CALENDAR_DAYS,
                Decimal("180"),
                Decimal("15"),
                baseline_date=date(2026, 1, 1),
            ),
            CriterionInput(
                MaintenanceCriterionBasis.ODOMETER_KM,
                Decimal("10000"),
                Decimal("1000"),
                baseline_value=Decimal("40000"),
            ),
            CriterionInput(
                MaintenanceCriterionBasis.HOUR_METER_HOURS,
                Decimal("500"),
                Decimal("50"),
                baseline_value=Decimal("2000"),
            ),
        ],
    )
    with pytest.raises(DomainError, match="without an odometer"):
        service.save_schedule(
            tracked.id,
            task_code=MaintenanceTaskCode.HYDRAULIC_OIL,
            custom_label=None,
            action_type=MaintenanceActionType.REPLACE,
            description=None,
            enabled=True,
            criteria=[
                CriterionInput(
                    MaintenanceCriterionBasis.ODOMETER_KM,
                    Decimal("1000"),
                    Decimal("100"),
                )
            ],
        )

    order = service.create_work_order(
        wheeled.id,
        schedule_id=schedule.id,
        title="Engine service",
        description=None,
        scheduled_for=date(2026, 10, 8),
    )
    service.transition_work_order(order.id, MaintenanceWorkOrderStatus.SCHEDULED)
    service.transition_work_order(order.id, MaintenanceWorkOrderStatus.IN_PROGRESS)
    completed, record = service.complete_work_order(
        order.id,
        service_date=date(2026, 10, 8),
        odometer_km=Decimal("48000"),
        hour_meter=Decimal("2100"),
        vendor="Pilot Workshop",
        parts_cost=Decimal("1.235"),
        labor_cost=Decimal("2.345"),
        other_cost=Decimal("0"),
        notes="Completed",
    )
    assert completed.status == MaintenanceWorkOrderStatus.COMPLETED
    assert record.total_cost == Decimal("3.59")
    reset = {item.basis: item for item in service.criteria_for(schedule.id)}
    assert reset[MaintenanceCriterionBasis.CALENDAR_DAYS].baseline_date == date(2026, 10, 8)
    assert reset[MaintenanceCriterionBasis.ODOMETER_KM].baseline_value == Decimal("48000")
    assert reset[MaintenanceCriterionBasis.HOUR_METER_HOURS].baseline_value == Decimal("2100")
    assert service.list_history(wheeled.id) == [record]
    assert db_session.scalar(select(MaintenanceRecord).where(MaintenanceRecord.id == record.id))

    foreign_asset = value(tenant_records, "tipper_b", FleetAsset)
    with pytest.raises(NotFoundError):
        service.ensure_plan(foreign_asset.id)


def test_template_matching_copy_isolation_generic_fallback_and_applicability(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    service = MaintenanceService(db_session, owner_context(tenant_records))
    asset = create_fleet_asset(
        db_session,
        company_id=company.id,
        asset_type=FleetAssetType.TIPPER,
        ownership_type=AssetOwnershipType.OWNED,
        asset_code="TPL-TIPPER",
        registration_number="KA09TT9999",
        short_name="Template Tipper",
        manufacturer="TATA",
        model="Signa 2823.K",
        model_year=2018,
    )
    tracked = create_fleet_asset(
        db_session,
        company_id=company.id,
        asset_type=FleetAssetType.EXCAVATOR,
        ownership_type=AssetOwnershipType.OWNED,
        asset_code="TPL-TRACKED",
        registration_number=None,
        short_name="Tracked",
    )
    exact = service.create_template(
        name="Verified Signa",
        version="2",
        source_type=MaintenanceTemplateSourceType.OEM,
        source_reference="Verified service manual reference",
        verification_status=MaintenanceTemplateVerificationStatus.VERIFIED,
        asset_type=FleetAssetType.TIPPER,
        manufacturer="TATA",
        model="Signa 2823.K",
        model_year_min=2017,
        model_year_max=2019,
        is_generic=False,
    )
    generic = service.create_template(
        name="Company generic starter",
        version="1",
        source_type=MaintenanceTemplateSourceType.COMPANY_DEFAULT,
        source_reference=None,
        verification_status=MaintenanceTemplateVerificationStatus.UNVERIFIED,
        asset_type=None,
        manufacturer=None,
        model=None,
        model_year_min=None,
        model_year_max=None,
        is_generic=True,
    )
    service.create_template(
        name="Wrong model",
        version="1",
        source_type=MaintenanceTemplateSourceType.COMPANY_DEFAULT,
        source_reference=None,
        verification_status=MaintenanceTemplateVerificationStatus.UNVERIFIED,
        asset_type=FleetAssetType.TIPPER,
        manufacturer="TATA",
        model="Other",
        model_year_min=None,
        model_year_max=None,
        is_generic=False,
    )
    template_item = service.add_template_item(
        exact.id,
        task_code=MaintenanceTaskCode.ENGINE_SERVICE,
        custom_label=None,
        action_type=MaintenanceActionType.SERVICE,
        description=None,
        enabled=True,
        criteria=[
            CriterionInput(
                MaintenanceCriterionBasis.ODOMETER_KM,
                Decimal("10000"),
                Decimal("1000"),
            )
        ],
    )
    matches = service.matching_templates(asset.id)
    assert matches[0] is exact
    assert generic in matches
    assert all(item.name != "Wrong model" for item in matches)

    plan = service.apply_template(asset.id, exact.id)
    assert plan.source_template_version == "2"
    _, copied = service.list_plan(asset.id)
    assert len(copied) == 1
    copied_criterion = service.criteria_for(copied[0].id)[0]
    copied_criterion.interval_value = Decimal("9000")
    service.add_template_item(
        exact.id,
        task_code=MaintenanceTaskCode.GREASING,
        custom_label=None,
        action_type=MaintenanceActionType.LUBRICATE,
        description=None,
        enabled=True,
        criteria=[
            CriterionInput(
                MaintenanceCriterionBasis.CALENDAR_DAYS,
                Decimal("30"),
                Decimal("5"),
            )
        ],
    )
    _, still_copied = service.list_plan(asset.id)
    assert len(still_copied) == 1
    master = db_session.scalar(
        select(MaintenanceTemplateCriterion).where(
            MaintenanceTemplateCriterion.template_item_id == template_item.id
        )
    )
    assert master is not None
    assert master.interval_value == Decimal("10000")

    tracked_catalog = {item.code for item in service.generic_starter(tracked.id)}
    assert MaintenanceTaskCode.TYRE_PRESSURE_CHECK not in tracked_catalog
    assert MaintenanceTaskCode.TRACK_TENSION_CHECK in tracked_catalog
    custom = service.save_schedule(
        tracked.id,
        task_code=MaintenanceTaskCode.CUSTOM,
        custom_label="Inspect attachment pins",
        action_type=MaintenanceActionType.INSPECT,
        description=None,
        enabled=True,
        criteria=[
            CriterionInput(
                MaintenanceCriterionBasis.CALENDAR_DAYS,
                Decimal("14"),
                Decimal("2"),
            )
        ],
    )
    assert custom.custom_label == "Inspect attachment pins"

    copied_asset = create_fleet_asset(
        db_session,
        company_id=company.id,
        asset_type=FleetAssetType.EXCAVATOR,
        ownership_type=AssetOwnershipType.OWNED,
        asset_code="TPL-COPY-TARGET",
        registration_number=None,
        short_name="Copy target",
    )
    copied_plan = service.copy_plan(copied_asset.id, tracked.id)
    assert copied_plan.source_asset_id == tracked.id
    _, copied_items = service.list_plan(copied_asset.id)
    assert [item.custom_label for item in copied_items] == ["Inspect attachment pins"]
    copied_baseline = service.criteria_for(copied_items[0].id)[0]
    assert copied_baseline.baseline_date is None
    assert copied_baseline.baseline_value is None


def test_maintenance_routes_are_owner_only_and_history_has_no_mutation_route(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    driver = client_for(db_session, value(tenant_records, "driver_a", CompanyMembership))
    owner = client_for(db_session, value(tenant_records, "owner_a_membership", CompanyMembership))
    try:
        assert driver.get("/api/v1/owner/maintenance/overview").status_code == 403
        response = owner.patch("/api/v1/owner/maintenance/history/not-a-record", json={})
        assert response.status_code == 404
    finally:
        driver.close()
        owner.close()


def test_rented_asset_keeps_history_but_is_excluded_from_company_maintenance(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    service = MaintenanceService(db_session, owner_context(tenant_records))
    asset = create_fleet_asset(
        db_session,
        company_id=company.id,
        asset_type=FleetAssetType.TIPPER,
        ownership_type=AssetOwnershipType.OWNED,
        asset_code="RENTAL-HISTORY",
        registration_number="KA09RH0001",
        short_name="Rental history",
    )
    schedule = service.save_schedule(
        asset.id,
        task_code=MaintenanceTaskCode.ENGINE_SERVICE,
        custom_label=None,
        action_type=MaintenanceActionType.SERVICE,
        description=None,
        enabled=True,
        criteria=[
            CriterionInput(
                MaintenanceCriterionBasis.CALENDAR_DAYS,
                Decimal("30"),
                Decimal("5"),
                baseline_date=date(2026, 1, 1),
            )
        ],
    )
    order = service.create_work_order(
        asset.id,
        schedule_id=schedule.id,
        title="Historical service",
        description=None,
        scheduled_for=None,
    )
    _completed, record = service.complete_work_order(
        order.id,
        service_date=date(2026, 2, 1),
        odometer_km=None,
        hour_meter=None,
        vendor=None,
        parts_cost=Decimal("0"),
        labor_cost=Decimal("0"),
        other_cost=Decimal("0"),
        notes=None,
    )
    asset.ownership_type = AssetOwnershipType.RENTED
    db_session.flush()

    assert service.evaluations() == []
    assert service.alert_counts()[MaintenanceDueState.OVERDUE] == 0
    assert service.list_history(asset.id) == [record]
    with pytest.raises(DomainError, match="rental owner"):
        service.ensure_plan(asset.id)
    with pytest.raises(DomainError, match="rental owner"):
        service.create_work_order(
            asset.id,
            schedule_id=None,
            title="Not permitted",
            description=None,
            scheduled_for=None,
        )


def test_driver_proof_requires_supervisor_review_and_rejection_keeps_due(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    site = value(tenant_records, "site_a", Site)
    asset = create_fleet_asset(
        db_session,
        company_id=company.id,
        asset_type=FleetAssetType.TIPPER,
        ownership_type=AssetOwnershipType.OWNED,
        asset_code="PROOF-ASSET",
        registration_number="KA09PF0001",
        short_name="Proof asset",
    )
    owner_service = MaintenanceService(db_session, owner_context(tenant_records))
    schedule = owner_service.save_schedule(
        asset.id,
        task_code=MaintenanceTaskCode.ENGINE_SERVICE,
        custom_label=None,
        action_type=MaintenanceActionType.SERVICE,
        description=None,
        enabled=True,
        criteria=[
            CriterionInput(
                MaintenanceCriterionBasis.CALENDAR_DAYS,
                Decimal("30"),
                Decimal("5"),
                baseline_date=date(2020, 1, 1),
            )
        ],
    )
    assignment = create_assignment(
        db_session,
        company_id=company.id,
        driver_membership_id=value(tenant_records, "driver_a", CompanyMembership).id,
        supervisor_membership_id=value(tenant_records, "supervisor_a", CompanyMembership).id,
        asset_id=asset.id,
        site_id=site.id,
        starts_at=datetime.now(UTC) - timedelta(hours=1),
    )
    grant_supervisor_site_access(
        db_session,
        company_id=company.id,
        supervisor_membership_id=value(tenant_records, "supervisor_a", CompanyMembership).id,
        site_id=site.id,
    )
    evidence_uuid = uuid4()
    evidence = EvidenceObject(
        company_id=company.id,
        membership_id=assignment.driver_membership_id,
        client_event_uuid=evidence_uuid,
        object_key=f"private/{evidence_uuid}.jpg",
        content_type="image/jpeg",
        size_bytes=20,
    )
    db_session.add(evidence)
    db_session.flush()

    driver_service = MaintenanceProofService(
        db_session,
        membership_context(db_session, tenant_records, "driver_a"),
    )
    assert [item.schedule.id for item in driver_service.driver_due_items()] == [schedule.id]
    submission_uuid = uuid4()
    submitted = driver_service.submit(
        client_submission_uuid=submission_uuid,
        schedule_id=schedule.id,
        evidence_object_references=[evidence.object_key],
        note="Service appears complete",
    )
    assert submitted.view.submission.status == MaintenanceProofStatus.PROOF_SUBMITTED
    assert driver_service.driver_due_items() == []
    assert driver_service.submit(
        client_submission_uuid=submission_uuid,
        schedule_id=schedule.id,
        evidence_object_references=[evidence.object_key],
        note="Service appears complete",
    ).duplicate
    assert (
        db_session.scalar(
            select(MaintenanceRecord).where(MaintenanceRecord.schedule_id == schedule.id)
        )
        is None
    )

    foreign_supervisor = MaintenanceProofService(
        db_session,
        membership_context(db_session, tenant_records, "supervisor_b"),
    )
    assert foreign_supervisor.list_supervisor_submissions() == []

    supervisor_service = MaintenanceProofService(
        db_session,
        membership_context(db_session, tenant_records, "supervisor_a"),
    )
    rejected = supervisor_service.reject(submitted.view.submission.id, reason="Wrong photo")
    assert rejected.submission.status == MaintenanceProofStatus.REJECTED
    assert [item.schedule.id for item in driver_service.driver_due_items()] == [schedule.id]
    assert (
        db_session.scalar(
            select(MaintenanceRecord).where(MaintenanceRecord.schedule_id == schedule.id)
        )
        is None
    )

    evidence_uuid_2 = uuid4()
    evidence_2 = EvidenceObject(
        company_id=company.id,
        membership_id=assignment.driver_membership_id,
        client_event_uuid=evidence_uuid_2,
        object_key=f"private/{evidence_uuid_2}.jpg",
        content_type="image/jpeg",
        size_bytes=22,
    )
    db_session.add(evidence_2)
    db_session.flush()
    resubmitted = driver_service.submit(
        client_submission_uuid=uuid4(),
        schedule_id=schedule.id,
        evidence_object_references=[evidence_2.object_key],
        note=None,
    )
    approved = supervisor_service.approve(resubmitted.view.submission.id)
    assert approved.submission.status == MaintenanceProofStatus.COMPLETED
    record = db_session.scalar(
        select(MaintenanceRecord).where(MaintenanceRecord.schedule_id == schedule.id)
    )
    assert record is not None
    assert record.actor_membership_id == value(tenant_records, "supervisor_a", CompanyMembership).id
    reset = service_criterion = owner_service.criteria_for(schedule.id)[0]
    assert reset.baseline_date == datetime.now(UTC).date()
    assert service_criterion.baseline_value is None
    assert (
        db_session.scalar(
            select(MaintenanceProofSubmission).where(
                MaintenanceProofSubmission.id == submitted.view.submission.id
            )
        )
        is not None
    )


def test_maintenance_proof_routes_enforce_role_site_and_idempotency(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    company = value(tenant_records, "company_a", Company)
    site = value(tenant_records, "site_a", Site)
    driver_membership = value(tenant_records, "driver_a", CompanyMembership)
    supervisor_membership = value(tenant_records, "supervisor_a", CompanyMembership)
    unauthorized_supervisor = value(tenant_records, "driver_a2", CompanyMembership)
    unauthorized_supervisor.role = MembershipRole.SUPERVISOR
    asset = create_fleet_asset(
        db_session,
        company_id=company.id,
        asset_type=FleetAssetType.TIPPER,
        ownership_type=AssetOwnershipType.OWNED,
        asset_code="PROOF-API",
        registration_number="KA09PA0001",
        short_name="Proof API asset",
    )
    schedule = MaintenanceService(db_session, owner_context(tenant_records)).save_schedule(
        asset.id,
        task_code=MaintenanceTaskCode.ENGINE_OIL,
        custom_label=None,
        action_type=MaintenanceActionType.REPLACE,
        description=None,
        enabled=True,
        criteria=[
            CriterionInput(
                MaintenanceCriterionBasis.CALENDAR_DAYS,
                Decimal("30"),
                Decimal("5"),
                baseline_date=date(2020, 1, 1),
            )
        ],
    )
    create_assignment(
        db_session,
        company_id=company.id,
        driver_membership_id=driver_membership.id,
        supervisor_membership_id=supervisor_membership.id,
        asset_id=asset.id,
        site_id=site.id,
        starts_at=datetime.now(UTC) - timedelta(hours=1),
    )
    grant_supervisor_site_access(
        db_session,
        company_id=company.id,
        supervisor_membership_id=supervisor_membership.id,
        site_id=site.id,
    )
    evidence_uuid = uuid4()
    evidence = EvidenceObject(
        company_id=company.id,
        membership_id=driver_membership.id,
        client_event_uuid=evidence_uuid,
        object_key=f"private/{evidence_uuid}.jpg",
        content_type="image/jpeg",
        size_bytes=24,
    )
    db_session.add(evidence)
    db_session.commit()

    driver = client_for(db_session, driver_membership)
    supervisor = client_for(db_session, supervisor_membership)
    wrong_site_supervisor = client_for(db_session, unauthorized_supervisor)
    try:
        due = driver.get("/api/v1/driver/maintenance/due")
        assert due.status_code == 200, due.text
        assert due.json() == [
            {
                "schedule_id": str(schedule.id),
                "asset_id": str(asset.id),
                "task_label": "Engine Oil",
                "status": "OVERDUE",
            }
        ]

        submission_uuid = uuid4()
        payload = {
            "client_submission_uuid": str(submission_uuid),
            "schedule_id": str(schedule.id),
            "evidence_object_references": [evidence.object_key],
            "note": "Service completed",
        }
        submitted = driver.post("/api/v1/driver/maintenance/proofs", json=payload)
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["duplicate"] is False
        duplicate = driver.post("/api/v1/driver/maintenance/proofs", json=payload)
        assert duplicate.status_code == 200, duplicate.text
        assert duplicate.json()["id"] == submitted.json()["id"]
        assert duplicate.json()["duplicate"] is True
        conflicting_pending = driver.post(
            "/api/v1/driver/maintenance/proofs",
            json={**payload, "client_submission_uuid": str(uuid4())},
        )
        assert conflicting_pending.status_code == 409
        assert driver.get("/api/v1/driver/maintenance/due").json() == []

        forbidden_list = wrong_site_supervisor.get(
            "/api/v1/supervisor/maintenance/proofs", params={"site_id": str(site.id)}
        )
        assert forbidden_list.status_code == 403
        assert (
            driver.post(
                f"/api/v1/supervisor/maintenance/proofs/{submitted.json()['id']}/review",
                json={"decision": "APPROVE"},
            ).status_code
            == 403
        )

        pending = supervisor.get(
            "/api/v1/supervisor/maintenance/proofs", params={"site_id": str(site.id)}
        )
        assert pending.status_code == 200, pending.text
        assert [item["id"] for item in pending.json()] == [submitted.json()["id"]]
        approved = supervisor.post(
            f"/api/v1/supervisor/maintenance/proofs/{submitted.json()['id']}/review",
            json={"decision": "APPROVE"},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "COMPLETED"
        assert approved.json()["work_order_id"] is not None
        assert driver.get("/api/v1/driver/maintenance/due").json() == []
    finally:
        driver.close()
        supervisor.close()
        wrong_site_supervisor.close()
