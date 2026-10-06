from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from fleet_api.db.models.common import UUIDTimestampModel
from fleet_api.domain.enums import AssetOwnershipType, FleetAssetType


class AssetDocumentPolicy(UUIDTimestampModel):
    """Company requirement for a document type and asset classification."""

    __tablename__ = "asset_document_policies"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_type: Mapped[FleetAssetType] = mapped_column(
        SAEnum(FleetAssetType, name="fleet_asset_type_enum"), nullable=False
    )
    ownership_type: Mapped[AssetOwnershipType | None] = mapped_column(
        SAEnum(AssetOwnershipType, name="asset_ownership_type_enum"), nullable=True
    )
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expiry_warning_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    created_by: Mapped[UUID] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_asset_document_policies_company_id"),
        Index(
            "uq_asset_document_policies_scope",
            "company_id",
            "asset_type",
            "ownership_type",
            "document_type",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_asset_document_policies_company_creator",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "expiry_warning_days BETWEEN 0 AND 3650",
            name="asset_document_policy_warning_days_range",
        ),
        CheckConstraint(
            "length(btrim(document_type)) BETWEEN 1 AND 64",
            name="asset_document_policy_type_non_empty",
        ),
    )


class AssetDocument(UUIDTimestampModel):
    """Stable identity for one type of document attached to an asset."""

    __tablename__ = "asset_documents"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    expiry_warning_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    created_by: Mapped[UUID] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_asset_documents_company_id"),
        UniqueConstraint(
            "company_id",
            "asset_id",
            "document_type",
            name="uq_asset_documents_company_asset_type",
        ),
        ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["fleet_assets.company_id", "fleet_assets.id"],
            name="fk_asset_documents_company_asset",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_asset_documents_company_creator",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "expiry_warning_days BETWEEN 0 AND 3650",
            name="asset_document_warning_days_range",
        ),
        CheckConstraint(
            "length(btrim(document_type)) BETWEEN 1 AND 64",
            name="asset_document_type_non_empty",
        ),
        Index("ix_asset_documents_company_asset", "company_id", "asset_id"),
    )


class AssetDocumentRevision(UUIDTimestampModel):
    """Append-only document metadata and private-object revision."""

    __tablename__ = "asset_document_revisions"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    issuer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_object_id: Mapped[UUID] = mapped_column(nullable=False)
    created_by: Mapped[UUID] = mapped_column(nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "document_id"],
            ["asset_documents.company_id", "asset_documents.id"],
            name="fk_asset_document_revisions_company_document",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "evidence_object_id"],
            ["evidence_objects.company_id", "evidence_objects.id"],
            name="fk_asset_document_revisions_company_evidence",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "created_by"],
            ["company_memberships.company_id", "company_memberships.id"],
            name="fk_asset_document_revisions_company_creator",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "document_id",
            "revision_number",
            name="uq_asset_document_revisions_company_document_version",
        ),
        UniqueConstraint(
            "company_id",
            "evidence_object_id",
            name="uq_asset_document_revisions_company_evidence",
        ),
        CheckConstraint("revision_number > 0", name="asset_document_revision_positive"),
        CheckConstraint(
            "expiry_date IS NULL OR issue_date IS NULL OR expiry_date >= issue_date",
            name="asset_document_revision_dates_ordered",
        ),
        Index(
            "ix_asset_document_revisions_company_document_created",
            "company_id",
            "document_id",
            "created_at",
        ),
    )
