from fastapi.testclient import TestClient

from fleet_api.core.config import Settings
from fleet_api.main import create_app


def test_public_rate_limit_fails_closed_without_affecting_health() -> None:
    app = create_app(
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            rate_limit_requests_per_minute=1,
            auth_rate_limit_requests_per_minute=1,
        )
    )

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health").status_code == 200
        assert client.get("/does-not-exist").status_code == 404
        limited = client.get("/does-not-exist")

    assert limited.status_code == 429
    assert limited.headers["Retry-After"]
    assert limited.json() == {"detail": "Too many requests. Please try again later."}
