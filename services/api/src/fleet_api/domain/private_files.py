from __future__ import annotations

from pathlib import PurePosixPath
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fleet_api.auth.service import AuthContext
from fleet_api.db.models import EvidenceObject
from fleet_api.domain.errors import EvidenceValidationError, ObjectStorageUnavailableError
from fleet_api.storage.objects import ObjectStorage

_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
}


def _matches_signature(content_type: str, content: bytes) -> bool:
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    if content_type == "application/pdf":
        return content.startswith(b"%PDF-")
    return False


def store_private_evidence(
    session: Session,
    context: AuthContext,
    storage: ObjectStorage,
    *,
    reference_uuid: UUID,
    purpose: str,
    content_type: str,
    content: bytes,
    allowed_mime_types: set[str],
    max_bytes: int,
) -> EvidenceObject:
    """Validate and persist a private object using a server-generated key."""

    normalized_type = content_type.lower().split(";", maxsplit=1)[0].strip()
    if normalized_type not in allowed_mime_types or normalized_type not in _EXTENSIONS:
        raise EvidenceValidationError("unsupported evidence type")
    if not content or len(content) > max_bytes:
        raise EvidenceValidationError("evidence size is invalid")
    if not _matches_signature(normalized_type, content):
        raise EvidenceValidationError("evidence content does not match its declared type")

    existing = session.scalar(
        select(EvidenceObject).where(
            EvidenceObject.company_id == context.company.id,
            EvidenceObject.membership_id == context.membership.id,
            EvidenceObject.client_event_uuid == reference_uuid,
        )
    )
    if existing is not None:
        return existing

    object_key = str(
        PurePosixPath(
            "companies",
            str(context.company.id),
            "memberships",
            str(context.membership.id),
            purpose,
            str(reference_uuid),
            f"{uuid4()}.{_EXTENSIONS[normalized_type]}",
        )
    )
    stored_key: str | None = None
    try:
        stored_key = storage.put_private(
            object_key=object_key,
            content=content,
            content_type=normalized_type,
        )
        evidence = EvidenceObject(
            company_id=context.company.id,
            membership_id=context.membership.id,
            client_event_uuid=reference_uuid,
            object_key=stored_key,
            content_type=normalized_type,
            size_bytes=len(content),
        )
        session.add(evidence)
        session.flush()
        return evidence
    except (IntegrityError, ObjectStorageUnavailableError):
        if stored_key is not None:
            try:
                storage.delete_private(object_key=stored_key)
            except ObjectStorageUnavailableError:
                pass
        raise
