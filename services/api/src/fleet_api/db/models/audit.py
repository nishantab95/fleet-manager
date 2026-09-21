from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.models.common import UUIDTimestampModel


class AuditLog(UUIDTimestampModel):
    """Explicit append-only audit record; no automatic secret-bearing auditing."""

    __tablename__ = "audit_logs"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_membership_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(nullable=False)
    old_values: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    new_values: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "actor_membership_id"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_audit_company_actor_membership",
            ondelete="RESTRICT",
        ),
        Index("ix_audit_logs_company_created", "company_id", "created_at"),
    )
