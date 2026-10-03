from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import server_manager


def test_evidence_snapshot_has_verified_hash_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "active-evidence"
    object_file = source / "objects" / "companies" / "one" / "photo.jpg"
    metadata_file = source / ".fleet-metadata" / "companies" / "one" / "photo.jpg.json"
    object_file.parent.mkdir(parents=True)
    metadata_file.parent.mkdir(parents=True)
    object_file.write_bytes(b"\xff\xd8\xffevidence")
    metadata_file.write_text('{"content_type":"image/jpeg"}', encoding="utf-8")
    backup_root = tmp_path / "backup"
    monkeypatch.setattr(server_manager, "EVIDENCE_BACKUP_ROOT", backup_root)

    snapshot, manifest_path, manifest = server_manager.create_evidence_snapshot(
        source, "20261001-120000+0530"
    )

    assert snapshot == backup_root / "20261001-120000+0530"
    assert manifest_path == snapshot / server_manager.EVIDENCE_MANIFEST_NAME
    assert manifest["file_count"] == 2
    assert manifest["secrets_included"] is False
    assert server_manager.verify_evidence_snapshot(snapshot) == manifest


def test_evidence_snapshot_verification_detects_tampering(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "active-evidence"
    source.mkdir()
    (source / "object.bin").write_bytes(b"original")
    monkeypatch.setattr(server_manager, "EVIDENCE_BACKUP_ROOT", tmp_path / "backup")
    snapshot, _, _ = server_manager.create_evidence_snapshot(
        source, "20261001-120001+0530"
    )
    (snapshot / "object.bin").write_bytes(b"tampered")

    with pytest.raises(server_manager.ServerError, match="hash verification"):
        server_manager.verify_evidence_snapshot(snapshot)


@pytest.mark.parametrize(
    "relative",
    ["../outside", r"..\outside", "/absolute", r"C:\outside", "safe/../outside"],
)
def test_evidence_manifest_rejects_unsafe_paths(tmp_path: Path, relative: str) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    manifest = {
        "format_version": 1,
        "files": [{"path": relative, "size": 0, "sha256": "0" * 64}],
    }
    (snapshot / server_manager.EVIDENCE_MANIFEST_NAME).write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    with pytest.raises(server_manager.ServerError, match="unsafe path"):
        server_manager.verify_evidence_snapshot(snapshot)


def test_server_start_requests_only_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []

    def record(args: list[str], **_: object) -> None:
        commands.append(args)

    monkeypatch.setattr(server_manager, "checked", record)
    monkeypatch.setattr(
        server_manager, "compose_health", lambda *_: {"postgres": "healthy"}
    )

    server_manager.ensure_infrastructure("docker", {})

    assert commands == [["docker", "compose", "up", "-d", "postgres"]]


def test_stop_targets_only_owned_api_and_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(server_manager, "require_runtime", lambda: ("docker", {}))
    monkeypatch.setattr(server_manager, "stop_api", lambda: calls.append("api") or 0)
    monkeypatch.setattr(server_manager, "docker_ready", lambda _: True)
    monkeypatch.setattr(
        server_manager,
        "checked",
        lambda args, **_: calls.append(args),
    )

    assert server_manager.stop_server() == 0
    assert calls == ["api", ["docker", "compose", "stop", "postgres"]]


def test_remote_access_requires_private_serve_and_healthy_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dns_name = "fleet-host.example.ts.net"
    status_payload = {
        "BackendState": "Running",
        "Self": {"Online": True, "DNSName": f"{dns_name}."},
    }
    serve_payload = {
        "TCP": {"443": {"HTTPS": True}},
        "Web": {
            f"{dns_name}:443": {
                "Handlers": {
                    "/": {"Proxy": server_manager.TAILSCALE_PROXY_TARGET},
                    f"{server_manager.TAILSCALE_PILOT_PATH}/": {
                        "Path": str(server_manager.PILOT_RELEASE_DIR)
                    },
                }
            }
        },
    }

    def capture(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        payload = status_payload if args[1] == "status" else serve_payload
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    def probe(url: str, timeout: float = 3.0) -> SimpleNamespace:
        del timeout
        if url.endswith("/health"):
            return SimpleNamespace(
                status=200,
                body='{"status":"ok","service":"fleet-manager-api"}',
            )
        return SimpleNamespace(status=200, body='{"status":"ready"}')

    monkeypatch.setattr(server_manager, "tailscale_executable", lambda: "tailscale")
    monkeypatch.setattr(server_manager, "tailscale_service_status", lambda: "RUNNING")
    monkeypatch.setattr(server_manager, "run_capture", capture)
    monkeypatch.setattr(server_manager, "default_http_probe", probe)

    assert server_manager.remote_access_status() == {
        "remote": "ONLINE",
        "remote_url": f"https://{dns_name}",
        "tailscale": "ONLINE",
        "tailscale_service": "RUNNING",
        "funnel": "OFF",
        "serve_root": "OK",
        "serve_pilot": "OK",
        "remote_health": "OK",
        "remote_ready": "OK",
        "reason": "",
    }


def test_funnel_configuration_never_reports_remote_online(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dns_name = "fleet-host.example.ts.net"
    status_payload = {
        "BackendState": "Running",
        "Self": {"Online": True, "DNSName": f"{dns_name}."},
    }
    serve_payload = {
        "TCP": {"443": {"HTTPS": True}},
        "AllowFunnel": {f"{dns_name}:443": True},
        "Web": {
            f"{dns_name}:443": {
                "Handlers": {"/": {"Proxy": server_manager.TAILSCALE_PROXY_TARGET}}
            }
        },
    }

    def capture(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        payload = status_payload if args[1] == "status" else serve_payload
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    monkeypatch.setattr(server_manager, "tailscale_executable", lambda: "tailscale")
    monkeypatch.setattr(server_manager, "tailscale_service_status", lambda: "RUNNING")
    monkeypatch.setattr(server_manager, "run_capture", capture)

    status = server_manager.remote_access_status()

    assert status["funnel"] == "ON"
    assert status["remote"] == "OFFLINE"


def test_start_check_self_heals_only_missing_pilot_serve(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dns_name = "fleet-host.example.ts.net"
    release = tmp_path / "pilot"
    release.mkdir()
    monkeypatch.setattr(server_manager, "PILOT_RELEASE_DIR", release)
    status_payload = {
        "BackendState": "Running",
        "Self": {"Online": True, "DNSName": f"{dns_name}."},
    }
    root_only = {
        "Web": {
            f"{dns_name}:443": {
                "Handlers": {"/": {"Proxy": server_manager.TAILSCALE_PROXY_TARGET}}
            }
        }
    }
    complete = {
        "Web": {
            f"{dns_name}:443": {
                "Handlers": {
                    "/": {"Proxy": server_manager.TAILSCALE_PROXY_TARGET},
                    f"{server_manager.TAILSCALE_PILOT_PATH}/": {"Path": str(release)},
                }
            }
        }
    }
    serve_status_calls = 0
    commands: list[list[str]] = []

    def capture(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal serve_status_calls
        if args[1:] == ["status", "--json"]:
            payload = status_payload
        elif args[1:] == ["funnel", "status", "--json"]:
            payload = root_only
        elif args[1:] == ["serve", "status", "--json"]:
            serve_status_calls += 1
            payload = root_only if serve_status_calls == 1 else complete
        else:
            commands.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    monkeypatch.setattr(server_manager, "tailscale_executable", lambda: "tailscale")
    monkeypatch.setattr(server_manager, "tailscale_service_status", lambda: "RUNNING")
    monkeypatch.setattr(server_manager, "run_capture", capture)
    monkeypatch.setattr(
        server_manager,
        "default_http_probe",
        lambda *_args, **_kwargs: SimpleNamespace(
            status=200, body='{"status":"ok","service":"fleet-manager-api"}'
        ),
    )

    status = server_manager.remote_access_status(ensure_serve=True)

    assert status["remote"] == "ONLINE"
    assert status["serve_root"] == "OK"
    assert status["serve_pilot"] == "OK"
    assert status["reason"] == ""
    assert commands == [
        [
            "tailscale",
            "serve",
            "--bg",
            "--set-path",
            "/pilot",
            str(release),
        ]
    ]


def test_pilot_serve_admin_requirement_does_not_break_remote_api(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dns_name = "fleet-host.example.ts.net"
    release = tmp_path / "pilot"
    release.mkdir()
    monkeypatch.setattr(server_manager, "PILOT_RELEASE_DIR", release)
    status_payload = {
        "BackendState": "Running",
        "Self": {"Online": True, "DNSName": f"{dns_name}."},
    }
    serve_payload = {
        "Web": {
            f"{dns_name}:443": {
                "Handlers": {"/": {"Proxy": server_manager.TAILSCALE_PROXY_TARGET}}
            }
        }
    }

    def capture(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if args[1:] == ["status", "--json"]:
            payload = status_payload
        elif args[1:] in (
            ["serve", "status", "--json"],
            ["funnel", "status", "--json"],
        ):
            payload = serve_payload
        else:
            return subprocess.CompletedProcess(args, 1, "", "must be a local admin")
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    monkeypatch.setattr(server_manager, "tailscale_executable", lambda: "tailscale")
    monkeypatch.setattr(server_manager, "tailscale_service_status", lambda: "RUNNING")
    monkeypatch.setattr(server_manager, "run_capture", capture)
    monkeypatch.setattr(
        server_manager,
        "default_http_probe",
        lambda *_args, **_kwargs: SimpleNamespace(
            status=200, body='{"status":"ok","service":"fleet-manager-api"}'
        ),
    )

    status = server_manager.remote_access_status(ensure_serve=True)

    assert status["remote"] == "ONLINE"
    assert status["serve_pilot"] == "MISSING"
    assert status["reason"] == "PILOT SERVE ADMIN APPROVAL REQUIRED"


def test_tailscale_needs_login_reports_security_boundary_without_serve_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def capture(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        payload = {"BackendState": "NeedsLogin"}
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    monkeypatch.setattr(server_manager, "tailscale_executable", lambda: "tailscale")
    monkeypatch.setattr(server_manager, "tailscale_service_status", lambda: "RUNNING")
    monkeypatch.setattr(server_manager, "run_capture", capture)

    status = server_manager.remote_access_status(ensure_serve=True)

    assert status["remote"] == "OFFLINE"
    assert status["reason"] == "TAILSCALE LOGIN REQUIRED"
    assert calls == [["tailscale", "status", "--json"]]


def test_remote_outage_does_not_fail_local_server_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_manager, "require_runtime", lambda: ("docker", {}))
    monkeypatch.setattr(
        server_manager,
        "component_status",
        lambda *_: {
            "docker": "OK",
            "postgres": "OK",
            "evidence": "OK",
            "api": "OK",
            "health": "OK",
            "ready": "OK",
            "remote": "OFFLINE",
            "remote_url": "",
            "tailscale": "OFFLINE",
            "funnel": "UNKNOWN",
        },
    )

    assert server_manager.check_server() == 0


def test_pilot_apk_absence_is_not_a_server_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = tmp_path / "pilot"
    release.mkdir()
    monkeypatch.setattr(server_manager, "PILOT_RELEASE_DIR", release)

    status = server_manager.pilot_release_status("https://fleet.example.ts.net")

    assert status["pilot_directory"] == "OK"
    assert status["pilot_apk"] == "NOT PUBLISHED"
    assert status["apk_url"] == ""


def test_pilot_publisher_status_is_independent_of_api_health(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    status_file = tmp_path / "publisher-status.json"
    status_file.write_text(
        json.dumps(
            {
                "state": "READY",
                "updatedAt": server_manager.datetime.now(
                    server_manager.UTC
                ).isoformat(),
                "detail": "Waiting for a complete pilot release pair.",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(server_manager, "PILOT_PUBLISHER_STATUS_FILE", status_file)

    status = server_manager.pilot_publisher_status()

    assert status["pilot_publisher"] == "READY"
    assert "pilot_publisher" not in server_manager.LOCAL_STATUS_KEYS


def test_pilot_apk_status_creates_and_verifies_sha256(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = tmp_path / "pilot"
    release.mkdir()
    apk = release / server_manager.PILOT_APK_NAME
    apk.write_bytes(b"verified pilot apk")
    monkeypatch.setattr(server_manager, "PILOT_RELEASE_DIR", release)

    status = server_manager.pilot_release_status("https://fleet.example.ts.net")

    digest = server_manager.sha256(apk)
    assert status["pilot_apk"] == "PUBLISHED"
    assert status["apk_url"].endswith(f"/pilot/{server_manager.PILOT_APK_NAME}")
    assert (release / server_manager.PILOT_SHA256_NAME).read_text(
        encoding="utf-8"
    ) == f"{digest}  {server_manager.PILOT_APK_NAME}\n"


def test_pilot_apk_status_warns_on_inconsistent_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = tmp_path / "pilot"
    release.mkdir()
    (release / server_manager.PILOT_APK_NAME).write_bytes(b"verified pilot apk")
    (release / server_manager.PILOT_SHA256_NAME).write_text(
        f"{'0' * 64}  {server_manager.PILOT_APK_NAME}\n", encoding="utf-8"
    )
    monkeypatch.setattr(server_manager, "PILOT_RELEASE_DIR", release)

    status = server_manager.pilot_release_status()

    assert status["pilot_apk"] == "WARNING"
    assert "inconsistent" in status["pilot_warning"]


def test_publish_pilot_apk_uses_verified_atomic_destination(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "built.apk"
    source.write_bytes(b"signed elsewhere")
    (source_dir / server_manager.PILOT_VERSION_NAME).write_text(
        "1.2.3+45\n", encoding="utf-8"
    )
    release = tmp_path / "release" / "pilot"
    monkeypatch.setattr(server_manager, "PILOT_RELEASE_DIR", release)
    monkeypatch.setattr(
        server_manager,
        "remote_access_status",
        lambda **_kwargs: {
            "remote": "ONLINE",
            "remote_url": "https://fleet.example.ts.net",
            "serve_pilot": "OK",
        },
    )
    monkeypatch.setattr(
        server_manager,
        "default_http_probe",
        lambda *_args, **_kwargs: SimpleNamespace(status=200, body=""),
    )

    assert server_manager.publish_pilot_apk(source) == 0

    published = release / server_manager.PILOT_APK_NAME
    assert published.read_bytes() == source.read_bytes()
    assert (release / server_manager.PILOT_VERSION_NAME).read_text(
        encoding="utf-8"
    ) == "1.2.3+45\n"
    assert not list(release.glob("*.tmp"))


def test_publish_rejects_missing_version_metadata_before_copy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "built.apk"
    source.write_bytes(b"signed elsewhere")
    release = tmp_path / "release" / "pilot"
    monkeypatch.setattr(server_manager, "PILOT_RELEASE_DIR", release)

    with pytest.raises(server_manager.ServerError, match="version metadata"):
        server_manager.publish_pilot_apk(source, tmp_path / "missing-version.txt")

    assert not (release / server_manager.PILOT_APK_NAME).exists()


def deployment_state(
    *,
    dependencies_current: bool = True,
    database_current: bool = True,
    database_revisions: tuple[str, ...] = ("0017_internal_ids",),
    repository_heads: tuple[str, ...] = ("0017_internal_ids",),
    api_running: bool = True,
    api_stale: bool = False,
    health_ok: bool = True,
    ready_ok: bool = True,
    remote_current: bool = True,
) -> server_manager.DeploymentState:
    return server_manager.DeploymentState(
        dependencies_current=dependencies_current,
        database_current=database_current,
        database_revisions=database_revisions,
        repository_heads=repository_heads,
        api_running=api_running,
        api_stale=api_stale,
        health_ok=health_ok,
        ready_ok=ready_ok,
        remote_current=remote_current,
    )


def mock_database_revision_rows(
    monkeypatch: pytest.MonkeyPatch, rows: list[object]
) -> None:
    class Result:
        def scalars(self) -> Result:
            return self

        def all(self) -> list[object]:
            return rows

    class Connection:
        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, _: object) -> Result:
            return Result()

    class Engine:
        def connect(self) -> Connection:
            return Connection()

        def dispose(self) -> None:
            return None

    monkeypatch.setattr(server_manager, "create_engine", lambda *_, **__: Engine())


def test_database_revision_current_returns_single_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_database_revision_rows(monkeypatch, ["0017_internal_ids"])

    assert server_manager._database_alembic_revisions(
        {"FLEET_DATABASE_URL": "postgresql+psycopg://example.invalid/fleet"}
    ) == ("0017_internal_ids",)


def test_database_revision_wrong_value_requires_migration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_database_revision_rows(monkeypatch, ["0016_report_templates"])

    revisions = server_manager._database_alembic_revisions(
        {"FLEET_DATABASE_URL": "postgresql+psycopg://example.invalid/fleet"}
    )

    assert revisions != ("0017_internal_ids",)


@pytest.mark.parametrize("rows", [[], ["0016_report_templates", "0017_internal_ids"]])
def test_database_revision_refuses_missing_or_multiple_rows(
    monkeypatch: pytest.MonkeyPatch, rows: list[object]
) -> None:
    mock_database_revision_rows(monkeypatch, rows)

    with pytest.raises(server_manager.ServerError, match="exactly one revision row"):
        server_manager._database_alembic_revisions(
            {"FLEET_DATABASE_URL": "postgresql+psycopg://example.invalid/fleet"}
        )


@pytest.mark.parametrize("value", ["", "   ", None, 17])
def test_database_revision_refuses_malformed_value(
    monkeypatch: pytest.MonkeyPatch, value: object
) -> None:
    mock_database_revision_rows(monkeypatch, [value])

    with pytest.raises(server_manager.ServerError, match="invalid revision value"):
        server_manager._database_alembic_revisions(
            {"FLEET_DATABASE_URL": "postgresql+psycopg://example.invalid/fleet"}
        )


def test_database_revision_timeout_is_distinct_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timed_out(*_: object, **__: object) -> None:
        raise server_manager.OperationalError(
            None, {}, TimeoutError("connection timed out")
        )

    monkeypatch.setattr(server_manager, "create_engine", timed_out)

    with pytest.raises(server_manager.ServerError, match="timed out while connecting"):
        server_manager._database_alembic_revisions(
            {"FLEET_DATABASE_URL": "postgresql+psycopg://example.invalid/fleet"}
        )


def test_database_revision_unreachable_is_distinct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unreachable(*_: object, **__: object) -> None:
        raise server_manager.OperationalError(
            None, {}, ConnectionRefusedError("connection refused")
        )

    monkeypatch.setattr(server_manager, "create_engine", unreachable)

    with pytest.raises(server_manager.ServerError, match="could not connect"):
        server_manager._database_alembic_revisions(
            {"FLEET_DATABASE_URL": "postgresql+psycopg://example.invalid/fleet"}
        )


def test_server_environment_removes_test_database_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            (
                "FLEET_ENVIRONMENT=pilot",
                "FLEET_DATABASE_URL=postgresql+psycopg://server.invalid/fleet",
                "FLEET_JWT_SIGNING_KEY=test-signing-key",
                "FLEET_OBJECT_STORAGE_PROVIDER=filesystem",
                f"FLEET_FILESYSTEM_STORAGE_ROOT={tmp_path / 'evidence'}",
                "POSTGRES_DB=fleet",
                "POSTGRES_USER=fleet",
                "POSTGRES_PASSWORD=test-password",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(server_manager, "ENV_FILE", env_file)
    monkeypatch.delenv("FLEET_DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "FLEET_TEST_DATABASE_URL", "postgresql+psycopg://test.invalid/fleet_test"
    )

    environment = server_manager.load_server_environment()

    assert environment["FLEET_DATABASE_URL"].endswith("server.invalid/fleet")
    assert "FLEET_TEST_DATABASE_URL" not in environment


def mock_current_git(monkeypatch: pytest.MonkeyPatch, current: str) -> None:
    def git_output(*args: str, **_: object) -> str:
        values = {
            ("status", "--porcelain", "--untracked-files=normal"): "",
            ("branch", "--show-current"): "main",
            ("remote", "get-url", "origin"): "https://example.invalid/fleet.git",
            ("rev-parse", "HEAD"): current,
            ("fetch", "origin"): "",
            ("rev-parse", "origin/main"): current,
        }
        return values[args]

    monkeypatch.setattr(server_manager, "git_output", git_output)


def configure_current_repair(
    monkeypatch: pytest.MonkeyPatch,
    *,
    before: server_manager.DeploymentState,
    events: list[str],
    backup: Path,
    database_revisions: tuple[str, ...] = ("0017_internal_ids",),
) -> None:
    states = iter((before, deployment_state()))

    def create_backup() -> Path:
        events.append("backup")
        return backup

    def stop_api() -> int:
        events.append("stop")
        return 0

    monkeypatch.setattr(server_manager, "_deployment_state", lambda _: next(states))
    monkeypatch.setattr(server_manager, "_require_verified_backup", create_backup)
    monkeypatch.setattr(server_manager, "stop_api", stop_api)
    monkeypatch.setattr(server_manager, "_locked_dependencies_current", lambda: True)
    monkeypatch.setattr(server_manager, "load_server_environment", lambda: {})
    monkeypatch.setattr(
        server_manager,
        "_repository_alembic_heads",
        lambda: ("0017_internal_ids",),
    )
    monkeypatch.setattr(
        server_manager,
        "_database_alembic_revisions",
        lambda _: database_revisions,
    )

    def checked(
        args: list[str], *, label: str, **_: object
    ) -> subprocess.CompletedProcess[str]:
        del args
        events.append("start" if label == "Fleet Manager restart" else "migrate")
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(server_manager, "checked", checked)


def test_update_already_current_exits_before_backup(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    current = "a" * 40

    def git_output(*args: str, **_: object) -> str:
        values = {
            ("status", "--porcelain", "--untracked-files=normal"): "",
            ("branch", "--show-current"): "main",
            ("remote", "get-url", "origin"): "https://example.invalid/fleet.git",
            ("rev-parse", "HEAD"): current,
            ("fetch", "origin"): "",
            ("rev-parse", "origin/main"): current,
        }
        return values[args]

    monkeypatch.setattr(server_manager, "git_output", git_output)
    monkeypatch.setattr(
        server_manager, "_deployment_state", lambda _: deployment_state()
    )
    monkeypatch.setattr(
        server_manager,
        "backup_server",
        lambda: pytest.fail("already-current update must not create a backup"),
    )

    assert server_manager.update_server() == 0
    output = capsys.readouterr().out
    assert "ALREADY UP TO DATE" in output
    assert "SOURCE          CURRENT" in output
    assert "DATABASE        CURRENT" in output
    assert "API             CURRENT" in output
    assert current in output


def test_update_unknown_database_revision_never_reports_current(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    current = "a" * 40
    mock_current_git(monkeypatch, current)
    monkeypatch.setattr(
        server_manager,
        "_deployment_state",
        lambda _: (_ for _ in ()).throw(
            server_manager.ServerError("Database revision check timed out")
        ),
    )
    monkeypatch.setattr(
        server_manager,
        "backup_server",
        lambda: pytest.fail("unknown revision must fail before backup"),
    )

    with pytest.raises(server_manager.ServerError, match="revision check timed out"):
        server_manager.update_server()

    assert "ALREADY UP TO DATE" not in capsys.readouterr().out


def test_update_git_current_database_behind_migrates_without_pull(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    current = "a" * 40
    backup = Path(r"F:\FleetManagerBackups\releases\test\server-backup-manifest.json")
    events: list[str] = []
    mock_current_git(monkeypatch, current)
    configure_current_repair(
        monkeypatch,
        before=deployment_state(
            database_current=False,
            database_revisions=("0016_report_templates",),
        ),
        events=events,
        backup=backup,
        database_revisions=("0016_report_templates",),
    )

    assert server_manager.update_server() == 0
    assert events == ["backup", "stop", "migrate", "start"]
    output = capsys.readouterr().out
    assert "SOURCE          CURRENT" in output
    assert "DATABASE        MIGRATION REQUIRED" in output
    assert "UPDATE COMPLETE" in output


def test_update_git_current_stale_api_restarts_without_migration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    current = "a" * 40
    backup = Path(r"F:\FleetManagerBackups\releases\test\server-backup-manifest.json")
    events: list[str] = []
    mock_current_git(monkeypatch, current)
    configure_current_repair(
        monkeypatch,
        before=deployment_state(api_stale=True),
        events=events,
        backup=backup,
    )

    assert server_manager.update_server() == 0
    assert events == ["backup", "stop", "start"]
    assert "STALE PROCESS - RESTART REQUIRED" in capsys.readouterr().out


def test_update_git_current_stopped_api_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = "a" * 40
    backup = Path(r"F:\FleetManagerBackups\releases\test\server-backup-manifest.json")
    events: list[str] = []
    mock_current_git(monkeypatch, current)
    configure_current_repair(
        monkeypatch,
        before=deployment_state(api_running=False, health_ok=False, ready_ok=False),
        events=events,
        backup=backup,
    )

    assert server_manager.update_server() == 0
    assert events == ["backup", "stop", "start"]


def test_update_git_current_unhealthy_api_restarts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = "a" * 40
    backup = Path(r"F:\FleetManagerBackups\releases\test\server-backup-manifest.json")
    events: list[str] = []
    mock_current_git(monkeypatch, current)
    configure_current_repair(
        monkeypatch,
        before=deployment_state(health_ok=False, ready_ok=False),
        events=events,
        backup=backup,
    )

    assert server_manager.update_server() == 0
    assert events == ["backup", "stop", "start"]


def test_update_syncs_only_when_locked_environment_is_outdated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = "a" * 40
    backup = Path(r"F:\FleetManagerBackups\releases\test\server-backup-manifest.json")
    events: list[str] = []
    mock_current_git(monkeypatch, current)
    configure_current_repair(
        monkeypatch,
        before=deployment_state(dependencies_current=False),
        events=events,
        backup=backup,
    )
    monkeypatch.setattr(server_manager, "_locked_dependencies_current", lambda: False)
    monkeypatch.setattr(
        server_manager,
        "_sync_locked_dependencies",
        lambda: events.append("sync"),
    )

    assert server_manager.update_server() == 0
    assert events == ["backup", "stop", "sync", "start"]


def test_update_refuses_dirty_worktree_before_backup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        server_manager,
        "git_output",
        lambda *args, **_: " M scripts/server_manager.py"
        if args == ("status", "--porcelain", "--untracked-files=normal")
        else pytest.fail(f"unexpected Git call: {args}"),
    )
    monkeypatch.setattr(
        server_manager,
        "backup_server",
        lambda: pytest.fail("dirty-tree update must not create a backup"),
    )

    with pytest.raises(server_manager.ServerError, match="working tree is not clean"):
        server_manager.update_server()


def test_api_staleness_uses_recorded_commit_and_legacy_start_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = "b" * 40
    assert server_manager._api_process_is_stale({"repository_head": "a" * 40}, current)
    assert not server_manager._api_process_is_stale(
        {"repository_head": current}, current
    )

    monkeypatch.setattr(server_manager, "_latest_deployment_source_mtime", lambda: 20.0)
    assert server_manager._api_process_is_stale(
        {"started_at": "1970-01-01T00:00:10+00:00"}, current
    )


def test_update_refuses_non_fast_forward_before_backup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = "a" * 40
    target = "b" * 40

    def git_output(*args: str, **_: object) -> str:
        values = {
            ("status", "--porcelain", "--untracked-files=normal"): "",
            ("branch", "--show-current"): "main",
            ("remote", "get-url", "origin"): "https://example.invalid/fleet.git",
            ("rev-parse", "HEAD"): old,
            ("fetch", "origin"): "",
            ("rev-parse", "origin/main"): target,
        }
        return values[args]

    monkeypatch.setattr(server_manager, "git_output", git_output)
    monkeypatch.setattr(
        server_manager,
        "run_capture",
        lambda args, **_: subprocess.CompletedProcess(args, 1, "", ""),
    )
    monkeypatch.setattr(
        server_manager,
        "backup_server",
        lambda: pytest.fail("non-fast-forward update must not create a backup"),
    )

    with pytest.raises(server_manager.ServerError, match="fast-forward"):
        server_manager.update_server()


def test_update_git_behind_runs_backup_pull_migrate_and_restart(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    old = "a" * 40
    target = "b" * 40
    backup = Path(r"F:\FleetManagerBackups\releases\test\server-backup-manifest.json")
    head = old
    events: list[str] = []

    def git_output(*args: str, **_: object) -> str:
        nonlocal head
        if args == ("status", "--porcelain", "--untracked-files=normal"):
            return ""
        if args == ("branch", "--show-current"):
            return "main"
        if args == ("remote", "get-url", "origin"):
            return "https://example.invalid/fleet.git"
        if args == ("rev-parse", "HEAD"):
            return head
        if args == ("fetch", "origin"):
            return ""
        if args == ("rev-parse", "origin/main"):
            return target
        if args == ("pull", "--ff-only", "origin", "main"):
            events.append("pull")
            head = target
            return ""
        raise AssertionError(f"unexpected git call: {args}")

    states = iter(
        (
            deployment_state(
                database_revisions=("0016_report_templates",),
                repository_heads=("0016_report_templates",),
            ),
            deployment_state(),
        )
    )

    def checked(
        args: list[str], *, label: str, **_: object
    ) -> subprocess.CompletedProcess[str]:
        del args
        events.append("start" if label == "Fleet Manager restart" else "migrate")
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(server_manager, "git_output", git_output)
    monkeypatch.setattr(
        server_manager,
        "run_capture",
        lambda args, **_: subprocess.CompletedProcess(args, 0, "", ""),
    )
    monkeypatch.setattr(
        server_manager,
        "_deployment_state",
        lambda _: next(states),
    )

    def create_backup() -> Path:
        events.append("backup")
        return backup

    def stop_api() -> int:
        events.append("stop")
        return 0

    monkeypatch.setattr(server_manager, "_require_verified_backup", create_backup)
    monkeypatch.setattr(server_manager, "stop_api", stop_api)
    monkeypatch.setattr(server_manager, "load_server_environment", lambda: {})
    monkeypatch.setattr(
        server_manager,
        "_locked_dependencies_current",
        lambda: True,
    )
    monkeypatch.setattr(
        server_manager,
        "_repository_alembic_heads",
        lambda: ("0017_internal_ids",),
    )
    monkeypatch.setattr(
        server_manager,
        "_database_alembic_revisions",
        lambda _: ("0016_report_templates",),
    )
    monkeypatch.setattr(server_manager, "checked", checked)

    assert server_manager.update_server() == 0
    assert events == ["backup", "stop", "pull", "migrate", "start"]
    output = capsys.readouterr().out
    assert "UPDATE COMPLETE" in output
    assert old in output
    assert target in output
    assert str(backup) in output


def test_update_migration_failure_reports_and_keeps_backup(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    old = "a" * 40
    target = old
    backup = Path(r"F:\FleetManagerBackups\releases\test\server-backup-manifest.json")

    def git_output(*args: str, **_: object) -> str:
        values = {
            ("status", "--porcelain", "--untracked-files=normal"): "",
            ("branch", "--show-current"): "main",
            ("remote", "get-url", "origin"): "https://example.invalid/fleet.git",
            ("fetch", "origin"): "",
            ("rev-parse", "origin/main"): target,
            ("rev-parse", "HEAD"): old,
        }
        return values[args]

    def checked(
        args: list[str], *, label: str, **_: object
    ) -> subprocess.CompletedProcess[str]:
        del args
        if label == "Alembic upgrade":
            raise server_manager.ServerError("migration failed safely")
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(server_manager, "git_output", git_output)
    monkeypatch.setattr(
        server_manager,
        "_deployment_state",
        lambda _: deployment_state(
            database_current=False,
            database_revisions=("0016_report_templates",),
        ),
    )
    monkeypatch.setattr(server_manager, "_require_verified_backup", lambda: backup)
    monkeypatch.setattr(server_manager, "stop_api", lambda: 0)
    monkeypatch.setattr(server_manager, "load_server_environment", lambda: {})
    monkeypatch.setattr(server_manager, "_locked_dependencies_current", lambda: True)
    monkeypatch.setattr(
        server_manager,
        "_repository_alembic_heads",
        lambda: ("0017_internal_ids",),
    )
    monkeypatch.setattr(
        server_manager,
        "_database_alembic_revisions",
        lambda _: ("0016_report_templates",),
    )
    monkeypatch.setattr(server_manager, "checked", checked)

    assert server_manager.update_server() == 1
    output = capsys.readouterr().out
    assert "UPDATE FAILED" in output
    assert old in output
    assert target in output
    assert str(backup) in output
    assert "Automatic migration downgrade was not attempted" in output


def test_parser_accepts_update_command() -> None:
    assert server_manager.build_parser().parse_args(["update"]).command == "update"


def test_parser_accepts_pilot_publish_source() -> None:
    args = server_manager.build_parser().parse_args(["publish-apk", "built.apk"])

    assert args.command == "publish-apk"
    assert args.apk == Path("built.apk")


def test_update_batch_wrapper_uses_repository_relative_paths() -> None:
    wrapper = (server_manager.ROOT / "Update Fleet Manager Server.bat").read_text(
        encoding="utf-8"
    )

    assert 'set "REPO_ROOT=%~dp0"' in wrapper
    assert '"%PYTHON_EXE%" "%REPO_ROOT%\\scripts\\server_manager.py" update' in wrapper
    assert "git reset" not in wrapper.lower()
    assert "git clean" not in wrapper.lower()


def test_publish_batch_wrapper_only_delegates_verified_apk_publish() -> None:
    wrapper = (server_manager.ROOT / "Publish Pilot APK.bat").read_text(
        encoding="utf-8"
    )

    assert 'set "REPO_ROOT=%~dp0"' in wrapper
    assert (
        '"%PYTHON_EXE%" "%REPO_ROOT%\\scripts\\server_manager.py" publish-apk'
        in wrapper
    )
    assert "flutter" not in wrapper.casefold()
    assert "sign" not in wrapper.casefold()
