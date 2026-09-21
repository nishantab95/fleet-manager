from fastapi.testclient import TestClient

from fleet_api import __version__
from fleet_api.main import app


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


def test_request_id_is_normalized_and_returned() -> None:
    request_id = "12345678-1234-5678-1234-567812345678"
    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": request_id})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == request_id
