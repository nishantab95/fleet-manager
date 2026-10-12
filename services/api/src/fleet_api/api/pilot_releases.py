from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from fleet_api.core.config import Settings

router = APIRouter(prefix="/api/v1/admin/pilot-releases", tags=["pilot-releases"])

EXPECTED_PACKAGE = "com.fleetmanager.fleet_manager_mobile.pilot"
EXPECTED_SIGNER_SHA256 = "fd25115e20ac18a8a7cda91b9f4d5f6153f54b4d79c751b5005a3ac734cc3c29"
MAX_METADATA_BYTES = 32 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
UPLOAD_OVERHEAD_ALLOWANCE = 1024 * 1024
HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SAFE_RESPONSE_DETAIL = "Pilot release was rejected by server validation."


@dataclass(frozen=True)
class PilotReleaseBackend:
    inbox_root: Path
    status_file: Path
    publish_upload: Callable[[Path, Mapping[str, object]], str]


class UploadRejected(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _default_token_file() -> Path:
    program_data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    return program_data / "FleetAISystems" / "pilot-publisher.token"


def _read_publisher_token(settings: Settings) -> str:
    path = settings.pilot_publisher_token_file or _default_token_file()
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pilot publisher credential is not configured.",
        ) from error
    if len(raw) > 4096:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pilot publisher credential is invalid.",
        )
    try:
        token = raw.decode("utf-8").rstrip("\r\n")
    except UnicodeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pilot publisher credential is invalid.",
        ) from error
    if len(token) < 32 or len(token) > 2048 or any(character.isspace() for character in token):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pilot publisher credential is invalid.",
        )
    return token


def _authenticate_publisher(authorization: str | None, settings: Settings) -> None:
    expected = _read_publisher_token(settings)
    supplied = ""
    if authorization and authorization.startswith("Bearer "):
        supplied = authorization.removeprefix("Bearer ")
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Publisher authentication failed.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def guard_pilot_release_upload(request: Request, settings: Settings) -> JSONResponse | None:
    """Reject unauthenticated or oversized uploads before multipart parsing."""

    if request.method != "POST" or request.url.path != router.prefix:
        return None
    try:
        _authenticate_publisher(request.headers.get("authorization"), settings)
    except HTTPException as error:
        return JSONResponse(
            status_code=error.status_code,
            content={"detail": error.detail},
            headers=error.headers,
        )
    content_length = request.headers.get("content-length")
    if content_length is None:
        return None
    try:
        request_bytes = int(content_length)
    except ValueError:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Content-Length is invalid."},
        )
    if request_bytes > settings.pilot_release_upload_max_bytes + UPLOAD_OVERHEAD_ALLOWANCE:
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={"detail": "APK exceeds the configured upload limit."},
        )
    return None


def _parse_metadata(raw: str) -> dict[str, object]:
    if len(raw.encode("utf-8")) > MAX_METADATA_BYTES:
        raise UploadRejected(status.HTTP_422_UNPROCESSABLE_ENTITY, "Release metadata is too large.")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise UploadRejected(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Release metadata must be valid JSON.",
        ) from error
    if not isinstance(value, dict):
        raise UploadRejected(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Release metadata must be a JSON object.",
        )
    required = {
        "schemaVersion",
        "package",
        "versionName",
        "versionCode",
        "apkSha256",
        "expectedSignerSha256",
        "sourceGitCommit",
    }
    missing = required - set(value)
    if missing:
        raise UploadRejected(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Release metadata is missing required fields.",
        )
    package = value.get("package")
    version_name = value.get("versionName")
    version_code = value.get("versionCode")
    apk_sha256 = value.get("apkSha256")
    signer = value.get("expectedSignerSha256")
    commit = value.get("sourceGitCommit")
    if value.get("schemaVersion") != 1:
        raise UploadRejected(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported schemaVersion.")
    if package != EXPECTED_PACKAGE:
        raise UploadRejected(status.HTTP_422_UNPROCESSABLE_ENTITY, "Release package is invalid.")
    if not isinstance(version_name, str) or not version_name.strip() or len(version_name) > 100:
        raise UploadRejected(status.HTTP_422_UNPROCESSABLE_ENTITY, "versionName is invalid.")
    if isinstance(version_code, bool) or not isinstance(version_code, int) or version_code < 1:
        raise UploadRejected(status.HTTP_422_UNPROCESSABLE_ENTITY, "versionCode is invalid.")
    if not isinstance(apk_sha256, str) or not HEX_SHA256_RE.fullmatch(apk_sha256.casefold()):
        raise UploadRejected(status.HTTP_422_UNPROCESSABLE_ENTITY, "APK SHA-256 is invalid.")
    if not isinstance(signer, str) or signer.casefold() != EXPECTED_SIGNER_SHA256:
        raise UploadRejected(status.HTTP_422_UNPROCESSABLE_ENTITY, "Release signer is invalid.")
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit.casefold()):
        raise UploadRejected(status.HTTP_422_UNPROCESSABLE_ENTITY, "Source commit is invalid.")
    auth_mode = value.get("authMode")
    build_profile = value.get("buildProfile")
    if (auth_mode is None) != (build_profile is None):
        raise UploadRejected(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Authentication mode and build profile must be supplied together.",
        )
    if auth_mode is not None and (auth_mode, build_profile) not in {
        ("company_pin", "company-pin"),
        ("firebase", "firebase-company"),
    }:
        raise UploadRejected(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Release authentication profile is invalid.",
        )
    return value


