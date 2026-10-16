import base64
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import validate_play_aab as validator

TEST_CERTIFICATE = b"synthetic-public-certificate"
TEST_SIGNER = hashlib.sha256(TEST_CERTIFICATE).hexdigest()
TEST_PEM = (
    "-----BEGIN CERTIFICATE-----\n"
    f"{base64.b64encode(TEST_CERTIFICATE).decode('ascii')}\n"
    "-----END CERTIFICATE-----\n"
)


def _manifest(
    *,
    package: str = validator.EXPECTED_PACKAGE,
    permission: str = "",
    target_sdk: int = 36,
    debuggable: str = "false",
) -> str:
    permission_xml = f'<uses-permission android:name="{permission}" />' if permission else ""
    return f"""<manifest xmlns:android="http://schemas.android.com/apk/res/android"
        android:versionCode="30" android:versionName="1.1.0" package="{package}">
      <uses-sdk android:minSdkVersion="24" android:targetSdkVersion="{target_sdk}" />
      {permission_xml}
      <application android:debuggable="{debuggable}" android:usesCleartextTraffic="false" />
    </manifest>"""


def _outputs(*, manifest: str | None = None) -> list[str]:
    return [
        "App Bundle information",
        manifest or _manifest(),
        TEST_PEM,
        "Certificate was added to keystore",
        "jar verified",
    ]


@pytest.fixture
def bundle_path() -> Iterator[Path]:
    path = Path.cwd() / ".fleet-play-validator-test.aab"
    path.write_bytes(b"signed-bundle")
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def test_play_bundle_contract_accepts_expected_identity(
    monkeypatch: pytest.MonkeyPatch, bundle_path: Path
) -> None:
    responses = iter(_outputs())
    monkeypatch.setattr(validator, "_tool", lambda _: "tool")
    monkeypatch.setattr(validator, "_verified_bundletool", lambda: Path("bundletool.jar"))
    monkeypatch.setattr(validator, "_run", lambda *_: next(responses))

    result = validator.validate_bundle(
        bundle_path,
        expected_version_name="1.1.0",
        expected_version_code=30,
        expected_signer=TEST_SIGNER,
    )

    assert result["package"] == validator.EXPECTED_PACKAGE
    assert result["targetSdk"] == 36
    assert result["privateApkInstallPermission"] == "absent"
    assert result["buildContractApiBaseUrl"] == validator.PRODUCTION_API
    assert result["buildContractAuthMode"] == "company_pin"
    assert "not inspected in AAB" in result["dartDefinesVerification"]
    assert "apiBaseUrl" not in result


def test_play_bundle_rejects_pilot_package(
    monkeypatch: pytest.MonkeyPatch, bundle_path: Path
) -> None:
    responses = iter(_outputs(manifest=_manifest(package=validator.PILOT_PACKAGE)))
    monkeypatch.setattr(validator, "_tool", lambda _: "tool")
    monkeypatch.setattr(validator, "_verified_bundletool", lambda: Path("bundletool.jar"))
    monkeypatch.setattr(validator, "_run", lambda *_: next(responses))

    with pytest.raises(validator.BundleValidationError, match="Wrong package"):
        validator.validate_bundle(
            bundle_path,
            expected_version_name="1.1.0",
            expected_version_code=30,
            expected_signer=TEST_SIGNER,
        )


def test_play_bundle_rejects_private_apk_install_permission(
    monkeypatch: pytest.MonkeyPatch, bundle_path: Path
) -> None:
    responses = iter(
        _outputs(manifest=_manifest(permission="android.permission.REQUEST_INSTALL_PACKAGES"))
    )
    monkeypatch.setattr(validator, "_tool", lambda _: "tool")
    monkeypatch.setattr(validator, "_verified_bundletool", lambda: Path("bundletool.jar"))
    monkeypatch.setattr(validator, "_run", lambda *_: next(responses))

    with pytest.raises(validator.BundleValidationError, match="sideload permission"):
        validator.validate_bundle(
            bundle_path,
            expected_version_name="1.1.0",
            expected_version_code=30,
            expected_signer=TEST_SIGNER,
        )


def test_play_bundle_rejects_outdated_target_sdk(
    monkeypatch: pytest.MonkeyPatch, bundle_path: Path
) -> None:
    responses = iter(_outputs(manifest=_manifest(target_sdk=35)))
    monkeypatch.setattr(validator, "_tool", lambda _: "tool")
    monkeypatch.setattr(validator, "_verified_bundletool", lambda: Path("bundletool.jar"))
    monkeypatch.setattr(validator, "_run", lambda *_: next(responses))

    with pytest.raises(validator.BundleValidationError, match="target API 36"):
        validator.validate_bundle(
            bundle_path,
            expected_version_name="1.1.0",
            expected_version_code=30,
            expected_signer=TEST_SIGNER,
        )


def test_play_bundle_rejects_debuggable_artifact(
    monkeypatch: pytest.MonkeyPatch, bundle_path: Path
) -> None:
    responses = iter(_outputs(manifest=_manifest(debuggable="true")))
    monkeypatch.setattr(validator, "_tool", lambda _: "tool")
    monkeypatch.setattr(validator, "_verified_bundletool", lambda: Path("bundletool.jar"))
    monkeypatch.setattr(validator, "_run", lambda *_: next(responses))

    with pytest.raises(validator.BundleValidationError, match="must not be debuggable"):
        validator.validate_bundle(
            bundle_path,
            expected_version_name="1.1.0",
            expected_version_code=30,
            expected_signer=TEST_SIGNER,
        )


