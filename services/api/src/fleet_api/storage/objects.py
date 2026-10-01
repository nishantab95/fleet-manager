from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Protocol

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from fleet_api.core.config import Settings
from fleet_api.domain.errors import ObjectStorageUnavailableError


class ObjectStorage(Protocol):
    def put_private(self, *, object_key: str, content: bytes, content_type: str) -> str:
        """Store one private object and return its server-generated key."""

    def delete_private(self, *, object_key: str) -> None:
        """Delete one private object during metadata rollback."""

    def read_private(self, *, object_key: str) -> tuple[bytes, str]:
        """Read one private object after an authorization decision."""

    def check_ready(self) -> None:
        """Raise when private object storage cannot safely serve requests."""


class UnavailableObjectStorage:
    def put_private(self, *, object_key: str, content: bytes, content_type: str) -> str:
        del object_key, content, content_type
        raise ObjectStorageUnavailableError("object storage is not configured")

    def delete_private(self, *, object_key: str) -> None:
        del object_key

    def read_private(self, *, object_key: str) -> tuple[bytes, str]:
        del object_key
        raise ObjectStorageUnavailableError("object storage is not configured")

    def check_ready(self) -> None:
        raise ObjectStorageUnavailableError("object storage is not configured")


class S3ObjectStorage:
    def __init__(self, settings: Settings) -> None:
        if not settings.s3_access_key_id or not settings.s3_secret_access_key:
            raise ObjectStorageUnavailableError("object storage credentials are not configured")
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
        )

    def _ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            try:
                self.client.create_bucket(Bucket=self.bucket)
            except (BotoCoreError, ClientError) as exc:
                raise ObjectStorageUnavailableError("object storage bucket is unavailable") from exc

    def put_private(self, *, object_key: str, content: bytes, content_type: str) -> str:
        try:
            self._ensure_bucket()
            self.client.put_object(
                Bucket=self.bucket,
                Key=object_key,
                Body=content,
                ContentType=content_type,
            )
        except (BotoCoreError, ClientError) as exc:
            raise ObjectStorageUnavailableError("object upload failed") from exc
        return object_key

    def delete_private(self, *, object_key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=object_key)
        except (BotoCoreError, ClientError) as exc:
            raise ObjectStorageUnavailableError("object deletion failed") from exc

    def read_private(self, *, object_key: str) -> tuple[bytes, str]:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=object_key)
            content = response["Body"].read()
            content_type = str(response.get("ContentType") or "application/octet-stream")
            return content, content_type
        except (BotoCoreError, ClientError) as exc:
            raise ObjectStorageUnavailableError("object read failed") from exc

    def check_ready(self) -> None:
        self._ensure_bucket()


