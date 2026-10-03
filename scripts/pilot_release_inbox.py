"""Receive, validate, and safely publish pilot APKs delivered by Tailscale Taildrop."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator, Mapping, Sequence
from uuid import uuid4

import pilot_release_common as common
import server_manager

try:
    import msvcrt
except ImportError:  # pragma: no cover - production is Windows
    msvcrt = None  # type: ignore[assignment]


INBOX_ROOT = Path(r"F:\FleetManagerData\releases\incoming")
ARCHIVE_DIR = INBOX_ROOT / "archive"
REJECTED_DIR = INBOX_ROOT / "rejected"
STAGING_DIR = INBOX_ROOT / "staging"
STATUS_FILE = INBOX_ROOT / "publisher-status.json"
LOCK_FILE = INBOX_ROOT / "publisher.lock"
LOG_FILE = Path(r"F:\FleetManagerData\logs\pilot-publisher.log")
DOWNLOADS_DIR = Path.home() / "Downloads"
TAILSCALE_EXE = server_manager.TAILSCALE_EXE
MAX_MANIFEST_BYTES = 32 * 1024
PAIR_RE = re.compile(r"^FleetManager-Pilot-upload-[A-Za-z0-9._-]{1,100}$")


class InboxError(RuntimeError):
    """A safely handled inbox or release validation failure."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def log(message: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    line = f"{_now()} {message.strip()}\n"
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(line)
    print(message)


def write_status(state: str, detail: str, release_id: str = "") -> None:
    safe_detail = " ".join(detail.split())[:1000]
    server_manager.atomic_write_json(
        STATUS_FILE,
        {
            "state": state,
            "updatedAt": _now(),
            "detail": safe_detail,
            "releaseId": release_id,
        },
    )


@contextmanager
def single_instance() -> Iterator[bool]:
    INBOX_ROOT.mkdir(parents=True, exist_ok=True)
    handle = LOCK_FILE.open("a+b")
    acquired = True
    if msvcrt is not None:
        try:
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            acquired = False
    try:
        yield acquired
    finally:
        if acquired and msvcrt is not None:
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        handle.close()


def _stable(path: Path, delay: float = 1.0) -> bool:
    try:
        first = path.stat()
        if delay:
            time.sleep(delay)
        second = path.stat()
    except OSError:
        return False
    return (
        first.st_size == second.st_size
        and first.st_mtime_ns == second.st_mtime_ns
        and second.st_size > 0
    )


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".{destination.name}.{uuid4().hex}.partial"
    try:
        shutil.copy2(source, temporary)
        if source.stat().st_size != temporary.stat().st_size:
            raise InboxError(f"Copy size verification failed for {source.name}")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def receive_taildrop_files() -> None:
    if not TAILSCALE_EXE.is_file():
        raise InboxError("ENABLE TAILSCALE SEND FILES: tailscale.exe is missing.")
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            str(TAILSCALE_EXE),
            "file",
            "get",
            "--conflict=rename",
            str(DOWNLOADS_DIR),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=45,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise InboxError(f"Taildrop receive failed: {detail or 'unknown error'}")

    for source in DOWNLOADS_DIR.iterdir():
        if not source.is_file():
            continue
        if not source.name.startswith(common.APK_PREFIX):
            continue
        if source.suffix.casefold() not in (common.APK_SUFFIX, common.MANIFEST_SUFFIX):
            continue
        if not _stable(source):
            continue
        destination = INBOX_ROOT / source.name
        if destination.exists():
            if common.sha256_file(source) == common.sha256_file(destination):
                source.unlink()
                continue
            destination = INBOX_ROOT / f"{source.stem}-{uuid4().hex[:8]}{source.suffix}"
        _atomic_copy(source, destination)
        source.unlink()
        log(f"Received {destination.name} from the private Taildrop landing folder.")


