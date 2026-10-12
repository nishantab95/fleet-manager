"""Validate and publish a built Pilot APK through private Tailscale transports."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import secrets
import shutil
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Sequence

import pilot_release_common as common


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APK = (
    ROOT
    / "apps"
    / "mobile"
    / "build"
    / "app"
    / "outputs"
    / "flutter-apk"
    / "app-pilot-release.apk"
)
DEFAULT_TARGET = "staunch-pc-03"
HTTPS_UPLOAD_PATH = "/api/v1/admin/pilot-releases"
MAX_RESPONSE_BYTES = 64 * 1024
MAX_APK_BYTES = 150_000_000


class SendError(RuntimeError):
    """A safe preflight or private transfer failure."""


class HttpsUploadUnavailable(SendError):
    """The optional HTTPS transport is not reachable on the target server."""


def _run(arguments: list[str], label: str, timeout: int = 120) -> str:
    result = subprocess.run(
        arguments,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SendError(f"{label} failed: {detail or 'unknown error'}")
    return result.stdout.strip()


def _tailscale() -> str:
    executable = shutil.which("tailscale")
    if not executable:
        candidate = Path(r"C:\Program Files\Tailscale\tailscale.exe")
        if candidate.is_file():
            executable = str(candidate)
    if not executable:
        raise SendError("ENABLE TAILSCALE SEND FILES: tailscale.exe is missing.")
    return executable


def _git_provenance() -> str:
    if _run(["git", "status", "--porcelain", "--untracked-files=normal"], "Git status"):
        raise SendError(
            "Git working tree is not clean; source provenance would be ambiguous."
        )
    commit = _run(["git", "rev-parse", "HEAD"], "Git commit lookup").casefold()
    if not common.COMMIT_RE.fullmatch(commit):
        raise SendError("Git did not return a full source commit SHA.")
    return commit


def _server_dns_name(tailscale: str, target: str) -> str:
    try:
        status = json.loads(_run([tailscale, "status", "--json"], "Tailscale status"))
    except json.JSONDecodeError as error:
        raise SendError("Tailscale status was not valid JSON.") from error
    if status.get("BackendState") != "Running":
        raise SendError("ENABLE TAILSCALE SEND FILES: Tailscale is not connected.")
    target_key = target.casefold().replace("_", "-")
    peers = status.get("Peer", {})
    if isinstance(peers, dict):
        for peer in peers.values():
            if not isinstance(peer, dict):
                continue
            host = str(peer.get("HostName", "")).casefold().replace("_", "-")
            dns = str(peer.get("DNSName", "")).rstrip(".")
            dns_host = dns.split(".", 1)[0].casefold().replace("_", "-")
            if target_key in (host, dns_host) or target_key == dns.casefold():
                if not peer.get("Online"):
                    raise SendError(f"Private release server {target} is offline.")
                return dns
    raise SendError(f"Private release server {target} was not found in this tailnet.")


def _fetch_text(url: str, timeout: float = 10) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        if response.status != 200:
            raise SendError(f"Verification URL returned HTTP {response.status}: {url}")
        return response.read(16 * 1024).decode("utf-8")


def _published_release(dns_name: str) -> dict[str, object]:
    url = f"https://{dns_name}/pilot/release.json"
    try:
        value = json.loads(_fetch_text(url))
    except (
        OSError,
        urllib.error.URLError,
        UnicodeError,
        json.JSONDecodeError,
    ) as error:
        raise SendError(
            "Published Pilot release manifest could not be verified; refusing transfer."
        ) from error
    if not isinstance(value, dict):
        raise SendError(
            "Published Pilot release manifest is invalid; refusing transfer."
        )
    return value


def _published_version_code(dns_name: str) -> int:
    value = _published_release(dns_name)
    version_code = value.get("version_code")
    if (
        isinstance(version_code, bool)
        or not isinstance(version_code, int)
        or version_code < 1
    ):
        raise SendError(
            "Published Pilot versionCode is missing or invalid; refusing transfer."
        )
    return version_code


def _validate_build_provenance(
    apk: Path,
    identity: common.ApkIdentity,
    commit: str,
    *,
    require_firebase_company: bool = False,
    require_company_pin: bool = False,
) -> dict[str, Any]:
    sidecar = Path(f"{apk}.build.json")
    try:
        record = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SendError(
            "Successful build provenance is missing or invalid; refusing transfer."
        ) from error
    expected = {
        "package": identity.package,
        "versionName": identity.version_name,
        "versionCode": identity.version_code,
        "signerSha256": identity.signer_sha256,
        "apkSha256": identity.apk_sha256,
        "sourceGitCommit": commit,
    }
    if not isinstance(record, dict) or record.get("sourceTreeClean") is not True:
        raise SendError(
            "Build provenance does not prove a clean source tree; refusing transfer."
        )
    for key, actual in expected.items():
        if record.get(key) != actual:
            raise SendError(f"Build provenance mismatch for {key}; refusing transfer.")
    profile = (record.get("authMode"), record.get("buildProfile"))
    allowed_profiles = {
        (None, None),
        ("firebase", "firebase-company"),
        ("company_pin", "company-pin"),
    }
    if profile not in allowed_profiles:
        raise SendError("Build provenance has an unsupported authentication profile.")
    if require_firebase_company and profile != ("firebase", "firebase-company"):
        raise SendError(
            "Build provenance does not identify a Firebase company APK; refusing transfer."
        )
    if require_company_pin and profile != ("company_pin", "company-pin"):
        raise SendError(
            "Build provenance does not identify a company PIN APK; refusing transfer."
        )
    return record


def _remote_file_hash(url: str) -> str:
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=30) as response:
        if response.status != 200:
            raise SendError(f"Remote APK returned HTTP {response.status}.")
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _wait_for_publication(
    dns_name: str,
    identity: common.ApkIdentity,
    commit: str,
    timeout: int,
) -> str:
    deadline = time.monotonic() + timeout
    last_detail = "publisher has not reported the expected release"
    while time.monotonic() < deadline:
        try:
            release = _published_release(dns_name)
            if (
                release.get("version_name") == identity.version_name
                and release.get("version_code") == identity.version_code
                and str(release.get("sha256", "")).casefold() == identity.apk_sha256
                and str(release.get("source_commit", "")).casefold() == commit
            ):
                apk_url = release.get("apk_url")
                parsed = urllib.parse.urlsplit(
                    apk_url if isinstance(apk_url, str) else ""
                )
                if (
                    parsed.scheme != "https"
                    or parsed.hostname != dns_name
                    or parsed.query
                    or parsed.fragment
                ):
                    raise SendError(
                        "Published APK URL is outside the private release origin."
                    )
                if _remote_file_hash(apk_url) != identity.apk_sha256:
                    raise SendError(
                        "Published APK download hash does not match the sent APK."
                    )
                return apk_url
            last_detail = "private release.json has not changed to the sent release"
        except (OSError, urllib.error.URLError, UnicodeError, SendError) as error:
            last_detail = str(error)
        time.sleep(5)
    raise SendError(f"Timed out waiting for private publication: {last_detail}")


def _release_manifest(
    identity: common.ApkIdentity,
    *,
    apk_file: str,
    release_id: str,
    commit: str,
    provenance: dict[str, Any],
    require_firebase_company: bool = False,
    require_company_pin: bool = False,
) -> dict[str, object]:
    manifest: dict[str, object] = {
        "schemaVersion": 1,
        "releaseId": release_id,
        "apkFile": apk_file,
        "package": identity.package,
        "versionName": identity.version_name,
        "versionCode": identity.version_code,
        "apkSha256": identity.apk_sha256,
        "expectedSignerSha256": common.EXPECTED_SIGNER_SHA256,
        "sourceGitCommit": commit,
    }
    auth_mode = provenance.get("authMode")
    build_profile = provenance.get("buildProfile")
    if auth_mode is not None or build_profile is not None:
        manifest["authMode"] = auth_mode
        manifest["buildProfile"] = build_profile
    if require_firebase_company and (auth_mode, build_profile) != (
        "firebase",
        "firebase-company",
    ):
        raise SendError("Firebase company release metadata is invalid.")
    if require_company_pin and (auth_mode, build_profile) != (
        "company_pin",
        "company-pin",
    ):
        raise SendError("Company PIN release metadata is invalid.")
    return manifest


def _publisher_token_path(configured: Path | None) -> Path:
    if configured is not None:
        return configured.expanduser().resolve()
    environment_path = os.environ.get("FLEET_PUBLISHER_TOKEN_FILE", "").strip()
    if environment_path:
        return Path(environment_path).expanduser().resolve()
    return Path.home() / ".fleetaisystems" / "pilot-publisher.token"


def _read_publisher_token(configured: Path | None) -> str:
    path = _publisher_token_path(configured)
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise HttpsUploadUnavailable(
            f"Publisher credential file is unavailable: {path}"
        ) from error
    if len(raw) > 4096:
        raise SendError("Publisher credential file is invalid.")
    try:
        token = raw.decode("utf-8").rstrip("\r\n")
    except UnicodeError as error:
        raise SendError("Publisher credential file is invalid.") from error
    if (
        len(token) < 32
        or len(token) > 2048
        or any(character.isspace() for character in token)
    ):
        raise SendError("Publisher credential file is invalid.")
    return token


def _safe_error_detail(body: bytes) -> str:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return "server returned no safe error detail"
    detail = value.get("detail") if isinstance(value, dict) else None
    return (
        " ".join(str(detail).split())[:500] if detail else "server rejected the upload"
    )


def _https_upload(
    dns_name: str,
    apk: Path,
    manifest: dict[str, object],
    token: str,
    *,
    timeout: int,
) -> dict[str, object]:
    boundary = f"fleet-{secrets.token_hex(24)}"
    metadata = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    preamble = (
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="metadata"\r\n'
            "Content-Type: application/json\r\n\r\n"
        ).encode()
        + metadata
        + (
            f"\r\n--{boundary}\r\n"
            'Content-Disposition: form-data; name="apk"; filename="candidate.apk"\r\n'
            "Content-Type: application/vnd.android.package-archive\r\n\r\n"
        ).encode()
    )
    epilogue = f"\r\n--{boundary}--\r\n".encode()
    content_length = len(preamble) + apk.stat().st_size + len(epilogue)
    connection = http.client.HTTPSConnection(
        dns_name,
        timeout=timeout,
        context=ssl.create_default_context(),
    )
    try:
        connection.putrequest("POST", HTTPS_UPLOAD_PATH)
        connection.putheader("Authorization", f"Bearer {token}")
        connection.putheader(
            "Content-Type", f"multipart/form-data; boundary={boundary}"
        )
        connection.putheader("Content-Length", str(content_length))
        connection.endheaders()
        connection.send(preamble)
        with apk.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                connection.send(chunk)
        connection.send(epilogue)
        response = connection.getresponse()
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise SendError("HTTPS upload response was unexpectedly large.")
        if response.status in {404, 405, 501, 502, 503, 504}:
            raise HttpsUploadUnavailable(
                f"HTTPS release upload returned HTTP {response.status}."
            )
        if response.status not in {200, 201}:
            raise SendError(
                f"HTTPS release upload returned HTTP {response.status}: {_safe_error_detail(body)}"
            )
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise SendError("HTTPS release upload returned invalid JSON.") from error
        if not isinstance(value, dict) or value.get("status") != "PUBLISHED":
            raise SendError("HTTPS release upload did not confirm publication.")
        return value
    except HttpsUploadUnavailable:
        raise
    except SendError:
        raise
    except (OSError, TimeoutError, http.client.HTTPException, ssl.SSLError) as error:
        raise HttpsUploadUnavailable("HTTPS release upload is unavailable.") from error
    finally:
        connection.close()


def _send_taildrop(
    tailscale: str,
    target: str,
    apk: Path,
    manifest: dict[str, object],
    *,
    release_id: str,
) -> None:
    basename = f"{common.APK_PREFIX}{release_id}"
    with tempfile.TemporaryDirectory(prefix="fleet-pilot-send-") as raw:
        transfer_dir = Path(raw)
        transfer_apk = transfer_dir / f"{basename}.apk"
        manifest_path = transfer_dir / f"{basename}.json"
        shutil.copy2(apk, transfer_apk)
        if common.sha256_file(transfer_apk) != manifest["apkSha256"]:
            raise SendError("Temporary transfer APK hash verification failed.")
        taildrop_manifest = dict(manifest)
        taildrop_manifest["apkFile"] = transfer_apk.name
        manifest_path.write_text(
            json.dumps(taildrop_manifest, indent=2) + "\n", encoding="utf-8"
        )
        _run(
            [tailscale, "file", "cp", str(transfer_apk), f"{target}:"],
            "APK Taildrop",
            timeout=300,
        )
        _run(
            [tailscale, "file", "cp", str(manifest_path), f"{target}:"],
            "Manifest Taildrop",
            timeout=60,
        )


def send(
    apk: Path,
    target: str,
    timeout: int,
    *,
    require_firebase_company: bool = False,
    require_company_pin: bool = False,
    publisher_token_file: Path | None = None,
    taildrop_fallback: bool = True,
) -> int:
    if require_firebase_company and require_company_pin:
        raise SendError("Choose only one required company authentication profile.")
    commit = _git_provenance()
    if apk.stat().st_size > MAX_APK_BYTES:
        raise SendError("APK exceeds the private release upload limit.")
    identity = common.inspect_apk(apk)
    common.validate_expected_identity(identity)
    provenance = _validate_build_provenance(
        apk,
        identity,
        commit,
        require_firebase_company=require_firebase_company,
        require_company_pin=require_company_pin,
    )
    tailscale = _tailscale()
    dns_name = _server_dns_name(tailscale, target)
    published_version_code = _published_version_code(dns_name)
    if identity.version_code <= published_version_code:
        raise SendError(
            f"versionCode {identity.version_code} must be greater than published "
            f"versionCode {published_version_code}."
        )

    release_id = f"{identity.version_code}-{identity.apk_sha256[:16]}"
    manifest = _release_manifest(
        identity,
        apk_file="candidate.apk",
        release_id=release_id,
        commit=commit,
        provenance=provenance,
        require_firebase_company=require_firebase_company,
        require_company_pin=require_company_pin,
    )

    print("\nFLEET MANAGER PILOT RELEASE\n")
    print(f"Version        {identity.version_name}")
    print(f"Version Code   {identity.version_code}")
    print("Package        VALID")
    print("Signer         VALID")
    print(f"SHA-256        {identity.apk_sha256}")
    print(f"\nServer         {target}")
    print("Tailscale      CONNECTED")
    try:
        token = _read_publisher_token(publisher_token_file)
        print("Transport      PRIVATE HTTPS")
        _https_upload(
            dns_name,
            apk,
            manifest,
            token,
            timeout=max(timeout, 300),
        )
    except HttpsUploadUnavailable as error:
        if not taildrop_fallback:
            raise
        print(f"HTTPS          UNAVAILABLE ({error})")
        print("Transport      TAILDROP FALLBACK")
        _send_taildrop(tailscale, target, apk, manifest, release_id=release_id)

    print("Waiting for private publication verification...")
    url = _wait_for_publication(dns_name, identity, commit, timeout)
    print("\nPUBLISHED SUCCESSFULLY")
    print(f"\nDownload:\n{url}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", nargs="?", type=Path, default=DEFAULT_APK)
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--timeout", type=int, default=360)
    parser.add_argument("--require-firebase-company", action="store_true")
    parser.add_argument("--require-company-pin", action="store_true")
    parser.add_argument("--publisher-token-file", type=Path)
    parser.add_argument(
        "--taildrop-fallback",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return send(
            args.apk.resolve(),
            args.target,
            args.timeout,
            require_firebase_company=args.require_firebase_company,
            require_company_pin=args.require_company_pin,
            publisher_token_file=args.publisher_token_file,
            taildrop_fallback=args.taildrop_fallback,
        )
    except (
        SendError,
        common.ReleaseValidationError,
        OSError,
        subprocess.TimeoutExpired,
    ) as error:
        print(f"\n[FAILED] {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
