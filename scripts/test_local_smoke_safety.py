"""Run the real smoke harness against Linux command doubles, never Docker.

The tests need native Bash/filesystem semantics. Every mutable path is a newly
created fixture and all Docker/curl operations are intercepted before execution.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SOURCE = Path(__file__).parent / "production" / "local-smoke-test.sh"
pytestmark = pytest.mark.skipif(os.name == "nt", reason="Linux Bash semantics required")
OWNED_IDS = ["a" * 64, "b" * 64]

DOCKER_DOUBLE = r"""
import json, os, pathlib, sys
args = sys.argv[1:]
if args[0] != "context":
    assert "DOCKER_CONTEXT" not in os.environ
    assert os.environ["DOCKER_HOST"].startswith(("unix:///", "npipe:////./pipe/"))
with open(os.environ["FIXTURE_TRACE"], "a") as stream:
    stream.write(json.dumps(["docker", *args]) + "\n")
fault = os.environ.get("FIXTURE_FAULT", "")
started = pathlib.Path(os.environ["FIXTURE_STARTED"])
if args[:2] == ["context", "show"]:
    print("desktop-linux")
elif args[:2] == ["context", "inspect"]:
    if fault == "context_query": sys.exit(18)
    print(os.environ.get("FIXTURE_ENDPOINT", "unix:///var/run/docker.sock"))
elif args[0] in {"container", "volume", "network"} and args[1] == "ls":
    if fault == "collision_query": sys.exit(19)
    selector = args[args.index("--filter") + 1]
    if "--no-trunc" in args:
        if fault == "cleanup_query": sys.exit(29)
        if started.exists():
            print("not-a-container-id" if fault == "invalid_id" else "a" * 64)
            print("invalid-second-id" if fault == "invalid_second_id" else "b" * 64)
    elif selector.startswith("label=") and fault == args[0] + "_collision":
        print("existing-resource")
    elif selector.startswith("name=") and fault == "unlabelled_" + args[0]:
        print(selector.removeprefix("name="))
elif args[0] == "inspect":
    if fault == "cleanup_inspect": sys.exit(28)
    print("fleet-manager" if fault == "wrong_project" else started.read_text())
elif args[0] == "stop":
    if fault == "stop": sys.exit(27)
elif args[:2] == ["image", "inspect"]:
    if fault == "image": sys.exit(25)
elif args[0] == "compose":
    project = args[args.index("--project-name") + 1]
    env_path = pathlib.Path(args[args.index("--env-file") + 1])
    entries = dict(line.split("=", 1) for line in env_path.read_text().splitlines())
    # Assert process variables override any ambient production settings safely,
    # without recording or printing configuration/credential values.
    if any(os.environ.get(key) != value for key, value in entries.items()):
        sys.exit(77)
    if os.environ.get("FLEET_COMPOSE_PROJECT_NAME") != project: sys.exit(78)
    command = args[args.index("--file") + 2:]
    if command[:1] == ["--profile"]: command = command[2:]
    if command[0] == "up":
        started.write_text(project)
        (env_path.parent / "preserved-evidence.txt").write_text("synthetic evidence")
        if fault == "startup": sys.exit(23)
    elif command[0] == "ps":
        if "--status" in command:
            if fault == "stats_query": sys.exit(24)
            if fault != "empty_stats": print("a" * 64 + "\n" + "b" * 64)
        else: print("a" * 64)
    elif command[0] == "exec" and "SELECT count" in command[-1]: print("1")
    elif command[0] == "exec" and command[-1].startswith("du -sk"): print("123 /fixture")
elif args[0] in {"port", "stats"}:
    pass
else:
    sys.exit("Unexpected Docker command in isolated fixture")
"""

CURL_DOUBLE = r"""
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FIXTURE_TRACE"], "a") as stream:
    stream.write(json.dumps(["curl", *args]) + "\n")
