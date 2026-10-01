"""Local-only Fleet Manager server control and backup helper.

The remote-test architecture uses Compose only for PostgreSQL. FastAPI is an
owned native process bound to 127.0.0.1, and evidence remains private in a
configured local filesystem root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launch import (  # noqa: E402
    ProcessInfo,
    default_http_probe,
    default_process_info,
    find_listening_pid,
    is_expected_api_health,
    locate_docker_desktop,
    parse_compose_health,
    parse_dotenv,
    port_is_open,
)


API_PORT = 8000
API_HEALTH_URL = "http://127.0.0.1:8000/health"
API_READY_URL = "http://127.0.0.1:8000/ready"
DOCKER_TIMEOUT_SECONDS = 120
INFRA_TIMEOUT_SECONDS = 90
API_TIMEOUT_SECONDS = 60
RUNTIME_DIR = ROOT / ".runtime" / "server"
LOG_DIR = ROOT / ".runtime" / "logs"
STATE_FILE = RUNTIME_DIR / "api.json"
API_LOG = LOG_DIR / "server-api.log"
API_PROJECT = ROOT / "services" / "api"
PROJECT_PYTHON = API_PROJECT / ".venv" / "Scripts" / "python.exe"
COMPOSE_FILE = ROOT / "docker-compose.yml"
ENV_FILE = ROOT / ".env"
BACKUP_ROOT = Path(r"F:\FleetManagerBackups")
EVIDENCE_BACKUP_ROOT = Path(r"C:\FleetManagerEvidenceBackup")
EVIDENCE_MANIFEST_NAME = "evidence-backup-manifest.json"


class ServerError(RuntimeError):
    """Expected server-control failure with an operator-safe message."""


def run_capture(
    args: Sequence[str],
    *,
    cwd: Path = ROOT,
    env: Mapping[str, str] | None = None,
    timeout: int = 30,
    text: bool = True,
) -> subprocess.CompletedProcess[Any]:
    try:
        return subprocess.run(
            list(args),
            cwd=str(cwd),
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=text,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ServerError(f"Could not run {Path(args[0]).name}: {error}") from error


def checked(
    args: Sequence[str],
    *,
    label: str,
    cwd: Path = ROOT,
    env: Mapping[str, str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    result = run_capture(args, cwd=cwd, env=env, timeout=timeout)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        safe_tail = "\n".join(detail[-12:])
        raise ServerError(f"{label} failed.\n{safe_tail}" if safe_tail else f"{label} failed.")
    return result


def load_server_environment() -> dict[str, str]:
    if not ENV_FILE.is_file():
        raise ServerError("Server configuration is missing: .env")
    values = parse_dotenv(ENV_FILE.read_text(encoding="utf-8"))
    required = (
        "FLEET_DATABASE_URL",
        "FLEET_JWT_SIGNING_KEY",
        "FLEET_OBJECT_STORAGE_PROVIDER",
        "FLEET_FILESYSTEM_STORAGE_ROOT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    )
    missing = [name for name in required if not values.get(name, "").strip()]
    if missing:
        raise ServerError("Server configuration is incomplete: " + ", ".join(missing))
    if values.get("FLEET_ENVIRONMENT", "").lower() in {"production", "prod"}:
        raise ServerError("This local server controller refuses production configuration.")
    if values.get("FLEET_OBJECT_STORAGE_PROVIDER", "").lower() != "filesystem":
        raise ServerError("Evidence storage must be configured as filesystem for this server.")
    effective = dict(os.environ)
    for key, value in values.items():
        effective.setdefault(key, value)
    return effective


def require_runtime() -> tuple[str, dict[str, str]]:
    if not COMPOSE_FILE.is_file():
        raise ServerError("docker-compose.yml is missing.")
    if not PROJECT_PYTHON.is_file():
        raise ServerError(f"Backend environment is missing: {PROJECT_PYTHON}")
    docker = shutil.which("docker")
    if not docker:
        raise ServerError("Docker CLI is not installed or not available on PATH.")
    return docker, load_server_environment()


def docker_ready(docker: str) -> bool:
    result = run_capture(
        [docker, "version", "--format", "{{.Server.Version}}"], timeout=15
    )
    return result.returncode == 0 and bool((result.stdout or "").strip())


def ensure_docker(docker: str, env: Mapping[str, str]) -> None:
    if docker_ready(docker):
        return
    desktop = locate_docker_desktop()
    if desktop is None:
        raise ServerError("Docker engine is offline and Docker Desktop was not found.")
    try:
        subprocess.Popen(
            [str(desktop)],
            cwd=str(ROOT),
            env=dict(env),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
        )
    except OSError as error:
        raise ServerError(f"Docker Desktop could not be started: {error}") from error
    deadline = time.monotonic() + DOCKER_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if docker_ready(docker):
            return
        time.sleep(2)
    raise ServerError("Docker engine did not become ready within 120 seconds.")


def evidence_root(env: Mapping[str, str]) -> Path:
    configured = env.get("FLEET_FILESYSTEM_STORAGE_ROOT", "").strip()
    if not configured:
        raise ServerError("FLEET_FILESYSTEM_STORAGE_ROOT is not configured.")
    root = Path(configured)
    if not root.is_absolute() or len(root.parts) < 3:
        raise ServerError("Evidence storage root must be a specific absolute path.")
    return root.resolve(strict=False)


def ensure_evidence_root(env: Mapping[str, str]) -> Path:
    root = evidence_root(env)
    probe: Path | None = None
    try:
        root.mkdir(parents=True, exist_ok=True)
        if not root.is_dir():
            raise ServerError("Evidence storage root is not a directory.")
        descriptor, raw_probe = tempfile.mkstemp(prefix=".fleet-ready-", dir=root)
        probe = Path(raw_probe)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(b"fleet-storage-ready")
            handle.flush()
            os.fsync(handle.fileno())
        if probe.read_bytes() != b"fleet-storage-ready":
            raise ServerError("Evidence storage readiness probe failed.")
    except OSError as exc:
        raise ServerError(f"Evidence storage is unavailable: {exc}") from exc
    finally:
        if probe is not None:
            probe.unlink(missing_ok=True)
    return root


def evidence_store_available(env: Mapping[str, str] | None) -> bool:
    if env is None:
        return False
    try:
        root = evidence_root(env)
        return root.is_dir() and os.access(root, os.R_OK | os.W_OK)
    except (OSError, ServerError):
        return False


def compose_health(docker: str, env: Mapping[str, str]) -> dict[str, str]:
    result = run_capture(
        [
            docker,
            "compose",
            "ps",
            "--format",
            "{{.Service}}\t{{.Health}}\t{{.State}}",
            "postgres",
        ],
        env=env,
        timeout=20,
    )
    return parse_compose_health(result.stdout or "") if result.returncode == 0 else {}


def ensure_infrastructure(docker: str, env: Mapping[str, str]) -> None:
    checked(
        [docker, "compose", "up", "-d", "postgres"],
        label="PostgreSQL startup",
        env=env,
        timeout=180,
    )
    deadline = time.monotonic() + INFRA_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        status = compose_health(docker, env)
        if status.get("postgres") == "healthy":
            return
        time.sleep(2)
    status = compose_health(docker, env)
    raise ServerError(
        "Infrastructure did not become healthy: "
        f"PostgreSQL={status.get('postgres', 'missing')}"
    )


def read_state() -> dict[str, Any]:
    if not STATE_FILE.is_file():
        return {}
    try:
        value = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def save_state(pid: int, command: Sequence[str]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(
            {
                "pid": pid,
                "command": list(command),
                "cwd": str(ROOT),
                "owned": True,
                "started_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def safe_process_info(pid: int | None) -> ProcessInfo | None:
    if not isinstance(pid, int) or pid <= 0:
        return None
    try:
        return default_process_info(pid)
    except Exception:
        return None


def is_owned_api(info: ProcessInfo | None, state: Mapping[str, Any]) -> bool:
    if info is None or not state.get("owned") or info.pid != state.get("pid"):
        return False
    normalized = " ".join(
        (info.command_line or info.executable_path).casefold().replace("/", "\\").split()
    )
    root = str(ROOT).casefold().replace("/", "\\")
    project_python = str(PROJECT_PYTHON).casefold().replace("/", "\\")
    executable = (info.executable_path or "").casefold().replace("/", "\\")
    return (
        root in normalized
        and "uvicorn" in normalized
        and "fleet_api.main:app" in normalized
        and "--host 127.0.0.1" in normalized
        and (executable == project_python or project_python in normalized)
    )


def process_parent_pid(pid: int) -> int | None:
    powershell = shutil.which("powershell") or shutil.which("powershell.exe")
    if not powershell:
        return None
    result = run_capture(
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-Command",
            f"(Get-CimInstance Win32_Process -Filter \"ProcessId = {pid}\").ParentProcessId",
        ],
        timeout=5,
    )
    try:
        return int((result.stdout or "").strip()) if result.returncode == 0 else None
    except ValueError:
        return None


def is_owned_listener(state: Mapping[str, Any], parent: ProcessInfo | None) -> bool:
    if not is_owned_api(parent, state):
        return False
    listener_pid = find_listening_pid(API_PORT)
    if listener_pid == state.get("pid"):
        return True
    listener = safe_process_info(listener_pid)
    if listener is None or process_parent_pid(listener.pid) != state.get("pid"):
        return False
    normalized = " ".join(
        (listener.command_line or listener.executable_path)
        .casefold()
        .replace("/", "\\")
        .split()
    )
    return (
        "uvicorn" in normalized
        and "fleet_api.main:app" in normalized
        and "--host 127.0.0.1" in normalized
        and "--port 8000" in normalized
    )


def api_health_ok() -> bool:
    return is_expected_api_health(default_http_probe(API_HEALTH_URL, 3.0))


def api_ready_ok() -> bool:
    probe = default_http_probe(API_READY_URL, 3.0)
    return probe is not None and probe.status == 200


def recorded_api() -> tuple[dict[str, Any], ProcessInfo | None]:
    state = read_state()
    pid = state.get("pid")
    return state, safe_process_info(pid if isinstance(pid, int) else None)


def start_api(env: Mapping[str, str]) -> str:
    state, info = recorded_api()
    if api_health_ok() and api_ready_ok():
        if is_owned_listener(state, info):
            return "ALREADY RUNNING"
        listener = safe_process_info(find_listening_pid(API_PORT))
        raise ServerError(
            "Port 8000 already has a healthy but unmanaged service. "
            f"PID={listener.pid if listener else 'unknown'}."
        )
    if port_is_open(API_PORT, "127.0.0.1"):
        listener = safe_process_info(find_listening_pid(API_PORT))
        raise ServerError(
            "Port 8000 is occupied by another process. "
            f"PID={listener.pid if listener else 'unknown'}."
        )
    if STATE_FILE.exists() and not is_owned_api(info, state):
        STATE_FILE.unlink()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        str(PROJECT_PYTHON),
        "-m",
        "uvicorn",
        "fleet_api.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(API_PORT),
    ]
    with API_LOG.open("a", encoding="utf-8") as log_file:
        log_file.write(f"\n=== server start {datetime.now(UTC).isoformat()} ===\n")
        log_file.flush()
        process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            env=dict(env),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=(
                getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            ),
        )
    save_state(int(process.pid), command)
    deadline = time.monotonic() + API_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ServerError(f"API exited during startup. Review {API_LOG}")
        if api_health_ok() and api_ready_ok():
            listener_pid = find_listening_pid(API_PORT)
            state, parent = recorded_api()
            if not listener_pid or not is_owned_listener(state, parent):
                raise ServerError("API listener ownership could not be verified.")
            return "STARTED"
        time.sleep(1)
    raise ServerError(f"API did not become ready within 60 seconds. Review {API_LOG}")


def component_status(docker: str | None, env: Mapping[str, str] | None) -> dict[str, str]:
    docker_ok = bool(docker and docker_ready(docker))
    compose = compose_health(docker, env) if docker_ok and docker and env else {}
    state, info = recorded_api()
    owned = is_owned_listener(state, info)
    listener = port_is_open(API_PORT, "127.0.0.1")
    health = api_health_ok()
    ready = api_ready_ok()
    api_state = "OK" if owned and listener and health else "OFFLINE"
    if listener and not owned:
        api_state = "UNMANAGED"
    return {
        "docker": "OK" if docker_ok else "OFFLINE",
        "postgres": "OK" if compose.get("postgres") == "healthy" else "OFFLINE",
        "evidence": "OK" if evidence_store_available(env) else "OFFLINE",
        "api": api_state,
        "health": "OK" if health else "OFFLINE",
        "ready": "OK" if ready else "OFFLINE",
    }


def print_start_status(status: Mapping[str, str], start_result: str | None = None) -> None:
    online = all(status[key] == "OK" for key in ("postgres", "evidence", "api", "ready"))
    print("\nFLEET MANAGER SERVER\n")
    print(f"PostgreSQL      {'RUNNING' if status['postgres'] == 'OK' else 'FAILED'}")
    print(f"Evidence Store  {'RUNNING' if status['evidence'] == 'OK' else 'FAILED'}")
    print(f"API             {'RUNNING' if status['api'] == 'OK' else status['api']}")
    print(f"Ready           {'YES' if status['ready'] == 'OK' else 'NO'}")
    if start_result == "ALREADY RUNNING":
        print("\nALREADY RUNNING")
    print("\nSERVER IS ONLINE" if online else "\nSERVER START FAILED")


def print_check_status(status: Mapping[str, str]) -> None:
    online = all(value == "OK" for value in status.values())
    print("\nFLEET MANAGER SERVER STATUS\n")
    print(f"Docker          {status['docker']}")
    print(f"PostgreSQL      {status['postgres']}")
    print(f"Evidence Store  {status['evidence']}")
    print(f"FastAPI         {status['api']}")
    print(f"/health         {status['health']}")
    print(f"/ready          {status['ready']}")
    print(f"\nOVERALL         {'ONLINE' if online else 'OFFLINE'}")


def start_server() -> int:
    docker: str | None = None
    env: dict[str, str] | None = None
    result: str | None = None
    try:
        docker, env = require_runtime()
        ensure_docker(docker, env)
        ensure_infrastructure(docker, env)
        ensure_evidence_root(env)
        result = start_api(env)
    except ServerError as error:
        print(f"\n[FAILED] {error}")
        print_start_status(component_status(docker, env), result)
        return 1
    print_start_status(component_status(docker, env), result)
    return 0


def check_server() -> int:
    try:
        docker, env = require_runtime()
    except ServerError as error:
        print(f"\n[FAILED] {error}")
        print_check_status(component_status(None, None))
        return 1
    status = component_status(docker, env)
    print_check_status(status)
    return 0 if all(value == "OK" for value in status.values()) else 1


def stop_api() -> int:
    state, info = recorded_api()
    if not state:
        print("Fleet Manager API was not started by the server controller.")
        return 0
    if not is_owned_api(info, state):
        if not port_is_open(API_PORT, "127.0.0.1"):
            STATE_FILE.unlink(missing_ok=True)
            print("Removed stale Fleet Manager API state; no process was stopped.")
            return 0
        raise ServerError("Refusing to stop API: recorded process ownership could not be verified.")
    assert info is not None
    result = run_capture(["taskkill", "/PID", str(info.pid), "/T"], timeout=20)
    taskkill_detail = f"{result.stdout or ''}\n{result.stderr or ''}".lower()
    expected_force_message = (
        "can only be terminated forcefully" in taskkill_detail
        or "child processes of this process were still running" in taskkill_detail
    )
    if (
        result.returncode != 0
        and "not found" not in taskkill_detail
        and not expected_force_message
    ):
        raise ServerError("Fleet Manager API could not be stopped safely.")
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and port_is_open(API_PORT, "127.0.0.1"):
        time.sleep(0.5)
    if port_is_open(API_PORT, "127.0.0.1"):
        current = safe_process_info(info.pid)
        if not is_owned_api(current, state):
            raise ServerError("Refusing forced stop: process identity changed.")
        forced = run_capture(["taskkill", "/PID", str(info.pid), "/T", "/F"], timeout=20)
        if forced.returncode != 0:
            raise ServerError("Fleet Manager API did not stop.")
    STATE_FILE.unlink(missing_ok=True)
    print("Stopped: Fleet Manager-owned API")
    return 0


def stop_server() -> int:
    docker, env = require_runtime()
    stop_api()
    if not docker_ready(docker):
        raise ServerError("Docker engine is offline; PostgreSQL could not be stopped.")
    checked(
        [docker, "compose", "stop", "postgres"],
        label="Fleet Manager PostgreSQL stop",
        env=env,
    )
    print("Stopped: Fleet Manager PostgreSQL container")
    print("Evidence files were left intact.")
    return 0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temporary = tempfile.mkstemp(prefix=".fleet-manifest-", dir=path.parent)
    temporary = Path(raw_temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def safe_snapshot_path(snapshot: Path, relative_text: str) -> Path:
    if (
        not relative_text
        or "\\" in relative_text
        or relative_text.startswith("/")
        or any(
            part in {"", ".", ".."} or ":" in part
            for part in relative_text.split("/")
        )
    ):
        raise ServerError("Evidence backup manifest contains an unsafe path.")
    candidate = snapshot.joinpath(*relative_text.split("/")).resolve(strict=False)
    try:
        candidate.relative_to(snapshot.resolve(strict=False))
    except ValueError as exc:
        raise ServerError("Evidence backup path escapes its snapshot.") from exc
    return candidate


def verify_evidence_snapshot(snapshot: Path) -> dict[str, Any]:
    manifest_path = snapshot / EVIDENCE_MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ServerError("Evidence backup manifest is missing or invalid.") from exc
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(manifest, dict) or manifest.get("format_version") != 1 or not isinstance(files, list):
        raise ServerError("Evidence backup manifest format is invalid.")
    expected_paths: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise ServerError("Evidence backup manifest entry is invalid.")
        relative = entry.get("path")
        expected_size = entry.get("size")
        expected_hash = entry.get("sha256")
        if (
            not isinstance(relative, str)
            or not isinstance(expected_size, int)
            or not isinstance(expected_hash, str)
        ):
            raise ServerError("Evidence backup manifest entry is incomplete.")
        candidate = safe_snapshot_path(snapshot, relative)
        if candidate.is_symlink() or not candidate.is_file():
            raise ServerError(f"Evidence backup file is unavailable: {relative}")
        if candidate.stat().st_size != expected_size or sha256(candidate) != expected_hash:
            raise ServerError(f"Evidence backup hash verification failed: {relative}")
        expected_paths.add(relative)
    actual_paths = {
        path.relative_to(snapshot).as_posix()
        for path in snapshot.rglob("*")
        if path.is_file() and path.name != EVIDENCE_MANIFEST_NAME
    }
    if actual_paths != expected_paths:
        raise ServerError("Evidence backup contents do not match the manifest.")
    return manifest


def create_evidence_snapshot(source_root: Path, timestamp: str) -> tuple[Path, Path, dict[str, Any]]:
    try:
        canonical_source = source_root.resolve(strict=True)
    except OSError as exc:
        raise ServerError("Evidence storage root is unavailable for backup.") from exc
    if not canonical_source.is_dir():
        raise ServerError("Evidence storage root is not a directory.")
    EVIDENCE_BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    final = EVIDENCE_BACKUP_ROOT / timestamp
    if final.exists():
        raise ServerError(f"Evidence backup already exists: {final}")
    staging = EVIDENCE_BACKUP_ROOT / f".{timestamp}.partial-{uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)
    try:
        entries: list[dict[str, Any]] = []
        for source in sorted(canonical_source.rglob("*"), key=lambda item: item.as_posix()):
            if source.is_symlink():
                raise ServerError("Evidence backup refuses symbolic links or junction files.")
            if not source.is_file():
                continue
            resolved_source = source.resolve(strict=True)
            try:
                relative = resolved_source.relative_to(canonical_source)
            except ValueError as exc:
                raise ServerError("Evidence file escapes the configured storage root.") from exc
            relative_text = relative.as_posix()
            if relative_text == EVIDENCE_MANIFEST_NAME:
                raise ServerError("Evidence root contains the reserved backup manifest name.")
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(resolved_source, destination)
            source_size = resolved_source.stat().st_size
            source_hash = sha256(resolved_source)
            if destination.stat().st_size != source_size or sha256(destination) != source_hash:
                raise ServerError(f"Evidence backup copy verification failed: {relative_text}")
            entries.append(
                {"path": relative_text, "size": source_size, "sha256": source_hash}
            )
        manifest: dict[str, Any] = {
            "format_version": 1,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "source": str(canonical_source),
            "files": entries,
            "file_count": len(entries),
            "total_bytes": sum(int(entry["size"]) for entry in entries),
            "secrets_included": False,
        }
        atomic_write_json(staging / EVIDENCE_MANIFEST_NAME, manifest)
        verify_evidence_snapshot(staging)
        os.replace(staging, final)
        verified = verify_evidence_snapshot(final)
        return final, final / EVIDENCE_MANIFEST_NAME, verified
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise


def safe_backup_manifest(
    *,
    timestamp: str,
    database_dump: Path,
    evidence_snapshot: Path,
    evidence_manifest: Path,
    evidence_details: Mapping[str, Any],
    docker: str,
    env: Mapping[str, str],
) -> dict[str, Any]:
    head = checked(["git", "rev-parse", "HEAD"], label="Git revision check").stdout.strip()
    current = checked(
        [str(PROJECT_PYTHON), "-m", "alembic", "current"],
        label="Alembic revision check",
        cwd=API_PROJECT,
        env=env,
    ).stdout.strip()
    containers: dict[str, str] = {}
    for service in ("postgres",):
        result = run_capture(
            [docker, "compose", "ps", "-q", service], env=env, timeout=20
        )
        container_id = (result.stdout or "").strip()
        if container_id:
            image = run_capture(
                [docker, "inspect", "--format", "{{.Image}}", container_id], timeout=20
            )
            containers[service] = (image.stdout or "").strip()
    return {
        "format_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "timestamp": timestamp,
        "repository_head": head,
        "alembic_current": current,
        "containers": containers,
        "configuration": {
            "database_credentials": "CONFIGURED",
            "evidence_storage": "PRIVATE_FILESYSTEM",
            "jwt_secret": "CONFIGURED",
            "pilot_otp_secrets": "CONFIGURED",
        },
        "database": {
            "file": str(database_dump),
            "bytes": database_dump.stat().st_size,
            "sha256": sha256(database_dump),
            "pg_restore_list_verified": True,
        },
        "evidence": {
            "directory": str(evidence_snapshot),
            "manifest": str(evidence_manifest),
            "manifest_sha256": sha256(evidence_manifest),
            "file_count": evidence_details["file_count"],
            "total_bytes": evidence_details["total_bytes"],
            "hashes_verified": True,
        },
        "secrets_included": False,
        "restore_test_performed": False,
    }


def backup_server() -> int:
    docker, env = require_runtime()
    if not docker_ready(docker):
        raise ServerError("Docker engine is offline; backup was not started.")
    status = compose_health(docker, env)
    if status.get("postgres") != "healthy":
        raise ServerError("PostgreSQL must be healthy before backup.")
    source_evidence_root = ensure_evidence_root(env)

    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S%z")
    database_dir = BACKUP_ROOT / "database" / timestamp
    release_dir = BACKUP_ROOT / "releases" / timestamp
    for path in (database_dir, release_dir):
        path.mkdir(parents=True, exist_ok=False)

    values = parse_dotenv(ENV_FILE.read_text(encoding="utf-8"))
    database = values["POSTGRES_DB"]
    database_user = values["POSTGRES_USER"]
    dump_file = database_dir / f"{database}.dump"
    with dump_file.open("wb") as output:
        process = subprocess.Popen(
            [
                docker,
                "compose",
                "exec",
                "-T",
                "postgres",
                "pg_dump",
                "--format=custom",
                "--no-owner",
                "--username",
                database_user,
                "--dbname",
                database,
            ],
            cwd=str(ROOT),
            env=dict(env),
            stdout=output,
            stderr=subprocess.PIPE,
        )
        process.communicate(timeout=180)
    if process.returncode != 0 or not dump_file.is_file() or dump_file.stat().st_size == 0:
        raise ServerError("PostgreSQL logical dump failed or was empty.")
    with dump_file.open("rb") as source:
        verify = subprocess.run(
            [
                docker,
                "compose",
                "exec",
                "-T",
                "postgres",
                "pg_restore",
                "--list",
            ],
            cwd=str(ROOT),
            env=dict(env),
            stdin=source,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
            check=False,
        )
    if verify.returncode != 0 or not verify.stdout.strip():
        raise ServerError("PostgreSQL dump could not be listed by pg_restore.")

    evidence_snapshot, evidence_manifest, evidence_details = create_evidence_snapshot(
        source_evidence_root, timestamp
    )
    manifest = safe_backup_manifest(
        timestamp=timestamp,
        database_dump=dump_file,
        evidence_snapshot=evidence_snapshot,
        evidence_manifest=evidence_manifest,
        evidence_details=evidence_details,
        docker=docker,
        env=env,
    )
    manifest_file = release_dir / "server-backup-manifest.json"
    atomic_write_json(manifest_file, manifest)
    json.loads(manifest_file.read_text(encoding="utf-8"))
    print("Fleet Manager server backup verified.")
    print(f"Database: {database_dir}")
    print(f"Evidence: {evidence_snapshot}")
    print(f"Evidence manifest: {evidence_manifest}")
    print(f"Manifest: {manifest_file}")
    print("Restore was not performed; use an isolated restore target in the next phase.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Control the local Fleet Manager server.")
    parser.add_argument("command", choices=("start", "check", "stop", "backup"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    command = build_parser().parse_args(argv).command
    try:
        if command == "start":
            return start_server()
        if command == "check":
            return check_server()
        if command == "stop":
            return stop_server()
        return backup_server()
    except ServerError as error:
        print(f"\n[FAILED] {error}")
        return 1
    except Exception as error:
        print(f"\n[FAILED] Unexpected server-control error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
