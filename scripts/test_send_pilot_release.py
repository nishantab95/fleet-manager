import json
from pathlib import Path

import pytest

import pilot_release_common as common
import send_pilot_release as sender


def _identity(apk: Path) -> common.ApkIdentity:
    return common.ApkIdentity(
        package=common.EXPECTED_PACKAGE,
        version_name="1.0.24-pilot",
        version_code=29,
        signer_sha256=common.EXPECTED_SIGNER_SHA256,
        apk_sha256=common.sha256_file(apk),
    )


def _provenance(
    identity: common.ApkIdentity,
    *,
    auth_mode: str = "company_pin",
    build_profile: str = "company-pin",
) -> dict[str, object]:
    return {
        "package": identity.package,
        "versionName": identity.version_name,
        "versionCode": identity.version_code,
        "signerSha256": identity.signer_sha256,
        "apkSha256": identity.apk_sha256,
        "sourceGitCommit": "a" * 40,
        "sourceTreeClean": True,
        "authMode": auth_mode,
        "buildProfile": build_profile,
    }


def _candidate(tmp_path: Path) -> tuple[Path, common.ApkIdentity]:
    apk = tmp_path / "company.apk"
    apk.write_bytes(b"company-apk")
    item = _identity(apk)
    Path(f"{apk}.build.json").write_text(
        json.dumps(_provenance(item)), encoding="utf-8"
    )
    return apk, item


def _configure_send(
    monkeypatch: pytest.MonkeyPatch,
    apk: Path,
    item: common.ApkIdentity,
) -> None:
    monkeypatch.setattr(sender, "_git_provenance", lambda: "a" * 40)
    monkeypatch.setattr(sender.common, "inspect_apk", lambda _: item)
    monkeypatch.setattr(sender, "_tailscale", lambda: "tailscale")
    monkeypatch.setattr(
        sender, "_server_dns_name", lambda *_: "staunch-pc-03.example.ts.net"
    )
    monkeypatch.setattr(sender, "_published_version_code", lambda _: 28)
    monkeypatch.setattr(sender, "_read_publisher_token", lambda _: "token")
    monkeypatch.setattr(
        sender,
        "_wait_for_publication",
        lambda *_: "https://staunch-pc-03.example.ts.net/pilot/build29.apk",
    )


def test_company_pin_provenance_and_manifest_are_explicit(tmp_path: Path) -> None:
    apk, identity = _candidate(tmp_path)
    provenance = sender._validate_build_provenance(
        apk,
        identity,
        "a" * 40,
        require_company_pin=True,
    )
    manifest = sender._release_manifest(
        identity,
        apk_file="FleetManager-Pilot-upload.apk",
        release_id="29-company-pin",
        commit="a" * 40,
        provenance=provenance,
        require_company_pin=True,
    )

    assert manifest["authMode"] == "company_pin"
    assert manifest["buildProfile"] == "company-pin"


def test_company_send_rejects_staging_provenance(tmp_path: Path) -> None:
    apk, identity = _candidate(tmp_path)
    provenance = _provenance(
        identity,
        auth_mode="firebase",
        build_profile="firebase-staging",
    )
    Path(f"{apk}.build.json").write_text(json.dumps(provenance), encoding="utf-8")

    with pytest.raises(sender.SendError, match="unsupported authentication profile"):
        sender._validate_build_provenance(apk, identity, "a" * 40)