assert args[args.index("--noproxy") + 1] == "*"
assert "--connect-timeout" in args and "--max-time" in args
url = args[-1]
if url.endswith("/ready"):
    if os.environ.get("FIXTURE_FAULT") == "readiness": sys.exit(22)
    print('{"status":"ready"}')
elif url.endswith("/privacy"): print("Privacy")
elif url.endswith("/health"): print('{"status":"ok"}')
else: print("404")
"""


def executable(path: Path, content: str, *, python: bool = False) -> None:
    path.write_text(
        (f"#!{sys.executable}\n" if python else "#!/usr/bin/env bash\n") + content,
        encoding="utf-8",
    )
    path.chmod(0o755)


@pytest.fixture
def layout(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    repo = tmp_path / "synthetic checkout with spaces"
    production = repo / "scripts" / "production"
    production.mkdir(parents=True)
    shutil.copyfile(SOURCE, production / SOURCE.name)
    commands = tmp_path / "commands"
    commands.mkdir()
    executable(commands / "docker", DOCKER_DOUBLE, python=True)
    executable(commands / "curl", CURL_DOUBLE, python=True)
    executable(commands / "seq", "printf '1\\n'\n")
    executable(commands / "sleep", "exit 0\n")
    (production / "common.sh").write_text("# synthetic common\n", encoding="utf-8")
    (production / "data-service-guard.sh").write_text(
        "require_unchanged_data_services() { :; }\n", encoding="utf-8"
    )
    executable(
        production / "backup.sh",
        'mkdir -p "$FLEET_PRODUCTION_STATE_DIR" "$FLEET_BACKUP_DIR/generation/evidence"\n'
        'printf fixture >"$FLEET_BACKUP_DIR/generation/evidence/photo.txt"\n'
        'printf "BACKUP_PATH=%s/generation\\n" "$FLEET_BACKUP_DIR"\n',
    )
    executable(production / "verify-backup.sh", 'test -f "$1/evidence/photo.txt"\n')
    executable(production / "healthcheck.sh", "exit 0\n")
    environment = os.environ.copy()
    # Doubles use only the Linux standard library; do not repeatedly search the
    # optional read-only pytest dependency mount when launching each command.
    for key in ("DOCKER_CONTEXT", "DOCKER_HOST", "PYTHONPATH"):
        environment.pop(key, None)
    environment.update(
        PATH=f"{commands}:{environment['PATH']}",
        FIXTURE_TRACE=str(tmp_path / "trace.jsonl"),
        FIXTURE_STARTED=str(tmp_path / "started"),
        FLEET_IMAGE_REGISTRY="ambient-not-the-smoke-registry",
        FLEET_IMAGE_TAG="f" * 40,
        FLEET_DATABASE_URL="ambient-not-a-database",
        FLEET_S3_ENDPOINT_URL="ambient-not-storage",
        FLEET_AUTH_MODE="ambient-not-company-pin",
        FLEET_LEAD_DIR="ambient-not-a-lead-directory",
        FLEET_BACKUP_DIR="ambient-not-a-backup-directory",
        FLEET_COMPOSE_PROJECT_NAME="fleet-manager",
        FLEET_HTTP_PORT="0.0.0.0:80",
        FLEET_HTTPS_PORT="0.0.0.0:443",
        HTTPS_PROXY="http://proxy.invalid:1",
    )
    return repo, environment


def run_smoke(
    layout: tuple[Path, dict[str, str]], **overrides: str
) -> tuple[subprocess.CompletedProcess[str], list[list[str]], dict[str, str]]:
    repo, environment = layout
    environment = {**environment, **overrides}
    result = subprocess.run(  # noqa: S603 -- isolated harness and command doubles only.
        ["bash", str(repo / "scripts/production" / SOURCE.name), "--reuse-images"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    trace_path = Path(environment["FIXTURE_TRACE"])
    trace = (
        [json.loads(line) for line in trace_path.read_text().splitlines()]
        if trace_path.exists()
        else []
    )
    report = dict(
        line.split("=", 1)
        for line in result.stdout.splitlines()
        if line.startswith("SMOKE_")
    )
    return result, trace, report


def test_success_preserves_artifacts_and_stops_only_owned_containers(
    layout: tuple[Path, dict[str, str]],
) -> None:
    result, trace, report = run_smoke(layout)
    assert result.returncode == 0, result.stderr
    assert "PRODUCTION_SMOKE=PASS" in result.stdout
    assert report["SMOKE_STOP_STATUS"] == "PASS"
    assert [call for call in trace if call[:2] == ["docker", "stop"]] == [
        ["docker", "stop", "--time", "30", "--", *OWNED_IDS]
    ]
    artifacts = Path(report["SMOKE_ARTIFACT_ROOT"])
    assert artifacts.is_dir() and artifacts.parent == layout[0]
    assert (artifacts / "preserved-evidence.txt").read_text() == "synthetic evidence"
    assert (artifacts / "backups/generation/evidence/photo.txt").is_file()
    env_file = Path(report["SMOKE_ENV_FILE"])
    assert env_file.is_file() and env_file.stat().st_mode & 0o777 == 0o600
    values = dict(line.split("=", 1) for line in env_file.read_text().splitlines())
    assert values["FLEET_HTTP_PORT"] == "127.0.0.1:18080"
    assert values["FLEET_HTTPS_PORT"] == "127.0.0.1:18443"
    assert values["FLEET_AUTH_MODE"] == "company_pin"
    assert "smoke-database-password" not in result.stdout + result.stderr
    assert "smoke-minio-root-password" not in result.stdout + result.stderr
    assert "SMOKE_MANUAL_REVIEW" in report


def test_project_comes_from_unique_mktemp_suffix_not_pid(
    layout: tuple[Path, dict[str, str]],
) -> None:
    first, _, a = run_smoke(layout)
    second, _, b = run_smoke(layout)
    assert first.returncode == second.returncode == 0
    assert a["SMOKE_PROJECT"] != b["SMOKE_PROJECT"]
    for report in (a, b):
        suffix = Path(report["SMOKE_ARTIFACT_ROOT"]).name.removeprefix(
            ".production-smoke."
        )
        assert report["SMOKE_PROJECT"] == f"fleet-ai-smoke-{suffix.lower()}"
        assert re.fullmatch(r"[a-zA-Z0-9]{6}", suffix)


@pytest.mark.parametrize(
    "fault", ["image", "startup", "readiness", "empty_stats", "stats_query"]
)
def test_failure_retains_environment_and_any_created_evidence(
    layout: tuple[Path, dict[str, str]], fault: str
) -> None:
    result, trace, report = run_smoke(layout, FIXTURE_FAULT=fault)
    assert result.returncode != 0
    artifacts = Path(report["SMOKE_ARTIFACT_ROOT"])
    assert artifacts.is_dir() and Path(report["SMOKE_ENV_FILE"]).is_file()
    if fault != "image":
        assert (artifacts / "preserved-evidence.txt").is_file()
        assert any(call[:2] == ["docker", "stop"] for call in trace)
    assert not any(call == ["docker", "stats", "--no-stream"] for call in trace)


@pytest.mark.parametrize(
    "fault",
    [
        "container_collision",
        "volume_collision",
        "network_collision",
        "unlabelled_volume",
        "unlabelled_network",
        "collision_query",
    ],
)
def test_collision_or_inventory_failure_never_starts_or_stops_resources(
    layout: tuple[Path, dict[str, str]], fault: str
) -> None:
    result, trace, report = run_smoke(layout, FIXTURE_FAULT=fault)
    assert result.returncode != 0
    assert report["SMOKE_STOP_STATUS"] == "NOT_STARTED"
    assert Path(report["SMOKE_ARTIFACT_ROOT"]).is_dir()
    assert not any(call[1] in {"compose", "stop", "build"} for call in trace)


@pytest.mark.parametrize(
    "fault",
    [
        "cleanup_query",
        "cleanup_inspect",
        "wrong_project",
        "invalid_id",
        "invalid_second_id",
    ],
)
def test_uncertain_container_ownership_fails_closed_without_any_stop(
    layout: tuple[Path, dict[str, str]], fault: str
) -> None:
    result, trace, report = run_smoke(layout, FIXTURE_FAULT=fault)
    assert result.returncode != 0
    assert report["SMOKE_STOP_STATUS"].startswith("FAILED_")
    assert Path(report["SMOKE_ARTIFACT_ROOT"]).is_dir()
    assert not any(call[:2] == ["docker", "stop"] for call in trace)


def test_stop_failure_preserves_artifacts_and_returns_failure(
    layout: tuple[Path, dict[str, str]],
) -> None:
    result, _, report = run_smoke(layout, FIXTURE_FAULT="stop")
    assert result.returncode != 0
    assert report["SMOKE_STOP_STATUS"] == "FAILED_STOP"
    assert Path(report["SMOKE_ENV_FILE"]).is_file()


@pytest.mark.parametrize(
    "endpoint",
    [
        "ssh://production.invalid",
        "tcp://127.0.0.1:2375",
        "tcp://production.invalid:2376",
        "",
    ],
)
def test_remote_or_unproven_daemon_refused_before_artifacts(
    layout: tuple[Path, dict[str, str]], endpoint: str
) -> None:
    result, trace, report = run_smoke(layout, FIXTURE_ENDPOINT=endpoint)
    assert result.returncode != 0 and report == {}
    assert not list(layout[0].glob(".production-smoke.*"))
    assert all(call[:2] == ["docker", "context"] for call in trace)


def test_selected_context_takes_priority_over_host_environment(
    layout: tuple[Path, dict[str, str]],
) -> None:
    result, trace, _ = run_smoke(
        layout, DOCKER_CONTEXT="explicit-local", DOCKER_HOST="ssh://ignored.invalid"
    )
    assert result.returncode == 0, result.stderr
    assert trace[0] == [
        "docker",
        "context",
        "inspect",
        "--format",
        "{{.Endpoints.docker.Host}}",
        "explicit-local",
    ]


@pytest.mark.parametrize(
    "host", ["unix:///var/run/docker.sock", "npipe:////./pipe/dockerDesktopLinuxEngine"]
)
def test_explicit_local_host_without_context_is_accepted(
    layout: tuple[Path, dict[str, str]], host: str
) -> None:
    result, trace, _ = run_smoke(layout, DOCKER_HOST=host)
    assert result.returncode == 0, result.stderr
    assert not any(call[:2] == ["docker", "context"] for call in trace)


def test_context_query_error_fails_before_artifacts(
    layout: tuple[Path, dict[str, str]],
) -> None:
    result, _, report = run_smoke(layout, FIXTURE_FAULT="context_query")
    assert result.returncode != 0 and report == {}
    assert not list(layout[0].glob(".production-smoke.*"))


@pytest.mark.parametrize(
    "http,https",
    [
        ("0", "18443"),
        ("65536", "18443"),
        ("0.0.0.0:80", "18443"),
        ("18080", "18080"),
        ("08080", "8080"),
    ],
)
def test_invalid_or_conflicting_ports_refused_before_docker(
    layout: tuple[Path, dict[str, str]], http: str, https: str
) -> None:
    result, trace, report = run_smoke(
        layout, FLEET_SMOKE_HTTP_PORT=http, FLEET_SMOKE_HTTPS_PORT=https
    )
    assert result.returncode != 0 and trace == [] and report == {}


def test_harness_has_no_automatic_destructive_cleanup() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert not re.search(
        r"\b(?:down|prune)\b",
        "\n".join(
            line
            for line in source.splitlines()
            if not line.startswith("#") and "printf" not in line
        ),
    )
    assert not re.search(r"\brm\s+-[a-zA-Z]*[rf]", source)
    assert "volume rm" not in source and "--remove-orphans" not in source
    assert 'SMOKE_PROJECT="fleet-ai-smoke-$$"' not in source
    assert 'docker stats --no-stream "${running_containers[@]}"' in source
