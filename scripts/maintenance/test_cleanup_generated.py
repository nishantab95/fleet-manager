"""Exercise manual cleanup guards against disposable fixtures, never real targets."""

from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("cleanup-generated.ps1")
POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / (
    "System32/WindowsPowerShell/v1.0/powershell.exe"
)
CACHE = "apps/web/.next/dev/cache"
pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows cleanup utility")


def literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def run_ps(code: str) -> str:
    # Dot-sourcing loads helpers but must never run the real cleanup entry point.
    text = f". {literal(SCRIPT)}\n{code}"
    encoded = base64.b64encode(text.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        [
            str(POWERSHELL),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-EncodedCommand",
            encoded,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def cache_file(root: Path, filename: str = ".rscinfo") -> Path:
    path = root / CACHE / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"synthetic generated fixture")
    return path


def test_dot_source_never_invokes_real_cleanup() -> None:
    assert run_ps("'HELPERS_ONLY'") == "HELPERS_ONLY"


def test_default_entry_point_reports_without_removing_synthetic_cache(
    tmp_path: Path,
) -> None:
    path = cache_file(tmp_path)
    result = run_ps(
        f"function Get-FleetCleanupRoot {{ {literal(tmp_path)} }}; "
        "function Assert-FleetNoTrackedTarget {}; function Assert-FleetNoBuildClients {}; "
        "Invoke-FleetGeneratedCleanup"
    )
    assert "REPORT_ONLY: nothing removed" in result
    assert "REMOVED_FILE" not in result
    assert path.read_bytes() == b"synthetic generated fixture"


@pytest.mark.parametrize(("exit_code", "output"), [(0, "tracked-file"), (128, "")])
def test_tracked_files_or_failed_git_verification_refuse_cleanup(
    tmp_path: Path, exit_code: int, output: str
) -> None:
    result = run_ps(
        f"function git {{ $global:LASTEXITCODE = {exit_code}; {literal(output)} }}; "
        f"try {{ Assert-FleetNoTrackedTarget {literal(tmp_path)} '{CACHE}'; throw 'UNSAFE' }} "
        "catch { $_.Exception.Message }"
    )
    assert (
        "Tracked files exist" in result
        or "Git tracked-file verification failed" in result
    )


@pytest.mark.parametrize(
    "relative",
    [
        ".",
        "..",
        ".git",
        ".runtime",
        "apps/web/node_modules",
        "apps/web/.next/dev/cache/../..",
    ],
)
def test_non_allowlisted_targets_are_refused(tmp_path: Path, relative: str) -> None:
    result = run_ps(
        f"try {{ Resolve-FleetCleanupTarget {literal(tmp_path)} {literal(relative)}; throw 'UNSAFE' }} catch {{ $_.Exception.Message }}"
    )
    assert "Target is not allowlisted" in result


def test_inventory_reports_exact_bytes_without_deleting(tmp_path: Path) -> None:
    path = cache_file(tmp_path)
    result = run_ps(
        f"$i = Get-FleetTargetInventory {literal(tmp_path)} '{CACHE}'; \"$($i.Files.Count):$($i.Bytes)\""
    )
    assert result == "1:27"
    assert path.read_bytes() == b"synthetic generated fixture"


@pytest.mark.parametrize(
    "filename", [".env", "private.jks", "pilot.apk", "events.sqlite3", "unexpected.txt"]
)
def test_protected_or_unknown_content_blocks_entire_target(
    tmp_path: Path, filename: str
) -> None:
    path = cache_file(tmp_path, filename)
    result = run_ps(
        f"try {{ Get-FleetTargetInventory {literal(tmp_path)} '{CACHE}'; throw 'UNSAFE' }} catch {{ $_.Exception.Message }}"
    )
    assert "refused" in result.lower() or "Unrecognised generated content" in result
    assert path.exists()


def test_expected_directory_cannot_be_replaced_by_file(tmp_path: Path) -> None:
    path = tmp_path / CACHE
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not a cache directory")
    result = run_ps(
        f"try {{ Get-FleetTargetInventory {literal(tmp_path)} '{CACHE}'; throw 'UNSAFE' }} catch {{ $_.Exception.Message }}"
    )
    assert "Expected generated directory" in result


def test_changed_tar_is_not_the_audited_disposable_export(tmp_path: Path) -> None:
    path = tmp_path / ".tmp/fleet-api-ci.tar"
    path.parent.mkdir()
    path.write_bytes(b"not the original export")
    result = run_ps(
        f"$i = Get-FleetTargetInventory {literal(tmp_path)} '.tmp/fleet-api-ci.tar'; try {{ Assert-FleetExclusiveFiles @($i); throw 'UNSAFE' }} catch {{ $_.Exception.Message }}"
    )
    assert "Tar differs from the independently audited" in result
    assert path.exists()


def test_hardlinks_are_refused(tmp_path: Path) -> None:
    path = cache_file(tmp_path)
    os.link(path, path.with_name("next-devtools-config.json"))
    result = run_ps(
        f"$i = Get-FleetTargetInventory {literal(tmp_path)} '{CACHE}'; try {{ Assert-FleetExclusiveFiles @($i); throw 'UNSAFE' }} catch {{ $_.Exception.Message }}"
    )
    assert "Hardlinked file refused" in result


def test_locked_files_are_refused(tmp_path: Path) -> None:
    path = cache_file(tmp_path)
    result = run_ps(
        f"$i = Get-FleetTargetInventory {literal(tmp_path)} '{CACHE}'; $lock = [IO.File]::Open({literal(path)}, 'Open', 'Read', 'None'); try {{ try {{ Assert-FleetExclusiveFiles @($i); throw 'UNSAFE' }} catch {{ $_.Exception.Message }} }} finally {{ $lock.Dispose() }}"
    )
    assert "being used by another process" in result
    assert path.exists()


def test_directory_junction_is_refused_without_traversal(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    protected = outside / "keep.txt"
    protected.write_bytes(b"must survive")
    target = tmp_path / CACHE
    target.parent.mkdir(parents=True)
    result = run_ps(
        f"New-Item -ItemType Junction -Path {literal(target)} -Target {literal(outside)} | Out-Null; try {{ Get-FleetTargetInventory {literal(tmp_path)} '{CACHE}'; throw 'UNSAFE' }} catch {{ $_.Exception.Message }}"
    )
    assert "Reparse point refused" in result
    assert protected.read_bytes() == b"must survive"


def test_verified_synthetic_files_only_are_removed(tmp_path: Path) -> None:
    path = cache_file(tmp_path)
    protected = tmp_path / "keep.txt"
    protected.write_bytes(b"outside target")
    result = run_ps(
        f"$i = Get-FleetTargetInventory {literal(tmp_path)} '{CACHE}'; Assert-FleetExclusiveFiles @($i); Remove-FleetVerifiedInventory $i"
    )
    assert "REMOVED_FILE logical_bytes=27" in result
    assert not path.exists()
    assert protected.read_bytes() == b"outside target"


def test_new_child_survives_race_after_directory_empty_check(tmp_path: Path) -> None:
    target = tmp_path / CACHE
    target.mkdir(parents=True)
    result = run_ps(
        f"$i = Get-FleetTargetInventory {literal(tmp_path)} '{CACHE}'; [IO.File]::WriteAllText({literal(target / 'new-source.txt')}, 'must survive'); function Get-ChildItem {{ @() }}; try {{ Remove-FleetVerifiedInventory $i; throw 'UNSAFE' }} catch {{ $_.Exception.Message }}"
    )
    assert "not empty" in result.lower()
    assert (target / "new-source.txt").read_text() == "must survive"


@pytest.mark.parametrize(
    ("name", "command", "blocked"),
    [
        ("node.exe", r"node C:\tools\next\dist\bin\next dev", True),
        ("dart.exe", "dart flutter_tools.snapshot build appbundle", True),
        ("java.exe", "java org.gradle.launcher.GradleMain", True),
        ("node.exe", "", True),
        ("node.exe", "node codex-repl", False),
        ("java.exe", "java org.gradle.launcher.daemon.bootstrap.GradleDaemon", False),
    ],
)
def test_build_client_detection(name: str, command: str, blocked: bool) -> None:
    result = run_ps(
        f"Test-FleetBuildClient ([pscustomobject]@{{ ProcessId = -1; Name = {literal(name)}; CommandLine = {literal(command)} }})"
    )
    assert result == str(blocked)
