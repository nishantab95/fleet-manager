"""Synthetic filesystem safety checks; never clean or inspect real runtime data."""

from __future__ import annotations

import os
import ctypes
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.maintenance import disk_audit as audit


@pytest.fixture
def no_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep ordinary accounting fixtures independent of the real checkout."""

    def run(arguments: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(arguments, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", run)


def test_recursive_totals_include_hidden_files_and_empty_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_git: None
) -> None:
    repo = tmp_path / "checkout"
    nested = repo / "nested"
    nested.mkdir(parents=True)
    (repo / "empty").mkdir()
    (tmp_path / "parent-only.txt").write_bytes(b"12345")
    (repo / ".hidden").write_bytes(b"123")
    (nested / "source.py").write_bytes(b"1234567")
    monkeypatch.setattr(audit, "allocation", lambda *_: 4096)

    result = audit.scan(tmp_path, repo)

    assert result["total"]["logical"] == 15
    assert result["total"]["allocated"] == 3 * 4096
    assert result["total"]["files"] == 3
    assert result["unique_allocated_bytes"] == 3 * 4096
    assert result["directories"]["checkout"]["logical"] == 10
    assert result["directories"]["checkout/nested"]["logical"] == 7
    assert result["directories"]["checkout/empty"]["files"] == 0
    assert [item["logical"] for item in result["largest_files"]] == [7, 5, 3]
    assert result["errors"] == []


def test_hardlinks_count_entries_but_only_one_unique_allocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_git: None
) -> None:
    original = tmp_path / "one.bin"
    original.write_bytes(b"synthetic")
    os.link(original, tmp_path / "two.bin")
    monkeypatch.setattr(audit, "allocation", lambda *_: 8192)

    result = audit.scan(tmp_path, tmp_path)

    assert result["total"]["logical"] == 18
    assert result["total"]["allocated"] == 16384
    assert result["unique_allocated_bytes"] == 8192
    assert result["repeated_hardlink_entries"] == 1


@pytest.mark.skipif(os.name != "nt", reason="Windows allocation API regression")
@pytest.mark.parametrize("size", [3, 8193])
def test_windows_allocation_is_reported_separately_from_logical_size(
    tmp_path: Path, size: int
) -> None:
    path = tmp_path / "synthetic-allocation.bin"
    path.write_bytes((bytes(range(256)) * ((size // 256) + 1))[:size])
    info = path.stat()
    sectors_per_cluster = ctypes.c_ulong()
    bytes_per_sector = ctypes.c_ulong()
    free_clusters = ctypes.c_ulong()
    total_clusters = ctypes.c_ulong()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    query = kernel.GetDiskFreeSpaceW
    query.argtypes = [ctypes.c_wchar_p] + [ctypes.POINTER(ctypes.c_ulong)] * 4
    query.restype = ctypes.c_int
    assert query(
        tmp_path.anchor,
        ctypes.byref(sectors_per_cluster),
        ctypes.byref(bytes_per_sector),
        ctypes.byref(free_clusters),
        ctypes.byref(total_clusters),
    )
    cluster_size = sectors_per_cluster.value * bytes_per_sector.value

    allocated = audit.allocation(path, info)

    assert cluster_size > 1
    assert allocated >= 0
    assert allocated != size
    # NTFS resident data can occupy 8-byte units inside its MFT record,
    # not a complete filesystem cluster. Do not equate this with freed space.
    assert allocated % 8 == 0
    compressed_or_sparse = (
        stat.FILE_ATTRIBUTE_COMPRESSED | stat.FILE_ATTRIBUTE_SPARSE_FILE
    )
    if size > cluster_size and not info.st_file_attributes & compressed_or_sparse:
        assert allocated % cluster_size == 0
        assert size <= allocated < size + cluster_size


def test_inventory_never_opens_file_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_git: None
) -> None:
    (tmp_path / "synthetic-sensitive.env").write_bytes(b"fixture-only")
    monkeypatch.setattr(audit, "allocation", lambda *_: 4096)

    def forbidden_open(*_: object, **__: object) -> None:
        raise AssertionError("An inventory must not read file contents")

    monkeypatch.setattr(Path, "open", forbidden_open)

    assert audit.scan(tmp_path, tmp_path)["total"]["logical"] == len(b"fixture-only")


@pytest.mark.skipif(os.name != "nt", reason="Windows extended-length path regression")
def test_windows_long_paths_have_allocation_and_identity_without_errors(
    tmp_path: Path, no_git: None
) -> None:
    relative = Path(*[f"nested-{number}-" + "x" * 45 for number in range(5)])
    normal = tmp_path / relative / "synthetic-long-path.bin"
    assert len(str(normal)) > 260
    extended = Path("\\\\?\\" + str(normal))
    extended.parent.mkdir(parents=True)
    extended.write_bytes(b"synthetic-data" * 1024)

    result = audit.scan(tmp_path, tmp_path)

    assert result["errors"] == []
    assert result["total"]["logical"] == len(b"synthetic-data") * 1024
    assert result["total"]["files"] == 1
    assert result["unique_allocated_bytes"] > 0
    assert result["largest_files"][0]["path"] == normal.relative_to(tmp_path).as_posix()


def test_hardlink_allocation_recovers_after_first_entry_is_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_git: None
) -> None:
    original = tmp_path / "one.bin"
    original.write_bytes(b"synthetic")
    os.link(original, tmp_path / "two.bin")
    calls = 0

    def allocation(*_: object) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("synthetic allocation denial")
        return 8192

    monkeypatch.setattr(audit, "allocation", allocation)

    result = audit.scan(tmp_path, tmp_path)

    assert result["total"]["logical"] == 18
    assert result["unique_allocated_bytes"] == 8192
    assert result["repeated_hardlink_entries"] == 1
    assert len(result["errors"]) == 1
    assert result["errors"][0]["operation"] == "allocation"
    assert sum(item["allocated"] is None for item in result["largest_files"]) == 1


def test_zero_direntry_inode_does_not_deduplicate_unrelated_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_git: None
) -> None:
    """Windows DirEntry.stat may omit inode IDs; path stat must supply them."""
    (tmp_path / "one.bin").write_bytes(b"first")
    (tmp_path / "two.bin").write_bytes(b"second")
    real_scandir = os.scandir

    class Entries:
        def __init__(self, path: Path) -> None:
            self.entries = real_scandir(path)

        def __enter__(self) -> list[SimpleNamespace]:
            wrapped: list[SimpleNamespace] = []
            for entry in self.entries:
                info = entry.stat(follow_symlinks=False)
                zero_inode = SimpleNamespace(
                    st_mode=info.st_mode,
                    st_size=info.st_size,
                    st_dev=0,
                    st_ino=0,
                    st_file_attributes=getattr(info, "st_file_attributes", 0),
                )
                wrapped.append(
                    SimpleNamespace(
                        name=entry.name,
                        path=entry.path,
                        stat=lambda *, follow_symlinks, value=zero_inode: value,
                    )
                )
            return wrapped

        def __exit__(self, *_: object) -> None:
            self.entries.close()

    monkeypatch.setattr(os, "scandir", Entries)
    monkeypatch.setattr(audit, "allocation", lambda *_: 4096)

    result = audit.scan(tmp_path, tmp_path)

    assert result["total"]["logical"] == 11
    assert result["unique_allocated_bytes"] == 8192
    assert result["repeated_hardlink_entries"] == 0


@pytest.mark.parametrize(
    ("mode", "attributes", "expected"),
    [
        (stat.S_IFLNK, 0, True),
        (stat.S_IFDIR, audit.REPARSE_POINT, True),
        (stat.S_IFREG, audit.REPARSE_POINT, True),
        (stat.S_IFREG, 0, False),
    ],
)
def test_link_detection_covers_windows_reparse_points(
    mode: int, attributes: int, expected: bool
) -> None:
    info = cast(
        os.stat_result, SimpleNamespace(st_mode=mode, st_file_attributes=attributes)
    )
    assert audit.is_link(info) is expected


def test_reparse_directory_is_not_traversed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_git: None
) -> None:
    linked = tmp_path / "synthetic-link"
    linked.mkdir()
    (linked / "must-not-be-counted").write_bytes(b"outside")
    (tmp_path / "kept").write_bytes(b"ok")
    link_id = linked.stat().st_ino
    monkeypatch.setattr(audit, "is_link", lambda info: info.st_ino == link_id)
    monkeypatch.setattr(audit, "allocation", lambda *_: 4096)

    result = audit.scan(tmp_path, tmp_path)

    assert result["total"]["logical"] == 2
    assert result["skipped_links_or_special"] == ["synthetic-link"]
    assert result["directories"].get("synthetic-link", {"files": 0})["files"] == 0


def test_root_with_reparse_ancestor_is_rejected_before_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    ancestor_id = tmp_path.stat().st_ino
    monkeypatch.setattr(audit, "is_link", lambda info: info.st_ino == ancestor_id)
    calls: list[object] = []
    monkeypatch.setattr(audit, "git_paths", lambda *args: calls.append(args))

    with pytest.raises(ValueError, match="symlink/reparse"):
        audit.scan(root, root)
    assert calls == []


def test_repo_with_reparse_ancestor_is_rejected_before_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    linked = tmp_path / "linked"
    repo = linked / "checkout"
    repo.mkdir(parents=True)
    link_id = linked.stat().st_ino
    monkeypatch.setattr(audit, "is_link", lambda info: info.st_ino == link_id)
    calls: list[object] = []
    monkeypatch.setattr(audit, "git_paths", lambda *args: calls.append(args))

    with pytest.raises(ValueError, match="symlink/reparse"):
        audit.scan(tmp_path, repo)
    assert calls == []


def test_queued_directory_is_rechecked_before_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_git: None
) -> None:
    queued = tmp_path / "replaced-directory"
    queued.mkdir()
    (queued / "must-not-be-counted").write_bytes(b"outside")
    queued_id = queued.stat().st_ino
    calls = 0

    def is_link(info: os.stat_result) -> bool:
        nonlocal calls
        # Windows DirEntry.stat may supply inode zero on the first encounter.
        if info.st_ino not in (0, queued_id) or not stat.S_ISDIR(info.st_mode):
            return False
        calls += 1
        return calls > 1

    monkeypatch.setattr(audit, "is_link", is_link)

    result = audit.scan(tmp_path, tmp_path)

    assert result["total"]["logical"] == 0
    assert "replaced-directory" in result["skipped_links_or_special"]


def test_unreadable_directory_is_reported_and_siblings_are_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_git: None
) -> None:
    denied = tmp_path / "denied"
    denied.mkdir()
    (tmp_path / "kept").write_bytes(b"ok")
    real_scandir = os.scandir

    def scandir(path: str | Path) -> Any:
        if Path(path).name == denied.name:
            raise PermissionError("synthetic enumeration denial")
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", scandir)
    monkeypatch.setattr(audit, "allocation", lambda *_: 4096)

    result = audit.scan(tmp_path, tmp_path)

    assert result["total"]["logical"] == 2
    assert result["errors"] == [
        {
            "path": "denied",
            "operation": "scandir",
            "error": "synthetic enumeration denial",
        }
    ]


def test_checkout_outside_audit_root_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "audit"
    repo = tmp_path / "other"
    root.mkdir()
    repo.mkdir()
    with pytest.raises(ValueError, match="inside the audit root"):
        audit.scan(root, repo)


@pytest.mark.parametrize(
    ("relative", "tracked", "expected"),
    [
        ("src/main.py", True, "A"),
        (".runtime/events.db", False, "D"),
        (".RUNTIME/events.db", False, "D"),
        (".git/objects/01/abcdef", False, "D"),
        (".env.production", False, "D"),
        ("infra/data/evidence/photo.jpg", False, "D"),
        ("android/key.properties", False, "D"),
        ("release/pilot.jks", False, "E"),
        ("build/outputs/app.aab", False, "E"),
        ("app/Node_Modules/a/index.js", False, "B"),
        (".venv/Lib/site-packages/p/a.py", False, "B"),
        ("app/.next/cache/file", False, "C"),
        (".pytest-test-123/synthetic.db", False, "C"),
        ("app/build/intermediate.o", False, "C"),
        ("backups/do-not-assume-disposable.dump", False, "F"),
        ("unidentified/data.bin", False, "F"),
    ],
)
def test_conservative_category_rules(
    relative: str, tracked: bool, expected: str
) -> None:
    assert audit.category(relative, tracked) == expected


def test_real_git_index_and_ignore_rules_are_not_confused(tmp_path: Path) -> None:
    def git(*arguments: str) -> None:
        subprocess.run(
            ["git", "-C", str(tmp_path), *arguments],
            check=True,
            capture_output=True,
        )

    git("init", "--quiet")
    (tmp_path / ".gitignore").write_text("*.generated\n", encoding="utf-8")
    (tmp_path / "source.txt").write_bytes(b"tracked")
    (tmp_path / "forced.generated").write_bytes(b"also-tracked")
    (tmp_path / "cache.generated").write_bytes(b"ignored")
    (tmp_path / "untracked.txt").write_bytes(b"untracked")
    git("add", "--", "source.txt")
    git("add", "-f", "--", "forced.generated")

    result = audit.scan(tmp_path, tmp_path)

    assert result["tracked_files"] == 2
    assert result["tracked_bytes"] == len(b"trackedalso-tracked")
    assert result["ignored_bytes"] == len(b"ignored")
    assert result["git_roots"] == ["."]
    assert result["errors"] == []
    by_path = {item["path"]: item for item in result["largest_files"]}
    assert by_path["source.txt"]["category"] == "A"
    assert by_path["forced.generated"]["category"] == "A"
    assert by_path["cache.generated"]["category"] == "F"


def test_git_failures_are_reported_not_silently_treated_as_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(arguments: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            arguments, 128, b"", b"synthetic git failure"
        )

    monkeypatch.setattr(subprocess, "run", run)
    result = audit.scan(tmp_path, tmp_path)
    assert {item["operation"] for item in result["errors"]} == {
        "git inventory",
        "git check-ignore",
    }


def test_report_output_refuses_existing_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "report.json"
    output.write_bytes(b"existing evidence must survive")
    monkeypatch.setattr(sys, "argv", ["disk_audit", "--output", str(output)])
    monkeypatch.setattr(audit, "scan", lambda *_: {"total": {"logical": 0}})

    with pytest.raises(FileExistsError):
        audit.main()
    assert output.read_bytes() == b"existing evidence must survive"
