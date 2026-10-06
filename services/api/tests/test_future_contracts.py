from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from fleet_api.core.config import Settings
from fleet_api.core.features import FeatureRegistry, FutureFeature
from fleet_api.domain.asset_documents import expiry_status
from fleet_api.domain.enums import (
    AssetDocumentExpiryStatus,
    DeliveryStatus,
    ExpenseCategory,
    FuelReconciliationStatus,
    FuelSourceType,
    NotificationCategory,
    NotificationChannel,
)
from fleet_api.domain.errors import (
    ConflictError,
    DomainError,
    FeatureUnavailableError,
    TenantConsistencyError,
)
from fleet_api.domain.expenses import (
    ExpenseTransactionImporter,
    ExternalFleetTransaction,
    validate_external_transaction,
)
from fleet_api.domain.fuel_integrations import (
    FuelTransaction,
    FuelTransactionImporter,
    reconcile_fuel,
    validate_fuel_transaction,
)
from fleet_api.domain.notifications import (
    NotificationCoordinator,
    NotificationDelivery,
    NotificationRecipient,
    NotificationRequest,
)
from fleet_api.domain.telematics import (
    ProviderPosition,
    TelematicsService,
    TelematicsVehicleReference,
)


def test_all_future_features_default_off() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    registry = FeatureRegistry.from_settings(settings)

    assert all(not registry.is_enabled(feature) for feature in FutureFeature)


def test_explicit_test_configuration_enables_only_selected_feature() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        environment="test",
        telematics_enabled=True,
    )
    registry = FeatureRegistry.from_settings(settings)

    assert registry.is_enabled(FutureFeature.TELEMATICS)
    assert not registry.is_enabled(FutureFeature.MAINTENANCE)


class RecordingNotificationProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    def deliver(
        self,
        *,
        notification_id: object,
        request: NotificationRequest,
    ) -> NotificationDelivery:
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider unavailable")
        return NotificationDelivery(
            notification_id=notification_id,  # type: ignore[arg-type]
            status=DeliveryStatus.ACCEPTED,
        )


def _notification(company_id: object) -> NotificationRequest:
    return NotificationRequest(
        company_id=company_id,  # type: ignore[arg-type]
        category=NotificationCategory.MAINTENANCE_DUE,
        recipient=NotificationRecipient(
            company_id=company_id,  # type: ignore[arg-type]
            membership_id=uuid4(),
            channel=NotificationChannel.IN_APP,
            address="membership:owner",
        ),
        title="Maintenance due",
        body="Review asset maintenance.",
        idempotency_key="maintenance:one",
        deep_link_metadata={"resource_type": "maintenance_schedule"},
    )


def test_notifications_are_disabled_idempotent_and_failure_isolated() -> None:
    company_id = uuid4()
    provider = RecordingNotificationProvider()
    disabled = NotificationCoordinator(FeatureRegistry(), provider)
    with pytest.raises(FeatureUnavailableError):
        disabled.send(_notification(company_id))
    assert provider.calls == 0

    enabled = NotificationCoordinator(
        FeatureRegistry(notifications_enabled=True),
        provider,
    )
    request = _notification(company_id)
    first = enabled.send(request)
    second = enabled.send(request)
    assert first == second
    assert provider.calls == 1

    failing = NotificationCoordinator(
        FeatureRegistry(notifications_enabled=True),
        RecordingNotificationProvider(fail=True),
    )
    assert failing.send(_notification(company_id)).status == DeliveryStatus.FAILED


def test_notification_recipient_must_share_tenant() -> None:
    request = _notification(uuid4())
    request = NotificationRequest(
        **{
            **request.__dict__,
            "recipient": NotificationRecipient(
                company_id=uuid4(),
                membership_id=uuid4(),
                channel=NotificationChannel.IN_APP,
                address="membership:foreign",
            ),
        }
    )
    coordinator = NotificationCoordinator(
        FeatureRegistry(notifications_enabled=True),
        RecordingNotificationProvider(),
    )
    with pytest.raises(TenantConsistencyError):
        coordinator.send(request)


class FakeTelematicsProvider:
    def __init__(self, position: ProviderPosition) -> None:
        self.position = position

    def fetch_latest_position(self, provider_vehicle_id: str) -> ProviderPosition:
        assert provider_vehicle_id == "vehicle-1"
        return self.position

    def fetch_history(
        self, provider_vehicle_id: str, *, starts_at: datetime, ends_at: datetime
    ) -> list[ProviderPosition]:
        del provider_vehicle_id, starts_at, ends_at
        return [self.position]

    def fetch_odometer(self, provider_vehicle_id: str) -> Decimal | None:
        del provider_vehicle_id
        return self.position.odometer_km

    def fetch_events(
        self, provider_vehicle_id: str, *, starts_at: datetime, ends_at: datetime
    ) -> list[str]:
        del provider_vehicle_id, starts_at, ends_at
        return []


