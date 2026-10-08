from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import pilot_release_common as common
import pilot_release_inbox as inbox


def identity(
    path: Path,
    *,
    code: int = 19,
    package: str = common.EXPECTED_PACKAGE,
    signer: str = common.EXPECTED_SIGNER_SHA256,
) -> common.ApkIdentity:
    return common.ApkIdentity(
        package=package,
        version_name=f"1.0.{code - 1}-pilot",
        version_code=code,
        signer_sha256=signer,
        apk_sha256=common.sha256_file(path),
    )


def manifest_for(apk: Path, item: common.ApkIdentity) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "releaseId": f"{item.version_code}-{item.apk_sha256[:16]}",
        "apkFile": apk.name,
        "package": item.package,
        "versionName": item.version_name,
        "versionCode": item.version_code,
        "apkSha256": item.apk_sha256,
        "expectedSignerSha256": item.signer_sha256,
        "sourceGitCommit": "a" * 40,
    }


def configure_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "incoming"
    monkeypatch.setattr(inbox, "INBOX_ROOT", root)
    monkeypatch.setattr(inbox, "ARCHIVE_DIR", root / "archive")
    monkeypatch.setattr(inbox, "REJECTED_DIR", root / "rejected")
    monkeypatch.setattr(inbox, "STAGING_DIR", root / "staging")
    monkeypatch.setattr(inbox, "STATUS_FILE", root / "publisher-status.json")
    monkeypatch.setattr(inbox, "LOCK_FILE", root / "publisher.lock")
    monkeypatch.setattr(inbox, "LOG_FILE", tmp_path / "publisher.log")
    root.mkdir()
    (root / "staging").mkdir()
    return root


def test_incomplete_pair_is_not_processed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = configure_paths(monkeypatch, tmp_path)
    manifest = root / "FleetManager-Pilot-upload-19-abc.json"
    manifest.write_text("{}", encoding="utf-8")

    assert inbox.process_manifest(manifest, stability_delay=0) == "INCOMPLETE"
    assert manifest.exists()


def test_complete_pair_is_validated_published_and_archived(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = configure_paths(monkeypatch, tmp_path)
    apk = root / "FleetManager-Pilot-upload-19-abc.apk"
    manifest_path = apk.with_suffix(".json")
    apk.write_bytes(b"candidate")
    item = identity(apk)
    manifest_path.write_text(json.dumps(manifest_for(apk, item)), encoding="utf-8")
    monkeypatch.setattr(inbox.common, "inspect_apk", lambda _: item)
    monkeypatch.setattr(inbox, "_publish_transaction", lambda *_: "PUBLISHED")

    assert inbox.process_manifest(manifest_path, stability_delay=0) == "PUBLISHED"
    archive = root / "archive" / f"19-{item.apk_sha256[:16]}"
    assert (archive / "manifest.json").is_file()
    assert (
        json.loads((archive / "receipt.json").read_text(encoding="utf-8"))["outcome"]
        == "PUBLISHED"
    )
    assert not apk.exists()
    assert not manifest_path.exists()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda value: value.update(apkSha256="0" * 64), "apkSha256"),
        (lambda value: value.update(package="wrong.package"), "package"),
        (lambda value: value.update(expectedSignerSha256="0" * 64), "expectedSigner"),
    ],
)
def test_manifest_identity_mismatch_is_rejected(
    tmp_path: Path, change: object, message: str
) -> None:
    apk = tmp_path / "FleetManager-Pilot-upload-19-abc.apk"
    apk.write_bytes(b"candidate")
    item = identity(apk)
    value = manifest_for(apk, item)
    change(value)  # type: ignore[operator]

    with pytest.raises(inbox.InboxError, match=message):
        inbox._validate_manifest(value, item, apk.name)


def test_signed_identity_rejects_wrong_package_and_signer(tmp_path: Path) -> None:
    apk = tmp_path / "candidate.apk"
    apk.write_bytes(b"candidate")
    with pytest.raises(common.ReleaseValidationError, match="Wrong package"):
        common.validate_expected_identity(identity(apk, package="wrong.package"))
    with pytest.raises(common.ReleaseValidationError, match="SIGNING_IDENTITY_MISMATCH=YES"):
        common.validate_expected_identity(identity(apk, signer="0" * 64))


