from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fleet_api.auth.service import AuthContext, ensure_role
from fleet_api.core.features import FeatureRegistry, FutureFeature
from fleet_api.db.models import CompanyMembership, InAppNotification
from fleet_api.domain.asset_documents import AssetDocumentService
from fleet_api.domain.enums import (
    AssetDocumentExpiryStatus,
    DeliveryStatus,
    MaintenanceDueStatus,
    MembershipRole,
    MembershipStatus,
    NotificationCategory,
    NotificationChannel,
    NotificationState,
)
from fleet_api.domain.errors import (
    ConflictError,
    FeatureUnavailableError,
    NotFoundError,
    TenantConsistencyError,
)
from fleet_api.domain.maintenance import MaintenanceService


@dataclass(frozen=True)
class NotificationRecipient:
    company_id: UUID
    membership_id: UUID
    channel: NotificationChannel
    address: str


@dataclass(frozen=True)
class NotificationRequest:
    company_id: UUID
    category: NotificationCategory
    recipient: NotificationRecipient
    title: str
    body: str
    idempotency_key: str
    deep_link_metadata: dict[str, str] | None = None


@dataclass(frozen=True)
class NotificationDelivery:
    notification_id: UUID
    status: DeliveryStatus
    provider_reference: str | None = None
    error_code: str | None = None


class NotificationProvider(Protocol):
    def deliver(
        self,
        *,
        notification_id: UUID,
        request: NotificationRequest,
    ) -> NotificationDelivery: ...


class NullNotificationProvider:
    def deliver(
        self,
        *,
        notification_id: UUID,
        request: NotificationRequest,
    ) -> NotificationDelivery:
        del request
        return NotificationDelivery(notification_id, DeliveryStatus.DISABLED)


class NotificationCoordinator:
    """Contract-only, retry-safe coordinator; no current workflow invokes it."""

    def __init__(self, registry: FeatureRegistry, provider: NotificationProvider) -> None:
        self.registry = registry
        self.provider = provider
        self._accepted: dict[
            tuple[UUID, str], tuple[NotificationRequest, NotificationDelivery]
        ] = {}

    def send(self, request: NotificationRequest) -> NotificationDelivery:
        if not self.registry.is_enabled(FutureFeature.NOTIFICATIONS):
            raise FeatureUnavailableError("notifications are disabled")
        if request.recipient.company_id != request.company_id:
            raise TenantConsistencyError("notification recipient belongs to another company")
        if not request.idempotency_key.strip():
            raise ConflictError("notification idempotency_key is required")
        key = (request.company_id, request.idempotency_key)
        previous = self._accepted.get(key)
        if previous is not None:
            if previous[0] != request:
                raise ConflictError("notification idempotency key was reused with new content")
            return previous[1]
        notification_id = uuid5(
            NAMESPACE_URL,
            f"fleet-notification:{request.company_id}:{request.idempotency_key}",
        )
        try:
            result = self.provider.deliver(
                notification_id=notification_id,
                request=request,
            )
        except Exception:
            # Provider failure becomes delivery state and cannot roll back a caller's
            # already-committed business transaction.
            result = NotificationDelivery(
                notification_id,
                DeliveryStatus.FAILED,
                error_code="PROVIDER_FAILURE",
            )
        self._accepted[key] = (request, result)
        return result