def test_sender_rejects_oversized_apk_before_transport(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    apk, _ = _candidate(tmp_path)
    monkeypatch.setattr(sender, "MAX_APK_BYTES", 2)
    monkeypatch.setattr(sender, "_git_provenance", lambda: "a" * 40)
    monkeypatch.setattr(
        sender.common,
        "inspect_apk",
        lambda _: pytest.fail("oversized APK must fail before inspection"),
    )

    with pytest.raises(sender.SendError, match="upload limit"):
        sender.send(apk, "staunch-pc-03", 1)


@pytest.mark.parametrize(
    "connection_fields",
    [
        {"CurAddr": "100.116.18.21:41641"},
        {"Relay": "blr"},
    ],
)
def test_tailscale_peer_is_accepted_with_direct_or_relay_connection(
    monkeypatch: pytest.MonkeyPatch,
    connection_fields: dict[str, str],
) -> None:
    status = {
        "BackendState": "Running",
        "Peer": {
            "peer": {
                "HostName": "staunch-pc-03",
                "DNSName": "staunch-pc-03.example.ts.net.",
                "Online": True,
                **connection_fields,
            }
        },
    }
    calls: list[list[str]] = []

    def run(arguments: list[str], _label: str, timeout: int = 120) -> str:
        del timeout
        calls.append(arguments)
        return json.dumps(status)

    monkeypatch.setattr(sender, "_run", run)

    assert (
        sender._server_dns_name("tailscale", "staunch-pc-03")
        == "staunch-pc-03.example.ts.net"
    )
    assert calls == [["tailscale", "status", "--json"]]
    assert all("ping" not in call for call in calls)


def test_https_is_preferred_and_taildrop_is_not_called(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    apk, item = _candidate(tmp_path)
    _configure_send(monkeypatch, apk, item)
    transports: list[str] = []
    monkeypatch.setattr(
        sender,
        "_https_upload",
        lambda *_args, **_kwargs: transports.append("https") or {"status": "PUBLISHED"},
    )
    monkeypatch.setattr(
        sender,
        "_send_taildrop",
        lambda *_args, **_kwargs: transports.append("taildrop"),
    )

    assert sender.send(apk, "staunch-pc-03", 1, require_company_pin=True) == 0
    assert transports == ["https"]


def test_https_upload_streams_multipart_and_accepts_publication_response(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    apk, item = _candidate(tmp_path)
    manifest = sender._release_manifest(
        item,
        apk_file="candidate.apk",
        release_id="29-company-pin",
        commit="a" * 40,
        provenance=_provenance(item),
        require_company_pin=True,
    )

    class Response:
        status = 201

        @staticmethod
        def read(_: int) -> bytes:
            return b'{"status":"PUBLISHED"}'

    class Connection:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}
            self.body = bytearray()
            self.request: tuple[str, str] | None = None

        def putrequest(self, method: str, path: str) -> None:
            self.request = (method, path)

        def putheader(self, name: str, value: str) -> None:
            self.headers[name] = value

        def endheaders(self) -> None:
            return None

        def send(self, value: bytes) -> None:
            self.body.extend(value)

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            return None

    connection = Connection()
    monkeypatch.setattr(
        sender.http.client,
        "HTTPSConnection",
        lambda *_args, **_kwargs: connection,
    )

    result = sender._https_upload(
        "staunch-pc-03.example.ts.net",
        apk,
        manifest,
        "publisher-token",
        timeout=30,
    )

    assert result == {"status": "PUBLISHED"}
    assert connection.request == ("POST", sender.HTTPS_UPLOAD_PATH)
    assert connection.headers["Authorization"] == "Bearer publisher-token"
    assert b'form-data; name="metadata"' in connection.body
    assert b'form-data; name="apk"; filename="candidate.apk"' in connection.body
    assert b"company-apk" in connection.body


def test_taildrop_is_used_only_when_https_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    apk, item = _candidate(tmp_path)
    _configure_send(monkeypatch, apk, item)
    transports: list[str] = []

    def unavailable(*_args: object, **_kwargs: object) -> dict[str, object]:
        transports.append("https")
        raise sender.HttpsUploadUnavailable("not installed")

    monkeypatch.setattr(sender, "_https_upload", unavailable)
    monkeypatch.setattr(
        sender,
        "_send_taildrop",
        lambda *_args, **_kwargs: transports.append("taildrop"),
    )

    assert sender.send(apk, "staunch-pc-03", 1, require_company_pin=True) == 0
    assert transports == ["https", "taildrop"]


def test_https_authentication_failure_does_not_fall_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    apk, item = _candidate(tmp_path)
    _configure_send(monkeypatch, apk, item)
    monkeypatch.setattr(
        sender,
        "_https_upload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            sender.SendError("HTTPS release upload returned HTTP 401")
        ),
    )
    monkeypatch.setattr(
        sender,
        "_send_taildrop",
        lambda *_args, **_kwargs: pytest.fail("auth failure must not fall back"),
    )

    with pytest.raises(sender.SendError, match="401"):
        sender.send(apk, "staunch-pc-03", 1, require_company_pin=True)


def test_publication_verification_checks_commit_and_download_hash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    apk, item = _candidate(tmp_path)
    url = "https://staunch-pc-03.example.ts.net/pilot/build29.apk"
    monkeypatch.setattr(
        sender,
        "_published_release",
        lambda _: {
            "version_name": item.version_name,
            "version_code": item.version_code,
            "sha256": item.apk_sha256,
            "source_commit": "a" * 40,
            "apk_url": url,
        },
    )
    monkeypatch.setattr(sender, "_remote_file_hash", lambda _: item.apk_sha256)

    assert (
        sender._wait_for_publication("staunch-pc-03.example.ts.net", item, "a" * 40, 1)
        == url
    )
