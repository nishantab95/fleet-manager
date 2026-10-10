from collections.abc import Callable
from typing import Any

import pytest

from fleet_api.auth import firebase as firebase_module
from fleet_api.auth.firebase import FirebasePhoneAuthProvider
from fleet_api.core.config import Settings
from fleet_api.domain.enums import AuthIdentityProvider
from fleet_api.domain.errors import FirebaseTokenError

firebase_auth: Any = vars(firebase_module)["auth"]


def _settings() -> Settings:
    return Settings(
        environment="test",
        auth_mode="firebase",
        firebase_project_id="fleet-auth-test",
    )


def test_firebase_adapter_verifies_with_revocation_and_returns_trusted_phone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FirebasePhoneAuthProvider(_settings())
    app = object()
    captured: dict[str, object] = {}
    monkeypatch.setattr(provider, "_firebase_app", lambda: app)

    def verify_token(id_token: str, **kwargs: object) -> dict[str, object]:
        captured.update({"id_token": id_token, **kwargs})
        return {
            "sub": "firebase-user-1",
            "phone_number": "+91 98765 43210",
            "auth_time": 1_760_000_000,
            "firebase": {"sign_in_provider": "phone"},
        }

    monkeypatch.setattr(firebase_auth, "verify_id_token", verify_token)

    identity = provider.verify("signed-token")

    assert identity.provider == AuthIdentityProvider.FIREBASE_PHONE
    assert identity.subject == "firebase-user-1"
    assert identity.normalized_phone == "+919876543210"
    assert captured == {
        "id_token": "signed-token",
        "app": app,
        "check_revoked": True,
    }


@pytest.mark.parametrize(
    "failure",
    [
        lambda: firebase_auth.InvalidIdTokenError("wrong audience"),
        lambda: firebase_auth.ExpiredIdTokenError("expired", None),
    ],
)
def test_firebase_adapter_maps_invalid_or_expired_tokens_to_safe_domain_error(
    monkeypatch: pytest.MonkeyPatch,
    failure: Callable[[], Exception],
) -> None:
    provider = FirebasePhoneAuthProvider(_settings())
    monkeypatch.setattr(provider, "_firebase_app", object)

    def reject(*args: Any, **kwargs: Any) -> dict[str, object]:
        del args, kwargs
        raise failure()

    monkeypatch.setattr(firebase_auth, "verify_id_token", reject)

    with pytest.raises(FirebaseTokenError):
        provider.verify("rejected-token")


def test_firebase_adapter_rejects_non_phone_sign_in_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FirebasePhoneAuthProvider(_settings())
    monkeypatch.setattr(provider, "_firebase_app", object)
    monkeypatch.setattr(
        firebase_auth,
        "verify_id_token",
        lambda *args, **kwargs: {
            "sub": "password-user",
            "phone_number": "+919876543210",
            "firebase": {"sign_in_provider": "password"},
        },
    )

    with pytest.raises(FirebaseTokenError, match="phone-auth"):
        provider.verify("non-phone-token")
