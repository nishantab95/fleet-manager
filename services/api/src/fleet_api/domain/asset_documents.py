from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fleet_api.auth.service import AuthContext, ensure_role
from fleet_api.core.config import Settings
from fleet_api.db.models import (
    AssetDocument,
    AssetDocumentPolicy,
    AssetDocumentRevision,
    EvidenceObject,
    FleetAsset,
)
from fleet_api.domain.audit import write_audit_log
from fleet_api.domain.enums import (
    AssetDocumentExpiryStatus,
    AssetOwnershipType,
    FleetAssetType,
    MembershipRole,
)
from fleet_api.domain.errors import ConflictError, DomainError, NotFoundError
from fleet_api.domain.private_files import store_private_evidence
from fleet_api.storage.objects import ObjectStorage


@dataclass(frozen=True)
class AssetDocumentView:
    document: AssetDocument
    revision: AssetDocumentRevision
    expiry_status: AssetDocumentExpiryStatus


@dataclass(frozen=True)
class AssetComplianceView:
    asset: FleetAsset
    policy: AssetDocumentPolicy
    document: AssetDocument | None
    revision: AssetDocumentRevision | None
    status: AssetDocumentExpiryStatus


BUILT_IN_DOCUMENT_TYPES = frozenset(
    {
        "REGISTRATION_CERTIFICATE",
        "INSURANCE",
        "FITNESS_CERTIFICATE",
        "POLLUTION_CERTIFICATE",
        "ROAD_TAX",
        "PERMIT",
        "PURCHASE_INVOICE",
        "RENTAL_AGREEMENT",
        "WARRANTY",
        "CUSTOM",
    }
)