def test_manifest_parser_rejects_invalid_xml() -> None:
    with pytest.raises(validator.BundleValidationError, match="invalid Android manifest"):
        validator._manifest_metadata("not xml")


@pytest.mark.parametrize(
    "manifest",
    ["<!DOCTYPE manifest><manifest />", " " * (1024 * 1024 + 1)],
    ids=["dtd", "oversized"],
)
def test_manifest_parser_rejects_dtd_or_oversized_input(manifest: str) -> None:
    with pytest.raises(validator.BundleValidationError, match="unsafe or oversized"):
        validator._manifest_metadata(manifest)


@pytest.mark.parametrize("exit_code", [1, 4, 8, 16, 32, 48])
def test_signature_verification_rejects_every_strict_failure(
    monkeypatch: pytest.MonkeyPatch, bundle_path: Path, exit_code: int
) -> None:
    calls: list[list[str]] = []

    def fake_run(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        if "-printcert" in arguments:
            return subprocess.CompletedProcess(arguments, 0, TEST_PEM, "")
        if "-importcert" in arguments:
            return subprocess.CompletedProcess(arguments, 0, "", "")
        assert "-strict" in arguments
        assert arguments[-1] == "approved-play-upload"
        return subprocess.CompletedProcess(
            arguments, exit_code, "jar verified, with signer errors", ""
        )

    monkeypatch.setattr(validator, "_tool", lambda name: name)
    monkeypatch.setattr(validator.subprocess, "run", fake_run)
    with pytest.raises(validator.BundleValidationError, match="signature verification failed"):
        validator._verify_signature(bundle_path, TEST_SIGNER)
    assert len(calls) == 3


@pytest.mark.parametrize("certificate_output", ["Not a signed jar file", TEST_PEM])
def test_signature_requires_the_approved_certificate(
    monkeypatch: pytest.MonkeyPatch, bundle_path: Path, certificate_output: str
) -> None:
    monkeypatch.setattr(validator, "_tool", lambda name: name)
    monkeypatch.setattr(validator, "_run", lambda *_: certificate_output)
    with pytest.raises(validator.BundleValidationError, match="does not match"):
        validator._verify_signature(bundle_path, "bb" * 32)


def test_signature_rejects_pilot_identity_before_tool_execution(bundle_path: Path) -> None:
    with pytest.raises(validator.BundleValidationError, match="must not reuse the Pilot signer"):
        validator._verify_signature(bundle_path, validator.PILOT_SIGNER_SHA256)


@pytest.fixture(scope="module")
def signed_test_archive() -> Iterator[tuple[Path, Path, str]]:
    if not all(shutil.which(name) for name in ("keytool", "jarsigner")):
        pytest.skip("JDK tools are needed for real JAR signature regression checks")
    # These disposable test-only identities never use release/Pilot keystores.
    with tempfile.TemporaryDirectory(prefix=".fleet-signature-test-", dir=Path.cwd()) as folder:
        directory = Path(folder)
        keystore = directory / "test-only.p12"
        archive = directory / "synthetic.aab"
        for alias in ("expected", "unexpected"):
            validator._run(
                [
                    validator._tool("keytool"),
                    "-genkeypair",
                    "-noprompt",
                    "-alias",
                    alias,
                    "-keystore",
                    str(keystore),
                    "-storetype",
                    "PKCS12",
                    "-storepass",
                    "test-only-password",
                    "-keyalg",
                    "RSA",
                    "-keysize",
                    "2048",
                    "-validity",
                    "2",
                    "-dname",
                    "CN=Disposable validation test",
                ],
                "Synthetic test certificate generation",
            )
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("base/assets/test.txt", "original payload")
        validator._run(
            [
                validator._tool("jarsigner"),
                "-keystore",
                str(keystore),
                "-storepass",
                "test-only-password",
                str(archive),
                "expected",
            ],
            "Synthetic test archive signing",
        )
        certificate = validator._run(
            [validator._tool("keytool"), "-printcert", "-rfc", "-jarfile", str(archive)],
            "Synthetic test certificate inspection",
        )
        encoded = re.search(
            r"-----BEGIN CERTIFICATE-----\s*(.*?)\s*-----END CERTIFICATE-----",
            certificate,
            re.DOTALL,
        )
        assert encoded is not None
        fingerprint = hashlib.sha256(base64.b64decode(encoded.group(1))).hexdigest()
        yield archive, keystore, fingerprint


def test_real_self_signed_archive_is_accepted(
    signed_test_archive: tuple[Path, Path, str],
) -> None:
    archive, _, fingerprint = signed_test_archive
    assert validator._verify_signature(archive, fingerprint) == fingerprint


@pytest.mark.parametrize("resign_with_other_identity", [False, True])
def test_real_archive_rejects_unsigned_or_differently_signed_added_content(
    signed_test_archive: tuple[Path, Path, str], resign_with_other_identity: bool
) -> None:
    original, keystore, fingerprint = signed_test_archive
    archive = original.with_name(f"modified-{resign_with_other_identity}.aab")
    shutil.copyfile(original, archive)
    with zipfile.ZipFile(archive, "a") as zipped:
        zipped.writestr("base/assets/added.txt", "not signed by the approved identity")
    if resign_with_other_identity:
        validator._run(
            [
                validator._tool("jarsigner"),
                "-keystore",
                str(keystore),
                "-storepass",
                "test-only-password",
                str(archive),
                "unexpected",
            ],
            "Synthetic test archive signing by another identity",
        )
    with pytest.raises(validator.BundleValidationError, match="signature verification failed"):
        validator._verify_signature(archive, fingerprint)
