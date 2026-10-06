from __future__ import annotations

import csv
import io
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from fleet_api.auth.service import AuthContext, ensure_role
from fleet_api.core.features import FeatureRegistry, FutureFeature
from fleet_api.db.models import (
    Assignment,
    DieselEvent,
    ExternalFuelTransaction,
    FleetAsset,
    FuelImportBatch,
    FuelReconciliation,
    OperationalEvent,
)
from fleet_api.domain.audit import write_audit_log
from fleet_api.domain.enums import (
    FuelImportBatchStatus,
    FuelImportRowStatus,
    FuelReconciliationStatus,
    FuelSourceType,
    MembershipRole,
    VerificationStatus,
)
from fleet_api.domain.errors import (
    ConflictError,
    DomainError,
    FeatureUnavailableError,
    NotFoundError,
)


@dataclass(frozen=True)
class FuelTransaction:
    company_id: UUID
    asset_id: UUID
    source_type: FuelSourceType
    source_name: str
    external_transaction_id: str
    occurred_at: datetime
    litres: Decimal


@dataclass(frozen=True)
class FuelReconciliationResult:
    status: FuelReconciliationStatus
    difference_litres: Decimal | None
    tolerance_litres: Decimal


class FuelProvider(Protocol):
    def fetch_transactions(
        self,
        *,
        starts_at: datetime,
        ends_at: datetime,
    ) -> list[FuelTransaction]: ...


def validate_fuel_transaction(transaction: FuelTransaction) -> FuelTransaction:
    source_name = transaction.source_name.strip()
    external_id = transaction.external_transaction_id.strip()
    if not source_name or not external_id:
        raise DomainError("fuel source and external transaction id are required")
    if transaction.occurred_at.tzinfo is None or transaction.occurred_at.utcoffset() is None:
        raise DomainError("fuel transaction timestamp must include a timezone")
    if not transaction.litres.is_finite() or transaction.litres <= 0:
        raise DomainError("fuel litres must be finite and positive")
    return replace(
        transaction,
        source_name=source_name,
        external_transaction_id=external_id,
    )


def reconcile_fuel(
    quantities: list[Decimal],
    *,
    tolerance_litres: Decimal,
) -> FuelReconciliationResult:
    if not tolerance_litres.is_finite() or tolerance_litres < 0:
        raise DomainError("fuel tolerance must be finite and non-negative")
    if len(quantities) < 2:
        return FuelReconciliationResult(
            FuelReconciliationStatus.INSUFFICIENT_DATA,
            None,
            tolerance_litres,
        )
    if any(not value.is_finite() or value <= 0 for value in quantities):
        raise DomainError("fuel quantities must be finite and positive")
    spread = max(quantities) - min(quantities)
    if spread == 0:
        status = FuelReconciliationStatus.MATCHED
    elif spread <= tolerance_litres:
        status = FuelReconciliationStatus.WITHIN_TOLERANCE
    else:
        status = FuelReconciliationStatus.MISMATCH
    return FuelReconciliationResult(status, spread, tolerance_litres)


class FuelTransactionImporter:
    """Contract-only normalizer with deterministic duplicate handling."""

    def __init__(self, registry: FeatureRegistry, *, company_id: UUID) -> None:
        self.registry = registry
        self.company_id = company_id
        self._seen: dict[tuple[str, str], FuelTransaction] = {}

    def accept(self, transaction: FuelTransaction) -> FuelTransaction:
        if not self.registry.is_enabled(FutureFeature.FUEL_INTEGRATIONS):
            raise FeatureUnavailableError("fuel integrations are disabled")
        if transaction.company_id != self.company_id:
            raise DomainError("fuel asset mapping belongs to another company")
        normalized = validate_fuel_transaction(transaction)
        key = (normalized.source_name, normalized.external_transaction_id)
        previous = self._seen.get(key)
        if previous is not None and previous != normalized:
            raise ConflictError("external fuel transaction id was reused")
        self._seen[key] = normalized
        return normalized


FUEL_CSV_HEADERS = (
    "external_transaction_id",
    "occurred_at",
    "litres",
    "asset_identifier",
    "source_type",
)


@dataclass(frozen=True)
class FuelImportResult:
    batch: FuelImportBatch
    rows: list[ExternalFuelTransaction]


def fuel_csv_template() -> str:
    return ",".join(FUEL_CSV_HEADERS) + "\n"


def spreadsheet_safe(value: object) -> object:
    """Neutralize formula-leading text while retaining numeric cell types."""

    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed


class FuelIntegrationService:
    """Owner-only CSV imports and reconciliation against verified diesel events."""

    def __init__(
        self,
        session: Session,
        context: AuthContext,
        *,
        request_id: str | None = None,
    ) -> None:
        ensure_role(context, MembershipRole.OWNER_ADMIN)
        self.session = session
        self.company_id = context.company.id
        self.actor_id = context.membership.id
        self.request_id = request_id

    def _map_asset(self, identifier: str) -> FleetAsset | None:
        clean = identifier.strip().upper()
        if not clean:
            return None
        matches = list(
            self.session.scalars(
                select(FleetAsset).where(
                    FleetAsset.company_id == self.company_id,
                    (FleetAsset.asset_code == clean) | (FleetAsset.registration_number == clean),
                )
            )
        )
        return matches[0] if len(matches) == 1 else None

    def import_csv(self, *, file_name: str, source_name: str, content: bytes) -> FuelImportResult:
        clean_source = source_name.strip()
        if not clean_source:
            raise DomainError("source_name is required")
        if len(content) > 5_000_000:
            raise DomainError("fuel CSV exceeds the 5 MB limit")
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DomainError("fuel CSV must be UTF-8 encoded") from exc
        reader = csv.DictReader(io.StringIO(decoded))
        if reader.fieldnames != list(FUEL_CSV_HEADERS):
            raise DomainError("fuel CSV headers must exactly match the published template")
        batch = FuelImportBatch(
            company_id=self.company_id,
            file_name=file_name.strip() or "fuel-import.csv",
            source_name=clean_source,
            status=FuelImportBatchStatus.PROCESSING,
            total_rows=0,
            imported_rows=0,
            rejected_rows=0,
            created_by=self.actor_id,
        )
        self.session.add(batch)
        self.session.flush()
        imported: list[ExternalFuelTransaction] = []
        for row_number, source_row in enumerate(reader, start=2):
            batch.total_rows += 1
            raw_row = {key: value or "" for key, value in source_row.items() if key is not None}
            external_id = raw_row.get("external_transaction_id", "").strip()
            asset_identifier = raw_row.get("asset_identifier", "").strip().upper()
            source_type_value = raw_row.get("source_type", "").strip().upper()
            row_status = FuelImportRowStatus.INVALID
            error: str | None = None
            occurred_at: datetime | None = None
            litres: Decimal | None = None
            asset: FleetAsset | None = None
            source_type = FuelSourceType.OTHER
            try:
                if not external_id:
                    raise ValueError("external_transaction_id is required")
                occurred_at = _parse_timestamp(raw_row.get("occurred_at", ""))
                litres = Decimal(raw_row.get("litres", ""))
                if not litres.is_finite() or litres <= 0:
                    raise ValueError("litres must be finite and positive")
                source_type = FuelSourceType(source_type_value)
                asset = self._map_asset(asset_identifier)
                if asset is None:
                    row_status = FuelImportRowStatus.UNMAPPED
                    error = (
                        "asset_identifier did not uniquely match asset_code or registration_number"
                    )
                else:
                    duplicate = self.session.scalar(
                        select(ExternalFuelTransaction.id).where(
                            ExternalFuelTransaction.company_id == self.company_id,
                            ExternalFuelTransaction.source_name == clean_source,
                            ExternalFuelTransaction.external_transaction_id == external_id,
                            ExternalFuelTransaction.row_status == FuelImportRowStatus.IMPORTED,
                        )
                    )
                    if duplicate is not None:
                        row_status = FuelImportRowStatus.DUPLICATE
                        error = "external transaction was already imported"
                    else:
                        row_status = FuelImportRowStatus.IMPORTED
            except (ValueError, ArithmeticError) as exc:
                error = str(exc)
            item = ExternalFuelTransaction(
                company_id=self.company_id,
                batch_id=batch.id,
                row_number=row_number,
                row_status=row_status,
                error_message=error,
                asset_id=asset.id if asset else None,
                asset_identifier=asset_identifier,
                source_type=source_type,
                source_name=clean_source,
                external_transaction_id=external_id or f"invalid-row-{row_number}",
                occurred_at=occurred_at,
                litres=litres,
                raw_row=raw_row,
            )
            self.session.add(item)
            self.session.flush()
            imported.append(item)
            if row_status == FuelImportRowStatus.IMPORTED:
                batch.imported_rows += 1
            else:
                batch.rejected_rows += 1
        batch.status = (
            FuelImportBatchStatus.COMPLETED_WITH_ERRORS
            if batch.rejected_rows
            else FuelImportBatchStatus.COMPLETED
        )
        self.session.flush()
        write_audit_log(
            self.session,
            company_id=self.company_id,
            actor_membership_id=self.actor_id,
            action="FUEL_CSV_IMPORTED",
            entity_type="FUEL_IMPORT_BATCH",
            entity_id=batch.id,
            new_values={
                "source_name": clean_source,
                "total_rows": batch.total_rows,
                "imported_rows": batch.imported_rows,
                "rejected_rows": batch.rejected_rows,
            },
            request_id=self.request_id,
        )
        return FuelImportResult(batch, imported)

    def reconcile_batch(
        self,
        batch_id: UUID,
        *,
        tolerance_litres: Decimal,
        time_window_minutes: int = 720,
    ) -> list[FuelReconciliation]:
        if not tolerance_litres.is_finite() or tolerance_litres < 0:
            raise DomainError("tolerance_litres must be finite and non-negative")
        if time_window_minutes <= 0 or time_window_minutes > 10080:
            raise DomainError("time_window_minutes must be between 1 and 10080")
        batch = self.session.scalar(
            select(FuelImportBatch).where(
                FuelImportBatch.company_id == self.company_id, FuelImportBatch.id == batch_id
            )
        )
        if batch is None:
            raise NotFoundError("fuel import batch not found")
        rows = list(
            self.session.scalars(
                select(ExternalFuelTransaction).where(
                    ExternalFuelTransaction.company_id == self.company_id,
                    ExternalFuelTransaction.batch_id == batch_id,
                    ExternalFuelTransaction.row_status == FuelImportRowStatus.IMPORTED,
                )
            )
        )
        results: list[FuelReconciliation] = []
        for row in rows:
            if row.asset_id is None or row.occurred_at is None or row.litres is None:
                continue
            existing = self.session.scalar(
                select(FuelReconciliation).where(
                    FuelReconciliation.company_id == self.company_id,
                    FuelReconciliation.external_transaction_id == row.id,
                )
            )
            if existing is not None:
                results.append(existing)
                continue
            window = timedelta(minutes=time_window_minutes)
            candidates = self.session.execute(
                select(OperationalEvent, DieselEvent)
                .join(DieselEvent, DieselEvent.event_id == OperationalEvent.id)
                .join(Assignment, Assignment.id == OperationalEvent.assignment_id)
                .where(
                    OperationalEvent.company_id == self.company_id,
                    Assignment.company_id == self.company_id,
                    Assignment.asset_id == row.asset_id,
                    OperationalEvent.verification_status.in_(
                        [VerificationStatus.APPROVED, VerificationStatus.AMENDED]
                    ),
                    OperationalEvent.device_created_at >= row.occurred_at - window,
                    OperationalEvent.device_created_at <= row.occurred_at + window,
                )
                .order_by(OperationalEvent.device_created_at)
            ).all()
            matching = [
                (event, diesel)
                for event, diesel in candidates
                if abs(diesel.litres - row.litres) <= tolerance_litres
            ]
            if len(matching) > 1:
                result_status = FuelReconciliationStatus.AMBIGUOUS
                event_id = None
                difference = None
            elif len(matching) == 1:
                event, diesel = matching[0]
                result = reconcile_fuel(
                    [row.litres, diesel.litres], tolerance_litres=tolerance_litres
                )
                result_status = result.status
                event_id = event.id
                difference = result.difference_litres
            elif candidates:
                nearest_event, nearest_diesel = min(
                    candidates,
                    key=lambda pair: abs(pair[0].device_created_at - row.occurred_at),
                )
                result_status = FuelReconciliationStatus.MISMATCH
                event_id = nearest_event.id
                difference = abs(nearest_diesel.litres - row.litres)
            else:
                result_status = FuelReconciliationStatus.INSUFFICIENT_DATA
                event_id = None
                difference = None
            reconciliation = FuelReconciliation(
                company_id=self.company_id,
                external_transaction_id=row.id,
                operational_event_id=event_id,
                status=result_status,
                tolerance_litres=tolerance_litres,
                difference_litres=difference,
                manually_resolved=False,
            )
            self.session.add(reconciliation)
            self.session.flush()
            results.append(reconciliation)
        return results

    def resolve(self, reconciliation_id: UUID, *, reason: str) -> FuelReconciliation:
        clean_reason = reason.strip()
        if not clean_reason:
            raise DomainError("resolution reason is required")
        item = self.session.scalar(
            select(FuelReconciliation)
            .where(
                FuelReconciliation.company_id == self.company_id,
                FuelReconciliation.id == reconciliation_id,
            )
            .with_for_update()
        )
        if item is None:
            raise NotFoundError("fuel reconciliation not found")
        item.manually_resolved = True
        item.resolution_reason = clean_reason
        item.resolved_by = self.actor_id
        self.session.flush()
        write_audit_log(
            self.session,
            company_id=self.company_id,
            actor_membership_id=self.actor_id,
            action="FUEL_RECONCILIATION_RESOLVED",
            entity_type="FUEL_RECONCILIATION",
            entity_id=item.id,
            new_values={"reason": clean_reason},
            request_id=self.request_id,
        )
        return item

    def list_batches(self) -> list[FuelImportBatch]:
        return list(
            self.session.scalars(
                select(FuelImportBatch)
                .where(FuelImportBatch.company_id == self.company_id)
                .order_by(FuelImportBatch.created_at.desc())
            )
        )

    def list_transactions(self) -> list[ExternalFuelTransaction]:
        return list(
            self.session.scalars(
                select(ExternalFuelTransaction)
                .where(ExternalFuelTransaction.company_id == self.company_id)
                .order_by(
                    ExternalFuelTransaction.created_at.desc(),
                    ExternalFuelTransaction.row_number,
                )
            )
        )

    def list_reconciliations(self) -> list[FuelReconciliation]:
        return list(
            self.session.scalars(
                select(FuelReconciliation)
                .where(FuelReconciliation.company_id == self.company_id)
                .order_by(FuelReconciliation.created_at.desc())
            )
        )