class InAppNotificationService:
    """Durable per-recipient notifications with deterministic evaluation keys."""

    def __init__(self, session: Session, context: AuthContext) -> None:
        ensure_role(context, MembershipRole.OWNER_ADMIN)
        self.session = session
        self.context = context
        self.company_id = context.company.id
        self.recipient_id = context.membership.id

    def _owners(self) -> list[UUID]:
        return list(
            self.session.scalars(
                select(CompanyMembership.id).where(
                    CompanyMembership.company_id == self.company_id,
                    CompanyMembership.role == MembershipRole.OWNER_ADMIN,
                    CompanyMembership.status == MembershipStatus.ACTIVE,
                )
            )
        )

    def _create_once(
        self,
        *,
        recipient_id: UUID,
        category: NotificationCategory,
        title: str,
        body: str,
        dedupe_key: str,
        deep_link: dict[str, str],
    ) -> bool:
        exists = self.session.scalar(
            select(InAppNotification.id).where(
                InAppNotification.company_id == self.company_id,
                InAppNotification.recipient_membership_id == recipient_id,
                InAppNotification.dedupe_key == dedupe_key,
            )
        )
        if exists is not None:
            return False
        self.session.add(
            InAppNotification(
                company_id=self.company_id,
                recipient_membership_id=recipient_id,
                category=category,
                title=title,
                body=body,
                dedupe_key=dedupe_key,
                deep_link=deep_link,
                state=NotificationState.UNREAD,
            )
        )
        self.session.flush()
        return True

    def evaluate(self, *, as_of: date | None = None) -> int:
        """Best-effort evaluator; a savepoint contains all notification failures."""

        today = as_of or date.today()
        created = 0
        try:
            with self.session.begin_nested():
                owners = self._owners()
                maintenance = MaintenanceService(self.session, self.context)
                for view in maintenance.list_schedule_views(as_of=today):
                    if view.due_status not in {
                        MaintenanceDueStatus.DUE_SOON,
                        MaintenanceDueStatus.DUE,
                        MaintenanceDueStatus.OVERDUE,
                    }:
                        continue
                    schedule = view.schedule
                    version = schedule.next_due_date or schedule.next_due_meter or "unknown"
                    label = view.due_status.value.lower().replace("_", " ")
                    for owner_id in owners:
                        created += self._create_once(
                            recipient_id=owner_id,
                            category=NotificationCategory.MAINTENANCE_DUE,
                            title=f"Maintenance {label}",
                            body=f"{schedule.maintenance_type} is {label}.",
                            dedupe_key=f"maintenance:{schedule.id}:{version}:{view.due_status.value}",
                            deep_link={"tab": "maintenance", "schedule_id": str(schedule.id)},
                        )
                documents = AssetDocumentService(self.session, self.context)
                for row in documents.compliance_matrix(as_of=today):
                    if row.status not in {
                        AssetDocumentExpiryStatus.MISSING,
                        AssetDocumentExpiryStatus.EXPIRING_SOON,
                        AssetDocumentExpiryStatus.EXPIRED,
                    }:
                        continue
                    doc_version = row.revision.revision_number if row.revision else "missing"
                    label = row.status.value.lower().replace("_", " ")
                    for owner_id in owners:
                        created += self._create_once(
                            recipient_id=owner_id,
                            category=NotificationCategory.DOCUMENT_EXPIRY,
                            title=f"Document {label}",
                            body=(
                                f"{row.policy.document_type} for {row.asset.asset_code} is {label}."
                            ),
                            dedupe_key=(
                                f"document:{row.asset.id}:{row.policy.id}:"
                                f"{doc_version}:{row.status.value}"
                            ),
                            deep_link={
                                "tab": "documents",
                                "asset_id": str(row.asset.id),
                                "policy_id": str(row.policy.id),
                            },
                        )
            return created
        except Exception:
            # Notifications are advisory. The nested transaction ensures an evaluator
            # failure cannot poison or roll back a business transaction.
            return 0

    def list_mine(self, *, unread_only: bool = False) -> list[InAppNotification]:
        query = select(InAppNotification).where(
            InAppNotification.company_id == self.company_id,
            InAppNotification.recipient_membership_id == self.recipient_id,
        )
        if unread_only:
            query = query.where(InAppNotification.state == NotificationState.UNREAD)
        return list(
            self.session.scalars(
                query.order_by(InAppNotification.created_at.desc(), InAppNotification.id)
            )
        )

    def unread_count(self) -> int:
        return int(
            self.session.scalar(
                select(func.count(InAppNotification.id)).where(
                    InAppNotification.company_id == self.company_id,
                    InAppNotification.recipient_membership_id == self.recipient_id,
                    InAppNotification.state == NotificationState.UNREAD,
                )
            )
            or 0
        )

    def mark(self, notification_id: UUID, state: NotificationState) -> InAppNotification:
        item = self.session.scalar(
            select(InAppNotification)
            .where(
                InAppNotification.company_id == self.company_id,
                InAppNotification.recipient_membership_id == self.recipient_id,
                InAppNotification.id == notification_id,
            )
            .with_for_update()
        )
        if item is None:
            raise NotFoundError("notification not found")
        now = datetime.now(UTC)
        item.state = state
        if state in {NotificationState.READ, NotificationState.ACKNOWLEDGED}:
            item.read_at = item.read_at or now
        if state == NotificationState.ACKNOWLEDGED:
            item.acknowledged_at = now
        self.session.flush()
        return item

    def mark_all_read(self) -> int:
        items = self.list_mine(unread_only=True)
        now = datetime.now(UTC)
        for item in items:
            item.state = NotificationState.READ
            item.read_at = now
        self.session.flush()
        return len(items)
