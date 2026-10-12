from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from fleet_api.api import pilot_releases
from fleet_api.core.config import Settings
from fleet_api.main import create_app

TOKEN = "publisher-token-that-is-long-enough-for-tests"


def metadata_for(apk: bytes, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schemaVersion": 1,
        "releaseId": "client-name-is-not-trusted",
        "apkFile": "../../client-name.apk",
        "package": pilot_releases.EXPECTED_PACKAGE,
        "versionName": "1.0.24-pilot",
        "versionCode": 29,
        "apkSha256": hashlib.sha256(apk).hexdigest(),
        "expectedSignerSha256": pilot_releases.EXPECTED_SIGNER_SHA256,
        "sourceGitCommit": "a" * 40,
        "authMode": "company_pin",
        "buildProfile": "company-pin",
    }
    value.update(overrides)
    return value


def upload_client(
    tmp_path: Path,
    *,
    processor: Any,
    max_bytes: int = 1_000_000,
) -> tuple[TestClient, Path]:
    token_file = tmp_path / "publisher.token"
    token_file.write_text(TOKEN, encoding="utf-8")
    settings = Settings(
        _env_file=None,
        pilot_publisher_token_file=token_file,
        pilot_release_upload_max_bytes=max_bytes,
    )  # type: ignore[call-arg]
    app = create_app(settings)
    inbox = tmp_path / "incoming"
    app.state.pilot_release_backend = pilot_releases.PilotReleaseBackend(
        inbox_root=inbox,
        status_file=inbox / "publisher-status.json",
        publish_upload=processor,
    )
    return TestClient(app), inbox


def post_release(
    client: TestClient,
    apk: bytes,
    metadata: dict[str, object],
    *,
    token: str | None = TOKEN,
) -> Any:
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return client.post(
        "/api/v1/admin/pilot-releases",
        headers=headers,
        data={"metadata": json.dumps(metadata)},
        files={
            "apk": (
                "../../untrusted-client-name.apk",
                apk,
                "application/vnd.android.package-archive",
            )
        },
    )


def test_https_upload_uses_server_names_and_publishes(tmp_path: Path) -> None:
    observed: dict[str, object] = {}

    def publish(staged_apk: Path, manifest: dict[str, object]) -> str:
        observed.update(manifest=manifest, staged_apk=staged_apk)
        assert staged_apk.read_bytes() == b"signed-apk"
        return "PUBLISHED"

    client, inbox = upload_client(tmp_path, processor=publish)
    response = post_release(client, b"signed-apk", metadata_for(b"signed-apk"))

    assert response.status_code == 201
    assert response.json()["status"] == "PUBLISHED"
    manifest = observed["manifest"]
    assert isinstance(manifest, dict)
    assert str(manifest["releaseId"]).startswith("https-")
    assert str(manifest["apkFile"]).startswith("FleetManager-Pilot-upload-https-")
    assert ".." not in str(manifest["apkFile"])
    assert cast(Path, observed["staged_apk"]).is_relative_to(inbox)


@pytest.mark.parametrize("token", [None, "wrong-token-that-is-long-enough-for-tests"])
def test_https_upload_rejects_missing_or_wrong_token(tmp_path: Path, token: str | None) -> None:
    client, inbox = upload_client(
        tmp_path,
        processor=lambda *_: pytest.fail("unauthenticated upload must not publish"),
    )

    response = post_release(client, b"apk", metadata_for(b"apk"), token=token)

    assert response.status_code == 401
    assert not inbox.exists()


@pytest.mark.parametrize(
    "metadata",
    [
        "not-json",
        json.dumps({"schemaVersion": 1}),
        json.dumps(metadata_for(b"apk", package="wrong.package")),
    ],
)
def test_https_upload_rejects_malformed_metadata(tmp_path: Path, metadata: str) -> None:
    client, inbox = upload_client(
        tmp_path,
        processor=lambda *_: pytest.fail("invalid metadata must not publish"),
    )
    response = client.post(
        "/api/v1/admin/pilot-releases",
        headers={"Authorization": f"Bearer {TOKEN}"},
        data={"metadata": metadata},
        files={"apk": ("candidate.apk", b"apk", "application/octet-stream")},
    )

    assert response.status_code == 422
    assert not inbox.exists()


def test_https_upload_rejects_hash_mismatch_before_publish(tmp_path: Path) -> None:
    client, inbox = upload_client(
        tmp_path,
        processor=lambda *_: pytest.fail("hash mismatch must not publish"),
    )

    response = post_release(client, b"different", metadata_for(b"expected"))

    assert response.status_code == 422
    assert not list(inbox.rglob("*.apk"))
    assert not list(inbox.rglob("*.partial"))


def test_https_upload_enforces_size_limit(tmp_path: Path) -> None:
    client, inbox = upload_client(
        tmp_path,
        processor=lambda *_: pytest.fail("oversized upload must not publish"),
    )
    apk = b"x" * 1_000_001

    response = post_release(client, apk, metadata_for(apk))

    assert response.status_code == 413
    assert not list(inbox.rglob("*.apk"))
    assert not list(inbox.rglob("*.partial"))


def test_interrupted_upload_removes_partial_file(tmp_path: Path) -> None:
    class InterruptedUpload:
        calls = 0

        async def read(self, _: int) -> bytes:
            self.calls += 1
            if self.calls == 1:
                return b"partial"
            raise ConnectionError("client disconnected")

        async def close(self) -> None:
            return None

    partial = tmp_path / "candidate.partial"

    with pytest.raises(pilot_releases.UploadRejected, match="interrupted"):
        asyncio.run(
            pilot_releases._stream_apk(
                cast(Any, InterruptedUpload()),
                partial,
                max_bytes=1_000_000,
            )
        )

    assert not partial.exists()
