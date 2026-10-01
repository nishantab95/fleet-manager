from __future__ import annotations

import json
from pathlib import Path

import pytest

from fleet_api.core.config import Settings
from fleet_api.domain.errors import ObjectStorageUnavailableError
from fleet_api.storage.objects import FilesystemObjectStorage, build_object_storage


def filesystem_settings(root: Path) -> Settings:
    return Settings(
        environment="test",
        object_storage_provider="filesystem",
        filesystem_storage_root=root,
    )


def test_filesystem_storage_round_trip_nested_key_and_delete(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(filesystem_settings(tmp_path / "evidence"))
    key = "companies/company-id/memberships/member-id/events/event-id/photo.jpg"
    content = b"\xff\xd8\xffprivate-evidence"

    assert storage.put_private(
        object_key=key, content=content, content_type="image/jpeg"
    ) == key
    assert storage.read_private(object_key=key) == (content, "image/jpeg")

    object_path = storage.objects_root.joinpath(*key.split("/"))
    metadata_path = storage.metadata_root.joinpath(
        *key.split("/")[:-1], f"{key.split('/')[-1]}.json"
    )
    assert object_path.read_bytes() == content
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["object_key"] == key
    assert metadata["content_type"] == "image/jpeg"
    assert not list(storage.root.rglob(".fleet-write-*"))
    assert not list(storage.root.rglob("*.lock"))

    storage.delete_private(object_key=key)
    assert not object_path.exists()
    assert not metadata_path.exists()


@pytest.mark.parametrize(
    "key",
    [
        "../outside.jpg",
        "safe/../outside.jpg",
        r"..\outside.jpg",
        "/absolute.jpg",
        r"C:\outside.jpg",
        r"\\server\share\outside.jpg",
        "safe//outside.jpg",
        "safe/./outside.jpg",
        "safe/stream:alternate.jpg",
    ],
)
def test_filesystem_storage_rejects_unsafe_keys(tmp_path: Path, key: str) -> None:
    root = tmp_path / "evidence"
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"sentinel")
    storage = FilesystemObjectStorage(filesystem_settings(root))

    with pytest.raises(ObjectStorageUnavailableError, match="object key"):
        storage.put_private(object_key=key, content=b"unsafe", content_type="image/jpeg")
    with pytest.raises(ObjectStorageUnavailableError, match="object key"):
        storage.read_private(object_key=key)
    with pytest.raises(ObjectStorageUnavailableError, match="object key"):
        storage.delete_private(object_key=key)

    assert outside.read_bytes() == b"sentinel"
    assert not list(root.rglob("outside.jpg"))


def test_filesystem_storage_never_overwrites_existing_object(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(filesystem_settings(tmp_path / "evidence"))
    key = "companies/company/events/event/photo.png"
    original = b"\x89PNG\r\n\x1a\noriginal"

    storage.put_private(object_key=key, content=original, content_type="image/png")
    with pytest.raises(ObjectStorageUnavailableError, match="already exists"):
        storage.put_private(
            object_key=key,
            content=b"\x89PNG\r\n\x1a\nreplacement",
            content_type="image/png",
        )

    assert storage.read_private(object_key=key) == (original, "image/png")


def test_filesystem_storage_detects_tampering(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(filesystem_settings(tmp_path / "evidence"))
    key = "companies/company/events/event/photo.webp"
    storage.put_private(
        object_key=key,
        content=b"RIFF\x04\x00\x00\x00WEBP",
        content_type="image/webp",
    )
    storage.objects_root.joinpath(*key.split("/")).write_bytes(b"tampered")

    with pytest.raises(ObjectStorageUnavailableError, match="integrity"):
        storage.read_private(object_key=key)


def test_filesystem_storage_readiness_probe_is_removed(tmp_path: Path) -> None:
    root = tmp_path / "nested" / "evidence"
    storage = FilesystemObjectStorage(filesystem_settings(root))

    storage.check_ready()

    assert root.is_dir()
    assert not list(root.glob(".fleet-write-*"))


def test_storage_factory_preserves_s3_and_adds_filesystem(tmp_path: Path) -> None:
    filesystem = build_object_storage(filesystem_settings(tmp_path / "evidence"))

    assert isinstance(filesystem, FilesystemObjectStorage)


def test_filesystem_provider_requires_a_root() -> None:
    with pytest.raises(ValueError, match="FLEET_FILESYSTEM_STORAGE_ROOT"):
        Settings(environment="test", object_storage_provider="filesystem")
