from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from fleet_api.core.features import FeatureRegistry, FutureFeature
from fleet_api.domain.enums import ExpenseCategory
from fleet_api.domain.errors import ConflictError, DomainError, FeatureUnavailableError


@dataclass(frozen=True)
class ExternalFleetTransaction:
    company_id: UUID
    asset_id: UUID
    provider: str
    provider_transaction_id: str
    occurred_at: datetime
    amount: Decimal
    currency: str
    category: ExpenseCategory
    location_name: str | None = None
    raw_provider_reference: str | None = None


class ExpenseProvider(Protocol):
    def fetch_transactions(
        self,
        *,
        starts_at: datetime,
        ends_at: datetime,
    ) -> list[ExternalFleetTransaction]: ...


def validate_external_transaction(
    transaction: ExternalFleetTransaction,
) -> ExternalFleetTransaction:
    provider = transaction.provider.strip()
    external_id = transaction.provider_transaction_id.strip()
    if not provider or not external_id:
        raise DomainError("expense provider and transaction id are required")
    if transaction.occurred_at.tzinfo is None or transaction.occurred_at.utcoffset() is None:
        raise DomainError("expense timestamp must include a timezone")
    if not transaction.amount.is_finite() or transaction.amount <= 0:
        raise DomainError("expense amount must be finite and positive")
    currency = transaction.currency.strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise DomainError("expense currency must be a three-letter code")
    return replace(
        transaction,
        provider=provider,
        provider_transaction_id=external_id,
        currency=currency,
        location_name=(transaction.location_name.strip() if transaction.location_name else None),
    )


class ExpenseTransactionImporter:
    """Vendor-neutral, contract-only normalization and idempotency boundary."""

    def __init__(self, registry: FeatureRegistry, *, company_id: UUID) -> None:
        self.registry = registry
        self.company_id = company_id
        self._seen: dict[tuple[str, str], ExternalFleetTransaction] = {}

    def accept(self, transaction: ExternalFleetTransaction) -> ExternalFleetTransaction:
        if not self.registry.is_enabled(FutureFeature.TOLL_EXPENSES):
            raise FeatureUnavailableError("toll and expense integrations are disabled")
        if transaction.company_id != self.company_id:
            raise DomainError("expense asset mapping belongs to another company")
        normalized = validate_external_transaction(transaction)
        key = (normalized.provider, normalized.provider_transaction_id)
        previous = self._seen.get(key)
        if previous is not None and previous != normalized:
            raise ConflictError("external expense transaction id was reused")
        self._seen[key] = normalized
        return normalized
