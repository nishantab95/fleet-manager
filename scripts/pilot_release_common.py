"""Shared, dependency-free verification for Fleet Manager pilot APK releases."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


EXPECTED_PACKAGE = "com.fleetmanager.fleet_manager_mobile.pilot"
EXPECTED_SIGNER_SHA256 = (
    "45a624b2f96e2ae4e51b2e5eb19acda0e321287bf501b2a09bfdd6e207034196"
)
APK_PREFIX = "FleetManager-Pilot-upload-"
APK_SUFFIX = ".apk"
MANIFEST_SUFFIX = ".json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class ReleaseValidationError(RuntimeError):
    """A release failed an identity, integrity, or provenance check."""


@dataclass(frozen=True)
class ApkIdentity:
    package: str
    version_name: str
    version_code: int
    signer_sha256: str
    apk_sha256: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_android_tool(name: str) -> Path:
    executable = (
        shutil.which(name) or shutil.which(f"{name}.bat") or shutil.which(f"{name}.exe")
    )
    if executable:
        return Path(executable)
    sdk = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    if not sdk and os.environ.get("LOCALAPPDATA"):
        sdk = str(Path(os.environ["LOCALAPPDATA"]) / "Android" / "Sdk")
    if sdk:
        build_tools = Path(sdk) / "build-tools"
        if build_tools.is_dir():
            for version in sorted(build_tools.iterdir(), reverse=True):
                for suffix in (".bat", ".exe", ""):
                    candidate = version / f"{name}{suffix}"
                    if candidate.is_file():
                        return candidate
    raise ReleaseValidationError(f"Android SDK tool is missing: {name}")


def _run_tool(arguments: list[str], label: str) -> str:
    result = subprocess.run(
        arguments,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ReleaseValidationError(f"{label} failed: {detail or 'unknown error'}")
    return result.stdout


def inspect_apk(path: Path) -> ApkIdentity:
    if not path.is_file() or path.suffix.casefold() != ".apk":
        raise ReleaseValidationError(f"APK was not found: {path}")
    badging = _run_tool(
        [str(_find_android_tool("aapt")), "dump", "badging", str(path)],
        "APK metadata inspection",
    )
    package_match = re.search(
        r"^package: name='([^']+)' versionCode='([0-9]+)' versionName='([^']+)'",
        badging,
        re.MULTILINE,
    )
    if not package_match:
        raise ReleaseValidationError(
            "APK package/version metadata could not be parsed."
        )
    signer_output = _run_tool(
        [str(_find_android_tool("apksigner")), "verify", "--print-certs", str(path)],
        "APK signature verification",
    )
    signer_match = re.search(
        r"Signer #1 certificate SHA-256 digest:\s*([0-9a-fA-F:]+)", signer_output
    )
    if not signer_match:
        raise ReleaseValidationError("APK signer SHA-256 could not be parsed.")
    signer = signer_match.group(1).replace(":", "").casefold()
    return ApkIdentity(
        package=package_match.group(1),
        version_code=int(package_match.group(2)),
        version_name=package_match.group(3),
        signer_sha256=signer,
        apk_sha256=sha256_file(path),
    )


def validate_expected_identity(identity: ApkIdentity) -> None:
    if identity.version_code <= 0 or not identity.version_name.strip():
        raise ReleaseValidationError("APK version metadata is invalid.")
    if not SHA256_RE.fullmatch(identity.apk_sha256):
        raise ReleaseValidationError("APK SHA-256 is invalid.")
    if identity.package != EXPECTED_PACKAGE:
        raise ReleaseValidationError(
            f"Wrong package: expected {EXPECTED_PACKAGE}, found {identity.package}"
        )
    if identity.signer_sha256 != EXPECTED_SIGNER_SHA256:
        raise ReleaseValidationError("Wrong APK signing certificate SHA-256.")


def version_text(identity: ApkIdentity, filename: str) -> str:
    return (
        "Fleet Manager Pilot\n"
        f"{identity.version_name}\n"
        f"VersionCode {identity.version_code}\n"
        f"{filename}\n"
    )
