import json
from pathlib import Path

import pytest

import pilot_release_common as common
import send_pilot_release as sender


def _identity(apk: Path) -> common.ApkIdentity:
    return common.ApkIdentity(
        package=common.EXPECTED_PACKAGE,
        version_name="1.0.21-pilot",
        version_code=22,
        signer_sha256=common.EXPECTED_SIGNER_SHA256,
        apk_sha256=common.sha256_file(apk),
    )


def _provenance(identity: common.ApkIdentity) -> dict[str, object]:
    return {
        "package": identity.package,
        "versionName": identity.version_name,
        "versionCode": identity.version_code,
        "signerSha256": identity.signer_sha256,
        "apkSha256": identity.apk_sha256,
        "sourceGitCommit": "a" * 40,
        "sourceTreeClean": True,
        "authMode": "firebase",
        "buildProfile": "firebase-company",
    }


def test_company_provenance_and_manifest_are_explicit(tmp_path: Path) -> None:
    apk = tmp_path / "company.apk"
    apk.write_bytes(b"company-apk")
    identity = _identity(apk)
    provenance = _provenance(identity)
    Path(f"{apk}.build.json").write_text(json.dumps(provenance), encoding="utf-8")

    validated = sender._validate_build_provenance(
        apk,
        identity,
        "a" * 40,
        require_firebase_company=True,
    )
    manifest = sender._release_manifest(
        identity,
        apk_file="FleetManager-Pilot-upload.apk",
        release_id="22-company",
        commit="a" * 40,
        provenance=validated,
        require_firebase_company=True,
    )

    assert manifest["authMode"] == "firebase"
    assert manifest["buildProfile"] == "firebase-company"


def test_company_send_rejects_staging_provenance(tmp_path: Path) -> None:
    apk = tmp_path / "staging.apk"
    apk.write_bytes(b"staging-apk")
    identity = _identity(apk)
    provenance = _provenance(identity)
    provenance["buildProfile"] = "firebase-staging"
    Path(f"{apk}.build.json").write_text(json.dumps(provenance), encoding="utf-8")

    with pytest.raises(sender.SendError, match="Firebase company APK"):
        sender._validate_build_provenance(
            apk,
            identity,
            "a" * 40,
            require_firebase_company=True,
        )