def load_manifest(path: Path) -> dict[str, object]:
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise InboxError("Manifest is unexpectedly large.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InboxError(f"Manifest is not valid UTF-8 JSON: {error}") from error
    if not isinstance(value, dict):
        raise InboxError("Manifest root must be a JSON object.")
    required = {
        "schemaVersion",
        "releaseId",
        "apkFile",
        "package",
        "versionName",
        "versionCode",
        "apkSha256",
        "expectedSignerSha256",
        "sourceGitCommit",
    }
    if not required.issubset(value):
        missing = ", ".join(sorted(required - set(value)))
        raise InboxError(f"Manifest is missing required fields: {missing}")
    return value


def _validate_manifest(
    manifest: Mapping[str, object], identity: common.ApkIdentity, apk_name: str
) -> str:
    release_id = manifest.get("releaseId")
    if not isinstance(release_id, str) or not re.fullmatch(
        r"[A-Za-z0-9._-]{1,100}", release_id
    ):
        raise InboxError("Manifest releaseId is invalid.")
    if manifest.get("schemaVersion") != 1:
        raise InboxError("Unsupported manifest schemaVersion.")
    expected: dict[str, object] = {
        "apkFile": apk_name,
        "package": identity.package,
        "versionName": identity.version_name,
        "versionCode": identity.version_code,
        "apkSha256": identity.apk_sha256,
        "expectedSignerSha256": identity.signer_sha256,
    }
    for key, actual in expected.items():
        supplied = manifest.get(key)
        if isinstance(actual, str) and key in ("apkSha256", "expectedSignerSha256"):
            supplied = supplied.casefold() if isinstance(supplied, str) else supplied
        if supplied != actual:
            raise InboxError(f"Manifest {key} does not match the signed APK.")
    commit = manifest.get("sourceGitCommit")
    if not isinstance(commit, str) or not common.COMMIT_RE.fullmatch(commit.casefold()):
        raise InboxError("Manifest sourceGitCommit must be a full Git commit SHA.")
    common.validate_expected_identity(identity)
    return release_id


def _remote_sha256(url: str) -> str:
    import hashlib

    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=30) as response:
        if response.status != 200:
            raise InboxError(f"Private APK download returned HTTP {response.status}.")
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _restore_publication(backup: Path, existed: Mapping[str, bool]) -> None:
    for name in (
        server_manager.PILOT_APK_NAME,
        server_manager.PILOT_SHA256_NAME,
        server_manager.PILOT_VERSION_NAME,
    ):
        destination = server_manager.PILOT_RELEASE_DIR / name
        if existed[name]:
            _atomic_copy(backup / name, destination)
        else:
            destination.unlink(missing_ok=True)


def _publish_transaction(identity: common.ApkIdentity, staged_apk: Path) -> str:
    release_dir = server_manager.PILOT_RELEASE_DIR
    release_dir.mkdir(parents=True, exist_ok=True)
    current_apk = release_dir / server_manager.PILOT_APK_NAME
    if current_apk.is_file():
        current = common.inspect_apk(current_apk)
        common.validate_expected_identity(current)
        if identity.version_code < current.version_code:
            raise InboxError(
                f"Downgrade refused: current versionCode is {current.version_code}."
            )
        if identity.version_code == current.version_code:
            if identity.apk_sha256 == current.apk_sha256:
                return "ALREADY PUBLISHED"
            raise InboxError(
                "Same versionCode has a different APK hash; publication refused."
            )

    safe_version = re.sub(r"[^A-Za-z0-9._-]+", "_", identity.version_name)
    versioned = release_dir / (
        f"FleetManager-Pilot-{safe_version}-code{identity.version_code}.apk"
    )
    versioned_existed = versioned.exists()
    if versioned_existed and common.sha256_file(versioned) != identity.apk_sha256:
        raise InboxError("Versioned APK path already exists with a different hash.")

    names = (
        server_manager.PILOT_APK_NAME,
        server_manager.PILOT_SHA256_NAME,
        server_manager.PILOT_VERSION_NAME,
    )
    with tempfile.TemporaryDirectory(prefix=".pilot-rollback-", dir=release_dir) as raw:
        rollback = Path(raw)
        existed = {name: (release_dir / name).is_file() for name in names}
        for name, present in existed.items():
            if present:
                shutil.copy2(release_dir / name, rollback / name)
        version_file = rollback / "candidate-version.txt"
        version_file.write_text(
            common.version_text(identity, server_manager.PILOT_APK_NAME),
            encoding="utf-8",
        )
        try:
            server_manager.publish_pilot_apk(staged_apk, version_file)
            remote = server_manager.remote_access_status()
            apk_url = remote.get("remote_url", "")
            if not apk_url or remote.get("serve_pilot") != "OK":
                raise InboxError("Private pilot download route is not ready.")
            download_url = (
                f"{apk_url}{server_manager.TAILSCALE_PILOT_PATH}/"
                f"{server_manager.PILOT_APK_NAME}"
            )
            if _remote_sha256(download_url) != identity.apk_sha256:
                raise InboxError(
                    "Private download hash does not match the candidate APK."
                )
            if not versioned_existed:
                _atomic_copy(staged_apk, versioned)
        except Exception:
            if not versioned_existed:
                versioned.unlink(missing_ok=True)
            _restore_publication(rollback, existed)
            raise
    return "PUBLISHED"


