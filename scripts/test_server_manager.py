from __future__ import annotations

import json
from pathlib import Path

import pytest

import server_manager


def test_evidence_snapshot_has_verified_hash_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "active-evidence"
    object_file = source / "objects" / "companies" / "one" / "photo.jpg"
    metadata_file = source / ".fleet-metadata" / "companies" / "one" / "photo.jpg.json"
    object_file.parent.mkdir(parents=True)
    metadata_file.parent.mkdir(parents=True)
    object_file.write_bytes(b"\xff\xd8\xffevidence")
    metadata_file.write_text('{"content_type":"image/jpeg"}', encoding="utf-8")
    backup_root = tmp_path / "backup"
    monkeypatch.setattr(server_manager, "EVIDENCE_BACKUP_ROOT", backup_root)

    snapshot, manifest_path, manifest = server_manager.create_evidence_snapshot(
        source, "20261001-120000+0530"
    )

    assert snapshot == backup_root / "20261001-120000+0530"
    assert manifest_path == snapshot / server_manager.EVIDENCE_MANIFEST_NAME
    assert manifest["file_count"] == 2
    assert manifest["secrets_included"] is False
    assert server_manager.verify_evidence_snapshot(snapshot) == manifest


def test_evidence_snapshot_verification_detects_tampering(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "active-evidence"
    source.mkdir()
    (source / "object.bin").write_bytes(b"original")
    monkeypatch.setattr(server_manager, "EVIDENCE_BACKUP_ROOT", tmp_path / "backup")
    snapshot, _, _ = server_manager.create_evidence_snapshot(
        source, "20261001-120001+0530"
    )
    (snapshot / "object.bin").write_bytes(b"tampered")

    with pytest.raises(server_manager.ServerError, match="hash verification"):
        server_manager.verify_evidence_snapshot(snapshot)


@pytest.mark.parametrize(
    "relative",
    ["../outside", r"..\outside", "/absolute", r"C:\outside", "safe/../outside"],
)
def test_evidence_manifest_rejects_unsafe_paths(tmp_path: Path, relative: str) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    manifest = {
        "format_version": 1,
        "files": [{"path": relative, "size": 0, "sha256": "0" * 64}],
    }
    (snapshot / server_manager.EVIDENCE_MANIFEST_NAME).write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    with pytest.raises(server_manager.ServerError, match="unsafe path"):
        server_manager.verify_evidence_snapshot(snapshot)


def test_server_start_requests_only_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []

    def record(args: list[str], **_: object) -> None:
        commands.append(args)

    monkeypatch.setattr(server_manager, "checked", record)
    monkeypatch.setattr(server_manager, "compose_health", lambda *_: {"postgres": "healthy"})

    server_manager.ensure_infrastructure("docker", {})

    assert commands == [["docker", "compose", "up", "-d", "postgres"]]


def test_stop_targets_only_owned_api_and_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(server_manager, "require_runtime", lambda: ("docker", {}))
    monkeypatch.setattr(server_manager, "stop_api", lambda: calls.append("api") or 0)
    monkeypatch.setattr(server_manager, "docker_ready", lambda _: True)
    monkeypatch.setattr(
        server_manager,
        "checked",
        lambda args, **_: calls.append(args),
    )

    assert server_manager.stop_server() == 0
    assert calls == ["api", ["docker", "compose", "stop", "postgres"]]
