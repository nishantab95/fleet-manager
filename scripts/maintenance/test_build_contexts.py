"""Synthetic manifest safety tests and static production-target contracts.

Dockerignore semantics are deliberately not approximated here. Real native
Docker exports, separately run and recorded, establish the filtered payload.
"""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.maintenance import build_context_manifest as audit


@pytest.fixture
def exported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    repo = tmp_path / "checkout"
    export = repo / ".tmp" / "native-export"
    source = repo / "apps" / "web"
    copied = export / "apps" / "web"
    source.mkdir(parents=True)
    copied.mkdir(parents=True)
    (source / "Dockerfile").write_bytes(b"FROM scratch\n")
    (source / "Dockerfile.dockerignore").write_bytes(b"**\n!apps/web/package.json\n")
    (repo / ".dockerignore").write_bytes(b"fallback-is-not-effective\n")
    for root in (source, copied):
        (root / "package.json").write_bytes(b'{"fixture":true}\n')
    monkeypatch.setattr(audit, "tracked_paths", lambda _: {"apps/web/package.json"})
    return repo, export


def test_exact_logical_bytes_hashes_controls_and_repeatability(
    exported: tuple[Path, Path],
) -> None:
    repo, export = exported
    result = audit.manifest(export, "web", repo)
    assert result == audit.manifest(export, "web", repo)
    payload = b'{"fixture":true}\n'
    assert result["copy_payload"] == {"files": 1, "bytes": len(payload)}
    assert result["files"] == [
        {
            "path": "apps/web/package.json",
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "git_tracked": True,
        }
    ]
    assert result["checkout_hashes_match"] is True
    assert result["git_tracked_files"] == 1
    assert result["untracked_paths"] == []
    assert [item["path"] for item in result["controls"]] == [
        "apps/web/Dockerfile",
        "apps/web/Dockerfile.dockerignore",
    ]
    assert result["control_bytes_not_in_copy_payload"] == sum(
        item["bytes"] for item in result["controls"]
    )


def test_control_files_are_not_counted_twice(exported: tuple[Path, Path]) -> None:
    repo, export = exported
    relative = Path("apps/web/Dockerfile")
    (export / relative).write_bytes((repo / relative).read_bytes())
    result = audit.manifest(export, "web", repo)
    assert result["controls"][0]["included_in_copy_payload"] is True
    assert result["control_bytes_not_in_copy_payload"] == result["controls"][1]["bytes"]


def test_root_ignore_is_used_only_without_specific_policy(
    exported: tuple[Path, Path],
) -> None:
    repo, export = exported
    (repo / "apps/web/Dockerfile.dockerignore").unlink()
    assert audit.manifest(export, "web", repo)["controls"][1]["path"] == ".dockerignore"


def test_untracked_input_is_explicit_not_claimed_clean(
    exported: tuple[Path, Path],
) -> None:
    repo, export = exported
    for root in (repo, export):
        (root / "apps/web/next-env.d.ts").write_bytes(
            b"// synthetic generated declaration\n"
        )
    result = audit.manifest(export, "web", repo)
    assert result["untracked_paths"] == ["apps/web/next-env.d.ts"]
    assert result["git_tracked_files"] == 1
    assert result["copy_payload"]["files"] == 2


def test_evidence_route_source_is_not_stored_evidence_data(
    exported: tuple[Path, Path],
) -> None:
    repo, export = exported
    for root in (repo, export):
        route = root / "apps/web/app/evidence/[event_id]/page.tsx"
        route.parent.mkdir(parents=True)
        route.write_bytes(b"// synthetic source route\n")
    result = audit.manifest(export, "web", repo)
    assert result["copy_payload"]["files"] == 2
    assert audit.protected_name(
        Path("apps/web/app/evidence/[event_id]/evidence/photo.jpg")
    )


@pytest.mark.parametrize(
    "relative",
    [
        "apps/web/.env",
        "apps/web/.env.production",
        "apps/web/nested/node_modules/file.js",
        "apps/web/.next/cache/value",
        "apps/web/data/evidence/photo.jpg",
        "apps/web/pilot.apk",
        "apps/web/upload.aab",
        "apps/web/secret.jks",
        "apps/web/key.properties",
        "apps/web/local.properties",
        "apps/web/google-services.json",
        "apps/web/x-credentials.json",
        "apps/web/x-service-account.json",
        "apps/web/x-firebase-adminsdk-secret.json",
        "apps/web/history.sqlite3",
        "apps/web/backup.tar.gz",
        "apps/web/.RUNTIME/file",
    ],
)
def test_protected_names_rejected_before_any_content_read(
    exported: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, relative: str
) -> None:
    repo, export = exported
    target = export / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"synthetic fixture; never read")
    monkeypatch.setattr(
        audit,
        "file_metadata",
        lambda _: pytest.fail("Protected export must not be hashed"),
    )
    with pytest.raises(ValueError, match="Protected/generated"):
        audit.manifest(export, "web", repo)


def test_wrong_component_is_rejected(exported: tuple[Path, Path]) -> None:
    repo, export = exported
    (export / "unrelated.py").write_bytes(b"fixture")
    with pytest.raises(ValueError, match="Unexpected component"):
        audit.manifest(export, "web", repo)


@pytest.mark.parametrize("location", ["outside", ".tmp"])
def test_broad_or_outside_export_root_is_rejected(
    exported: tuple[Path, Path], location: str
) -> None:
    repo, _ = exported
    with pytest.raises(ValueError, match="dedicated directory"):
        audit.manifest(repo / location, "web", repo)