def _archive_success(
    manifest_path: Path,
    apk_path: Path,
    manifest: Mapping[str, object],
    outcome: str,
) -> None:
    release_id = str(manifest["releaseId"])
    target = ARCHIVE_DIR / release_id
    target.mkdir(parents=True, exist_ok=True)
    _atomic_copy(manifest_path, target / "manifest.json")
    server_manager.atomic_write_json(
        target / "receipt.json",
        {
            "completedAt": _now(),
            "outcome": outcome,
            "versionName": manifest["versionName"],
            "versionCode": manifest["versionCode"],
            "apkSha256": manifest["apkSha256"],
            "sourceGitCommit": manifest["sourceGitCommit"],
        },
    )
    manifest_path.unlink(missing_ok=True)
    apk_path.unlink(missing_ok=True)


def _reject(manifest_path: Path, apk_path: Path | None, reason: str) -> None:
    target = (
        REJECTED_DIR / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    )
    target.mkdir(parents=True, exist_ok=False)
    for source in (manifest_path, apk_path):
        if source is not None and source.exists():
            _atomic_copy(source, target / source.name)
            source.unlink()
    server_manager.atomic_write_json(
        target / "rejection.json", {"rejectedAt": _now(), "reason": reason}
    )


def process_manifest(manifest_path: Path, *, stability_delay: float = 1.0) -> str:
    base = manifest_path.stem
    if not PAIR_RE.fullmatch(base):
        reason = f"Unsafe inbox manifest filename: {manifest_path.name}"
        _reject(manifest_path, None, reason)
        write_status("ERROR", reason)
        log(f"PUBLISH REJECTED {manifest_path.name}: {reason}")
        return "REJECTED"
    apk_path = manifest_path.with_suffix(".apk")
    if not apk_path.is_file():
        return "INCOMPLETE"
    if not _stable(manifest_path, stability_delay) or not _stable(
        apk_path, stability_delay
    ):
        return "INCOMPLETE"
    release_id = ""
    write_status("PROCESSING", f"Validating {manifest_path.name}")
    stage = STAGING_DIR / f"{base}-{uuid4().hex}"
    stage.mkdir(parents=True, exist_ok=False)
    staged_apk = stage / apk_path.name
    try:
        manifest = load_manifest(manifest_path)
        release_id = str(manifest.get("releaseId", ""))
        write_status("PROCESSING", f"Validating {manifest_path.name}", release_id)
        _atomic_copy(apk_path, staged_apk)
        identity = common.inspect_apk(staged_apk)
        release_id = _validate_manifest(manifest, identity, apk_path.name)
        outcome = _publish_transaction(identity, staged_apk)
        _archive_success(manifest_path, apk_path, manifest, outcome)
        write_status(
            "READY",
            f"{outcome}: {identity.version_name} ({identity.version_code})",
            release_id,
        )
        log(
            f"{outcome}: {identity.version_name} (versionCode {identity.version_code})."
        )
        return outcome
    except Exception as error:
        reason = str(error)
        _reject(manifest_path, apk_path, reason)
        write_status("ERROR", reason, release_id)
        log(f"PUBLISH REJECTED {manifest_path.name}: {reason}")
        return "REJECTED"
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def process_inbox(*, receive: bool = True, stability_delay: float = 1.0) -> int:
    for directory in (INBOX_ROOT, ARCHIVE_DIR, REJECTED_DIR, STAGING_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    with single_instance() as acquired:
        if not acquired:
            log(
                "Another pilot publisher instance is already running; this run is exiting."
            )
            return 0
        try:
            if receive:
                receive_taildrop_files()
            manifests = sorted(
                INBOX_ROOT.glob(f"{common.APK_PREFIX}*{common.MANIFEST_SUFFIX}")
            )
            outcomes = [
                process_manifest(path, stability_delay=stability_delay)
                for path in manifests
            ]
            if "REJECTED" in outcomes:
                return 1
            if not outcomes or all(outcome == "INCOMPLETE" for outcome in outcomes):
                previous: dict[str, object] = {}
                try:
                    previous = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError):
                    pass
                if previous.get("state") == "ERROR":
                    write_status(
                        "ERROR", str(previous.get("detail", "Publication rejected."))
                    )
                else:
                    write_status("READY", "Waiting for a complete pilot release pair.")
            return 0
        except Exception as error:
            write_status("ERROR", str(error))
            log(f"ERROR: {error}")
            return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-receive", action="store_true", help="Do not collect Taildrop files."
    )
    parser.add_argument("--stability-delay", type=float, default=1.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return process_inbox(
        receive=not args.no_receive, stability_delay=args.stability_delay
    )


if __name__ == "__main__":
    raise SystemExit(main())