def _production_backend() -> PilotReleaseBackend:
    repository_root = Path(__file__).resolve().parents[5]
    scripts_dir = repository_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    inbox: Any = importlib.import_module("pilot_release_inbox")

    return PilotReleaseBackend(
        inbox_root=inbox.INBOX_ROOT,
        status_file=inbox.STATUS_FILE,
        publish_upload=inbox.publish_uploaded_pair,
    )


def _backend(request: Request) -> PilotReleaseBackend:
    configured = getattr(request.app.state, "pilot_release_backend", None)
    return configured if isinstance(configured, PilotReleaseBackend) else _production_backend()


async def _stream_apk(
    upload: UploadFile,
    destination: Path,
    *,
    max_bytes: int,
) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with destination.open("xb") as handle:
            while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
                size += len(chunk)
                if size > max_bytes:
                    raise UploadRejected(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        "APK exceeds the configured upload limit.",
                    )
                handle.write(chunk)
                digest.update(chunk)
            handle.flush()
            os.fsync(handle.fileno())
    except UploadRejected:
        destination.unlink(missing_ok=True)
        raise
    except Exception as error:
        destination.unlink(missing_ok=True)
        raise UploadRejected(
            status.HTTP_400_BAD_REQUEST,
            "APK upload was interrupted.",
        ) from error
    finally:
        await upload.close()
    if size == 0:
        destination.unlink(missing_ok=True)
        raise UploadRejected(status.HTTP_422_UNPROCESSABLE_ENTITY, "APK upload is empty.")
    return digest.hexdigest(), size


def _publisher_detail(backend: PilotReleaseBackend) -> str:
    try:
        value = json.loads(backend.status_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return SAFE_RESPONSE_DETAIL
    detail = value.get("detail") if isinstance(value, dict) else None
    return " ".join(str(detail).split())[:500] if detail else SAFE_RESPONSE_DETAIL


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_pilot_release(
    request: Request,
    metadata: Annotated[str, Form(...)],
    apk: Annotated[UploadFile, File(...)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    _authenticate_publisher(authorization, settings)
    try:
        manifest = _parse_metadata(metadata)
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                request_bytes = int(content_length)
            except ValueError as error:
                raise UploadRejected(
                    status.HTTP_400_BAD_REQUEST,
                    "Content-Length is invalid.",
                ) from error
            if request_bytes > settings.pilot_release_upload_max_bytes + UPLOAD_OVERHEAD_ALLOWANCE:
                raise UploadRejected(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    "APK exceeds the configured upload limit.",
                )

        backend = _backend(request)
        staging_dir = backend.inbox_root / "staging" / "https-uploads"
        staging_dir.mkdir(parents=True, exist_ok=True)
        upload_id = uuid4().hex
        base = f"FleetManager-Pilot-upload-https-{upload_id}"
        partial = staging_dir / f".{base}.partial"
        digest, _ = await _stream_apk(
            apk,
            partial,
            max_bytes=settings.pilot_release_upload_max_bytes,
        )
        expected_digest = str(manifest["apkSha256"]).casefold()
        if not hmac.compare_digest(digest, expected_digest):
            partial.unlink(missing_ok=True)
            raise UploadRejected(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "APK SHA-256 does not match release metadata.",
            )

        backend.inbox_root.mkdir(parents=True, exist_ok=True)
        apk_name = f"{base}.apk"
        server_manifest: dict[str, object] = {
            "schemaVersion": 1,
            "releaseId": f"https-{upload_id}",
            "apkFile": apk_name,
            "package": manifest["package"],
            "versionName": manifest["versionName"],
            "versionCode": manifest["versionCode"],
            "apkSha256": expected_digest,
            "expectedSignerSha256": EXPECTED_SIGNER_SHA256,
            "sourceGitCommit": str(manifest["sourceGitCommit"]).casefold(),
        }
        for key in ("authMode", "buildProfile"):
            if key in manifest:
                server_manifest[key] = manifest[key]
        try:
            try:
                outcome = await run_in_threadpool(
                    backend.publish_upload,
                    partial,
                    server_manifest,
                )
            except Exception as error:
                raise UploadRejected(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "Pilot publisher is unavailable; retry the upload.",
                ) from error
        finally:
            partial.unlink(missing_ok=True)
        if outcome != "PUBLISHED":
            raise UploadRejected(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                _publisher_detail(backend),
            )
        return {
            "status": "PUBLISHED",
            "version_name": manifest["versionName"],
            "version_code": manifest["versionCode"],
            "sha256": expected_digest,
            "source_commit": str(manifest["sourceGitCommit"]).casefold(),
        }
    except UploadRejected as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
