from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import launch


def valid_environment() -> dict[str, str]:
    return {
        "FLEET_ENVIRONMENT": "development",
        "FLEET_PILOT_DRIVER_PHONE": "+919606743463",
        "FLEET_JWT_SIGNING_KEY": "local-signing-key-that-is-at-least-32-characters",
        "FLEET_OTP_PROVIDER": "pilot",
        "FLEET_PILOT_OTP": "123456",
        "FLEET_CORS_ALLOWED_ORIGINS": "http://localhost:3000",
    }


def test_repository_root_resolves_from_launcher_path() -> None:
    assert launch.resolve_repo_root(Path("D:/repo/launch.py")) == Path("D:/repo")


def test_production_environment_rejects_qa_launcher() -> None:
    environment = valid_environment()
    environment["FLEET_ENVIRONMENT"] = "production"

    with pytest.raises(launch.LauncherError, match="production"):
        launch.validate_local_configuration(environment)


def test_fresh_reset_requires_exact_confirmation() -> None:
    assert launch.confirm_fresh_reset(lambda _: "reset pilot") is False
    assert launch.confirm_fresh_reset(lambda _: "RESET PILOT") is True


def test_start_continue_does_not_reset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    launcher = launch.RoleLabLauncher(paths=launch.LauncherPaths.from_root(tmp_path))
    calls: list[str] = []
    monkeypatch.setattr(launcher, "prepare_config", lambda: calls.append("config"))
    monkeypatch.setattr(
        launcher, "ensure_infrastructure", lambda: calls.append("docker")
    )
    monkeypatch.setattr(launcher, "run_migrations", lambda: calls.append("migrate"))
    monkeypatch.setattr(
        launcher, "bootstrap_fixture", lambda: calls.append("bootstrap")
    )
    monkeypatch.setattr(launcher, "ensure_api", lambda: calls.append("api") or "reused")
    monkeypatch.setattr(launcher, "ensure_web", lambda: calls.append("web") or "reused")
    monkeypatch.setattr(
        launcher, "open_role_workspaces", lambda: calls.append("browsers")
    )
    monkeypatch.setattr(launcher, "print_ready", lambda: calls.append("ready"))
    monkeypatch.setattr(launcher, "reset_fixture", lambda: calls.append("reset"))

    launcher.start()

    assert "reset" not in calls
    assert calls == [
        "config",
        "docker",
        "migrate",
        "bootstrap",
        "api",
        "web",
        "browsers",
        "ready",
    ]


def test_fresh_start_reuses_existing_reset_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    launcher = launch.RoleLabLauncher(paths=launch.LauncherPaths.from_root(tmp_path))
    calls: list[tuple[str, tuple[str, ...]]] = []
    monkeypatch.setattr(
        launcher,
        "_run_existing_script",
        lambda script, *arguments: calls.append((script, arguments)),
    )

    launcher.reset_fixture()

    assert calls == [("reset-pilot.ps1", ("-ConfirmPilotReset",))]


def test_alembic_runs_from_services_api_directory(tmp_path: Path) -> None:
    paths = launch.LauncherPaths.from_root(tmp_path)
    calls: list[dict[str, object]] = []

    def fake_run(args: list[str], **kwargs: object):
        calls.append({"args": args, **kwargs})
        return launch.subprocess.CompletedProcess(args, 0, "", "")

    launcher = launch.RoleLabLauncher(paths=paths, run=fake_run)
    launcher.tools = launch.CommandTools("docker", "uv", "npm", "python", "powershell")
    launcher.env = {}

    launcher.run_migrations()

    assert Path(str(calls[0]["cwd"])).resolve() == paths.api.resolve()
    assert (
        calls[0]["args"][-3:] == ["run", "alembic", "upgrade"]
        or "alembic" in calls[0]["args"]
    )
    assert "head" in calls[0]["args"]


def test_web_environment_always_enables_driver_qa() -> None:
    web_env = launch.build_web_environment({"FLEET_ENVIRONMENT": "development"})

    assert web_env["NEXT_PUBLIC_ENABLE_DRIVER_QA"] == "true"


def test_edge_command_isolated_app_and_first_run_safe(tmp_path: Path) -> None:
    command = launch.build_edge_command(
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        launch.ROLE_URLS["OWNER"],
        tmp_path / "FleetManagerRoleLab" / "profiles" / "owner",
    )

    assert command[1] == "--app=http://localhost:3000/owner"
    assert "--no-first-run" in command
    assert "--no-default-browser-check" in command
    assert "--disable-features=msEdgeFirstRunExperience" in command
    assert "--new-window" not in command


