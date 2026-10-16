"""Exercise read-only host gates with synthetic Linux probes, never Docker/SSH."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

SOURCE = Path(__file__).parent / "production" / "healthcheck.sh"
pytestmark = pytest.mark.skipif(
    os.name == "nt", reason="Run host-resource fixtures under Linux"
)

COMMON_DOUBLE = r"""
die() { printf '[FAILED] %s\n' "$*" >&2; exit 1; }
require_command() { :; }
require_production_files() { :; }
env_value() { printf '%s\n' "$FAKE_BACKUPS"; }
uname() { printf '%s\n' "$FAKE_OS"; }
timeout() {
  printf 'timeout|%s\n' "$*" >>"$FAKE_TRACE"
  shift
  case "$1" in
    docker)
      [[ "$FAKE_FAILURE" != docker ]] || return 124
      printf '%s\n' "$FAKE_DOCKER_ROOT" ;;
    df)
      [[ "$FAKE_FAILURE" != disk_unreadable ]] || return 1
      if [[ "$FAKE_FAILURE" == disk_malformed ]]; then
        printf 'Avail Use%%\nunknown unknown\n'
      elif [[ "$FAKE_DISK_PATH" == all || "${@: -1}" == "$FAKE_DISK_PATH" ]]; then
        printf 'Avail Use%%\n%s %s%%\n' "$FAKE_FREE_BYTES" "$FAKE_USED_PERCENT"
      else
        printf 'Avail Use%%\n20000000000 20%%\n'
      fi ;;
    awk) "$@" ;;
    *) return 90 ;;
  esac
}
fleet_compose() {
  if [[ "$*" == ps* ]]; then
    printf 'synthetic-container\n'
  elif [[ "$*" == *'/ready'* ]]; then
    printf 'ready\n'
  else
    printf 'ok\n'
  fi
}
docker() { printf 'true\n'; }
curl() {
  if [[ "$*" == *write-out* ]]; then
    printf '404'
  else
    printf '{"status":"ok"}'
  fi
}
"""


def _run(
    tmp_path: Path,
    *,
    failure: str = "none",
    free_bytes: str = "20000000000",
    used_percent: str = "20",
    memory: str = "MemTotal: 4000000 kB\nMemAvailable: 2000000 kB\n",
    load: str = "0.15 0.20 0.25 1/100 42\n",
    internal: bool = False,
    operating_system: str = "Linux",
    disk: str = "all",
) -> tuple[subprocess.CompletedProcess[str], str]:
    scripts = tmp_path / "production"
    scripts.mkdir()
    memory_file = tmp_path / "meminfo"
    memory_file.write_text(memory, encoding="ascii")
    load_file = tmp_path / "loadavg"
    load_file.write_text(load, encoding="ascii")
    source = SOURCE.read_text(encoding="utf-8")
    assert source.count("/proc/meminfo") == source.count("/proc/loadavg") == 1
    # Only the test copy replaces kernel-file literals; production has no
    # fixture-path environment variables or option to bypass normal host gates.
    source = source.replace("/proc/meminfo", shlex.quote(str(memory_file))).replace(
        "/proc/loadavg", shlex.quote(str(load_file))
    )
    (scripts / "healthcheck.sh").write_text(source, encoding="utf-8", newline="\n")
    (scripts / "common.sh").write_text(COMMON_DOUBLE, encoding="utf-8", newline="\n")
    docker_root = tmp_path / "docker"
    docker_root.mkdir()
    backups = tmp_path / "backups"
    backups.mkdir()
    if failure == "memory_unreadable":
        memory_file.rename(tmp_path / "retained-meminfo")
    if failure == "load_unreadable":
        load_file.rename(tmp_path / "retained-loadavg")
    trace = tmp_path / "probes.log"
    environment = os.environ.copy()
    environment.update(
        FAKE_FAILURE=failure,
        FAKE_TRACE=str(trace),
        FAKE_DOCKER_ROOT=str(docker_root),
        FAKE_BACKUPS=str(backups),
        FAKE_FREE_BYTES=free_bytes,
        FAKE_USED_PERCENT=used_percent,
        FAKE_DISK_PATH={
            "root": "/",
            "docker": str(docker_root),
            "backups": str(backups),
        }.get(disk, disk),
        FAKE_OS=operating_system,
    )
    bash = shutil.which("bash")
    assert bash
    arguments = [bash, str(scripts / "healthcheck.sh")]
    if internal:
        arguments.append("--internal-only")
    result = subprocess.run(  # noqa: S603
        arguments,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    return result, trace.read_text() if trace.exists() else ""


def test_healthy_resources_pass_all_three_filesystems(tmp_path: Path) -> None:
    result, probes = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "HOST_RESOURCES=PASS" in result.stdout
    assert "PRODUCTION_HEALTH=PASS" in result.stdout
    assert probes.count("timeout|5s df ") == 3
    assert "timeout|10s docker info" in probes
    assert probes.count("timeout|5s awk ") == 2
    for label in ("root", "docker", "backups"):
        assert f"HOST_DISK_{label}_AVAILABLE_BYTES=20000000000" in result.stdout


@pytest.mark.parametrize("disk", ["root", "docker", "backups"])
@pytest.mark.parametrize("values", [("20000000000", "75"), ("9999999999", "20")])
def test_each_filesystem_enforces_both_thresholds(
    tmp_path: Path, disk: str, values: tuple[str, str]
) -> None:
    result, _ = _run(tmp_path, disk=disk, free_bytes=values[0], used_percent=values[1])
    assert result.returncode != 0
    assert f"{disk} filesystem requires" in result.stderr
    assert "PRODUCTION_HEALTH=PASS" not in result.stdout


def test_exact_free_disk_and_load_boundary_pass(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, free_bytes="10000000000", load="0.1 0.2 1.50 1/100 42\n")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("available", ["1200000", "1199999"])
def test_available_memory_at_or_below_thirty_percent_fails(
    tmp_path: Path, available: str
) -> None:
    result, _ = _run(
        tmp_path, memory=f"MemTotal: 4000000 kB\nMemAvailable: {available} kB\n"
    )
    assert result.returncode != 0
    assert "memory must exceed 30%" in result.stderr


def test_fifteen_minute_load_above_boundary_fails(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, load="0.1 0.2 1.51 1/100 42\n")
    assert result.returncode != 0
    assert "15-minute load exceeds" in result.stderr


@pytest.mark.parametrize(
    "failure",
    [
        "docker",
        "disk_unreadable",
        "disk_malformed",
        "memory_unreadable",
        "load_unreadable",
    ],
)
def test_unreadable_or_invalid_probe_fails_closed(tmp_path: Path, failure: str) -> None:
    result, _ = _run(tmp_path, failure=failure)
    assert result.returncode != 0
    assert "[FAILED]" in result.stderr
    assert "HOST_RESOURCES=PASS" not in result.stdout


@pytest.mark.parametrize(
    "memory",
    [
        "MemTotal: 4000000 kB\n",
        "MemTotal: 0 kB\nMemAvailable: 0 kB\n",
        "MemTotal: 4000000 kB\nMemAvailable: unknown kB\n",
        "MemTotal: 4000000 kB\nMemAvailable: 5000000 kB\n",
        "MemTotal: 4000000 kB\nMemAvailable: 2000000 MB\n",
    ],
)
def test_malformed_memory_is_not_healthy(tmp_path: Path, memory: str) -> None:
    result, _ = _run(tmp_path, memory=memory)
    assert result.returncode != 0
    assert "available-memory measurement failed" in result.stderr


@pytest.mark.parametrize("load", ["", "0.1 0.2 invalid 1/100 42\n"])
def test_malformed_load_is_not_healthy(tmp_path: Path, load: str) -> None:
    result, _ = _run(tmp_path, load=load)
    assert result.returncode != 0
    assert "load measurement failed" in result.stderr


@pytest.mark.parametrize("operating_system", ["Linux", "MINGW64_NT-10.0"])
def test_internal_only_skips_all_host_probes(
    tmp_path: Path, operating_system: str
) -> None:
    result, probes = _run(tmp_path, internal=True, operating_system=operating_system)
    assert result.returncode == 0, result.stderr
    assert probes == ""
    assert "HOST_RESOURCES=SKIPPED_INTERNAL_ONLY" in result.stdout
    assert "EXTERNAL_CHECKS=SKIPPED" in result.stdout


def test_normal_non_linux_health_is_not_reported_as_vps_pass(tmp_path: Path) -> None:
    result, probes = _run(tmp_path, operating_system="MINGW64_NT-10.0")
    assert result.returncode != 0
    assert "require Linux" in result.stderr
    assert probes == ""
