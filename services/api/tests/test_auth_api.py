from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_otp_provider
from fleet_api.auth.providers import FakeOtpProvider
from fleet_api.core.config import Settings
from fleet_api.db.models import CompanyMembership, User
from fleet_api.db.session import get_db as session_get_db
from fleet_api.main import create_app

pytestmark = pytest.mark.postgres


def value[T](records: dict[str, object], key: str, expected_type: type[T]) -> T:
    item = records[key]
    assert isinstance(item, expected_type)
    return item


def user_by_name(db_session: Session, display_name: str) -> User:
    user = db_session.scalar(select(User).where(User.display_name == display_name))
    assert user is not None
    return user


def test_auth_http_flow_and_generic_otp_request(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    owner = user_by_name(db_session, "Owner A")
    owner.phone_number = "+919876543210"
    db_session.flush()
    provider = FakeOtpProvider()
    settings = Settings(
        environment="test",
        phone_default_region="IN",
        jwt_signing_key="test-signing-key-that-is-longer-than-32-characters",
        otp_resend_cooldown_seconds=0,
    )
    app = create_app(settings)

    def override_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[session_get_db] = override_db
    app.dependency_overrides[get_otp_provider] = lambda: provider
    try:
        with TestClient(app) as client:
            request_response = client.post(
                "/api/v1/auth/otp/request",
                json={"phone": "09876543210"},
            )
            assert request_response.status_code == 202
            challenge_id = request_response.json()["challenge_id"]
            assert "otp" not in request_response.text.lower()

            code = provider.deliveries[next(iter(provider.deliveries))]
            wrong_code = "000000" if code != "000000" else "000001"
            wrong_response = client.post(
                "/api/v1/auth/otp/verify",
                json={"challenge_id": challenge_id, "otp": wrong_code},
            )
            assert wrong_response.status_code == 401
            assert wrong_response.json()["detail"]["code"] == "AUTHENTICATION_FAILED"

            verify_response = client.post(
                "/api/v1/auth/otp/verify",
                json={"challenge_id": challenge_id, "otp": code},
            )
            assert verify_response.status_code == 200
            pre_session_token = verify_response.json()["pre_session_token"]

            memberships_response = client.post(
                "/api/v1/auth/memberships",
                json={"pre_session_token": pre_session_token},
            )
            assert memberships_response.status_code == 200
            membership_id = memberships_response.json()["memberships"][0]["membership_id"]

            session_response = client.post(
                "/api/v1/auth/session",
                json={
                    "pre_session_token": pre_session_token,
                    "membership_id": membership_id,
                },
            )
            assert session_response.status_code == 200
            session_json: dict[str, Any] = session_response.json()
            access_token = session_json["access_token"]
            refresh_token = session_json["refresh_token"]

            web_session = client.post(
                "/api/v1/auth/web-session",
                json={
                    "pre_session_token": pre_session_token,
                    "membership_id": membership_id,
                },
            )
            assert web_session.status_code == 200
            assert "refresh_token" not in web_session.json()
            assert "fleet_web_refresh=" in web_session.headers["set-cookie"]
            web_refresh = client.post("/api/v1/auth/web-refresh")
            assert web_refresh.status_code == 200
            assert "refresh_token" not in web_refresh.json()
            assert "HttpOnly" in web_refresh.headers["set-cookie"]

            me_response = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert me_response.status_code == 200
            assert me_response.json()["role"] == "OWNER_ADMIN"
            assert me_response.json()["company_id"]

            rotated_response = client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh_token},
            )
            assert rotated_response.status_code == 200
            rotated_access = rotated_response.json()["access_token"]

            logout_response = client.post(
                "/api/v1/auth/logout",
                headers={"Authorization": f"Bearer {rotated_access}"},
            )
            assert logout_response.status_code == 204
            assert (
                client.get(
                    "/api/v1/auth/me",
                    headers={"Authorization": f"Bearer {rotated_access}"},
                ).status_code
                == 401
            )
    finally:
        app.dependency_overrides.clear()


def test_auth_http_blocks_foreign_membership_selection(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    owner = user_by_name(db_session, "Owner A")
    owner.phone_number = "+919876543210"
    db_session.flush()
    foreign_membership = value(tenant_records, "driver_b", CompanyMembership)
    provider = FakeOtpProvider()
    app = create_app(
        Settings(
            environment="test",
            phone_default_region="IN",
            jwt_signing_key="test-signing-key-that-is-longer-than-32-characters",
        )
    )

    def override_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[session_get_db] = override_db
    app.dependency_overrides[get_otp_provider] = lambda: provider
    try:
        with TestClient(app) as client:
            challenge_response = client.post(
                "/api/v1/auth/otp/request",
                json={"phone": owner.phone_number},
            )
            challenge_id = challenge_response.json()["challenge_id"]
            pre_session = client.post(
                "/api/v1/auth/otp/verify",
                json={
                    "challenge_id": challenge_id,
                    "otp": provider.deliveries[next(iter(provider.deliveries))],
                },
            ).json()["pre_session_token"]
            response = client.post(
                "/api/v1/auth/session",
                json={
                    "pre_session_token": pre_session,
                    "membership_id": str(foreign_membership.id),
                },
            )
            assert response.status_code == 403
            assert response.json()["detail"]["code"] == "FORBIDDEN"
    finally:
        app.dependency_overrides.clear()
