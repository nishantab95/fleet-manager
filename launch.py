"""One-command Windows launcher for the local PC Role Lab.

This is deliberately a small development/pilot helper. It orchestrates the
existing infrastructure, migration, bootstrap, and reset scripts; it does
not contain domain or database mutation logic of its own.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


class LauncherError(RuntimeError):
    """An expected, actionable launcher failure."""


class PortOccupiedError(LauncherError):
    """A required port belongs to a service the launcher cannot safely reuse."""


@dataclass(frozen=True)
class LauncherPaths:
    root: Path
    api: Path
    web: Path
    scripts: Path
    runtime: Path
    logs: Path
    state: Path

    @classmethod
    def from_root(cls, root: Path) -> "LauncherPaths":
        return cls(
            root=root,
            api=root / "services" / "api",
            web=root / "apps" / "web",
            scripts=root / "scripts",
            runtime=root / ".runtime",
            logs=root / ".runtime" / "logs",
            state=root / ".runtime" / "role-lab.json",
        )


@dataclass(frozen=True)
class HttpProbe:
    status: int
    body: str


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str
    executable_path: str
    command_line: str


@dataclass(frozen=True)
class ServiceStatus:
    state: str
    detail: str = ""


@dataclass(frozen=True)
class CommandTools:
    docker: str
    uv: str
    npm: str
    python: str
    powershell: str


OWNER_PHONE = "+919876543210"
SUPERVISOR_PHONE = "+919876543222"
KNOWN_BOOKKEEPER_ROOT = r"D:\Git\AI-MSME-Book-Keeper"
ROLE_URLS = {
    "OWNER": "http://localhost:3000/owner",
    "SUPERVISOR": "http://localhost:3000/supervisor",
    "DRIVER QA": "http://localhost:3000/driver-test",
}
ROLE_PHONES = {
    "OWNER": OWNER_PHONE,
    "SUPERVISOR": SUPERVISOR_PHONE,
    "DRIVER QA": "FLEET_PILOT_DRIVER_PHONE",
}
FIXTURE_SQL = """
SELECT CASE WHEN EXISTS (
    SELECT 1
    FROM companies c
    JOIN sites s ON s.company_id = c.id AND s.name = 'Pilot Site'
    JOIN tippers t ON t.company_id = c.id AND t.registration_number = 'PILOT12'
    JOIN assignments a ON a.company_id = c.id
        AND a.site_id = s.id
        AND a.tipper_id = t.id
        AND a.ends_at IS NULL
    JOIN company_memberships dm ON dm.company_id = c.id
        AND dm.id = a.driver_membership_id
        AND dm.role = 'DRIVER'
        AND dm.status = 'ACTIVE'
    JOIN users du ON du.id = dm.user_id AND du.display_name = 'Pilot Driver'
    JOIN company_memberships sm ON sm.company_id = c.id
        AND sm.id = a.supervisor_membership_id
        AND sm.role = 'SUPERVISOR'
        AND sm.status = 'ACTIVE'
    JOIN users su ON su.id = sm.user_id AND su.display_name = 'Pilot Supervisor'
    JOIN supervisor_site_access ssa ON ssa.company_id = c.id
        AND ssa.supervisor_membership_id = sm.id
        AND ssa.site_id = s.id
    WHERE c.name = 'Pilot Construction'
) THEN 'READY' ELSE 'MISSING' END
""".strip()


def resolve_repo_root(script_file: str | Path = __file__) -> Path:
    """Resolve the repository from launch.py, not from the caller's cwd."""

    return Path(script_file).resolve().parent


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse the small KEY=VALUE subset used by the project's local .env."""

    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def load_local_environment(
    root: Path,
    environ: Mapping[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Return effective child environment and values read from the local .env."""

    env_file = root / ".env"
    if not env_file.is_file():
        raise LauncherError(
            "A local .env is required. Copy .env.example to .env and configure the pilot OTP."
        )
    local_values = parse_dotenv(env_file.read_text(encoding="utf-8"))
    effective = dict(os.environ if environ is None else environ)
    for key, value in local_values.items():
        effective.setdefault(key, value)
    return effective, local_values


def validate_local_configuration(env: Mapping[str, str]) -> list[str]:
    """Validate only launcher prerequisites; never print secret values."""

    environment = env.get("FLEET_ENVIRONMENT", "development").strip().lower()
    if environment in {"production", "prod"}:
        raise LauncherError(
            "Refusing the PC Role Lab: FLEET_ENVIRONMENT is production."
        )

    missing = [
        key
        for key in ("FLEET_PILOT_DRIVER_PHONE", "FLEET_JWT_SIGNING_KEY")
        if not env.get(key, "").strip()
    ]
    if missing:
        raise LauncherError(f"Missing local pilot configuration: {', '.join(missing)}")
    if len(env["FLEET_JWT_SIGNING_KEY"]) < 32:
        raise LauncherError(
            "FLEET_JWT_SIGNING_KEY must contain at least 32 characters locally."
        )

    provider = env.get("FLEET_OTP_PROVIDER", "").strip().lower()
    if provider != "pilot":
        raise LauncherError(
            "FLEET_OTP_PROVIDER must be 'pilot' for the local Role Lab; no production OTP fallback is used."
        )
    otp = env.get("FLEET_PILOT_OTP", "").strip()
    if len(otp) != 6 or not otp.isdigit():
        raise LauncherError("FLEET_PILOT_OTP must be configured as six local digits.")

    origins = {
        origin.strip().rstrip("/")
        for origin in env.get("FLEET_CORS_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    }
    if "http://localhost:3000" not in origins:
        raise LauncherError(
            "FLEET_CORS_ALLOWED_ORIGINS must include http://localhost:3000."
        )

    warnings: list[str] = []
    if env.get("FLEET_OBJECT_STORAGE_PROVIDER", "unavailable").strip().lower() != "s3":
        warnings.append(
            "FLEET_OBJECT_STORAGE_PROVIDER is not s3; MinIO is ready but evidence uploads may remain unavailable."
        )
    return warnings


def find_required_commands(
    which: Callable[[str], str | None] = shutil.which,
) -> CommandTools:
    """Resolve required Windows commands without assuming a particular shell."""

    def require(label: str, *names: str) -> str:
        for name in names:
            resolved = which(name)
            if resolved:
                return resolved
        raise LauncherError(
            f"Required command not found: {label}. Install it and rerun launch.py."
        )

    return CommandTools(
        docker=require("docker", "docker"),
        uv=require("uv", "uv"),
        npm=require("npm", "npm.cmd", "npm"),
        python=require("python", "python", "python.exe"),
        powershell=require("PowerShell", "pwsh", "powershell", "powershell.exe"),
    )


def build_alembic_command(uv: str, cache_dir: Path) -> list[str]:
    return [uv, "--cache-dir", str(cache_dir), "run", "alembic", "upgrade", "head"]


def build_api_command(uv: str, cache_dir: Path) -> list[str]:
    return [
        uv,
        "--cache-dir",
        str(cache_dir),
        "run",
        "--project",
        "services/api",
        "uvicorn",
        "fleet_api.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ]


def build_web_environment(env: Mapping[str, str]) -> dict[str, str]:
    web_env = dict(env)
    web_env["NEXT_PUBLIC_ENABLE_DRIVER_QA"] = "true"
    return web_env


def build_edge_command(edge: Path, role_url: str, profile_dir: Path) -> list[str]:
    """Build one isolated Edge app window without touching the default profile."""

    return [
        str(edge),
        f"--app={role_url}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=msEdgeFirstRunExperience",
    ]


def is_expected_api_health(probe: HttpProbe | None) -> bool:
    if probe is None or probe.status != 200:
        return False
    try:
        body = json.loads(probe.body)
    except json.JSONDecodeError:
        return False
    return body.get("service") == "fleet-manager-api" and body.get("status") == "ok"


def is_expected_web_response(probe: HttpProbe | None) -> bool:
    if probe is None or probe.status < 200 or probe.status >= 400:
        return False
    body = probe.body.lower()
    return "fleet manager" in body and "next" in body


def command_line_matches(
    root: Path, record: Mapping[str, Any], command_line: str
) -> bool:
    """Positive identity check used before the launcher stops a process."""

    normalized = command_line.replace("/", "\\").lower()
    root_text = str(root).replace("/", "\\").lower().rstrip("\\")
    if root_text not in normalized:
        return False
    kind = record.get("kind")
    if kind == "api":
        return "uvicorn" in normalized or "fleet_api" in normalized
    if kind == "web":
        return "next" in normalized or "apps\\web" in normalized
    return False


def parse_compose_health(output: str) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for line in output.splitlines():
        parts = line.strip().split("\t")
        if len(parts) >= 3:
            service, health, state = (
                parts[0].strip(),
                parts[1].strip(),
                parts[2].strip(),
            )
            statuses[service] = health or state
    return statuses


def default_http_probe(url: str, timeout: float = 3.0) -> HttpProbe | None:
    request = urllib.request.Request(
        url, headers={"User-Agent": "fleet-manager-role-lab"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(256_000).decode("utf-8", errors="replace")
            return HttpProbe(response.status, body)
    except urllib.error.HTTPError as error:
        body = error.read(256_000).decode("utf-8", errors="replace")
        return HttpProbe(error.code, body)
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def default_process_info(pid: int) -> ProcessInfo:
    if os.name != "nt":
        return ProcessInfo(pid, "", "", "")
    command = (
        "$p = Get-CimInstance Win32_Process -Filter 'ProcessId = %d' "
        "-ErrorAction SilentlyContinue; "
        "if ($p) { [pscustomobject]@{ Name=$p.Name; "
        "ExecutablePath=$p.ExecutablePath; CommandLine=$p.CommandLine } "
        "| ConvertTo-Json -Compress }" % pid
    )
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            command,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        value = json.loads(result.stdout.strip())
    except (json.JSONDecodeError, TypeError):
        return ProcessInfo(pid, "", "", "")
    if not isinstance(value, dict):
        return ProcessInfo(pid, "", "", "")
    return ProcessInfo(
        pid,
        str(value.get("Name") or ""),
        str(value.get("ExecutablePath") or ""),
        str(value.get("CommandLine") or ""),
    )


def default_process_command_line(pid: int) -> str:
    return default_process_info(pid).command_line


def normalized_process_text(value: str) -> str:
    return value.replace("/", "\\").casefold()


def is_known_bookkeeper_process(info: ProcessInfo | None) -> bool:
    if info is None:
        return False
    root = normalized_process_text(KNOWN_BOOKKEEPER_ROOT)
    return root in normalized_process_text(
        info.executable_path
    ) or root in normalized_process_text(info.command_line)


def process_name(info: ProcessInfo) -> str:
    if info.name.strip():
        return Path(info.name.strip()).name
    if info.executable_path.strip():
        return Path(info.executable_path.strip()).name
    return "unknown"


def safe_command_summary(info: ProcessInfo, limit: int = 240) -> str:
    value = " ".join((info.command_line or info.executable_path).split())
    if not value:
        return "unavailable"
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def find_listening_pid(
    port: int, run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
) -> int | None:
    if os.name != "nt":
        return None
    result = run(
        ["netstat", "-ano", "-p", "tcp"],
        capture_output=True,
        text=True,
        check=False,
    )
    for line in result.stdout.splitlines():
        parts = line.split()
        if (
            len(parts) < 5
            or parts[0].upper() != "TCP"
            or parts[3].upper() != "LISTENING"
        ):
            continue
        try:
            local_port = int(parts[1].rsplit(":", 1)[1])
            pid = int(parts[-1])
        except (IndexError, ValueError):
            continue
        if local_port == port:
            return pid
    return None


def port_is_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


class RoleLabLauncher:
    def __init__(
        self,
        paths: LauncherPaths | None = None,
        *,
        probe: Callable[[str, float], HttpProbe | None] = default_http_probe,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        popen: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
        run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        process_command_line: Callable[[int], str] = default_process_command_line,
        process_info: Callable[[int], ProcessInfo] = default_process_info,
        listener_pid: Callable[[int], int | None] | None = None,
        command_lookup: Callable[[str], str | None] = shutil.which,
        input_fn: Callable[[str], str] = input,
    ) -> None:
        root = resolve_repo_root() if paths is None else paths.root
        self.paths = paths or LauncherPaths.from_root(root)
        self.probe = probe
        self.sleep = sleep
        self.monotonic = monotonic
        self.popen = popen
        self.run = run
        self.process_command_line = process_command_line
        self.process_info = process_info
        self.listener_pid = listener_pid or (
            lambda port: find_listening_pid(port, run=self.run)
        )
        self.command_lookup = command_lookup
        self.input_fn = input_fn
        self.env: dict[str, str] = {}
        self.local_env: dict[str, str] = {}
        self.tools: CommandTools | None = None
        self.warnings: list[str] = []
        self.browser_workspaces: list[str] = []

    def prepare_config(self) -> None:
        self.env, self.local_env = load_local_environment(self.paths.root)
        self.warnings = validate_local_configuration(self.env)
        self.tools = find_required_commands(self.command_lookup)

    def _require_tools(self) -> CommandTools:
        if self.tools is None:
            raise LauncherError("Launcher configuration has not been prepared.")
        return self.tools

    def _run_checked(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float = 180,
        label: str,
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = self.run(
                list(args),
                cwd=str(cwd or self.paths.root),
                env=dict(env or self.env),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as error:
            raise LauncherError(f"{label} could not start: {error}") from error
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            tail = "\n".join(detail[-12:])
            raise LauncherError(f"{label} failed (exit {result.returncode}).\n{tail}")
        return result

    def _run_capture(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        timeout: float = 30,
    ) -> subprocess.CompletedProcess[str]:
        return self.run(
            list(args),
            cwd=str(cwd or self.paths.root),
            env=dict(self.env),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def _load_state(self) -> dict[str, Any]:
        if not self.paths.state.is_file():
            return {}
        try:
            value = json.loads(self.paths.state.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            print("[WARN] Ignoring unreadable launcher runtime metadata.")
            return {}
        return value if isinstance(value, dict) else {}

    def _save_state(self, state: Mapping[str, Any]) -> None:
        self.paths.runtime.mkdir(parents=True, exist_ok=True)
        self.paths.state.write_text(
            json.dumps(state, indent=2) + "\n", encoding="utf-8"
        )

    def _record(
        self, kind: str, pid: int, command: Sequence[str], cwd: Path
    ) -> dict[str, Any]:
        return {
            "kind": kind,
            "pid": pid,
            "command": list(command),
            "cwd": str(cwd),
            "owned": True,
            "driver_qa": kind == "web",
        }

    def _is_record_alive_and_owned(self, record: Mapping[str, Any]) -> bool:
        if not record.get("owned") or not isinstance(record.get("pid"), int):
            return False
        pid = int(record["pid"])
        try:
            os.kill(pid, 0)
        except (OSError, ProcessLookupError):
            return False
        return command_line_matches(
            self.paths.root, record, self.process_command_line(pid)
        )

    def ensure_infrastructure(self) -> None:
        tools = self._require_tools()
        try:
            self._run_checked(
                [tools.docker, "compose", "up", "-d", "postgres", "minio"],
                label="Docker Compose infrastructure startup",
                timeout=120,
            )
        except LauncherError as error:
            message = str(error).lower()
            if (
                "cannot connect" in message
                or "daemon" in message
                or "docker" in message
            ):
                raise LauncherError(
                    "Docker Desktop is not running. Start Docker Desktop and try again."
                ) from error
            raise

        deadline = self.monotonic() + 60
        last = "no health status yet"
        while self.monotonic() < deadline:
            result = self._run_capture(
                [
                    tools.docker,
                    "compose",
                    "ps",
                    "--format",
                    "{{.Service}}\t{{.Health}}\t{{.State}}",
                    "postgres",
                    "minio",
                ],
                timeout=15,
            )
            statuses = parse_compose_health(result.stdout)
            last = result.stderr.strip() or result.stdout.strip() or last
            if (
                statuses.get("postgres") == "healthy"
                and statuses.get("minio") == "healthy"
            ):
                print("PostgreSQL      READY")
                print("MinIO           READY")
                return
            if result.returncode != 0 and "cannot connect" in result.stderr.lower():
                raise LauncherError(
                    "Docker Desktop is not running. Start Docker Desktop and try again."
                )
            self.sleep(2)
        raise LauncherError(
            f"PostgreSQL/MinIO did not become healthy within 60 seconds.\n{last}"
        )

    def docker_status(self) -> tuple[ServiceStatus, ServiceStatus]:
        tools = self._require_tools()
        engine = self._run_capture(
            [tools.docker, "version", "--format", "{{.Server.Version}}"], timeout=15
        )
        if engine.returncode != 0:
            detail = engine.stderr.strip() or "Docker engine is unavailable."
            return ServiceStatus("unavailable", detail), ServiceStatus(
                "unavailable", detail
            )
        compose = self._run_capture(
            [
                tools.docker,
                "compose",
                "ps",
                "--format",
                "{{.Service}}\t{{.Health}}\t{{.State}}",
                "postgres",
                "minio",
            ],
            timeout=15,
        )
        statuses = parse_compose_health(compose.stdout)
        return (
            ServiceStatus(
                "ready" if statuses.get("postgres") == "healthy" else "not ready"
            ),
            ServiceStatus(
                "ready" if statuses.get("minio") == "healthy" else "not ready"
            ),
        )

    def run_migrations(self) -> None:
        tools = self._require_tools()
        command = build_alembic_command(tools.uv, self.paths.root / ".uv-cache")
        self._run_checked(
            command, cwd=self.paths.api, label="Alembic migration", timeout=240
        )

    def _run_existing_script(self, script_name: str, *arguments: str) -> None:
        tools = self._require_tools()
        script = self.paths.scripts / script_name
        command = [
            tools.powershell,
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            *arguments,
        ]
        self._run_checked(command, label=script_name, timeout=240)

    def bootstrap_fixture(self) -> None:
        self._run_existing_script("bootstrap-pilot.ps1")

    def reset_fixture(self) -> None:
        self._run_existing_script("reset-pilot.ps1", "-ConfirmPilotReset")

    def _api_probe(self) -> ServiceStatus:
        probe = self.probe("http://localhost:8000/health", 3.0)
        if is_expected_api_health(probe):
            return ServiceStatus("ready")
        if port_is_open(8000):
            return ServiceStatus(
                "occupied", "Port 8000 is occupied by another service."
            )
        return ServiceStatus("stopped")

    def _web_probe(self) -> ServiceStatus:
        probe = self.probe("http://localhost:3000/", 3.0)
        if is_expected_web_response(probe):
            return ServiceStatus("ready")
        if port_is_open(3000):
            return ServiceStatus(
                "occupied", "Port 3000 is occupied by another service."
            )
        return ServiceStatus("stopped")

    def _wait_for(
        self, label: str, predicate: Callable[[], bool], timeout: float = 60
    ) -> None:
        deadline = self.monotonic() + timeout
        while self.monotonic() < deadline:
            if predicate():
                return
            self.sleep(1)
        raise LauncherError(
            f"{label} did not become ready within {int(timeout)} seconds."
        )

    def _terminate_verified(
        self, record: Mapping[str, Any], *, allow_external: bool = False
    ) -> None:
        if not allow_external and not record.get("owned"):
            return
        pid = record.get("pid")
        if not isinstance(pid, int):
            return
        command_line = self.process_command_line(pid)
        if not command_line_matches(self.paths.root, record, command_line):
            raise LauncherError(
                f"Refusing to stop PID {pid}: process identity was not verified."
            )
        if os.name == "nt":
            result = self.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
            if (
                result.returncode != 0
                and "not found" not in (result.stderr or "").lower()
            ):
                raise LauncherError(
                    f"Could not stop launcher-owned PID {pid}.\n{result.stderr}"
                )
        else:
            os.kill(pid, signal.SIGTERM)

    def _start_process(
        self,
        kind: str,
        command: Sequence[str],
        cwd: Path,
        env: Mapping[str, str],
        log_name: str,
    ) -> dict[str, Any]:
        self.paths.logs.mkdir(parents=True, exist_ok=True)
        log_path = self.paths.logs / log_name
        log_file = log_path.open("w", encoding="utf-8")
        creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        try:
            process = self.popen(
                list(command),
                cwd=str(cwd),
                env=dict(env),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                creationflags=creation_flags,
            )
        except Exception:
            log_file.close()
            raise
        # The child owns the file handle after spawn; keeping this launcher
        # handle open is unnecessary on Windows and complicates cleanup.
        log_file.close()
        record = self._record(kind, int(process.pid), command, cwd)
        record["log"] = str(log_path)
        state = self._load_state()
        state[kind] = record
        self._save_state(state)
        return record

    def _port_process_info(self, port: int) -> ProcessInfo | None:
        pid = self.listener_pid(port)
        if pid is None:
            return None
        return self.process_info(pid)

    def _unknown_port_error(
        self, port: int, owner: ProcessInfo | None
    ) -> PortOccupiedError:
        if owner is None:
            return PortOccupiedError(
                f"Port {port} is occupied by another application, but no listening PID could be identified.\n"
                "Close it manually and rerun launch.py."
            )
        return PortOccupiedError(
            f"Port {port} is occupied by another application.\n"
            f"PID: {owner.pid}\n"
            f"Process: {process_name(owner)}\n"
            f"Command: {safe_command_summary(owner)}\n"
            "Close it manually and rerun launch.py."
        )

    def _terminate_known_bookkeeper(self, owner: ProcessInfo) -> None:
        current = self.process_info(owner.pid)
        if not is_known_bookkeeper_process(current):
            raise LauncherError(
                f"Refusing to stop PID {owner.pid}: its process identity changed."
            )
        if os.name != "nt":
            raise LauncherError(
                "Stopping the known Windows Bookkeeper development server is only supported on Windows."
            )
        result = self.run(
            ["taskkill", "/PID", str(owner.pid), "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 and "not found" not in (result.stderr or "").lower():
            raise LauncherError(
                f"Could not stop AI-MSME-Book-Keeper PID {owner.pid}.\n"
                f"{result.stderr or result.stdout}"
            )

    def _handle_api_port_conflict(self) -> None:
        owner = self._port_process_info(8000)
        if not is_known_bookkeeper_process(owner):
            raise self._unknown_port_error(8000, owner)
        print("Port 8000 is currently used by AI-MSME-Book-Keeper.")
        answer = self.input_fn("Stop that development server and continue? [y/N] ")
        if answer.strip().lower() not in {"y", "yes"}:
            raise PortOccupiedError(
                "AI-MSME-Book-Keeper was left running; port 8000 is still occupied."
            )
        assert owner is not None
        self._terminate_known_bookkeeper(owner)
        self._wait_for("Port 8000 to become free", lambda: not port_is_open(8000), 20)

    def ensure_api(self) -> str:
        tools = self._require_tools()
        status = self._api_probe()
        if status.state == "ready":
            self._wait_for(
                "API /ready",
                lambda: (
                    self.probe("http://localhost:8000/ready", 3.0) or HttpProbe(0, "")
                ).status
                == 200,
                10,
            )
            print("API 8000        READY (reused)")
            return "reused"
        if status.state == "occupied":
            self._handle_api_port_conflict()

        command = build_api_command(tools.uv, self.paths.root / ".uv-cache")
        record = self._start_process(
            "api", command, self.paths.root, self.env, "api.log"
        )
        try:
            self._wait_for(
                "API /health",
                lambda: is_expected_api_health(
                    self.probe("http://localhost:8000/health", 3.0)
                ),
                60,
            )
            self._wait_for(
                "API /ready",
                lambda: (
                    self.probe("http://localhost:8000/ready", 3.0) or HttpProbe(0, "")
                ).status
                == 200,
                60,
            )
        except LauncherError as error:
            error.args = (*error.args, f"See: {record['log']}")
            raise
        record["pid"] = self.listener_pid(8000) or record["pid"]
        state = self._load_state()
        state["api"] = record
        self._save_state(state)
        print("API 8000        READY (started by launch.py)")
        return "started"

    def ensure_web(self) -> str:
        state = self._load_state()
        existing = state.get("web") if isinstance(state.get("web"), dict) else None
        status = self._web_probe()
        if status.state == "ready":
            if (
                existing
                and existing.get("driver_qa")
                and self._is_record_alive_and_owned(existing)
            ):
                print("Web 3000        READY (reused)")
                return "reused"
            pid = self.listener_pid(3000)
            owner = self.process_info(pid) if pid is not None else None
            record = existing if isinstance(existing, dict) else None
            if (
                pid
                and record
                and record.get("owned")
                and record.get("pid") == pid
                and command_line_matches(
                    self.paths.root, record, self.process_command_line(pid)
                )
            ):
                print(
                    "Existing Fleet Manager web server found; restarting it with Driver QA enabled."
                )
                self._terminate_verified(record)
                self._wait_for(
                    "Web port 3000 to become free", lambda: not port_is_open(3000), 20
                )
            else:
                raise self._unknown_port_error(3000, owner)
        elif status.state == "occupied":
            raise self._unknown_port_error(3000, self._port_process_info(3000))

        tools = self._require_tools()
        command = [tools.npm, "run", "dev"]
        record = self._start_process(
            "web", command, self.paths.web, build_web_environment(self.env), "web.log"
        )
        try:
            self._wait_for(
                "Web http://localhost:3000",
                lambda: self._web_probe().state == "ready",
                90,
            )
            for name, url in ROLE_URLS.items():
                self._wait_for(
                    f"{name} role URL",
                    lambda target=url: self._url_is_ready(target),
                    30,
                )
        except LauncherError as error:
            error.args = (*error.args, f"See: {record['log']}")
            raise
        record["pid"] = self.listener_pid(3000) or record["pid"]
        state = self._load_state()
        state["web"] = record
        self._save_state(state)
        print("Web 3000        READY (started by launch.py)")
        return "started"

    def _url_is_ready(self, url: str) -> bool:
        probe = self.probe(url, 3.0)
        return probe is not None and 200 <= probe.status < 400

    def fixture_status(self, postgres: ServiceStatus | None = None) -> ServiceStatus:
        tools = self._require_tools()
        postgres = postgres or self.docker_status()[0]
        if postgres.state != "ready":
            return ServiceStatus("error", "PostgreSQL is not ready.")
        db_name = self.env.get("POSTGRES_DB", "fleet")
        db_user = self.env.get("POSTGRES_USER", "fleet")
        result = self._run_capture(
            [
                tools.docker,
                "compose",
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                db_user,
                "-d",
                db_name,
                "-tAc",
                FIXTURE_SQL,
            ],
            timeout=30,
        )
        if result.returncode != 0:
            return ServiceStatus(
                "error", result.stderr.strip() or "Fixture query failed."
            )
        value = result.stdout.strip().upper()
        if value == "READY":
            return ServiceStatus("ready")
        if value == "MISSING":
            return ServiceStatus("missing")
        return ServiceStatus("error", "Fixture query returned an unexpected result.")

    def status_snapshot(self) -> dict[str, ServiceStatus]:
        postgres, minio = self.docker_status()
        api = self._api_probe()
        web = self._web_probe()
        fixture = self.fixture_status(postgres)
        return {
            "docker": ServiceStatus(
                "ok" if postgres.state != "unavailable" else "unavailable"
            ),
            "postgres": postgres,
            "minio": minio,
            "api": api,
            "web": web,
            "fixture": fixture,
        }

    def stop_owned_processes(self) -> list[str]:
        state = self._load_state()
        stopped: list[str] = []
        changed = False
        for kind in ("api", "web"):
            record = state.get(kind)
            if not isinstance(record, dict) or not record.get("owned"):
                continue
            try:
                self._terminate_verified(record)
            except LauncherError as error:
                print(f"[WARN] {error}")
                continue
            stopped.append(kind)
            state.pop(kind, None)
            changed = True
        if changed:
            if state:
                self._save_state(state)
            elif self.paths.state.exists():
                self.paths.state.unlink()
        return stopped

    def open_role_workspaces(self) -> None:
        state = self._load_state()
        previous = state.get("browser")
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        profile_root = base / "FleetManagerRoleLab" / "profiles"
        profiles_in_use = any(
            any(
                (profile_root / role.lower().replace(" ", "-") / lock_name).exists()
                for lock_name in ("SingletonLock", "lockfile")
            )
            for role in ROLE_URLS
        )
        if (
            isinstance(previous, dict)
            and len(previous.get("workspaces", [])) == len(ROLE_URLS)
        ) or profiles_in_use:
            answer = self.input_fn(
                "Role windows may already be open. Open another set? [y/N] "
            )
            if answer.strip().lower() not in {"y", "yes"}:
                self.browser_workspaces = list(
                    previous.get("workspaces", ROLE_URLS)
                    if isinstance(previous, dict)
                    else ROLE_URLS
                )
                print(
                    "[INFO] Existing role windows left untouched; no duplicate windows opened."
                )
                return

        edge = locate_edge()
        if edge is None:
            print(
                "[INFO] Microsoft Edge was not found; open the three URLs shown below manually."
            )
            return
        opened: list[str] = []
        for role, url in ROLE_URLS.items():
            profile = profile_root / role.lower().replace(" ", "-")
            profile.mkdir(parents=True, exist_ok=True)
            try:
                self.popen(
                    build_edge_command(edge, url, profile),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                opened.append(role)
            except OSError as error:
                print(f"[WARN] Could not open {role} in Edge: {error}")
        self.browser_workspaces = opened
        if opened:
            state = self._load_state()
            state["browser"] = {
                "workspaces": opened,
                "profiles_root": str(profile_root),
                "urls": {role: ROLE_URLS[role] for role in opened},
            }
            self._save_state(state)
        if len(opened) != len(ROLE_URLS):
            print(
                f"[WARN] Opened {len(opened)} of {len(ROLE_URLS)} requested Edge workspaces."
            )

    def print_ready(self) -> None:
        driver_phone = self.env.get(
            "FLEET_PILOT_DRIVER_PHONE", "<configured local driver phone>"
        )
        print("\n" + "=" * 58)
        print("FLEET MANAGER PC ROLE LAB — READY")
        print("=" * 58)
        print("Infrastructure")
        print("PostgreSQL      READY")
        print("MinIO           READY")
        print("\nBackend")
        print("API             READY")
        print("http://localhost:8000")
        print("\nFrontend")
        print("Web             READY")
        print("http://localhost:3000")
        print("\nManual workspaces")
        print(f"OWNER\n{ROLE_URLS['OWNER']}\nPhone: {OWNER_PHONE}")
        print(f"\nSUPERVISOR\n{ROLE_URLS['SUPERVISOR']}\nPhone: {SUPERVISOR_PHONE}")
        print(f"\nDRIVER QA\n{ROLE_URLS['DRIVER QA']}\nPhone: {driver_phone}")
        print("\nPilot OTP: Configured in local .env")
        print(
            "\nExpected clean-test values: START KM 10000 · TRIPS 4 · DIESEL 30 L · END KM 10120"
        )
        print("\nManual checklist")
        print(
            "1. Owner: confirm Pilot Site, Tipper 12, Pilot Driver, Pilot Supervisor, active assignment."
        )
        print(
            "2. Driver QA: START 10000, TRIP x4, DIESEL 30 L, END 10120, one test emergency."
        )
        print(
            "3. Supervisor: confirm 8 events, evidence, approve 7 operational events, resolve emergency."
        )
        print(
            "4. Owner: confirm Trips 4, Distance 120 KM, Diesel 30 L, Pending 0, Missing KM 0."
        )
        print("\nBrowser workspaces opened:")
        if self.browser_workspaces:
            for role in self.browser_workspaces:
                phone = (
                    self.env.get(ROLE_PHONES[role], "<configured driver phone>")
                    if role == "DRIVER QA"
                    else ROLE_PHONES[role]
                )
                print(f"{role}\n{phone}")
            print(
                "Use the locally configured pilot OTP. Three isolated Edge app windows should be open."
            )
        else:
            print(
                "Open the three printed role URLs manually; no Edge windows were opened."
            )
        for warning in self.warnings:
            print(f"[WARN] {warning}")

    def start(self, *, fresh: bool = False) -> None:
        self.prepare_config()
        self.ensure_infrastructure()
        self.run_migrations()
        if fresh:
            self.reset_fixture()
        self.bootstrap_fixture()
        self.ensure_api()
        self.ensure_web()
        self.open_role_workspaces()
        self.print_ready()

    def print_status(self) -> None:
        self.prepare_config()
        snapshot = self.status_snapshot()
        print("\nFLEET MANAGER PC ROLE LAB — STATUS")
        print(f"Docker engine:   {snapshot['docker'].state.upper()}")
        print(f"PostgreSQL:      {snapshot['postgres'].state.upper()}")
        print(f"MinIO:           {snapshot['minio'].state.upper()}")
        print(f"API 8000:        {snapshot['api'].state.upper()}")
        print(f"Web 3000:        {snapshot['web'].state.upper()}")
        print(f"Pilot fixture:   {snapshot['fixture'].state.upper()}")
        for key in ("docker", "postgres", "minio", "api", "web", "fixture"):
            if snapshot[key].detail:
                print(f"  {key}: {snapshot[key].detail}")


def locate_edge() -> Path | None:
    candidates = [
        shutil.which("msedge.exe"),
        shutil.which("msedge"),
    ]
    roots = [
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("PROGRAMFILES"),
        os.environ.get("LOCALAPPDATA"),
    ]
    for root in roots:
        if root:
            candidates.append(
                str(Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
            )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def print_menu() -> None:
    print("\n" + "=" * 50)
    print("FLEET MANAGER — PC ROLE LAB")
    print("=" * 50)
    print("1. Start / continue current manual test")
    print("2. Start a FRESH manual test day")
    print("3. Check system status")
    print("4. Stop PC Role Lab")
    print("5. Exit")


def confirm_fresh_reset(input_fn: Callable[[str], str] = input) -> bool:
    print("\nWARNING:")
    print("This deletes current Pilot Construction operational TEST events,")
    print("verification history, evidence and closure records.")
    print(
        "It does not delete the company, users, memberships, site, tipper, access, or assignment."
    )
    return input_fn("Type RESET PILOT to continue: ").strip() == "RESET PILOT"


def run_menu(launcher: RoleLabLauncher, input_fn: Callable[[str], str] = input) -> int:
    while True:
        print_menu()
        choice = input_fn("Choose [1]: ").strip() or "1"
        try:
            if choice == "1":
                launcher.start()
            elif choice == "2":
                if confirm_fresh_reset(input_fn):
                    launcher.start(fresh=True)
                else:
                    print("Fresh reset cancelled; no data was changed.")
            elif choice == "3":
                launcher.print_status()
            elif choice == "4":
                stopped = launcher.stop_owned_processes()
                print(
                    "Stopped: "
                    + (
                        ", ".join(stopped)
                        if stopped
                        else "no launcher-owned API/web processes"
                    )
                )
                print("Docker services were left running; volumes were not touched.")
            elif choice == "5":
                return 0
            else:
                print("Choose 1, 2, 3, 4, or 5.")
        except LauncherError as error:
            print(f"\n[FAIL] {error}")
        except KeyboardInterrupt:
            print(
                "\nExiting without stopping services. Use option 4 to stop launcher-owned API/web processes."
            )
            return 130
    return 0


def main() -> int:
    launcher = RoleLabLauncher()
    try:
        return run_menu(launcher)
    except EOFError:
        print(
            "\nNo interactive console was available. Rerun python launch.py from a terminal."
        )
        return 2
    except Exception as error:  # unexpected programming diagnostics remain visible
        print(f"\n[FAIL] Unexpected launcher error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
