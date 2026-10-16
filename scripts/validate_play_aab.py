"""Validate a signed Fleet AI Systems Google Play app bundle."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED_PACKAGE = "com.fleetmanager.fleet_manager_mobile"
PILOT_PACKAGE = "com.fleetmanager.fleet_manager_mobile.pilot"
PILOT_SIGNER_SHA256 = "fd25115e20ac18a8a7cda91b9f4d5f6153f54b4d79c751b5005a3ac734cc3c29"
PRODUCTION_API = "https://api.fleetaisystems.com"
REQUIRED_TARGET_SDK = 36
BUNDLETOOL_VERSION = "1.18.3"
BUNDLETOOL_SHA256 = "a099cfa1543f55593bc2ed16a70a7c67fe54b1747bb7301f37fdfd6d91028e29"
BUNDLETOOL_URL = (
    "https://github.com/google/bundletool/releases/download/"
    f"{BUNDLETOOL_VERSION}/bundletool-all-{BUNDLETOOL_VERSION}.jar"
)
ANDROID_NAMESPACE = "http://schemas.android.com/apk/res/android"


class BundleValidationError(RuntimeError):
    """The candidate AAB does not satisfy the production release contract."""


def _tool(name: str) -> str:
    candidates = [name, f"{name}.bat", f"{name}.exe"]
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
    java_home = os.environ.get("JAVA_HOME", "").strip()
    if java_home and name in {"keytool", "jarsigner"}:
        candidate = Path(java_home) / "bin" / f"{name}.exe"
        if candidate.is_file():
            return str(candidate)
    raise BundleValidationError(f"Required release tool is unavailable: {name}")


def _run(arguments: list[str], label: str) -> str:
    # Callers resolve fixed JDK tools; argument arrays are never passed to a shell.
    result = subprocess.run(  # noqa: S603
        arguments,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise BundleValidationError(f"{label} failed: {detail[-1] if detail else 'unknown error'}")
    return result.stdout


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_bundletool() -> Path:
    configured = os.environ.get("FLEET_BUNDLETOOL_JAR", "").strip()
    if configured:
        candidate = Path(configured).expanduser().resolve()
    else:
        cache_root = Path(tempfile.gettempdir()) / "fleet-ai-release-tools"
        cache_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        candidate = cache_root / f"bundletool-all-{BUNDLETOOL_VERSION}.jar"
        if not candidate.is_file():
            partial = candidate.with_suffix(".jar.part")
            try:
                # Fixed HTTPS release URL; verify the pinned SHA-256 before execution.
                with urllib.request.urlopen(BUNDLETOOL_URL, timeout=60) as response:  # noqa: S310
                    with partial.open("wb") as destination:
                        shutil.copyfileobj(response, destination)
                partial.replace(candidate)
            except Exception as error:
                partial.unlink(missing_ok=True)
                raise BundleValidationError(
                    "Pinned bundletool could not be downloaded; set FLEET_BUNDLETOOL_JAR "
                    "to an approved local copy."
                ) from error
    if not candidate.is_file():
        raise BundleValidationError(f"Configured bundletool JAR is unavailable: {candidate}")
    actual_digest = _sha256(candidate)
    if actual_digest != BUNDLETOOL_SHA256:
        raise BundleValidationError(
            f"bundletool {BUNDLETOOL_VERSION} checksum mismatch; refusing to execute it."
        )
    return candidate


def _manifest_metadata(manifest_xml: str) -> dict[str, str | int | set[str]]:
    if len(manifest_xml) > 1024 * 1024 or "<!DOCTYPE" in manifest_xml.upper():
        raise BundleValidationError("bundletool returned an unsafe or oversized Android manifest.")
    try:
        # Input comes from pinned bundletool; DTDs and oversized input are rejected above.
        root = ET.fromstring(manifest_xml)  # noqa: S314
    except ET.ParseError as error:
        raise BundleValidationError("bundletool returned an invalid Android manifest.") from error
    android = f"{{{ANDROID_NAMESPACE}}}"
    uses_sdk = root.find("uses-sdk")
    application = root.find("application")
    if uses_sdk is None or application is None:
        raise BundleValidationError("Android bundle manifest is missing required elements.")
    try:
        version_code = int(root.attrib[f"{android}versionCode"])
        target_sdk = int(uses_sdk.attrib[f"{android}targetSdkVersion"])
    except (KeyError, ValueError) as error:
        raise BundleValidationError("AAB numeric metadata is invalid.") from error
    permissions = {
        permission.attrib.get(f"{android}name", "")
        for permission in root.findall("uses-permission")
    }
    return {
        "package": root.attrib.get("package", ""),
        "versionName": root.attrib.get(f"{android}versionName", ""),
        "versionCode": version_code,
        "targetSdk": target_sdk,
        "debuggable": application.attrib.get(f"{android}debuggable", "false"),
        "usesCleartextTraffic": application.attrib.get(f"{android}usesCleartextTraffic", "false"),
        "permissions": permissions,
    }


def normalize_fingerprint(value: str) -> str:
    normalized = value.replace(":", "").strip().casefold()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        raise BundleValidationError("Expected Play upload certificate SHA-256 is invalid.")
    return normalized


def _verify_signature(bundle: Path, expected_signer: str) -> str:
    expected = normalize_fingerprint(expected_signer)
    if expected == PILOT_SIGNER_SHA256:
        raise BundleValidationError(
            "The Google Play upload identity must not reuse the Pilot signer."
        )
    keytool = _tool("keytool")
    certificates = _run(
        [keytool, "-J-Duser.language=en", "-printcert", "-rfc", "-jarfile", str(bundle)],
        "AAB certificate inspection",
    )
    approved_certificate = None
    for encoded in re.findall(
        r"-----BEGIN CERTIFICATE-----\s*(.*?)\s*-----END CERTIFICATE-----",
        certificates,
        re.DOTALL,
    ):
        try:
            der = base64.b64decode(re.sub(r"\s+", "", encoded), validate=True)
        except (ValueError, binascii.Error) as error:
            raise BundleValidationError("AAB signer certificate is invalid.") from error
        if hashlib.sha256(der).hexdigest() == expected:
            approved_certificate = (
                f"-----BEGIN CERTIFICATE-----\n{encoded}\n-----END CERTIFICATE-----\n"
            )
    if approved_certificate is None:
        raise BundleValidationError(
            "AAB signer does not match the approved Play upload certificate."
        )

    # Trust only the externally pinned public certificate, never the developer's
    # default keystore. This permits a self-signed upload certificate without
    # accepting jarsigner's unsigned-entry or wrong-signer warnings. No private
    # key is read, created, or imported by this verification-only truststore.
    with tempfile.TemporaryDirectory(prefix="fleet-play-verify-") as directory:
        certificate_file = Path(directory) / "approved-upload.pem"
        truststore = Path(directory) / "verification.p12"
        certificate_file.write_text(approved_certificate, encoding="ascii")
        public_store_password = secrets.token_hex(16)
        alias = "approved-play-upload"
        _run(
            [
                keytool,
                "-J-Duser.language=en",
                "-importcert",
                "-noprompt",
                "-alias",
                alias,
                "-file",
                str(certificate_file),
                "-keystore",
                str(truststore),
                "-storetype",
                "PKCS12",
                "-storepass",
                public_store_password,
            ],
            "Approved AAB public certificate import",
        )
        signature_output = _run(
            [
                _tool("jarsigner"),
                "-J-Duser.language=en",
                "-verify",
                "-strict",
                "-certs",
                "-keystore",
                str(truststore),
                "-storetype",
                "PKCS12",
                "-storepass",
                public_store_password,
                str(bundle),
                alias,
            ],
            "AAB signature verification",
        )
    if not re.search(r"\bjar verified\b", signature_output, re.IGNORECASE):
        raise BundleValidationError("AAB signature verification did not confirm a signed bundle.")
    return expected


def validate_bundle(
    bundle: Path,
    *,
    expected_version_name: str,
    expected_version_code: int,
    expected_signer: str,
) -> dict[str, str | int]:
    if not bundle.is_file() or bundle.suffix.casefold() != ".aab":
        raise BundleValidationError(f"AAB was not found: {bundle}")

    bundletool = _verified_bundletool()
    java = _tool("java")
    _run(
        [java, "-jar", str(bundletool), "validate", f"--bundle={bundle}"],
        "Android App Bundle validation",
    )
    manifest = _run(
        [java, "-jar", str(bundletool), "dump", "manifest", f"--bundle={bundle}"],
        "Android App Bundle manifest inspection",
    )
    metadata = _manifest_metadata(manifest)
    package = str(metadata["package"])
    version_name = str(metadata["versionName"])
    version_code = int(metadata["versionCode"])
    target_sdk = int(metadata["targetSdk"])
    permissions = metadata["permissions"]
    assert isinstance(permissions, set)
    if "android.permission.REQUEST_INSTALL_PACKAGES" in permissions:
        raise BundleValidationError(
            "Google Play bundle contains the private APK sideload permission."
        )
    if metadata["debuggable"] == "true":
        raise BundleValidationError("Google Play bundle must not be debuggable.")
    if metadata["usesCleartextTraffic"] != "false":
        raise BundleValidationError("Google Play bundle must disable cleartext traffic.")

    if package != EXPECTED_PACKAGE or package == PILOT_PACKAGE:
        raise BundleValidationError(f"Wrong package: expected {EXPECTED_PACKAGE}, found {package}")
    if version_name != expected_version_name or version_code != expected_version_code:
        raise BundleValidationError("AAB version does not match the approved release inputs.")
    if target_sdk != REQUIRED_TARGET_SDK:
        raise BundleValidationError(
            f"Google Play bundle must target API {REQUIRED_TARGET_SDK}; found {target_sdk}."
        )
    signer = _verify_signature(bundle, expected_signer)

    digest = _sha256(bundle)
    return {
        "package": package,
        "versionName": version_name,
        "versionCode": version_code,
        "targetSdk": target_sdk,
        "signerSha256": signer,
        "aabSha256": digest,
        # Dart defines are enforced by the approved builder/workflow. Bundletool
        # manifest inspection does not establish the values compiled into Dart.
        "buildContractApiBaseUrl": PRODUCTION_API,
        "buildContractAuthMode": "company_pin",
        "dartDefinesVerification": "build-workflow-only; not inspected in AAB",
        "privateApkInstallPermission": "absent",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--version-name", required=True)
    parser.add_argument("--version-code", required=True, type=int)
    parser.add_argument("--signer-sha256", required=True)
    args = parser.parse_args()
    try:
        result = validate_bundle(
            args.bundle,
            expected_version_name=args.version_name,
            expected_version_code=args.version_code,
            expected_signer=args.signer_sha256,
        )
    except (BundleValidationError, OSError, subprocess.TimeoutExpired) as error:
        print(f"[FAILED] {error}", file=sys.stderr)
        return 1
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