def normalize_document_type(value: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", value.strip().upper()).strip("_")
    if not normalized or len(normalized) > 64:
        raise DomainError("document_type must contain at most 64 safe characters")
    return normalized


def validate_policy_document_type(value: str) -> str:
    normalized = normalize_document_type(value)
    if normalized not in BUILT_IN_DOCUMENT_TYPES:
        raise DomainError("document_type is not supported")
    return normalized


def expiry_status(
    expiry_date: date | None,
    *,
    as_of: date,
    warning_days: int,
) -> AssetDocumentExpiryStatus:
    if warning_days < 0:
        raise DomainError("warning_days cannot be negative")
    if expiry_date is None:
        return AssetDocumentExpiryStatus.NO_EXPIRY
    if expiry_date < as_of:
        return AssetDocumentExpiryStatus.EXPIRED
    if expiry_date <= as_of + timedelta(days=warning_days):
        return AssetDocumentExpiryStatus.EXPIRING_SOON
    return AssetDocumentExpiryStatus.VALID


class AssetDocumentService:
    """Owner-only document metadata, revision history, and private-file boundary."""

    def __init__(
        self,
        session: Session,
        context: AuthContext,
        *,
        request_id: str | None = None,
    ) -> None:
        ensure_role(context, MembershipRole.OWNER_ADMIN)
        self.session = session
        self.context = context
        self.company_id = context.company.id
        self.actor_id = context.membership.id
        self.request_id = request_id

    def _asset(self, asset_id: UUID) -> FleetAsset:
        asset = self.session.scalar(
            select(FleetAsset).where(
                FleetAsset.company_id == self.company_id,
                FleetAsset.id == asset_id,
            )
        )
        if asset is None:
            raise NotFoundError("asset not found")
        return asset

    def _document(self, document_id: UUID, *, lock: bool = False) -> AssetDocument:
        query = select(AssetDocument).where(
            AssetDocument.company_id == self.company_id,
            AssetDocument.id == document_id,
        )
        if lock:
            query = query.with_for_update()
        document = self.session.scalar(query)
        if document is None:
            raise NotFoundError("asset document not found")
        return document

    def _evidence(self, evidence_id: UUID) -> EvidenceObject:
        evidence = self.session.scalar(
            select(EvidenceObject).where(
                EvidenceObject.company_id == self.company_id,
                EvidenceObject.id == evidence_id,
                EvidenceObject.membership_id == self.actor_id,
            )
        )
        if evidence is None:
            raise NotFoundError("private evidence not found")
        return evidence

    def upload(
        self,
        storage: ObjectStorage,
        settings: Settings,
        *,
        upload_id: UUID,
        content_type: str,
        content: bytes,
    ) -> EvidenceObject:
        return store_private_evidence(
            self.session,
            self.context,
            storage,
            reference_uuid=upload_id,
            purpose="asset-documents",
            content_type=content_type,
            content=content,
            allowed_mime_types=settings.asset_document_mime_types,
            max_bytes=settings.evidence_max_bytes,
        )

    def _revision(
        self,
        *,
        document: AssetDocument,
        revision_number: int,
        evidence_object_id: UUID,
        document_number: str | None,
        issue_date: date | None,
        expiry_date_value: date | None,
        issuer: str | None,
        notes: str | None,
    ) -> AssetDocumentRevision:
        if issue_date is not None and expiry_date_value is not None:
            if expiry_date_value < issue_date:
                raise DomainError("expiry_date cannot be before issue_date")
        self._evidence(evidence_object_id)
        used = self.session.scalar(
            select(AssetDocumentRevision.id).where(
                AssetDocumentRevision.company_id == self.company_id,
                AssetDocumentRevision.evidence_object_id == evidence_object_id,
            )
        )
        if used is not None:
            raise ConflictError("private evidence is already attached to a document")
        revision = AssetDocumentRevision(
            company_id=self.company_id,
            document_id=document.id,
            revision_number=revision_number,
            document_number=document_number.strip() if document_number else None,
            issue_date=issue_date,
            expiry_date=expiry_date_value,
            issuer=issuer.strip() if issuer else None,
            notes=notes.strip() if notes else None,
            evidence_object_id=evidence_object_id,
            created_by=self.actor_id,
        )
        self.session.add(revision)
        self.session.flush()
        return revision

    def create(
        self,
        *,
        asset_id: UUID,
        document_type: str,
        expiry_warning_days: int,
        evidence_object_id: UUID,
        document_number: str | None,
        issue_date: date | None,
        expiry_date_value: date | None,
        issuer: str | None,
        notes: str | None,
        as_of: date,
    ) -> AssetDocumentView:
        self._asset(asset_id)
        if not 0 <= expiry_warning_days <= 3650:
            raise DomainError("expiry_warning_days must be between 0 and 3650")
        normalized_type = normalize_document_type(document_type)
        duplicate = self.session.scalar(
            select(AssetDocument.id).where(
                AssetDocument.company_id == self.company_id,
                AssetDocument.asset_id == asset_id,
                AssetDocument.document_type == normalized_type,
            )
        )
        if duplicate is not None:
            raise ConflictError("document type already exists for this asset")
        document = AssetDocument(
            company_id=self.company_id,
            asset_id=asset_id,
            document_type=normalized_type,
            expiry_warning_days=expiry_warning_days,
            created_by=self.actor_id,
        )
        self.session.add(document)
        self.session.flush()
        revision = self._revision(
            document=document,
            revision_number=1,
            evidence_object_id=evidence_object_id,
            document_number=document_number,
            issue_date=issue_date,
            expiry_date_value=expiry_date_value,
            issuer=issuer,
            notes=notes,
        )
        write_audit_log(
            self.session,
            company_id=self.company_id,
            actor_membership_id=self.actor_id,
            action="ASSET_DOCUMENT_CREATED",
            entity_type="ASSET_DOCUMENT",
            entity_id=document.id,
            new_values={
                "asset_id": str(asset_id),
                "document_type": normalized_type,
                "revision_number": 1,
            },
            request_id=self.request_id,
        )
        return self._view(document, revision, as_of=as_of)

    def upsert_policy(
        self,
        *,
        asset_type: FleetAssetType,
        ownership_type: AssetOwnershipType | None,
        document_type: str,
        required: bool,
        expiry_warning_days: int,
    ) -> AssetDocumentPolicy:
        if not 0 <= expiry_warning_days <= 3650:
            raise DomainError("expiry_warning_days must be between 0 and 3650")
        normalized_type = validate_policy_document_type(document_type)
        query = select(AssetDocumentPolicy).where(
            AssetDocumentPolicy.company_id == self.company_id,
            AssetDocumentPolicy.asset_type == asset_type,
            AssetDocumentPolicy.document_type == normalized_type,
        )
        if ownership_type is None:
            query = query.where(AssetDocumentPolicy.ownership_type.is_(None))
        else:
            query = query.where(AssetDocumentPolicy.ownership_type == ownership_type)
        policy = self.session.scalar(query.with_for_update())
        action = "ASSET_DOCUMENT_POLICY_UPDATED"
        if policy is None:
            policy = AssetDocumentPolicy(
                company_id=self.company_id,
                asset_type=asset_type,
                ownership_type=ownership_type,
                document_type=normalized_type,
                required=required,
                expiry_warning_days=expiry_warning_days,
                created_by=self.actor_id,
            )
            self.session.add(policy)
            action = "ASSET_DOCUMENT_POLICY_CREATED"
        else:
            policy.required = required
            policy.expiry_warning_days = expiry_warning_days
        self.session.flush()
        write_audit_log(
            self.session,
            company_id=self.company_id,
            actor_membership_id=self.actor_id,
            action=action,
            entity_type="ASSET_DOCUMENT_POLICY",
            entity_id=policy.id,
            new_values={
                "asset_type": asset_type.value,
                "ownership_type": ownership_type.value if ownership_type else None,
                "document_type": normalized_type,
                "required": required,
                "expiry_warning_days": expiry_warning_days,
            },
            request_id=self.request_id,
        )
        return policy

    def list_policies(self) -> list[AssetDocumentPolicy]:
        return list(
            self.session.scalars(
                select(AssetDocumentPolicy)
                .where(AssetDocumentPolicy.company_id == self.company_id)
                .order_by(
                    AssetDocumentPolicy.asset_type,
                    AssetDocumentPolicy.document_type,
                    AssetDocumentPolicy.ownership_type,
                )
            )
        )

    def compliance_matrix(
        self, *, as_of: date, asset_id: UUID | None = None
    ) -> list[AssetComplianceView]:
        asset_query = select(FleetAsset).where(FleetAsset.company_id == self.company_id)
        if asset_id is not None:
            self._asset(asset_id)
            asset_query = asset_query.where(FleetAsset.id == asset_id)
        assets = list(self.session.scalars(asset_query.order_by(FleetAsset.asset_code)))
        policies = self.list_policies()
        documents = list(
            self.session.scalars(
                select(AssetDocument).where(AssetDocument.company_id == self.company_id)
            )
        )
        by_asset_type = {(item.asset_id, item.document_type): item for item in documents}
        rows: list[AssetComplianceView] = []
        for asset in assets:
            applicable = [
                policy
                for policy in policies
                if policy.asset_type == asset.asset_type
                and (policy.ownership_type is None or policy.ownership_type == asset.ownership_type)
            ]
            for policy in applicable:
                document = by_asset_type.get((asset.id, policy.document_type))
                revision = self._latest_revision(document) if document else None
                if revision is None:
                    status = (
                        AssetDocumentExpiryStatus.MISSING
                        if policy.required
                        else AssetDocumentExpiryStatus.NOT_REQUIRED
                    )
                else:
                    status = expiry_status(
                        revision.expiry_date,
                        as_of=as_of,
                        warning_days=policy.expiry_warning_days,
                    )
                    if status == AssetDocumentExpiryStatus.NO_EXPIRY:
                        status = AssetDocumentExpiryStatus.VALID
                rows.append(AssetComplianceView(asset, policy, document, revision, status))
        return rows

    def replace(
        self,
        document_id: UUID,
        *,
        evidence_object_id: UUID,
        document_number: str | None,
        issue_date: date | None,
        expiry_date_value: date | None,
        issuer: str | None,
        notes: str | None,
        as_of: date,
    ) -> AssetDocumentView:
        document = self._document(document_id, lock=True)
        current_version = self.session.scalar(
            select(func.max(AssetDocumentRevision.revision_number)).where(
                AssetDocumentRevision.company_id == self.company_id,
                AssetDocumentRevision.document_id == document.id,
            )
        )
        revision_number = int(current_version or 0) + 1
        revision = self._revision(
            document=document,
            revision_number=revision_number,
            evidence_object_id=evidence_object_id,
            document_number=document_number,
            issue_date=issue_date,
            expiry_date_value=expiry_date_value,
            issuer=issuer,
            notes=notes,
        )
        write_audit_log(
            self.session,
            company_id=self.company_id,
            actor_membership_id=self.actor_id,
            action="ASSET_DOCUMENT_REPLACED",
            entity_type="ASSET_DOCUMENT",
            entity_id=document.id,
            old_values={"revision_number": revision_number - 1},
            new_values={"revision_number": revision_number},
            request_id=self.request_id,
        )
        return self._view(document, revision, as_of=as_of)

    def _latest_revision(self, document: AssetDocument) -> AssetDocumentRevision:
        revision = self.session.scalar(
            select(AssetDocumentRevision)
            .where(
                AssetDocumentRevision.company_id == self.company_id,
                AssetDocumentRevision.document_id == document.id,
            )
            .order_by(AssetDocumentRevision.revision_number.desc())
            .limit(1)
        )
        if revision is None:
            raise NotFoundError("asset document has no revision")
        return revision

    @staticmethod
    def _view(
        document: AssetDocument,
        revision: AssetDocumentRevision,
        *,
        as_of: date,
    ) -> AssetDocumentView:
        return AssetDocumentView(
            document=document,
            revision=revision,
            expiry_status=expiry_status(
                revision.expiry_date,
                as_of=as_of,
                warning_days=document.expiry_warning_days,
            ),
        )

    def list_documents(self, *, asset_id: UUID | None, as_of: date) -> list[AssetDocumentView]:
        query = select(AssetDocument).where(AssetDocument.company_id == self.company_id)
        if asset_id is not None:
            self._asset(asset_id)
            query = query.where(AssetDocument.asset_id == asset_id)
        documents = self.session.scalars(query.order_by(AssetDocument.created_at, AssetDocument.id))
        return [
            self._view(document, self._latest_revision(document), as_of=as_of)
            for document in documents
        ]

    def revisions(self, document_id: UUID) -> list[AssetDocumentRevision]:
        self._document(document_id)
        return list(
            self.session.scalars(
                select(AssetDocumentRevision)
                .where(
                    AssetDocumentRevision.company_id == self.company_id,
                    AssetDocumentRevision.document_id == document_id,
                )
                .order_by(AssetDocumentRevision.revision_number)
            )
        )

    def latest_private_evidence(self, document_id: UUID) -> EvidenceObject:
        document = self._document(document_id)
        revision = self._latest_revision(document)
        evidence = self.session.scalar(
            select(EvidenceObject).where(
                EvidenceObject.company_id == self.company_id,
                EvidenceObject.id == revision.evidence_object_id,
            )
        )
        if evidence is None:
            raise NotFoundError("private evidence not found")
        return evidence