def test_telematics_normalizes_and_blocks_invalid_or_foreign_mapping() -> None:
    company_id = uuid4()
    mapping = TelematicsVehicleReference(company_id, uuid4(), "fake", "vehicle-1")
    provider = FakeTelematicsProvider(
        ProviderPosition(
            timestamp=datetime.now(UTC),
            latitude=Decimal("12.9716"),
            longitude=Decimal("77.5946"),
            speed_kph=Decimal("22.5"),
            heading=Decimal("180"),
            odometer_km=Decimal("1000.5"),
        )
    )
    service = TelematicsService(
        FeatureRegistry(telematics_enabled=True),
        provider,
        company_id=company_id,
    )
    assert service.latest(mapping).asset_id == mapping.asset_id

    with pytest.raises(FeatureUnavailableError):
        TelematicsService(FeatureRegistry(), provider, company_id=company_id).latest(mapping)

    with pytest.raises(TenantConsistencyError):
        service.latest(TelematicsVehicleReference(uuid4(), uuid4(), "fake", "vehicle-1"))

    invalid = FakeTelematicsProvider(
        ProviderPosition(datetime.now(UTC), Decimal("91"), Decimal("0"))
    )
    with pytest.raises(DomainError, match="latitude"):
        TelematicsService(
            FeatureRegistry(telematics_enabled=True), invalid, company_id=company_id
        ).latest(mapping)


def test_fuel_reconciliation_and_external_idempotency_are_deterministic() -> None:
    assert (
        reconcile_fuel([Decimal("100"), Decimal("100")], tolerance_litres=Decimal("2")).status
        == FuelReconciliationStatus.MATCHED
    )
    assert (
        reconcile_fuel([Decimal("100"), Decimal("99")], tolerance_litres=Decimal("2")).status
        == FuelReconciliationStatus.WITHIN_TOLERANCE
    )
    assert (
        reconcile_fuel([Decimal("100"), Decimal("94")], tolerance_litres=Decimal("2")).status
        == FuelReconciliationStatus.MISMATCH
    )

    company_id = uuid4()
    transaction = FuelTransaction(
        company_id,
        uuid4(),
        FuelSourceType.BUNK_DISPENSER,
        "fake-bunk",
        "txn-1",
        datetime.now(UTC),
        Decimal("100"),
    )
    importer = FuelTransactionImporter(
        FeatureRegistry(fuel_integrations_enabled=True), company_id=company_id
    )
    assert importer.accept(transaction) == importer.accept(transaction)
    with pytest.raises(ConflictError):
        importer.accept(FuelTransaction(**{**transaction.__dict__, "litres": Decimal("101")}))
    with pytest.raises(DomainError, match="positive"):
        validate_fuel_transaction(
            FuelTransaction(**{**transaction.__dict__, "litres": Decimal("0")})
        )


def test_expense_normalization_duplicate_tenant_and_disabled_guards() -> None:
    company_id = uuid4()
    transaction = ExternalFleetTransaction(
        company_id=company_id,
        asset_id=uuid4(),
        provider="fake-fastag",
        provider_transaction_id="toll-1",
        occurred_at=datetime.now(UTC),
        amount=Decimal("250.00"),
        currency="INR",
        category=ExpenseCategory.TOLL,
        location_name="Test plaza",
    )
    disabled = ExpenseTransactionImporter(FeatureRegistry(), company_id=company_id)
    with pytest.raises(FeatureUnavailableError):
        disabled.accept(transaction)

    importer = ExpenseTransactionImporter(
        FeatureRegistry(toll_expenses_enabled=True), company_id=company_id
    )
    assert importer.accept(transaction) == importer.accept(transaction)
    with pytest.raises(ConflictError):
        importer.accept(
            ExternalFleetTransaction(**{**transaction.__dict__, "amount": Decimal("251.00")})
        )
    with pytest.raises(DomainError, match="another company"):
        importer.accept(ExternalFleetTransaction(**{**transaction.__dict__, "company_id": uuid4()}))
    with pytest.raises(DomainError, match="positive"):
        validate_external_transaction(
            ExternalFleetTransaction(**{**transaction.__dict__, "amount": Decimal("-1.00")})
        )


def test_document_expiry_policy_is_explicit_and_deterministic() -> None:
    as_of = datetime(2026, 10, 6, tzinfo=UTC).date()
    assert expiry_status(None, as_of=as_of, warning_days=30) == AssetDocumentExpiryStatus.NO_EXPIRY
    assert (
        expiry_status(as_of, as_of=as_of, warning_days=0) == AssetDocumentExpiryStatus.EXPIRING_SOON
    )
    assert (
        expiry_status(as_of.replace(day=5), as_of=as_of, warning_days=30)
        == AssetDocumentExpiryStatus.EXPIRED
    )