def test_downgrade_is_refused_before_publish(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = tmp_path / "pilot"
    release.mkdir()
    current = release / inbox.server_manager.PILOT_APK_NAME
    current.write_bytes(b"current")
    candidate = tmp_path / "candidate.apk"
    candidate.write_bytes(b"candidate")
    monkeypatch.setattr(inbox.server_manager, "PILOT_RELEASE_DIR", release)
    monkeypatch.setattr(
        inbox.common, "inspect_apk", lambda _: identity(current, code=20)
    )
    monkeypatch.setattr(
        inbox.server_manager,
        "publish_pilot_apk",
        lambda *_: pytest.fail("downgrade must not publish"),
    )

    with pytest.raises(inbox.InboxError, match="Downgrade refused"):
        inbox._publish_transaction(identity(candidate, code=19), candidate)


def test_same_version_and_hash_is_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = tmp_path / "pilot"
    release.mkdir()
    current = release / inbox.server_manager.PILOT_APK_NAME
    current.write_bytes(b"same")
    monkeypatch.setattr(inbox.server_manager, "PILOT_RELEASE_DIR", release)
    current_identity = identity(current, code=19)
    monkeypatch.setattr(inbox.common, "inspect_apk", lambda _: current_identity)

    assert inbox._publish_transaction(current_identity, current) == "ALREADY PUBLISHED"


def test_remote_failure_restores_previous_latest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = tmp_path / "pilot"
    release.mkdir()
    names = (
        inbox.server_manager.PILOT_APK_NAME,
        inbox.server_manager.PILOT_SHA256_NAME,
        inbox.server_manager.PILOT_VERSION_NAME,
    )
    old = {names[0]: b"old-apk", names[1]: b"old-sha", names[2]: b"old-version"}
    for name, content in old.items():
        (release / name).write_bytes(content)
    candidate = tmp_path / "candidate.apk"
    candidate.write_bytes(b"new-apk")
    old_identity = identity(release / names[0], code=18)
    new_identity = identity(candidate, code=19)
    monkeypatch.setattr(inbox.server_manager, "PILOT_RELEASE_DIR", release)
    monkeypatch.setattr(inbox.common, "inspect_apk", lambda _: old_identity)

    def publish(source: Path, version_file: Path) -> int:
        shutil.copy2(source, release / names[0])
        (release / names[1]).write_text("new-sha", encoding="utf-8")
        shutil.copy2(version_file, release / names[2])
        return 0

    monkeypatch.setattr(inbox.server_manager, "publish_pilot_apk", publish)
    monkeypatch.setattr(
        inbox.server_manager,
        "remote_access_status",
        lambda: {"remote_url": "https://fleet.test", "serve_pilot": "OK"},
    )
    monkeypatch.setattr(inbox, "_remote_sha256", lambda _: "0" * 64)

    with pytest.raises(inbox.InboxError, match="download hash"):
        inbox._publish_transaction(new_identity, candidate)

    assert {name: (release / name).read_bytes() for name in names} == old
    assert not list(release.glob("FleetManager-Pilot-1.0.18-pilot-code19.apk"))


def test_successful_publish_preserves_versioned_apk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = tmp_path / "pilot"
    candidate = tmp_path / "candidate.apk"
    candidate.write_bytes(b"new-apk")
    item = identity(candidate, code=19)
    monkeypatch.setattr(inbox.server_manager, "PILOT_RELEASE_DIR", release)

    def publish(source: Path, version_file: Path) -> int:
        release.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, release / inbox.server_manager.PILOT_APK_NAME)
        shutil.copy2(version_file, release / inbox.server_manager.PILOT_VERSION_NAME)
        (release / inbox.server_manager.PILOT_SHA256_NAME).write_text(
            item.apk_sha256, encoding="utf-8"
        )
        return 0

    monkeypatch.setattr(inbox.server_manager, "publish_pilot_apk", publish)
    monkeypatch.setattr(
        inbox.server_manager,
        "remote_access_status",
        lambda: {"remote_url": "https://fleet.test", "serve_pilot": "OK"},
    )
    monkeypatch.setattr(inbox, "_remote_sha256", lambda _: item.apk_sha256)

    assert inbox._publish_transaction(item, candidate) == "PUBLISHED"
    versioned = release / "FleetManager-Pilot-1.0.18-pilot-code19.apk"
    assert versioned.read_bytes() == candidate.read_bytes()
    assert (
        release / inbox.server_manager.PILOT_APK_NAME
    ).read_bytes() == candidate.read_bytes()
