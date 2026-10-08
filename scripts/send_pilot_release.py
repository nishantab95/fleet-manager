"""Validate and Taildrop a built pilot APK to the private Fleet Manager server."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Sequence

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


class SendError(RuntimeError):
    """A safe preflight or private transfer failure."""


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
                    raise SendError(f"Taildrop destination {target} is offline.")
                return dns
    raise SendError(f"Taildrop destination {target} was not found in this tailnet.")


def _fetch_text(url: str, timeout: float = 10) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        if response.status != 200:
            raise SendError(f"Verification URL returned HTTP {response.status}: {url}")
        return response.read(16 * 1024).decode("utf-8")


def _remote_file_hash(url: str) -> str:
    import hashlib

    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=30) as response:
        if response.status != 200:
            raise SendError(f"Remote APK returned HTTP {response.status}.")
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _wait_for_publication(
    dns_name: str, identity: common.ApkIdentity, timeout: int
) -> str:
    base = f"https://{dns_name}/pilot"
    expected_code = f"VersionCode {identity.version_code}"
    deadline = time.monotonic() + timeout
    last_detail = "publisher has not reported the expected version"
    while time.monotonic() < deadline:
        try:
            version = _fetch_text(f"{base}/version.txt")
            checksum = _fetch_text(f"{base}/sha256.txt").split()
            if identity.version_name in version and expected_code in version:
                if checksum and checksum[0].casefold() == identity.apk_sha256:
                    remote = _remote_file_hash(f"{base}/FleetManager-Pilot-latest.apk")
                    if remote != identity.apk_sha256:
                        raise SendError(
                            "Published APK download hash does not match the sent APK."
                        )
                    return f"{base}/FleetManager-Pilot-latest.apk"
            last_detail = "private metadata has not changed to the sent release"
        except (OSError, urllib.error.URLError, UnicodeError) as error:
            last_detail = str(error)
        time.sleep(5)
    raise SendError(f"Timed out waiting for private publication: {last_detail}")


def send(apk: Path, target: str, timeout: int) -> int:
    commit = _git_provenance()
    identity = common.inspect_apk(apk)
    common.validate_expected_identity(identity)
    tailscale = _tailscale()
    dns_name = _server_dns_name(tailscale, target)
    _run(
        [tailscale, "ping", "--c", "1", target],
        "Tailscale destination check",
        timeout=30,
    )

    release_id = f"{identity.version_code}-{identity.apk_sha256[:16]}"
    basename = f"{common.APK_PREFIX}{release_id}"
    with tempfile.TemporaryDirectory(prefix="fleet-pilot-send-") as raw:
        transfer_dir = Path(raw)
        transfer_apk = transfer_dir / f"{basename}.apk"
        manifest_path = transfer_dir / f"{basename}.json"
        shutil.copy2(apk, transfer_apk)
        if common.sha256_file(transfer_apk) != identity.apk_sha256:
            raise SendError("Temporary transfer APK hash verification failed.")
        manifest = {
            "schemaVersion": 1,
            "releaseId": release_id,
            "apkFile": transfer_apk.name,
            "package": identity.package,
            "versionName": identity.version_name,
            "versionCode": identity.version_code,
            "apkSha256": identity.apk_sha256,
            "expectedSignerSha256": common.EXPECTED_SIGNER_SHA256,
            "sourceGitCommit": commit,
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

        print("\nFLEET MANAGER PILOT RELEASE\n")
        print(f"Version        {identity.version_name}")
        print(f"Version Code   {identity.version_code}")
        print("Package        VALID")
        print("Signer         VALID")
        print(f"SHA-256        {identity.apk_sha256}")
        print(f"\nServer         {target}")
        print("Tailscale      CONNECTED")
        print("\nSending APK...")
        _run(
            [tailscale, "file", "cp", str(transfer_apk), f"{target}:"],
            "APK Taildrop",
            timeout=300,
        )
        print("Sending manifest...")
        _run(
            [tailscale, "file", "cp", str(manifest_path), f"{target}:"],
            "Manifest Taildrop",
            timeout=60,
        )

    print("\nTRANSFER COMPLETE")
    print("Waiting for server publication...")
    url = _wait_for_publication(dns_name, identity, timeout)
    print("\nPILOT RELEASE PUBLISHED")
    print(f"\nDownload:\n{url}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", nargs="?", type=Path, default=DEFAULT_APK)
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--timeout", type=int, default=360)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return send(args.apk.resolve(), args.target, args.timeout)
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
