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
    monkeypatch.setattr(server_manager, "compose_health", lambda *_: {"postgres": "healthy"})

    server_manager.ensure_infrastructure("docker", {})

    assert commands == [["docker", "compose", "up", "-d", "postgres"]]


def test_stop_targets_only_owned_api_and_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
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
        server_manager,
        "backup_server",
        lambda: pytest.fail("already-current update must not create a backup"),
    )

    assert server_manager.update_server() == 0
    output = capsys.readouterr().out
    assert "ALREADY UP TO DATE" in output
    assert current in output


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


def test_update_fast_forward_runs_backup_stop_pull_sync_migrate_start(
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

    manifest_calls = iter((set(), {backup}))

    def checked(args: list[str], *, label: str, **_: object) -> subprocess.CompletedProcess[str]:
        del args
        events.append("start" if label == "Fleet Manager restart" else "migrate")
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(server_manager, "git_output", git_output)
    monkeypatch.setattr(
        server_manager,
        "run_capture",
        lambda args, **_: subprocess.CompletedProcess(args, 0, "", ""),
    )
    monkeypatch.setattr(server_manager, "_backup_manifests", lambda: next(manifest_calls))
    monkeypatch.setattr(
        server_manager, "backup_server", lambda: events.append("backup") or 0
    )
    monkeypatch.setattr(server_manager, "stop_api", lambda: events.append("stop") or 0)
    monkeypatch.setattr(server_manager, "load_server_environment", lambda: {})
    monkeypatch.setattr(
        server_manager,
        "_sync_locked_dependencies",
        lambda: events.append("sync"),
    )
    monkeypatch.setattr(server_manager, "checked", checked)
    monkeypatch.setattr(server_manager, "api_health_ok", lambda: True)
    monkeypatch.setattr(server_manager, "api_ready_ok", lambda: True)
    monkeypatch.setattr(
        server_manager,
        "remote_access_status",
        lambda: {"tailscale": "ONLINE", "remote": "ONLINE"},
    )

    assert server_manager.update_server() == 0
    assert events == ["backup", "stop", "pull", "sync", "migrate", "start"]
    output = capsys.readouterr().out
    assert "UPDATE COMPLETE" in output
    assert old in output
    assert target in output
    assert str(backup) in output


def test_update_failure_reports_commits_and_keeps_backup(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    old = "a" * 40
    target = "b" * 40
    backup = Path(r"F:\FleetManagerBackups\releases\test\server-backup-manifest.json")
    head = old

    def git_output(*args: str, **_: object) -> str:
        nonlocal head
        values = {
            ("status", "--porcelain", "--untracked-files=normal"): "",
            ("branch", "--show-current"): "main",
            ("remote", "get-url", "origin"): "https://example.invalid/fleet.git",
            ("fetch", "origin"): "",
            ("rev-parse", "origin/main"): target,
        }
        if args == ("rev-parse", "HEAD"):
            return head
        if args == ("pull", "--ff-only", "origin", "main"):
            head = target
            return ""
        return values[args]

    manifest_calls = iter((set(), {backup}))

    def checked(args: list[str], *, label: str, **_: object) -> subprocess.CompletedProcess[str]:
        del args
        if label == "Alembic upgrade":
            raise server_manager.ServerError("migration failed safely")
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(server_manager, "git_output", git_output)
    monkeypatch.setattr(
        server_manager,
        "run_capture",
        lambda args, **_: subprocess.CompletedProcess(args, 0, "", ""),
    )
    monkeypatch.setattr(server_manager, "_backup_manifests", lambda: next(manifest_calls))
    monkeypatch.setattr(server_manager, "backup_server", lambda: 0)
    monkeypatch.setattr(server_manager, "stop_api", lambda: 0)
    monkeypatch.setattr(server_manager, "load_server_environment", lambda: {})
    monkeypatch.setattr(server_manager, "_sync_locked_dependencies", lambda: None)
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
    assert '"%PYTHON_EXE%" "%REPO_ROOT%\\scripts\\server_manager.py" publish-apk' in wrapper
    assert "flutter" not in wrapper.casefold()
    assert "sign" not in wrapper.casefold()
