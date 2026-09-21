from __future__ import annotations

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


class UnavailableObjectStorage:
    def put_private(self, *, object_key: str, content: bytes, content_type: str) -> str:
        del object_key, content, content_type
        raise ObjectStorageUnavailableError("object storage is not configured")

    def delete_private(self, *, object_key: str) -> None:
        del object_key

    def read_private(self, *, object_key: str) -> tuple[bytes, str]:
        del object_key
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


def build_object_storage(settings: Settings) -> ObjectStorage:
    provider = settings.object_storage_provider.lower()
    if provider == "s3":
        return S3ObjectStorage(settings)
    if provider == "unavailable":
        return UnavailableObjectStorage()
    raise ObjectStorageUnavailableError("configured object storage provider is unavailable")
