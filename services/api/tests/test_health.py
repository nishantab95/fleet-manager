from pathlib import Path

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from fleet_api import __version__
from fleet_api.core.config import Settings
from fleet_api.main import app, create_app


def test_health_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "fleet-manager-api",
        "version": __version__,
    }
    assert response.headers["x-request-id"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_request_id_is_normalized_and_returned() -> None:
    request_id = "12345678-1234-5678-1234-567812345678"
    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": request_id})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == request_id


def test_ready_checks_private_filesystem_storage(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("fleet_api.main.check_database", lambda: True)
    settings = Settings(
        environment="test",
        object_storage_provider="filesystem",
        filesystem_storage_root=tmp_path / "evidence",
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "available",
        "object_storage": "available",
    }


def test_ready_fails_closed_when_filesystem_storage_is_unavailable(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    blocked_root = tmp_path / "not-a-directory"
    blocked_root.write_text("file", encoding="utf-8")
    monkeypatch.setattr("fleet_api.main.check_database", lambda: True)
    settings = Settings(
        environment="test",
        object_storage_provider="filesystem",
        filesystem_storage_root=blocked_root,
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "database": "available",
        "object_storage": "unavailable",
    }
