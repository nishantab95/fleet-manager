"""Linux fixture-only retention checks. No real Docker, backups or deletion calls."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parent / "production"
pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Run in the isolated Linux test container"
)


def snapshot(root: Path) -> dict[str, tuple[object, ...]]:
    result: dict[str, tuple[object, ...]] = {}
    for path in root.rglob("*"):
        info = path.lstat()
        payload = (
            os.readlink(path)
            if path.is_symlink()
            else path.read_bytes()
            if path.is_file()
            else None
        )
        result[str(path.relative_to(root))] = (
            info.st_mode,
            info.st_mtime_ns,
            info.st_nlink,
            payload,
        )
    return result


@pytest.fixture
def fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    scripts = tmp_path / "scripts" / "production"
    scripts.mkdir(parents=True)
    root = tmp_path / "synthetic backups"
    root.mkdir()
    for name in ("common.sh", "prune-local-backups.sh"):
        shutil.copyfile(SOURCE / name, scripts / name)
    env_file = tmp_path / "synthetic.env"
    env_file.write_text(f"FLEET_BACKUP_DIR={root}\n")
    environment = os.environ.copy()
    environment["FLEET_PRODUCTION_ENV_FILE"] = str(env_file)
    return scripts, root, environment


def generation(root: Path, day: int) -> Path:
    path = root / f"fleet-202610{day:02d}-010203Z-abc123"
    path.mkdir()
    (path / "evidence").mkdir()
    (path / "evidence" / "synthetic-image").write_bytes(b"fake evidence fixture")
    for name in (
        "postgres.dump",
        "postgres.sha256",
        "evidence.sha256",
        "evidence.present",
        "manifest.txt",
        ".offsite-complete",
    ):
        (path / name).write_bytes(b"synthetic metadata\n")
    os.utime(path / ".offsite-complete", (1000 + day, 1000 + day))
    return path


def run_report(
    fixture: tuple[Path, Path, dict[str, str]], *args: str
) -> subprocess.CompletedProcess[str]:
    scripts, _, environment = fixture
    return subprocess.run(
        ["bash", str(scripts / "prune-local-backups.sh"), *args],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )


def test_old_generations_report_exact_bytes_and_remain_unchanged(
    fixture: tuple[Path, Path, dict[str, str]],
) -> None:
    _, root, _ = fixture
    paths = [generation(root, day) for day in (1, 2, 3, 4)]
    before = snapshot(root)
    result = run_report(fixture)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    retained = [line for line in lines if line.startswith("LOCAL_BACKUP_RETAIN ")]
    candidates = [
        line for line in lines if line.startswith("LOCAL_BACKUP_REVIEW_CANDIDATE ")
    ]
    assert len(retained) == len(candidates) == 2
    for path in paths[:2]:
        line = next(line for line in candidates if path.name in line)
        size = sum(child.stat().st_size for child in path.rglob("*") if child.is_file())
        assert f"logical_bytes={size} " in line
    assert all(any(path.name in line for line in retained) for path in paths[2:])
    assert "OPERATOR_APPROVAL_REQUIRED=YES" in result.stdout
    assert "LOCAL_BACKUPS_REMOVED=0" in result.stdout
    assert snapshot(root) == before


def test_keep_can_increase_but_never_remove(
    fixture: tuple[Path, Path, dict[str, str]],
) -> None:
    _, root, _ = fixture
    for day in range(1, 5):
        generation(root, day)
    before = snapshot(root)
    result = run_report(fixture, "--keep", "3")
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("LOCAL_BACKUP_REVIEW_CANDIDATE ") == 1
    assert result.stdout.count("LOCAL_BACKUP_RETAIN ") == 3
    assert snapshot(root) == before


@pytest.mark.parametrize(
    "args",
    [
        ("--keep", "1"),
        ("--keep", "0"),
        ("--keep", "-2"),
        ("--keep", "bad"),
        ("--apply",),
        ("/outside/target",),
    ],
)
def test_invalid_or_deletion_arguments_refused(
    fixture: tuple[Path, Path, dict[str, str]], args: tuple[str, ...]
) -> None:
    _, root, _ = fixture
    generation(root, 1)
    before = snapshot(root)
    result = run_report(fixture, *args)
    assert result.returncode != 0
    assert snapshot(root) == before


@pytest.mark.parametrize(
    "condition", ["missing_marker", "partial", "unknown", "symlink", "hardlink", "fifo"]
)
def test_incomplete_unknown_and_linked_contents_are_preserved(
    fixture: tuple[Path, Path, dict[str, str]], condition: str
) -> None:
    _, root, _ = fixture
    candidate = generation(root, 1)
    if condition == "missing_marker":
        (candidate / ".offsite-complete").rename(candidate / "incomplete-marker")
    elif condition == "partial":
        (candidate / "postgres.dump.partial").write_bytes(
            b"incomplete synthetic database"
        )
    elif condition == "unknown":
        (candidate / "unrecognized-file").write_bytes(b"preserve")
    elif condition == "symlink":
        (candidate / "evidence" / "external-link").symlink_to(root.parent / "outside")
    elif condition == "hardlink":
        os.link(candidate / "postgres.dump", root.parent / "linked-synthetic-dump")
    else:
        getattr(os, "mkfifo")(candidate / "evidence" / "synthetic-fifo")
    before = snapshot(root)
    result = run_report(fixture)
    assert result.returncode == 0, result.stderr
    assert "LOCAL_BACKUP_PRESERVED " in result.stdout
    assert "LOCAL_BACKUP_REVIEW_CANDIDATE " not in result.stdout
    assert "LOCAL_BACKUP_RETAIN " not in result.stdout
    assert snapshot(root) == before


def test_generation_symlink_cannot_traverse_outside_root(
    fixture: tuple[Path, Path, dict[str, str]],
) -> None:
    _, root, _ = fixture
    outside = root.parent / "outside"
    outside.mkdir()
    (outside / "sentinel").write_bytes(b"must remain untouched")
    (root / "fleet-20261001-010203Z-abc123").symlink_to(
        outside, target_is_directory=True
    )
    before = snapshot(root.parent)
    result = run_report(fixture)
    assert result.returncode == 0, result.stderr
    assert "reason=link_or_non_directory" in result.stdout
    assert snapshot(root.parent) == before


@pytest.mark.parametrize("kind", ["symlink", "relative", "root", "noncanonical"])
def test_unsafe_backup_roots_are_refused(
    fixture: tuple[Path, Path, dict[str, str]], kind: str
) -> None:
    _, root, environment = fixture
    alias = root.parent / "alias"
    alias.symlink_to(root, target_is_directory=True)
    configured = {
        "symlink": str(alias),
        "relative": "relative",
        "root": "/",
        "noncanonical": str(root / ".." / root.name),
    }[kind]
    Path(environment["FLEET_PRODUCTION_ENV_FILE"]).write_text(
        f"FLEET_BACKUP_DIR={configured}\n"
    )
    before = snapshot(root)
    result = run_report(fixture)
    assert result.returncode != 0
    assert snapshot(root) == before


def test_unknown_generation_name_is_not_a_retention_candidate(
    fixture: tuple[Path, Path, dict[str, str]],
) -> None:
    _, root, _ = fixture
    candidate = generation(root, 1)
    candidate.rename(root / "fleet-important-manual-backup")
    before = snapshot(root)
    result = run_report(fixture)
    assert result.returncode == 0, result.stderr
    assert "reason=unknown_generation_name" in result.stdout
    assert snapshot(root) == before


def test_backup_chain_never_invokes_retention(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(SOURCE / "backup-and-verify.sh", scripts / "backup-and-verify.sh")
    trace = tmp_path / "trace"
    for name in (
        "backup.sh",
        "verify-backup.sh",
        "offsite-backup.sh",
        "prune-local-backups.sh",
    ):
        body = f'printf "%s\\n" "{name}" >>"$TRACE_PATH"\n'
        if name == "backup.sh":
            body += 'printf "BACKUP_PATH=/synthetic/generation\\n"\n'
        (scripts / name).write_text("#!/usr/bin/env bash\n" + body)
    result = subprocess.run(
        ["bash", str(scripts / "backup-and-verify.sh")],
        env={**os.environ, "TRACE_PATH": str(trace)},
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert trace.read_text().splitlines() == [
        "backup.sh",
        "verify-backup.sh",
        "offsite-backup.sh",
    ]
    assert "SCHEDULED_BACKUP=PASS" in result.stdout


def test_failed_database_dump_preserves_private_partial_generation(
    tmp_path: Path,
) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    root = tmp_path / "backups"
    root.mkdir()
    shutil.copyfile(SOURCE / "backup.sh", scripts / "backup.sh")
    (scripts / "common.sh").write_text(
        "require_command() { :; }\nrequire_production_files() { :; }\n"
        'env_value() { printf "%s" "$FAKE_BACKUP_ROOT"; }\n'
        'die() { printf "%s\\n" "$*" >&2; exit 1; }\n'
        'fleet_compose() { printf "synthetic partial dump"; return 23; }\n'
    )
    result = subprocess.run(
        ["bash", str(scripts / "backup.sh")],
        env={**os.environ, "FAKE_BACKUP_ROOT": str(root)},
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 23, result.stderr
    generations = list(root.iterdir())
    assert len(generations) == 1
    partial = generations[0] / "postgres.dump.partial"
    assert partial.read_bytes() == b"synthetic partial dump"
    assert partial.stat().st_mode & 0o777 == 0o600
    assert generations[0].stat().st_mode & 0o777 == 0o700
    assert not (generations[0] / ".offsite-complete").exists()
    assert "Incomplete backup preserved for review:" in result.stderr
