"""Exercise release control flow with isolated command doubles; never use Docker."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parent / "production"
CURRENT_TAG = "a" * 40
CANDIDATE_TAG = "b" * 40
CONFIG_HASH = "c" * 64
APP_START = "up --detach --wait --wait-timeout 180 --no-build --no-deps api web marketing caddy"

COMMON_DOUBLE = r"""#!/usr/bin/env bash
set -Eeuo pipefail
STATE_DIR="$SCRIPT_DIR/state"
STATE_FILE="$STATE_DIR/current.env"
LOCK_FILE="$STATE_DIR/deploy.lock"
die() { printf '[FAILED] %s\n' "$*" >&2; exit 1; }
require_command() { :; }
require_production_files() { :; }
flock() { :; }
install() { mkdir -p "${@: -1}"; }
state_value() { printf '%s' "$FAKE_CURRENT_TAG"; }
current_image_tag() { printf '%s' "${FLEET_IMAGE_TAG:-$FAKE_CURRENT_TAG}"; }
write_deploy_state() { printf 'state|%s\n' "$*" >>"$TRACE_PATH"; }
fleet_compose() {
  printf 'compose|%s|%s\n' "${FLEET_IMAGE_TAG:-}" "$*" >>"$TRACE_PATH"
  case "$*" in
    'ps --all --quiet postgres'|'ps --all --quiet minio')
      if [[ "$FAKE_DATA" != absent && "$FAKE_DATA" != *volume ]]; then
        printf '%s-container\n' "${@: -1}"
      fi ;;
    'config --hash postgres'|'config --hash minio')
      printf '%s %s\n' "${@: -1}" "$FAKE_CONFIG_HASH" ;;
    '--profile tools run --rm --no-deps migrate')
      [[ "$FAKE_FAILURE" != migration ]] || return 23 ;;
    'up --detach --wait --wait-timeout 180 --no-build --no-deps api web marketing caddy')
      if [[ "$FAKE_FAILURE" == application && "$FLEET_IMAGE_TAG" == "$FAKE_CANDIDATE_TAG" ]]; then
        return 24
      fi ;;
  esac
}
docker() {
  printf 'docker|%s\n' "$*" >>"$TRACE_PATH"
  if [[ "$1" == inspect ]]; then
    if [[ "$*" == *State.Running* ]]; then
      [[ "$FAKE_DATA" != stopped ]] && printf 'true\n' || printf 'false\n'
    elif [[ "$FAKE_DATA" == changed && "${@: -1}" == postgres-container ]]; then
      printf '%064d\n' 0
    else
      printf '%s\n' "$FAKE_CONFIG_HASH"
    fi
  elif [[ "$1" == volume && "$FAKE_DATA" == orphan-volume && "$*" == *label=* ]]; then
    printf 'preserved-data-volume\n'
  elif [[ "$1" == volume && "$FAKE_DATA" == unlabeled-volume && "$*" == *name=* ]]; then
    printf 'fleet-ai-production_postgres_data\n'
  fi
}
"""


def _run_control(
    tmp_path: Path,
    *,
    script: str = "deploy.sh",
    current: str = CURRENT_TAG,
    data: str = "running",
    failure: str = "none",
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bash = shutil.which("bash")
    if os.name == "nt":
        git_bash = Path("C:/Program Files/Git/bin/bash.exe")
        if git_bash.is_file():
            bash = str(git_bash)
    assert bash is not None, "Git Bash or Linux Bash is required for deployment-control tests"
    scripts = tmp_path / "production"
    scripts.mkdir()
    for name in ("deploy.sh", "rollback.sh", "data-service-guard.sh"):
        shutil.copyfile(SOURCE / name, scripts / name)
    (scripts / "common.sh").write_text(COMMON_DOUBLE, encoding="utf-8", newline="\n")
    (scripts / "validate-config.sh").write_text(
        '#!/usr/bin/env bash\nprintf "validate\\n" >>"$TRACE_PATH"\n',
        encoding="utf-8",
        newline="\n",
    )
    (scripts / "backup-and-verify.sh").write_text(
        "#!/usr/bin/env bash\n"
        'printf "backup|%s\\n" "$FLEET_IMAGE_TAG" >>"$TRACE_PATH"\n'
        '[[ "$FAKE_FAILURE" != backup ]] || exit 22\n'
        'printf "BACKUP_PATH=/fake/verified-generation\\n"\n',
        encoding="utf-8",
        newline="\n",
    )
    (scripts / "healthcheck.sh").write_text(
        '#!/usr/bin/env bash\nprintf "health|%s\\n" "$FLEET_IMAGE_TAG" >>"$TRACE_PATH"\n',
        encoding="utf-8",
        newline="\n",
    )
    if current:
        (scripts / "state").mkdir()
        (scripts / "state" / "current.env").write_text(
            f"FLEET_IMAGE_TAG={current}\n", encoding="utf-8"
        )
    trace = tmp_path / "trace.log"
    environment = os.environ.copy()
    environment.pop("FLEET_IMAGE_TAG", None)
    environment.update(
        TRACE_PATH=trace.as_posix(),
        FAKE_CURRENT_TAG=current,
        FAKE_CANDIDATE_TAG=CANDIDATE_TAG,
        FAKE_CONFIG_HASH=CONFIG_HASH,
        FAKE_DATA=data,
        FAKE_FAILURE=failure,
    )
    arguments = [bash, (scripts / script).as_posix()]
    if script == "deploy.sh":
        arguments.extend(["--image-tag", CANDIDATE_TAG])
    else:
        arguments.append(CANDIDATE_TAG)
    # Only checked-in scripts and test-created doubles are executed; Docker is
    # replaced by a shell function and no live service is contacted.
    result = subprocess.run(  # noqa: S603
        arguments,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result, trace.read_text(encoding="utf-8").splitlines()


def _application_starts(trace: list[str]) -> list[str]:
    return [line for line in trace if f"|{APP_START}" in line]


def test_existing_deploy_backs_up_running_tag_without_reconciling_data(tmp_path: Path) -> None:
    result, trace = _run_control(tmp_path)
    assert result.returncode == 0, result.stderr
    backup = trace.index(f"backup|{CURRENT_TAG}")
    migrate = trace.index(f"compose|{CANDIDATE_TAG}|--profile tools run --rm --no-deps migrate")
    start = trace.index(f"compose|{CANDIDATE_TAG}|{APP_START}")
    assert backup < migrate < start
    assert not any("|up --detach --wait postgres minio" in line for line in trace)
    assert not any("|pull postgres" in line or "minio-init minio-init" in line for line in trace)


@pytest.mark.parametrize("data", ["changed", "stopped", "absent"])
def test_existing_data_service_change_or_loss_refuses_before_mutations(
    tmp_path: Path, data: str
) -> None:
    result, trace = _run_control(tmp_path, data=data)
    assert result.returncode != 0
    assert not any(line.startswith("backup|") or "|pull " in line for line in trace)
    assert not _application_starts(trace)


@pytest.mark.parametrize("failure", ["backup", "migration"])
def test_failure_before_application_replacement_does_not_restart_old_services(
    tmp_path: Path, failure: str
) -> None:
    result, trace = _run_control(tmp_path, failure=failure)
    assert result.returncode != 0
    assert f"backup|{CURRENT_TAG}" in trace
    assert not _application_starts(trace)
    assert not any(line.startswith("state|") for line in trace)
    if failure == "backup":
        assert not any("--no-deps migrate" in line for line in trace)


def test_failed_application_replacement_rolls_back_images_without_dependencies(
    tmp_path: Path,
) -> None:
    result, trace = _run_control(tmp_path, failure="application")
    assert result.returncode == 24
    assert _application_starts(trace) == [
        f"compose|{CANDIDATE_TAG}|{APP_START}",
        f"compose|{CURRENT_TAG}|{APP_START}",
    ]
    assert not any(line.startswith("state|") for line in trace)


def test_empty_first_install_bootstraps_data_before_initial_backup(tmp_path: Path) -> None:
    result, trace = _run_control(tmp_path, current="", data="absent")
    assert result.returncode == 0, result.stderr
    assert trace.index(f"compose|{CANDIDATE_TAG}|up --detach --wait postgres minio") < trace.index(
        f"backup|{CANDIDATE_TAG}"
    )


@pytest.mark.parametrize("data", ["running", "orphan-volume", "unlabeled-volume"])
def test_unrecorded_existing_data_is_never_bootstrapped_over(tmp_path: Path, data: str) -> None:
    # An orphan volume has no container, so let the double expose only the volume.
    result, trace = _run_control(tmp_path, current="", data=data)
    assert result.returncode != 0
    assert not any("|pull " in line or "|up " in line for line in trace)
    assert not any(line.startswith("backup|") for line in trace)


def test_manual_rollback_backs_up_current_tag_and_never_reconciles_data(tmp_path: Path) -> None:
    result, trace = _run_control(tmp_path, script="rollback.sh")
    assert result.returncode == 0, result.stderr
    starts = _application_starts(trace)
    assert starts == [f"compose|{CANDIDATE_TAG}|{APP_START}"]
    assert trace.index(f"backup|{CURRENT_TAG}") < trace.index(starts[0])
    assert not any(" migrate" in line or "|pull postgres" in line for line in trace)