def test_empty_export_cannot_claim_success(exported: tuple[Path, Path]) -> None:
    repo, _ = exported
    empty = repo / ".tmp" / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="Empty export"):
        audit.manifest(empty, "web", repo)


def test_changed_checkout_does_not_validate_stale_export(
    exported: tuple[Path, Path],
) -> None:
    repo, export = exported
    (repo / "apps/web/package.json").write_bytes(b"new checkout state")
    with pytest.raises(ValueError, match="differs from current checkout"):
        audit.manifest(export, "web", repo)


def test_missing_checkout_counterpart_fails(exported: tuple[Path, Path]) -> None:
    repo, export = exported
    (export / "apps/web/unexpected.txt").write_bytes(b"fixture")
    with pytest.raises(FileNotFoundError):
        audit.manifest(export, "web", repo)


@pytest.mark.parametrize(
    "mode,attributes", [(stat.S_IFLNK, 0), (stat.S_IFDIR, 0x400), (stat.S_IFREG, 0x400)]
)
def test_symlink_and_windows_reparse_detection(mode: int, attributes: int) -> None:
    info = cast(
        os.stat_result, SimpleNamespace(st_mode=mode, st_file_attributes=attributes)
    )
    assert audit.is_link(info)


def test_reparse_ancestor_is_refused_before_git_or_contents(
    exported: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, export = exported
    identity = (repo / ".tmp").lstat().st_ino
    monkeypatch.setattr(audit, "is_link", lambda info: info.st_ino == identity)
    monkeypatch.setattr(
        audit, "tracked_paths", lambda _: pytest.fail("Must reject link before Git")
    )
    with pytest.raises(ValueError, match="Symlink/reparse"):
        audit.manifest(export, "web", repo)


def test_reparse_child_is_refused_before_hashing(
    exported: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, export = exported
    target = export / "apps/web/linked"
    target.mkdir()
    identity = target.lstat().st_ino
    monkeypatch.setattr(audit, "is_link", lambda info: info.st_ino == identity)
    monkeypatch.setattr(
        audit, "file_metadata", lambda _: pytest.fail("Must reject link before hashing")
    )
    with pytest.raises(ValueError, match="Symlink/reparse"):
        audit.manifest(export, "web", repo)


def test_unreadable_directory_is_not_silently_skipped(
    exported: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, export = exported

    def denied(_: Path) -> Any:
        raise PermissionError("synthetic enumeration failure")

    monkeypatch.setattr(os, "scandir", denied)
    with pytest.raises(PermissionError, match="synthetic"):
        audit.manifest(export, "web", repo)


def test_git_inventory_failure_is_not_an_empty_tracked_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_, **__: subprocess.CompletedProcess([], 128, b"", b"fixture failure"),
    )
    with pytest.raises(ValueError, match="Git tracked-file inventory failed"):
        audit.tracked_paths(Path("."))


def test_real_git_inventory_distinguishes_tracked_and_untracked(tmp_path: Path) -> None:
    repo = tmp_path / "checkout with spaces"
    repo.mkdir()
    subprocess.run(
        ["git", "-C", str(repo), "init", "--quiet"], check=True, capture_output=True
    )
    (repo / "tracked source.txt").write_bytes(b"synthetic tracked input")
    (repo / "untracked.txt").write_bytes(b"synthetic untracked input")
    subprocess.run(
        ["git", "-C", str(repo), "add", "--", "tracked source.txt"],
        check=True,
        capture_output=True,
    )
    assert audit.tracked_paths(repo) == {"tracked source.txt"}


def test_nonregular_entry_is_refused_before_hashing(
    exported: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, export = exported
    target = export / "apps/web/synthetic-special-file"
    target.write_bytes(b"fixture")
    real_lstat = Path.lstat

    def fake_lstat(path: Path) -> Any:
        if path == target:
            return SimpleNamespace(st_mode=stat.S_IFIFO, st_file_attributes=0)
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    monkeypatch.setattr(
        audit,
        "file_metadata",
        lambda _: pytest.fail("Must reject special file before hashing"),
    )
    with pytest.raises(ValueError, match="Non-regular entry"):
        audit.manifest(export, "web", repo)


def test_file_mutation_during_hashing_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "synthetic-source.txt"
    target.write_bytes(b"fixture")
    real_check = audit.check_path
    calls = 0

    def changed(path: Path, *, directory: bool = False) -> os.stat_result:
        nonlocal calls
        calls += 1
        if calls == 2:
            target.write_bytes(b"different content")
        return real_check(path, directory=directory)

    monkeypatch.setattr(audit, "check_path", changed)
    with pytest.raises(ValueError, match="File changed during hashing"):
        audit.file_metadata(target)


def test_main_returns_nonzero_json_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        sys, "argv", ["manifest", "--component", "web", "--export", ".tmp/nonexistent"]
    )

    def denied(*_: Any) -> Any:
        raise ValueError("synthetic manifest rejection")

    monkeypatch.setattr(audit, "manifest", denied)
    assert audit.main() == 1
    assert '"status": "FAIL"' in capsys.readouterr().out


@pytest.mark.parametrize("component", list(audit.COMPONENTS.values()))
def test_native_audit_target_is_independent_and_runtime_is_default(
    component: str,
) -> None:
    lines = (
        (audit.ROOT / component / "Dockerfile").read_text(encoding="utf-8").splitlines()
    )
    instructions = [
        line.strip()
        for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert instructions[:2] == ["FROM scratch AS context-audit", "COPY . /"]
    assert instructions[2].startswith("FROM ")
    assert [line for line in instructions if line.startswith("FROM ")][-1].endswith(
        " AS runtime"
    )
    assert not any("context-audit" in line.lower() for line in instructions[2:])
