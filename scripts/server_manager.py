"""Fleet Manager remote-test server control, update, and backup helper.

The remote-test architecture uses Compose only for PostgreSQL. FastAPI is an
owned native process bound to 127.0.0.1, and evidence remains private in a
configured local filesystem root. Optional remote status uses private Tailscale
Serve without making local health depend on Tailscale availability.
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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError
from sqlalchemy.pool import NullPool


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
from scripts.pilot_release_common import (  # noqa: E402
    ApkIdentity,
    ReleaseValidationError,
    inspect_apk,
    validate_expected_identity,
    version_text,
)


API_PORT = 8000
API_HEALTH_URL = "http://127.0.0.1:8000/health"
API_READY_URL = "http://127.0.0.1:8000/ready"
DOCKER_TIMEOUT_SECONDS = 120
INFRA_TIMEOUT_SECONDS = 90
API_TIMEOUT_SECONDS = 60
DATABASE_CONNECT_TIMEOUT_SECONDS = 2
DATABASE_REVISION_TIMEOUT_SECONDS = 5
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
TAILSCALE_EXE = Path(r"C:\Program Files\Tailscale\tailscale.exe")
TAILSCALE_PROXY_TARGET = "http://127.0.0.1:8000"
TAILSCALE_PILOT_PATH = "/pilot"
PILOT_RELEASE_DIR = Path(r"F:\FleetManagerData\releases\pilot")
PILOT_APK_NAME = "FleetManager-Pilot-latest.apk"
PILOT_SHA256_NAME = "sha256.txt"
PILOT_VERSION_NAME = "version.txt"
PILOT_RELEASE_MANIFEST_NAME = "release.json"
PILOT_PUBLISHER_STATUS_FILE = Path(
    r"F:\FleetManagerData\releases\incoming\publisher-status.json"
)
LOCAL_STATUS_KEYS = ("docker", "postgres", "evidence", "api", "health", "ready")
DEPLOYMENT_SOURCE_PATHS = (
    API_PROJECT / "src",
    API_PROJECT / "migrations",
    API_PROJECT / "pyproject.toml",
    API_PROJECT / "uv.lock",
)


class ServerError(RuntimeError):
    """Expected server-control failure with an operator-safe message."""


@dataclass(frozen=True)
class DeploymentState:
    """Read-only assessment of the state required for a current deployment."""

    dependencies_current: bool
    database_current: bool
    database_revisions: tuple[str, ...]
    repository_heads: tuple[str, ...]
    api_running: bool
    api_stale: bool
    health_ok: bool
    ready_ok: bool
    remote_current: bool

    @property
    def api_current(self) -> bool:
        return (
            self.api_running and not self.api_stale and self.health_ok and self.ready_ok
        )

    @property
    def current(self) -> bool:
        return (
            self.dependencies_current
            and self.database_current
            and self.api_current
            and self.remote_current
        )


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
        raise ServerError(
            f"{label} failed.\n{safe_tail}" if safe_tail else f"{label} failed."
        )
    return result


def git_output(*args: str, timeout: int = 120) -> str:
    result = checked(
        ["git", *args],
        label=f"git {' '.join(args)}",
        timeout=timeout,
    )
    return (result.stdout or "").strip()


def find_uv() -> str | None:
    resolved = shutil.which("uv")
    if resolved:
        return resolved
    user_profile = Path(os.environ.get("USERPROFILE", ""))
    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = (
        user_profile / ".local" / "bin" / "uv.exe",
        local_app_data / "uv" / "uv.exe",
        user_profile / ".cargo" / "bin" / "uv.exe",
        user_profile / "scoop" / "shims" / "uv.exe",
    )
    return next((str(path) for path in candidates if path.is_file()), None)


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
        raise ServerError(
            "This local server controller refuses production configuration."
        )
    if values.get("FLEET_OBJECT_STORAGE_PROVIDER", "").lower() != "filesystem":
        raise ServerError(
            "Evidence storage must be configured as filesystem for this server."
        )
    effective = dict(os.environ)
    for key, value in values.items():
        effective.setdefault(key, value)
    # Alembic intentionally honors FLEET_TEST_DATABASE_URL for the test suite.
    # The server controller must always target the same FLEET_DATABASE_URL as FastAPI.
    effective.pop("FLEET_TEST_DATABASE_URL", None)
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
    try:
        repository_head = git_output("rev-parse", "HEAD")
    except ServerError:
        repository_head = ""
    STATE_FILE.write_text(
        json.dumps(
            {
                "pid": pid,
                "command": list(command),
                "cwd": str(ROOT),
                "owned": True,
                "started_at": datetime.now(UTC).isoformat(),
                "repository_head": repository_head,
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
        (info.command_line or info.executable_path)
        .casefold()
        .replace("/", "\\")
        .split()
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
            f'(Get-CimInstance Win32_Process -Filter "ProcessId = {pid}").ParentProcessId',
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
    return bool(is_expected_api_health(default_http_probe(API_HEALTH_URL, 3.0)))


def api_ready_ok() -> bool:
    probe = default_http_probe(API_READY_URL, 3.0)
    return bool(probe is not None and probe.status == 200)


def tailscale_executable() -> str | None:
    resolved = shutil.which("tailscale")
    if resolved:
        return resolved
    return str(TAILSCALE_EXE) if TAILSCALE_EXE.is_file() else None


def tailscale_service_status() -> str:
    if os.name != "nt":
        return "UNKNOWN"
    result = run_capture(["sc.exe", "query", "Tailscale"], timeout=10)
    if result.returncode != 0:
        return "OFFLINE"
    return "RUNNING" if "RUNNING" in (result.stdout or "").upper() else "OFFLINE"


def _private_serve_handler(
    config: Mapping[str, Any], dns_name: str, route: str
) -> Mapping[str, Any] | None:
    web = config.get("Web")
    if not isinstance(web, dict):
        return None
    host_config = web.get(f"{dns_name}:443")
    if not isinstance(host_config, dict):
        return None
    handlers = host_config.get("Handlers")
    if not isinstance(handlers, dict):
        return None
    handler = handlers.get(route)
    if not isinstance(handler, dict) and route != "/":
        handler = handlers.get(f"{route.rstrip('/')}/")
    if not isinstance(handler, dict):
        return None
    return handler


def _private_serve_target(config: Mapping[str, Any], dns_name: str) -> str | None:
    root_handler = _private_serve_handler(config, dns_name, "/")
    if root_handler is None:
        return None
    proxy = root_handler.get("Proxy")
    return proxy if isinstance(proxy, str) else None


def _private_serve_path(config: Mapping[str, Any], dns_name: str) -> str | None:
    pilot_handler = _private_serve_handler(config, dns_name, TAILSCALE_PILOT_PATH)
    if pilot_handler is None:
        return None
    path = pilot_handler.get("Path")
    return path if isinstance(path, str) else None


def _same_local_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.normpath(str(left))) == os.path.normcase(
        os.path.normpath(str(right))
    )


def _funnel_enabled(config: Mapping[str, Any]) -> bool:
    allowed = config.get("AllowFunnel")
    if allowed is True:
        return True
    if isinstance(allowed, dict) and any(value is True for value in allowed.values()):
        return True
    if isinstance(allowed, list) and bool(allowed):
        return True
    tcp = config.get("TCP")
    if not isinstance(tcp, dict):
        return False
    return any(
        isinstance(listener, dict) and listener.get("Funnel") is True
        for listener in tcp.values()
    )


def _configure_pilot_serve(executable: str) -> tuple[bool, str]:
    result = run_capture(
        [
            executable,
            "serve",
            "--bg",
            "--set-path",
            TAILSCALE_PILOT_PATH,
            str(PILOT_RELEASE_DIR),
        ],
        timeout=30,
    )
    if result.returncode == 0:
        return True, ""
    detail = f"{result.stdout or ''}\n{result.stderr or ''}".casefold()
    if "local admin" in detail or "administrator" in detail:
        return False, "PILOT SERVE ADMIN APPROVAL REQUIRED"
    return False, "PILOT SERVE CONFIGURATION REQUIRED"


def remote_access_status(*, ensure_serve: bool = False) -> dict[str, str]:
    result = {
        "remote": "OFFLINE",
        "remote_url": "",
        "tailscale": "OFFLINE",
        "tailscale_service": tailscale_service_status(),
        "funnel": "UNKNOWN",
        "serve_root": "MISSING",
        "serve_pilot": "MISSING",
        "remote_health": "OFFLINE",
        "remote_ready": "OFFLINE",
        "reason": "TAILSCALE NOT AVAILABLE",
    }
    executable = tailscale_executable()
    if not executable:
        return result
    status = run_capture([executable, "status", "--json"], timeout=10)
    if status.returncode != 0:
        return result
    try:
        status_payload = json.loads(status.stdout or "{}")
    except json.JSONDecodeError:
        return result
    self_status = status_payload.get("Self")
    backend_state = str(status_payload.get("BackendState") or "")
    if backend_state != "Running" or not isinstance(self_status, dict):
        if backend_state == "NeedsLogin":
            result["reason"] = "TAILSCALE LOGIN REQUIRED"
        else:
            result["reason"] = "TAILSCALE NOT CONNECTED"
        return result
    if self_status.get("Online") is not True:
        result["reason"] = "TAILSCALE DISCONNECTED"
        return result
    result["tailscale"] = "ONLINE"
    dns_name = str(self_status.get("DNSName") or "").strip().rstrip(".").lower()
    if not dns_name:
        result["reason"] = "TAILSCALE DNS NAME UNAVAILABLE"
        return result
    result["remote_url"] = f"https://{dns_name}"
    serve = run_capture([executable, "serve", "status", "--json"], timeout=10)
    funnel = run_capture([executable, "funnel", "status", "--json"], timeout=10)
    if serve.returncode != 0 or funnel.returncode != 0:
        result["reason"] = "TAILSCALE SERVE STATUS UNAVAILABLE"
        return result
    try:
        serve_payload = json.loads(serve.stdout or "{}")
        funnel_payload = json.loads(funnel.stdout or "{}")
    except json.JSONDecodeError:
        return result
    if not isinstance(serve_payload, dict) or not isinstance(funnel_payload, dict):
        return result
    funnel_enabled = _funnel_enabled(funnel_payload)
    result["funnel"] = "ON" if funnel_enabled else "OFF"
    if funnel_enabled:
        result["reason"] = "TAILSCALE FUNNEL MUST BE OFF"
        return result

    root_ok = _private_serve_target(serve_payload, dns_name) == TAILSCALE_PROXY_TARGET
    result["serve_root"] = "OK" if root_ok else "MISSING"
    pilot_path = _private_serve_path(serve_payload, dns_name)
    pilot_ok = bool(pilot_path and _same_local_path(pilot_path, PILOT_RELEASE_DIR))
    if ensure_serve and root_ok and not pilot_ok and PILOT_RELEASE_DIR.is_dir():
        configured, reason = _configure_pilot_serve(executable)
        if configured:
            refreshed = run_capture(
                [executable, "serve", "status", "--json"], timeout=10
            )
            try:
                refreshed_payload = json.loads(refreshed.stdout or "{}")
            except json.JSONDecodeError:
                refreshed_payload = {}
            if refreshed.returncode == 0 and isinstance(refreshed_payload, dict):
                serve_payload = refreshed_payload
                root_ok = (
                    _private_serve_target(serve_payload, dns_name)
                    == TAILSCALE_PROXY_TARGET
                )
                pilot_path = _private_serve_path(serve_payload, dns_name)
                pilot_ok = bool(
                    pilot_path and _same_local_path(pilot_path, PILOT_RELEASE_DIR)
                )
                result["serve_root"] = "OK" if root_ok else "MISSING"
        elif reason:
            result["reason"] = reason
    result["serve_pilot"] = "OK" if pilot_ok else "MISSING"

    if not root_ok:
        result["reason"] = "TAILSCALE ROOT SERVE CONFIGURATION REQUIRED"
        return result
    health = default_http_probe(f"{result['remote_url']}/health", timeout=5)
    ready = default_http_probe(f"{result['remote_url']}/ready", timeout=5)
    health_ok = is_expected_api_health(health)
    ready_ok = ready is not None and ready.status == 200
    result["remote_health"] = "OK" if health_ok else "OFFLINE"
    result["remote_ready"] = "OK" if ready_ok else "OFFLINE"
    if health_ok and ready_ok:
        result["remote"] = "ONLINE"
        if pilot_ok:
            result["reason"] = ""
        elif not result["reason"].startswith("PILOT SERVE"):
            result["reason"] = "PILOT SERVE CONFIGURATION REQUIRED"
    else:
        result["reason"] = "REMOTE API HEALTH CHECK FAILED"
    return result


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


def component_status(
    docker: str | None,
    env: Mapping[str, str] | None,
    *,
    ensure_remote: bool = False,
) -> dict[str, str]:
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
    status = {
        "docker": "OK" if docker_ok else "OFFLINE",
        "postgres": "OK" if compose.get("postgres") == "healthy" else "OFFLINE",
        "evidence": "OK" if evidence_store_available(env) else "OFFLINE",
        "api": api_state,
        "health": "OK" if health else "OFFLINE",
        "ready": "OK" if ready else "OFFLINE",
    }
    status.update(remote_access_status(ensure_serve=ensure_remote))
    status.update(pilot_release_status(status.get("remote_url", "")))
    status.update(pilot_publisher_status())
    return status


def print_start_status(
    status: Mapping[str, str], start_result: str | None = None
) -> None:
    online = all(
        status[key] == "OK" for key in ("postgres", "evidence", "api", "ready")
    )
    print("\nFLEET MANAGER SERVER\n")
    print(f"Docker          {status['docker']}")
    print(f"PostgreSQL      {status['postgres']}")
    print(f"Evidence Store  {status['evidence']}")
    print(f"FastAPI         {status['api']}")
    print(f"Local Ready     {status['ready']}")
    print(f"Remote Access   {status.get('remote', 'OFFLINE')}")
    print(
        "Tailscale       "
        + ("CONNECTED" if status.get("tailscale") == "ONLINE" else "OFFLINE")
    )
    print(f"Tailscale Svc   {status.get('tailscale_service', 'UNKNOWN')}")
    print(f"Serve Root      {status.get('serve_root', 'MISSING')}")
    print(f"Serve /pilot    {status.get('serve_pilot', 'MISSING')}")
    print(f"Funnel          {status.get('funnel', 'UNKNOWN')}")
    if status.get("remote_url"):
        print(f"\nRemote URL:\n{status['remote_url']}")
    print(f"\nPilot APK:\n{status.get('pilot_apk', 'NOT PUBLISHED')}")
    if status.get("apk_url") and status.get("serve_pilot") == "OK":
        print(f"\nAPK:\n{status['apk_url']}")
    if status.get("reason"):
        print(f"\nReason          {status['reason']}")
    if status.get("pilot_warning"):
        print(f"Warning         {status['pilot_warning']}")
    if start_result == "ALREADY RUNNING":
        print("\nALREADY RUNNING")
    print("\nSERVER IS ONLINE" if online else "\nSERVER START FAILED")


def print_check_status(status: Mapping[str, str]) -> None:
    online = all(status.get(key) == "OK" for key in LOCAL_STATUS_KEYS)
    print("\nFLEET MANAGER SERVER STATUS\n")
    print(f"Docker          {status['docker']}")
    print(f"PostgreSQL      {status['postgres']}")
    print(f"Evidence Store  {status['evidence']}")
    print(f"FastAPI         {status['api']}")
    print(f"/health         {status['health']}")
    print(f"/ready          {status['ready']}")
    print(f"Remote Access   {status.get('remote', 'OFFLINE')}")
    print(
        "Tailscale       "
        + ("CONNECTED" if status.get("tailscale") == "ONLINE" else "OFFLINE")
    )
    print(f"Tailscale Svc   {status.get('tailscale_service', 'UNKNOWN')}")
    print(f"Serve Root      {status.get('serve_root', 'MISSING')}")
    print(f"Serve /pilot    {status.get('serve_pilot', 'MISSING')}")
    print(f"Funnel          {status.get('funnel', 'UNKNOWN')}")
    print(f"Remote /health  {status.get('remote_health', 'OFFLINE')}")
    print(f"Remote /ready   {status.get('remote_ready', 'OFFLINE')}")
    print(f"Pilot APK       {status.get('pilot_apk', 'NOT PUBLISHED')}")
    print(f"Pilot Publisher {status.get('pilot_publisher', 'ERROR')}")
    if status.get("remote_url"):
        print(f"Remote URL      {status['remote_url']}")
    if status.get("apk_url") and status.get("serve_pilot") == "OK":
        print(f"APK URL         {status['apk_url']}")
    if status.get("reason"):
        print(f"Reason          {status['reason']}")
    if status.get("pilot_warning"):
        print(f"Warning         {status['pilot_warning']}")
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
        ensure_pilot_release_directory()
        result = start_api(env)
    except ServerError as error:
        print(f"\n[FAILED] {error}")
        print_start_status(component_status(docker, env), result)
        return 1
    print_start_status(component_status(docker, env, ensure_remote=True), result)
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
    return 0 if all(status.get(key) == "OK" for key in LOCAL_STATUS_KEYS) else 1


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
        raise ServerError(
            "Refusing to stop API: recorded process ownership could not be verified."
        )
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
        forced = run_capture(
            ["taskkill", "/PID", str(info.pid), "/T", "/F"], timeout=20
        )
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


def stable_sha256(path: Path) -> tuple[str, int]:
    before = path.stat()
    digest = sha256(path)
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ServerError(f"File changed while it was being verified: {path.name}")
    return digest, after.st_size


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temporary = tempfile.mkstemp(
        prefix=f".{path.name}-", dir=path.parent
    )
    temporary = Path(raw_temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def ensure_pilot_release_directory() -> None:
    if PILOT_RELEASE_DIR.exists() and not PILOT_RELEASE_DIR.is_dir():
        raise ServerError(f"Pilot release path is not a directory: {PILOT_RELEASE_DIR}")
    PILOT_RELEASE_DIR.mkdir(parents=True, exist_ok=True)


def pilot_publisher_status() -> dict[str, str]:
    result = {
        "pilot_publisher": "ERROR",
        "pilot_publisher_detail": "Status unavailable.",
    }
    try:
        payload = json.loads(PILOT_PUBLISHER_STATUS_FILE.read_text(encoding="utf-8"))
        state = payload.get("state")
        updated = datetime.fromisoformat(str(payload.get("updatedAt", "")))
        if updated.tzinfo is None:
            raise ValueError("publisher timestamp has no timezone")
        age = (datetime.now(UTC) - updated.astimezone(UTC)).total_seconds()
        if state not in ("READY", "PROCESSING", "ERROR"):
            raise ValueError("publisher state is invalid")
        if age > 300:
            return {
                "pilot_publisher": "ERROR",
                "pilot_publisher_detail": "Publisher status is stale.",
            }
        result["pilot_publisher"] = state
        result["pilot_publisher_detail"] = str(payload.get("detail", ""))[:1000]
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as error:
        result["pilot_publisher_detail"] = f"Publisher status unavailable: {error}"
    return result


def pilot_release_status(remote_url: str = "") -> dict[str, str]:
    result = {
        "pilot_directory": "OK" if PILOT_RELEASE_DIR.is_dir() else "MISSING",
        "pilot_apk": "NOT PUBLISHED",
        "pilot_warning": "",
        "apk_url": "",
    }
    apk = PILOT_RELEASE_DIR / PILOT_APK_NAME
    checksum_file = PILOT_RELEASE_DIR / PILOT_SHA256_NAME
    if not apk.is_file():
        return result
    try:
        digest, _ = stable_sha256(apk)
    except (OSError, ServerError) as error:
        result["pilot_apk"] = "WARNING"
        result["pilot_warning"] = str(error)
        return result
    expected_line = f"{digest}  {PILOT_APK_NAME}\n"
    if not checksum_file.exists():
        try:
            atomic_write_text(checksum_file, expected_line)
        except OSError as error:
            result["pilot_apk"] = "WARNING"
            result["pilot_warning"] = f"Could not create {PILOT_SHA256_NAME}: {error}"
            return result
    try:
        fields = checksum_file.read_text(encoding="utf-8").strip().split()
    except (OSError, UnicodeError) as error:
        result["pilot_apk"] = "WARNING"
        result["pilot_warning"] = f"Could not read {PILOT_SHA256_NAME}: {error}"
        return result
    filename_ok = len(fields) == 1 or (
        len(fields) == 2 and fields[1].lstrip("*") == PILOT_APK_NAME
    )
    if not fields or fields[0].casefold() != digest or not filename_ok:
        result["pilot_apk"] = "WARNING"
        result["pilot_warning"] = "Pilot APK SHA-256 metadata is inconsistent."
        return result
    result["pilot_apk"] = "PUBLISHED"
    if remote_url:
        result["apk_url"] = f"{remote_url}{TAILSCALE_PILOT_PATH}/{PILOT_APK_NAME}"
    return result


def _pilot_versioned_apk_name(identity: ApkIdentity) -> str:
    safe_version = "".join(
        character if character.isalnum() or character in ".-_" else "-"
        for character in identity.version_name
    ).strip(".-_")
    if not safe_version:
        raise ServerError("Pilot APK version name cannot form a safe filename.")
    return f"FleetManager-Pilot-{safe_version}-{identity.version_code}.apk"


def _stage_pilot_file(target: Path, content: bytes) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".staged", dir=PILOT_RELEASE_DIR
    )
    staged = Path(raw_path)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        return staged
    except Exception:
        staged.unlink(missing_ok=True)
        raise


def _stage_pilot_copy(target: Path, source: Path) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".staged", dir=PILOT_RELEASE_DIR
    )
    os.close(descriptor)
    staged = Path(raw_path)
    try:
        shutil.copyfile(source, staged)
        copied_digest, copied_size = stable_sha256(staged)
        if copied_digest != sha256(source) or copied_size != source.stat().st_size:
            raise ServerError("Pilot APK staging verification failed.")
        return staged
    except Exception:
        staged.unlink(missing_ok=True)
        raise


def _publish_pilot_transaction(staged_files: Mapping[Path, Path], verify: Any) -> None:
    """Replace the active release as one rollback-capable filesystem transaction."""
    backups: dict[Path, Path] = {}
    published: list[Path] = []
    committed = False
    try:
        for target, staged in staged_files.items():
            if target.exists():
                backup = PILOT_RELEASE_DIR / f".{target.name}.{uuid4().hex}.backup"
                try:
                    # A same-volume hard link is a cheap immutable rollback
                    # snapshot. Copying is the safe fallback where unsupported.
                    os.link(target, backup)
                except OSError:
                    shutil.copyfile(target, backup)
                backups[target] = backup
            os.replace(staged, target)
            published.append(target)
        verify()
        committed = True
    except Exception:
        rollback_errors: list[str] = []
        for target in reversed(published):
            try:
                target.unlink(missing_ok=True)
            except OSError as error:
                rollback_errors.append(f"remove {target.name}: {error}")
        for target, backup in backups.items():
            try:
                os.replace(backup, target)
            except OSError as error:
                rollback_errors.append(f"{target.name}: {error}")
        if rollback_errors:
            raise ServerError(
                "Pilot publication failed and rollback was incomplete: "
                + "; ".join(rollback_errors)
            )
        raise
    finally:
        for staged in staged_files.values():
            staged.unlink(missing_ok=True)
        if committed:
            for backup in backups.values():
                backup.unlink(missing_ok=True)


def _pilot_release_manifest(
    identity: ApkIdentity,
    apk_url: str,
    *,
    mandatory: bool,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "version_name": identity.version_name,
        "version_code": identity.version_code,
        "apk_url": apk_url,
        "sha256": identity.apk_sha256,
        "mandatory": mandatory,
        "published_at": datetime.now(UTC).isoformat(),
    }
    try:
        source_commit = git_output("rev-parse", "HEAD")
        if len(source_commit) == 40:
            manifest["source_commit"] = source_commit
    except ServerError:
        pass
    return manifest


def publish_pilot_apk(
    source: Path,
    version_file: Path | None = None,
    *,
    mandatory: bool = False,
) -> int:
    if not source.is_file():
        raise ServerError(f"Pilot APK source was not found: {source}")
    if source.suffix.casefold() != ".apk":
        raise ServerError("Pilot publish source must be an APK file.")
    ensure_pilot_release_directory()
    source = source.resolve(strict=True)
    destination = PILOT_RELEASE_DIR / PILOT_APK_NAME
    if source == destination.resolve(strict=False):
        raise ServerError("Pilot APK is already at the publish destination.")
    if version_file is not None and not version_file.is_file():
        raise ServerError(f"Pilot version metadata was not found: {version_file}")
    try:
        identity = inspect_apk(source)
        validate_expected_identity(identity)
    except ReleaseValidationError as error:
        raise ServerError(f"Pilot APK validation failed: {error}") from error

    remote = remote_access_status(ensure_serve=True)
    remote_url = remote.get("remote_url", "").rstrip("/")
    if (
        remote.get("remote") != "ONLINE"
        or remote.get("serve_pilot") != "OK"
        or not remote_url.startswith("https://")
    ):
        raise ServerError(
            "Pilot APK was not published because its private HTTPS Tailscale URL is not ready."
        )

    versioned = PILOT_RELEASE_DIR / _pilot_versioned_apk_name(identity)
    if versioned.exists() and sha256(versioned) != identity.apk_sha256:
        raise ServerError(
            "Pilot versioned APK already exists with different contents; "
            "increase the Android versionCode before publishing."
        )
    download_url = f"{remote_url}{TAILSCALE_PILOT_PATH}/{versioned.name}"
    latest_url = f"{remote_url}{TAILSCALE_PILOT_PATH}/{PILOT_APK_NAME}"
    manifest = _pilot_release_manifest(identity, download_url, mandatory=mandatory)
    staged: dict[Path, Path] = {}
    try:
        staged[versioned] = _stage_pilot_copy(versioned, source)
        staged[destination] = _stage_pilot_copy(destination, source)
        staged[PILOT_RELEASE_DIR / PILOT_SHA256_NAME] = _stage_pilot_file(
            PILOT_RELEASE_DIR / PILOT_SHA256_NAME,
            f"{identity.apk_sha256}  {PILOT_APK_NAME}\n".encode(),
        )
        staged[PILOT_RELEASE_DIR / PILOT_VERSION_NAME] = _stage_pilot_file(
            PILOT_RELEASE_DIR / PILOT_VERSION_NAME,
            version_text(identity, versioned.name).encode(),
        )
        staged[PILOT_RELEASE_DIR / PILOT_RELEASE_MANIFEST_NAME] = _stage_pilot_file(
            PILOT_RELEASE_DIR / PILOT_RELEASE_MANIFEST_NAME,
            (json.dumps(manifest, indent=2) + "\n").encode(),
        )
    except Exception:
        for staged_file in staged.values():
            staged_file.unlink(missing_ok=True)
        raise

    def verify_publication() -> None:
        release = pilot_release_status(remote_url)
        if release["pilot_apk"] != "PUBLISHED":
            raise ServerError(
                release["pilot_warning"] or "Pilot APK verification failed."
            )
        published_manifest = json.loads(
            (PILOT_RELEASE_DIR / PILOT_RELEASE_MANIFEST_NAME).read_text(
                encoding="utf-8"
            )
        )
        if published_manifest != manifest:
            raise ServerError("Pilot release manifest verification failed.")
        probe = default_http_probe(download_url, timeout=10)
        if probe is None or probe.status != 200:
            raise ServerError(
                "Pilot private download URL is unreachable; previous release restored."
            )
        latest_probe = default_http_probe(latest_url, timeout=10)
        if latest_probe is None or latest_probe.status != 200:
            raise ServerError(
                "Pilot latest APK URL is unreachable; previous release restored."
            )
        manifest_url = (
            f"{remote_url}{TAILSCALE_PILOT_PATH}/{PILOT_RELEASE_MANIFEST_NAME}"
        )
        manifest_probe = default_http_probe(manifest_url, timeout=10)
        if manifest_probe is None or manifest_probe.status != 200:
            raise ServerError(
                "Pilot release manifest URL is unreachable; previous release restored."
            )

    _publish_pilot_transaction(staged, verify_publication)
    print("\nFLEET MANAGER PILOT APK\n")
    print("PUBLISHED       YES")
    print(f"APK             {destination}")
    print(f"VERSIONED APK   {versioned}")
    print(f"RELEASE JSON    {PILOT_RELEASE_DIR / PILOT_RELEASE_MANIFEST_NAME}")
    print(f"SHA-256         {identity.apk_sha256}")
    print(f"PRIVATE URL     {download_url}")
    return 0


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temporary = tempfile.mkstemp(
        prefix=".fleet-manifest-", dir=path.parent
    )
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
            part in {"", ".", ".."} or ":" in part for part in relative_text.split("/")
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
    if (
        not isinstance(manifest, dict)
        or manifest.get("format_version") != 1
        or not isinstance(files, list)
    ):
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
        if (
            candidate.stat().st_size != expected_size
            or sha256(candidate) != expected_hash
        ):
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


def create_evidence_snapshot(
    source_root: Path, timestamp: str
) -> tuple[Path, Path, dict[str, Any]]:
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
        for source in sorted(
            canonical_source.rglob("*"), key=lambda item: item.as_posix()
        ):
            if source.is_symlink():
                raise ServerError(
                    "Evidence backup refuses symbolic links or junction files."
                )
            if not source.is_file():
                continue
            resolved_source = source.resolve(strict=True)
            try:
                relative = resolved_source.relative_to(canonical_source)
            except ValueError as exc:
                raise ServerError(
                    "Evidence file escapes the configured storage root."
                ) from exc
            relative_text = relative.as_posix()
            if relative_text == EVIDENCE_MANIFEST_NAME:
                raise ServerError(
                    "Evidence root contains the reserved backup manifest name."
                )
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(resolved_source, destination)
            source_size = resolved_source.stat().st_size
            source_hash = sha256(resolved_source)
            if (
                destination.stat().st_size != source_size
                or sha256(destination) != source_hash
            ):
                raise ServerError(
                    f"Evidence backup copy verification failed: {relative_text}"
                )
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
    head = checked(
        ["git", "rev-parse", "HEAD"], label="Git revision check"
    ).stdout.strip()
    current = ", ".join(_database_alembic_revisions(env))
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
    if (
        process.returncode != 0
        or not dump_file.is_file()
        or dump_file.stat().st_size == 0
    ):
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
    print(
        "Restore was not performed; use an isolated restore target in the next phase."
    )
    return 0


def _backup_manifests() -> set[Path]:
    releases = BACKUP_ROOT / "releases"
    if not releases.is_dir():
        return set()
    return set(releases.glob("*/server-backup-manifest.json"))


def _uv_sync_arguments(*, check: bool = False) -> list[str]:
    uv = find_uv()
    if not uv:
        operation = "verification" if check else "synchronization"
        raise ServerError(f"uv is required for locked dependency {operation}.")
    arguments = [
        uv,
        "--cache-dir",
        str(ROOT / ".uv-cache"),
        "sync",
        "--project",
        str(API_PROJECT),
        "--python",
        str(PROJECT_PYTHON),
        "--locked",
        "--all-groups",
    ]
    if check:
        arguments.extend(("--check", "--offline"))
    return arguments


def _locked_dependencies_current() -> bool:
    sync_env = dict(os.environ)
    sync_env["UV_PYTHON_DOWNLOADS"] = "never"
    result = run_capture(
        _uv_sync_arguments(check=True),
        env=sync_env,
        timeout=120,
    )
    return result.returncode == 0


def _sync_locked_dependencies() -> None:
    sync_env = dict(os.environ)
    sync_env["UV_PYTHON_DOWNLOADS"] = "never"
    checked(
        _uv_sync_arguments(),
        label="Locked Python dependency synchronization",
        env=sync_env,
        timeout=600,
    )


def _repository_alembic_heads() -> tuple[str, ...]:
    config = Config(str(API_PROJECT / "alembic.ini"))
    config.set_main_option("script_location", str(API_PROJECT / "migrations"))
    return tuple(sorted(ScriptDirectory.from_config(config).get_heads()))


def _database_revision_timed_out(error: BaseException) -> bool:
    original = error.orig if isinstance(error, DBAPIError) else error
    sqlstate = getattr(original, "sqlstate", None)
    detail = str(original).casefold()
    return (
        sqlstate in {"55P03", "57014"} or "timed out" in detail or "timeout" in detail
    )


def _database_alembic_revisions(env: Mapping[str, str]) -> tuple[str, ...]:
    database_url = env.get("FLEET_DATABASE_URL", "").strip()
    if not database_url:
        raise ServerError("Database revision check has no configured database URL.")
    engine: Engine | None = None
    try:
        engine = create_engine(
            database_url,
            poolclass=NullPool,
            connect_args={
                "connect_timeout": DATABASE_CONNECT_TIMEOUT_SECONDS,
                "options": (
                    f"-c statement_timeout={DATABASE_REVISION_TIMEOUT_SECONDS * 1000} "
                    f"-c lock_timeout={DATABASE_REVISION_TIMEOUT_SECONDS * 1000}"
                ),
            },
        )
        with engine.connect() as connection:
            revisions = (
                connection.execute(text("SELECT version_num FROM alembic_version"))
                .scalars()
                .all()
            )
    except OperationalError as error:
        if _database_revision_timed_out(error):
            if error.statement:
                raise ServerError(
                    "Database revision query timed out or was blocked by a database lock."
                ) from error
            raise ServerError(
                "Database revision check timed out while connecting to PostgreSQL."
            ) from error
        raise ServerError(
            "Database revision check could not connect to configured PostgreSQL."
        ) from error
    except DBAPIError as error:
        if _database_revision_timed_out(error):
            raise ServerError(
                "Database revision query timed out or was blocked by a database lock."
            ) from error
        raise ServerError("Database revision query failed.") from error
    except SQLAlchemyError as error:
        raise ServerError("Database revision query failed.") from error
    finally:
        if engine is not None:
            engine.dispose()
    if len(revisions) != 1:
        raise ServerError(
            "Database alembic_version must contain exactly one revision row."
        )
    revision = revisions[0]
    if not isinstance(revision, str) or not revision.strip():
        raise ServerError(
            "Database alembic_version contains an invalid revision value."
        )
    return (revision.strip(),)


def _latest_deployment_source_mtime() -> float:
    latest = 0.0
    for path in DEPLOYMENT_SOURCE_PATHS:
        candidates = path.rglob("*.py") if path.is_dir() else (path,)
        for candidate in candidates:
            try:
                latest = max(latest, candidate.stat().st_mtime)
            except OSError:
                continue
    return latest


def _api_process_is_stale(state: Mapping[str, Any], current_commit: str) -> bool:
    recorded_commit = state.get("repository_head")
    if isinstance(recorded_commit, str) and recorded_commit:
        return recorded_commit != current_commit
    started_at = state.get("started_at")
    if not isinstance(started_at, str):
        return True
    try:
        started = datetime.fromisoformat(started_at)
    except ValueError:
        return True
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    return _latest_deployment_source_mtime() > started.timestamp()


def _deployment_state(current_commit: str) -> DeploymentState:
    env = load_server_environment()
    repository_heads = _repository_alembic_heads()
    if len(repository_heads) != 1:
        raise ServerError("Repository must have exactly one Alembic head.")
    database_revisions = _database_alembic_revisions(env)
    state, info = recorded_api()
    api_running = is_owned_listener(state, info)
    remote = remote_access_status()
    return DeploymentState(
        dependencies_current=_locked_dependencies_current(),
        database_current=database_revisions == repository_heads,
        database_revisions=database_revisions,
        repository_heads=repository_heads,
        api_running=api_running,
        api_stale=api_running and _api_process_is_stale(state, current_commit),
        health_ok=api_health_ok(),
        ready_ok=api_ready_ok(),
        remote_current=(
            remote.get("tailscale") != "ONLINE" or remote.get("remote") == "ONLINE"
        ),
    )


def _format_revisions(revisions: tuple[str, ...]) -> str:
    return ", ".join(revisions) if revisions else "NONE"


def _print_deployment_state(source_current: bool, state: DeploymentState) -> None:
    print("\nFLEET MANAGER SERVER UPDATE\n")
    print(f"SOURCE          {'CURRENT' if source_current else 'UPDATE REQUIRED'}")
    print(
        "DEPENDENCIES    "
        + ("CURRENT" if state.dependencies_current else "SYNCHRONIZATION REQUIRED")
    )
    if state.database_current:
        print("DATABASE        CURRENT")
    else:
        print("DATABASE        MIGRATION REQUIRED")
        print(f"DATABASE REV    {_format_revisions(state.database_revisions)}")
        print(f"REPOSITORY HEAD {_format_revisions(state.repository_heads)}")
    if state.api_current:
        print("API             CURRENT")
    elif state.api_stale:
        print("API             STALE PROCESS - RESTART REQUIRED")
    elif not state.api_running:
        print("API             STOPPED OR UNMANAGED - RECOVERY REQUIRED")
    else:
        print("API             UNHEALTHY - RESTART REQUIRED")
    print(f"/health         {'CURRENT' if state.health_ok else 'FAILED'}")
    print(f"/ready          {'CURRENT' if state.ready_ok else 'FAILED'}")
    print(
        f"REMOTE STATUS   {'CURRENT' if state.remote_current else 'REVALIDATION REQUIRED'}"
    )


def _require_verified_backup() -> Path:
    before_backups = _backup_manifests()
    backup_server()
    created_backups = _backup_manifests() - before_backups
    if len(created_backups) != 1:
        raise ServerError(
            "Update refused: the pre-update backup location was not unambiguous."
        )
    return created_backups.pop()


def _print_update_failure(
    error: ServerError, old_commit: str, new_commit: str, backup: Path
) -> None:
    print("\nUPDATE FAILED")
    print(f"OLD COMMIT     {old_commit}")
    print(f"NEW COMMIT     {new_commit}")
    print(f"BACKUP LOCATION {backup}")
    print(str(error))
    print("Automatic migration downgrade was not attempted.")
    print("Keep the backup for manual recovery.")


def update_server() -> int:
    if git_output("status", "--porcelain", "--untracked-files=normal"):
        raise ServerError("Update refused: the Git working tree is not clean.")
    branch = git_output("branch", "--show-current")
    if branch != "main":
        raise ServerError(
            f"Update refused: expected branch main, found {branch or 'detached HEAD'}."
        )
    if not git_output("remote", "get-url", "origin"):
        raise ServerError("Update refused: origin is not configured.")
    old_commit = git_output("rev-parse", "HEAD")
    git_output("fetch", "origin", timeout=300)
    target_commit = git_output("rev-parse", "origin/main")
    source_current = old_commit == target_commit
    if not source_current:
        ancestor = run_capture(
            ["git", "merge-base", "--is-ancestor", old_commit, target_commit],
            timeout=30,
        )
        if ancestor.returncode != 0:
            raise ServerError(
                "Update refused: origin/main cannot be applied as a fast-forward. "
                "No backup, stop, pull, or migration was performed."
            )

    state = _deployment_state(old_commit)
    _print_deployment_state(source_current, state)
    if source_current and state.current:
        print("\nALREADY UP TO DATE")
        print(f"CURRENT COMMIT  {old_commit}")
        return 0

    backup = _require_verified_backup()
    new_commit = old_commit
    try:
        stop_api()
        if not source_current:
            git_output("pull", "--ff-only", "origin", "main", timeout=300)
            new_commit = git_output("rev-parse", "HEAD")
            if new_commit != target_commit:
                raise ServerError("git pull completed at an unexpected commit.")
        if not _locked_dependencies_current():
            _sync_locked_dependencies()
        env = load_server_environment()
        repository_heads = _repository_alembic_heads()
        if len(repository_heads) != 1:
            raise ServerError("Repository must have exactly one Alembic head.")
        database_revisions = _database_alembic_revisions(env)
        if database_revisions != repository_heads:
            print("DATABASE MIGRATION REQUIRED")
            checked(
                [str(PROJECT_PYTHON), "-m", "alembic", "upgrade", "head"],
                label="Alembic upgrade",
                cwd=API_PROJECT,
                env=env,
                timeout=300,
            )
        start = checked(
            [str(PROJECT_PYTHON), str(Path(__file__).resolve()), "start"],
            label="Fleet Manager restart",
            timeout=180,
        )
        if start.stdout:
            print(start.stdout.rstrip())
        verified = _deployment_state(new_commit)
        if not verified.current:
            _print_deployment_state(True, verified)
            raise ServerError("Updated deployment failed final state verification.")
    except ServerError as error:
        try:
            new_commit = git_output("rev-parse", "HEAD")
        except ServerError:
            pass
        _print_update_failure(error, old_commit, new_commit, backup)
        return 1

    _print_deployment_state(True, verified)
    print("UPDATE COMPLETE")
    print(f"OLD COMMIT      {old_commit}")
    print(f"NEW COMMIT      {new_commit}")
    print(f"BACKUP LOCATION {backup}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Control the local Fleet Manager server."
    )
    parser.add_argument(
        "command",
        choices=("start", "check", "stop", "backup", "update", "publish-apk"),
    )
    parser.add_argument("apk", nargs="?", type=Path)
    parser.add_argument("--version-file", type=Path)
    parser.add_argument("--mandatory", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command
    try:
        if command == "start":
            return start_server()
        if command == "check":
            return check_server()
        if command == "stop":
            return stop_server()
        if command == "backup":
            return backup_server()
        if command == "publish-apk":
            if args.apk is None:
                raise ServerError("Publish Pilot APK requires a source APK path.")
            return publish_pilot_apk(
                args.apk, args.version_file, mandatory=args.mandatory
            )
        return update_server()
    except ServerError as error:
        print(f"\n[FAILED] {error}")
        return 1
    except Exception as error:
        print(f"\n[FAILED] Unexpected server-control error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