def test_browser_launcher_requests_three_distinct_role_profiles(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands: list[list[str]] = []

    def fake_popen(args: list[str], **_: object) -> None:
        commands.append(args)

    monkeypatch.setattr(launch, "locate_edge", lambda: Path("C:/edge/msedge.exe"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    launcher = launch.RoleLabLauncher(
        paths=launch.LauncherPaths.from_root(tmp_path), popen=fake_popen
    )

    launcher.open_role_workspaces()

    assert len(commands) == 3
    profiles = [
        next(item for item in command if item.startswith("--user-data-dir="))
        for command in commands
    ]
    assert len(set(profiles)) == 3
    assert all("FleetManagerRoleLab\\profiles" in profile for profile in profiles)
    assert all("--no-first-run" in command for command in commands)
    assert all("--no-default-browser-check" in command for command in commands)
    assert all(
        "--disable-features=msEdgeFirstRunExperience" in command for command in commands
    )
    assert all("--app=http://localhost:3000/" in command[1] for command in commands)
    assert all("Microsoft\\Edge\\User Data" not in profile for profile in profiles)


def test_browser_rerun_defaults_to_no_duplicate_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands: list[list[str]] = []
    launcher = launch.RoleLabLauncher(
        paths=launch.LauncherPaths.from_root(tmp_path),
        popen=lambda args, **_: commands.append(args),
        input_fn=lambda _: "",
    )
    launcher._save_state({"browser": {"workspaces": list(launch.ROLE_URLS)}})
    monkeypatch.setattr(launch, "locate_edge", lambda: Path("C:/edge/msedge.exe"))

    launcher.open_role_workspaces()

    assert commands == []


def test_browser_profile_lock_prevents_duplicates_without_launcher_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands: list[list[str]] = []
    local_app_data = tmp_path / "local-app-data"
    (local_app_data / "FleetManagerRoleLab" / "profiles" / "owner").mkdir(parents=True)
    (local_app_data / "FleetManagerRoleLab" / "profiles" / "owner" / "lockfile").touch()
    launcher = launch.RoleLabLauncher(
        paths=launch.LauncherPaths.from_root(tmp_path),
        popen=lambda args, **_: commands.append(args),
        input_fn=lambda _: "",
    )
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setattr(launch, "locate_edge", lambda: Path("C:/edge/msedge.exe"))

    launcher.open_role_workspaces()

    assert commands == []
    assert launcher.browser_workspaces == list(launch.ROLE_URLS)


def test_start_calls_browser_launcher_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    launcher = launch.RoleLabLauncher(paths=launch.LauncherPaths.from_root(tmp_path))
    calls: list[str] = []
    monkeypatch.setattr(launcher, "prepare_config", lambda: calls.append("config"))
    monkeypatch.setattr(
        launcher, "ensure_infrastructure", lambda: calls.append("docker")
    )
    monkeypatch.setattr(launcher, "run_migrations", lambda: calls.append("migrate"))
    monkeypatch.setattr(
        launcher, "bootstrap_fixture", lambda: calls.append("bootstrap")
    )
    monkeypatch.setattr(launcher, "ensure_api", lambda: calls.append("api") or "reused")
    monkeypatch.setattr(launcher, "ensure_web", lambda: calls.append("web") or "reused")
    monkeypatch.setattr(
        launcher, "open_role_workspaces", lambda: calls.append("browsers")
    )
    monkeypatch.setattr(launcher, "print_ready", lambda: calls.append("ready"))

    launcher.start()

    assert calls.count("browsers") == 1


def test_unknown_port_process_is_not_safe_to_stop(tmp_path: Path) -> None:
    launcher = launch.RoleLabLauncher(
        paths=launch.LauncherPaths.from_root(tmp_path),
        process_command_line=lambda _: r"C:\Other\unrelated.exe",
    )
    record = {"kind": "web", "pid": 1234, "owned": False}

    with pytest.raises(launch.LauncherError, match="identity"):
        launcher._terminate_verified(record, allow_external=True)


def test_status_path_has_no_reset_or_bootstrap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    launcher = launch.RoleLabLauncher(paths=launch.LauncherPaths.from_root(tmp_path))
    launcher.tools = launch.CommandTools("docker", "uv", "npm", "python", "powershell")
    launcher.env = {"POSTGRES_DB": "fleet", "POSTGRES_USER": "fleet"}
    monkeypatch.setattr(
        launcher,
        "docker_status",
        lambda: (launch.ServiceStatus("not ready"), launch.ServiceStatus("not ready")),
    )
    monkeypatch.setattr(launcher, "_api_probe", lambda: launch.ServiceStatus("stopped"))
    monkeypatch.setattr(launcher, "_web_probe", lambda: launch.ServiceStatus("stopped"))
    monkeypatch.setattr(
        launcher, "reset_fixture", lambda: pytest.fail("status reset business data")
    )
    monkeypatch.setattr(
        launcher, "bootstrap_fixture", lambda: pytest.fail("status bootstrapped data")
    )

    snapshot = launcher.status_snapshot()

    assert snapshot["fixture"].state == "error"


def test_stop_ignores_unowned_process_records(tmp_path: Path) -> None:
    launcher = launch.RoleLabLauncher(paths=launch.LauncherPaths.from_root(tmp_path))
    launcher._save_state({"api": {"kind": "api", "pid": 1234, "owned": False}})

    assert launcher.stop_owned_processes() == []


def test_ready_summary_does_not_print_secrets(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    launcher = launch.RoleLabLauncher(paths=launch.LauncherPaths.from_root(tmp_path))
    secret_otp = "908172"
    secret_jwt = "another-local-jwt-secret-that-must-not-print"
    launcher.env = {
        "FLEET_PILOT_DRIVER_PHONE": "+919606743463",
        "FLEET_PILOT_OTP": secret_otp,
        "FLEET_JWT_SIGNING_KEY": secret_jwt,
    }

    launcher.print_ready()
    output = capsys.readouterr().out

    assert secret_otp not in output
    assert secret_jwt not in output
    assert "Configured in local .env" in output
