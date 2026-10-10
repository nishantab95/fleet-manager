"""Verify a Firebase client APK without printing configured client values."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from zipfile import ZipFile

from pilot_release_common import inspect_apk, validate_expected_identity


FORBIDDEN_MARKERS = {
    "service-account private key": b"-----BEGIN PRIVATE KEY-----",
    "service-account private_key field": b'"private_key"',
    "service-account private_key_id field": b'"private_key_id"',
    "Firebase Admin service account name": b"firebase-adminsdk",
}


def scan_apk_strings(
    path: Path,
    *,
    required: dict[str, bytes],
    forbidden: dict[str, bytes] = FORBIDDEN_MARKERS,
) -> tuple[set[str], set[str]]:
    """Return labels for required markers found and forbidden markers present."""

    found_required: set[str] = set()
    found_forbidden: set[str] = set()
    patterns = {**required, **forbidden}
    max_pattern = max((len(pattern) for pattern in patterns.values()), default=1)
    with ZipFile(path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            tail = b""
            with archive.open(member) as handle:
                while chunk := handle.read(1024 * 1024):
                    window = tail + chunk
                    for label, pattern in required.items():
                        if label not in found_required and pattern in window:
                            found_required.add(label)
                    for label, pattern in forbidden.items():
                        if label not in found_forbidden and pattern in window:
                            found_forbidden.add(label)
                    tail = window[-(max_pattern - 1) :] if max_pattern > 1 else b""
    return found_required, found_forbidden


def verify_staging_apk(
    path: Path,
    *,
    version_name: str,
    version_code: int,
    api_base_url: str,
    api_key: str,
    app_id: str,
    sender_id: str,
    project_id: str,
    build_profile: str = "firebase-staging",
) -> dict[str, object]:
    if build_profile not in {"firebase-staging", "firebase-company"}:
        raise RuntimeError("Unsupported Firebase build profile")
    identity = inspect_apk(path)
    validate_expected_identity(identity)
    if (
        identity.version_name != f"{version_name}-pilot"
        or identity.version_code != version_code
    ):
        raise RuntimeError("APK version does not match pubspec.yaml")

    required = {
        "Firebase build profile": build_profile.encode("utf-8"),
        "API base URL": api_base_url.encode("utf-8"),
        "Firebase Android API key": api_key.encode("utf-8"),
        "Firebase Android app ID": app_id.encode("utf-8"),
        "Firebase messaging sender ID": sender_id.encode("utf-8"),
        "Firebase project ID": project_id.encode("utf-8"),
    }
    found, forbidden = scan_apk_strings(path, required=required)
    missing = sorted(set(required) - found)
    if missing:
        raise RuntimeError(
            "APK is missing expected Firebase markers: " + ", ".join(missing)
        )
    if forbidden:
        raise RuntimeError(
            "APK contains forbidden credential markers: " + ", ".join(sorted(forbidden))
        )

    return {
        "package": identity.package,
        "versionName": identity.version_name,
        "versionCode": identity.version_code,
        "signerSha256": identity.signer_sha256,
        "apkSha256": identity.apk_sha256,
        "authMode": "firebase",
        "buildProfile": build_profile,
        "requiredMarkersVerified": sorted(found),
        "forbiddenCredentialMarkers": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("apk", type=Path)
    parser.add_argument("--version-name", required=True)
    parser.add_argument("--version-code", required=True, type=int)
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--sender-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument(
        "--build-profile",
        choices=("firebase-staging", "firebase-company"),
        default="firebase-staging",
    )
    args = parser.parse_args()
    result = verify_staging_apk(
        args.apk,
        version_name=args.version_name,
        version_code=args.version_code,
        api_base_url=args.api_base_url,
        api_key=args.api_key,
        app_id=args.app_id,
        sender_id=args.sender_id,
        project_id=args.project_id,
        build_profile=args.build_profile,
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