class FilesystemObjectStorage:
    """Private filesystem implementation for server-generated logical object keys."""

    _METADATA_DIRECTORY = ".fleet-metadata"

    def __init__(self, settings: Settings) -> None:
        configured_root = settings.filesystem_storage_root
        if configured_root is None:
            raise ObjectStorageUnavailableError("filesystem storage root is not configured")
        self.root = configured_root.expanduser().resolve(strict=False)
        self.objects_root = self.root / "objects"
        self.metadata_root = self.root / self._METADATA_DIRECTORY
        self._initialize_root()

    def _initialize_root(self) -> None:
        try:
            self.objects_root.mkdir(parents=True, exist_ok=True)
            self.metadata_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ObjectStorageUnavailableError(
                "filesystem storage root could not be initialized"
            ) from exc
        if not self.objects_root.is_dir() or not self.metadata_root.is_dir():
            raise ObjectStorageUnavailableError("filesystem storage root is unavailable")

    @staticmethod
    def _relative_key(object_key: str) -> Path:
        if not object_key or "\x00" in object_key or "\\" in object_key:
            raise ObjectStorageUnavailableError("object key is invalid")
        raw_parts = object_key.split("/")
        if any(part in {"", ".", ".."} or ":" in part for part in raw_parts):
            raise ObjectStorageUnavailableError("object key is invalid")
        posix_key = PurePosixPath(object_key)
        windows_key = PureWindowsPath(object_key)
        if posix_key.is_absolute() or windows_key.is_absolute() or windows_key.drive:
            raise ObjectStorageUnavailableError("object key is invalid")
        return Path(*raw_parts)

    @staticmethod
    def _require_contained(base: Path, candidate: Path) -> Path:
        resolved_base = base.resolve(strict=False)
        resolved_candidate = candidate.resolve(strict=False)
        try:
            resolved_candidate.relative_to(resolved_base)
        except ValueError as exc:
            raise ObjectStorageUnavailableError("object key escapes storage root") from exc
        return resolved_candidate

    def _paths(self, object_key: str, *, create_parents: bool) -> tuple[Path, Path]:
        relative = self._relative_key(object_key)
        object_path = self._require_contained(self.objects_root, self.objects_root / relative)
        metadata_path = self._require_contained(
            self.metadata_root,
            self.metadata_root / relative.parent / f"{relative.name}.json",
        )
        if create_parents:
            try:
                object_path.parent.mkdir(parents=True, exist_ok=True)
                metadata_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise ObjectStorageUnavailableError(
                    "filesystem object directory could not be initialized"
                ) from exc
            object_path = self._require_contained(self.objects_root, object_path)
            metadata_path = self._require_contained(self.metadata_root, metadata_path)
        return object_path, metadata_path

    @staticmethod
    def _write_temporary(parent: Path, *, content: bytes) -> Path:
        descriptor, raw_path = tempfile.mkstemp(prefix=".fleet-write-", dir=parent)
        temporary = Path(raw_path)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return temporary

    @staticmethod
    def _exists(path: Path) -> bool:
        return os.path.lexists(path)

    def put_private(self, *, object_key: str, content: bytes, content_type: str) -> str:
        object_path, metadata_path = self._paths(object_key, create_parents=True)
        lock_path = metadata_path.with_name(f"{metadata_path.name}.lock")
        lock_descriptor: int | None = None
        object_temporary: Path | None = None
        metadata_temporary: Path | None = None
        metadata_published = False
        try:
            lock_descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            if self._exists(object_path) or self._exists(metadata_path):
                raise ObjectStorageUnavailableError("object already exists")
            object_temporary = self._write_temporary(object_path.parent, content=content)
            metadata = json.dumps(
                {
                    "format_version": 1,
                    "object_key": object_key,
                    "content_type": content_type,
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            metadata_temporary = self._write_temporary(metadata_path.parent, content=metadata)
            os.replace(metadata_temporary, metadata_path)
            metadata_temporary = None
            metadata_published = True
            os.replace(object_temporary, object_path)
            object_temporary = None
            return object_key
        except FileExistsError as exc:
            raise ObjectStorageUnavailableError("object write is already in progress") from exc
        except ObjectStorageUnavailableError:
            raise
        except OSError as exc:
            raise ObjectStorageUnavailableError("object upload failed") from exc
        finally:
            if object_temporary is not None:
                object_temporary.unlink(missing_ok=True)
            if metadata_temporary is not None:
                metadata_temporary.unlink(missing_ok=True)
            if metadata_published and not self._exists(object_path):
                metadata_path.unlink(missing_ok=True)
            if lock_descriptor is not None:
                os.close(lock_descriptor)
                lock_path.unlink(missing_ok=True)

    def delete_private(self, *, object_key: str) -> None:
        object_path, metadata_path = self._paths(object_key, create_parents=False)
        try:
            object_path.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
        except OSError as exc:
            raise ObjectStorageUnavailableError("object deletion failed") from exc

    def read_private(self, *, object_key: str) -> tuple[bytes, str]:
        object_path, metadata_path = self._paths(object_key, create_parents=False)
        try:
            if object_path.is_symlink() or metadata_path.is_symlink():
                raise ObjectStorageUnavailableError("object storage path is unsafe")
            object_path = self._require_contained(
                self.objects_root, object_path.resolve(strict=True)
            )
            metadata_path = self._require_contained(
                self.metadata_root, metadata_path.resolve(strict=True)
            )
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            content = object_path.read_bytes()
            if (
                not isinstance(metadata, dict)
                or metadata.get("format_version") != 1
                or metadata.get("object_key") != object_key
                or metadata.get("size") != len(content)
                or metadata.get("sha256") != hashlib.sha256(content).hexdigest()
                or not isinstance(metadata.get("content_type"), str)
            ):
                raise ObjectStorageUnavailableError("object integrity verification failed")
            return content, metadata["content_type"]
        except ObjectStorageUnavailableError:
            raise
        except (OSError, json.JSONDecodeError) as exc:
            raise ObjectStorageUnavailableError("object read failed") from exc

    def check_ready(self) -> None:
        self._initialize_root()
        probe: Path | None = None
        expected = b"fleet-storage-ready"
        try:
            probe = self._write_temporary(self.root, content=expected)
            if probe.read_bytes() != expected:
                raise ObjectStorageUnavailableError("filesystem readiness probe failed")
        except ObjectStorageUnavailableError:
            raise
        except OSError as exc:
            raise ObjectStorageUnavailableError("filesystem storage is not writable") from exc
        finally:
            if probe is not None:
                probe.unlink(missing_ok=True)


def build_object_storage(settings: Settings) -> ObjectStorage:
    provider = settings.object_storage_provider.lower()
    if provider == "s3":
        return S3ObjectStorage(settings)
    if provider == "filesystem":
        return FilesystemObjectStorage(settings)
    if provider == "unavailable":
        return UnavailableObjectStorage()
    raise ObjectStorageUnavailableError("configured object storage provider is unavailable")
