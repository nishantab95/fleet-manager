from __future__ import annotations

import json
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
    monkeypatch.setattr(
        inbox, "_publish_transaction", lambda *_args, **_kwargs: "PUBLISHED"
    )

    assert inbox.process_manifest(manifest_path, stability_delay=0) == "PUBLISHED"
    archive = root / "archive" / f"19-{item.apk_sha256[:16]}"
    assert (archive / "manifest.json").is_file()
    assert (
        json.loads((archive / "receipt.json").read_text(encoding="utf-8"))["outcome"]
        == "PUBLISHED"
    )
    assert not apk.exists()
    assert not manifest_path.exists()


def test_oversized_taildrop_candidate_is_rejected_before_publication(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = configure_paths(monkeypatch, tmp_path)
    apk = root / "FleetManager-Pilot-upload-19-large.apk"
    manifest_path = apk.with_suffix(".json")
    apk.write_bytes(b"too-large")
    item = identity(apk)
    manifest_path.write_text(json.dumps(manifest_for(apk, item)), encoding="utf-8")
    monkeypatch.setattr(inbox, "MAX_APK_BYTES", 2)
    monkeypatch.setattr(
        inbox,
        "_publish_transaction",
        lambda *_args, **_kwargs: pytest.fail("oversized candidate must not publish"),
    )

    assert inbox.process_manifest(manifest_path, stability_delay=0) == "REJECTED"
    assert not apk.exists()
    assert not manifest_path.exists()


def test_https_pair_is_staged_and_processed_under_shared_lock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = configure_paths(monkeypatch, tmp_path)
    staged = root / "staging" / "candidate.partial"
    staged.write_bytes(b"candidate")
    manifest = {
        "releaseId": "https-safe",
        "apkFile": "FleetManager-Pilot-upload-https-safe.apk",
    }
    observed: dict[str, Path] = {}

    def process(path: Path, *, stability_delay: float) -> str:
        observed["manifest"] = path
        observed["apk"] = path.with_suffix(".apk")
        assert stability_delay == 0
        assert path.is_file()
        assert path.with_suffix(".apk").read_bytes() == b"candidate"
        return "PUBLISHED"

    monkeypatch.setattr(inbox, "process_manifest", process)

    assert inbox.publish_uploaded_pair(staged, manifest) == "PUBLISHED"
    assert not staged.exists()
    assert observed["manifest"].parent == root


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


def test_company_manifest_requires_company_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    apk = tmp_path / "candidate.apk"
    apk.write_bytes(b"candidate")
    manifest = {"authMode": "firebase", "buildProfile": "firebase-company"}
    monkeypatch.setattr(
        inbox, "scan_apk_strings", lambda *_args, **_kwargs: (set(), set())
    )

    with pytest.raises(inbox.InboxError, match="company build markers"):
        inbox._validate_optional_company_profile(manifest, apk)


def test_company_pin_manifest_requires_auth_and_profile_markers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    apk = tmp_path / "candidate.apk"
    apk.write_bytes(b"candidate")
    manifest = {"authMode": "company_pin", "buildProfile": "company-pin"}
    monkeypatch.setattr(
        inbox,
        "scan_apk_strings",
        lambda *_args, **_kwargs: (
            {"Company PIN auth mode", "Company PIN build profile"},
            set(),
        ),
    )

    inbox._validate_optional_company_profile(manifest, apk)


def test_company_manifest_rejects_service_account_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    apk = tmp_path / "candidate.apk"
    apk.write_bytes(b"candidate")
    manifest = {"authMode": "firebase", "buildProfile": "firebase-company"}
    monkeypatch.setattr(
        inbox,
        "scan_apk_strings",
        lambda *_args, **_kwargs: (
            {"Firebase company build profile"},
            {"service-account private key"},
        ),
    )

    with pytest.raises(inbox.InboxError, match="forbidden credential"):
        inbox._validate_optional_company_profile(manifest, apk)


def test_signed_identity_rejects_wrong_package_and_signer(tmp_path: Path) -> None:
    apk = tmp_path / "candidate.apk"
    apk.write_bytes(b"candidate")
    with pytest.raises(common.ReleaseValidationError, match="Wrong package"):
        common.validate_expected_identity(identity(apk, package="wrong.package"))
    with pytest.raises(
        common.ReleaseValidationError, match="SIGNING_IDENTITY_MISMATCH=YES"
    ):
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
        inbox._publish_transaction(
            identity(candidate, code=19),
            candidate,
            source_commit="a" * 40,
        )


def test_same_version_is_refused_even_when_hash_matches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = tmp_path / "pilot"
    release.mkdir()
    current = release / inbox.server_manager.PILOT_APK_NAME
    current.write_bytes(b"same")
    monkeypatch.setattr(inbox.server_manager, "PILOT_RELEASE_DIR", release)
    current_identity = identity(current, code=19)
    monkeypatch.setattr(inbox.common, "inspect_apk", lambda _: current_identity)

    with pytest.raises(inbox.InboxError, match="Same versionCode"):
        inbox._publish_transaction(
            current_identity,
            current,
            source_commit="a" * 40,
        )


def test_publication_failure_leaves_existing_release_for_shared_transaction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = tmp_path / "pilot"
    release.mkdir()
    names = (
        inbox.server_manager.PILOT_APK_NAME,
        inbox.server_manager.PILOT_SHA256_NAME,
        inbox.server_manager.PILOT_VERSION_NAME,
        inbox.server_manager.PILOT_RELEASE_MANIFEST_NAME,
    )
    old = {
        names[0]: b"old-apk",
        names[1]: b"old-sha",
        names[2]: b"old-version",
        names[3]: b'{"version_code": 18}\n',
    }
    for name, content in old.items():
        (release / name).write_bytes(content)
    candidate = tmp_path / "candidate.apk"
    candidate.write_bytes(b"new-apk")
    old_identity = identity(release / names[0], code=18)
    new_identity = identity(candidate, code=19)
    monkeypatch.setattr(inbox.server_manager, "PILOT_RELEASE_DIR", release)
    monkeypatch.setattr(inbox.common, "inspect_apk", lambda _: old_identity)

    def publish(*_args: object, **_kwargs: object) -> int:
        raise inbox.server_manager.ServerError("simulated atomic publication failure")

    monkeypatch.setattr(inbox.server_manager, "publish_pilot_apk", publish)
    with pytest.raises(inbox.server_manager.ServerError, match="publication failure"):
        inbox._publish_transaction(
            new_identity,
            candidate,
            source_commit="a" * 40,
        )

    assert {name: (release / name).read_bytes() for name in names} == old


def test_successful_publish_delegates_source_commit_to_shared_publisher(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = tmp_path / "pilot"
    candidate = tmp_path / "candidate.apk"
    candidate.write_bytes(b"new-apk")
    item = identity(candidate, code=19)
    monkeypatch.setattr(inbox.server_manager, "PILOT_RELEASE_DIR", release)

    observed: dict[str, object] = {}

    def publish(source: Path, **kwargs: object) -> int:
        observed.update(source=source, **kwargs)
        return 0

    monkeypatch.setattr(inbox.server_manager, "publish_pilot_apk", publish)

    assert (
        inbox._publish_transaction(item, candidate, source_commit="b" * 40)
        == "PUBLISHED"
    )
    assert observed == {"source": candidate, "source_commit": "b" * 40}
