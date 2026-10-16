"""Create a deterministic, source-free VPS operations bundle from verified Git blobs.

Only the fixed operations allowlist is packaged. No Docker images, application
source, Git metadata, local configuration, signing files or runtime data enter it.
Output creation is exclusive; a failed write preserves its partial output for
inspection and a retry must choose a new path.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import tarfile
from pathlib import Path
from typing import Any

ALLOWLIST = (
    "infra/production/docker-compose.yml",
    "infra/production/Caddyfile",
    "infra/production/init-minio.sh",
    "infra/production/minio-evidence-policy.json",
    "infra/production/systemd/fleet-ai-backup.service",
    "infra/production/systemd/fleet-ai-backup.timer",
    "infra/production/systemd/fleet-ai-health.service",
    "infra/production/systemd/fleet-ai-health.timer",
    "scripts/production/common.sh",
    "scripts/production/data-service-guard.sh",
    "scripts/production/validate-config.sh",
    "scripts/production/deploy.sh",
    "scripts/production/rollback.sh",
    "scripts/production/healthcheck.sh",
    "scripts/production/backup.sh",
    "scripts/production/backup-and-verify.sh",
    "scripts/production/verify-backup.sh",
    "scripts/production/offsite-backup.sh",
    "scripts/production/verify-offsite-backup.sh",
    "scripts/production/prune-local-backups.sh",
)
REPARSE_POINT = 0x400


class BundleError(ValueError):
    """A source or output does not satisfy the release bundle contract."""


def _git(repo: Path, *arguments: str, accepted: tuple[int, ...] = (0,)) -> bytes:
    result = subprocess.run(  # noqa: S603 -- fixed Git commands, no shell or remote mutation.
        ["git", "-C", str(repo), *arguments],  # noqa: S607 -- use the workstation's Git.
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode not in accepted:
        raise BundleError(f"Git {arguments[0]} failed (exit {result.returncode})")
    return result.stdout


def _no_links(path: Path) -> None:
    for candidate in (path, *path.parents):
        info = candidate.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & REPARSE_POINT
        ):
            raise BundleError(f"Symlink/reparse path refused: {candidate}")


def _verified_sources(repo: Path, commit: str) -> dict[str, bytes]:
    if not re.fullmatch("[0-9a-f]{40}", commit):
        raise BundleError("Commit must be a full 40-character lowercase Git SHA")
    _no_links(repo)
    actual_root = Path(
        os.path.abspath(_git(repo, "rev-parse", "--show-toplevel").decode().strip())
    )
    if actual_root != repo:
        raise BundleError("--repo must name the actual Git checkout root")
    if _git(repo, "rev-parse", "HEAD").decode().strip() != commit:
        raise BundleError("Requested commit must equal checkout HEAD")
    tree = _git(repo, "ls-tree", "-z", commit, "--", *ALLOWLIST)
    entries: dict[str, tuple[str, str, str]] = {}
    for encoded_entry in tree.split(b"\0"):
        if not encoded_entry:
            continue
        metadata, raw_name = encoded_entry.split(b"\t", 1)
        mode, kind, object_id = metadata.decode("ascii").split()
        entries[raw_name.decode("utf-8")] = (mode, kind, object_id)
    payloads: dict[str, bytes] = {}
    for name in ALLOWLIST:
        entry = entries.get(name)
        if entry is None:
            raise BundleError(f"Required file is missing or untracked at HEAD: {name}")
        mode, kind, object_id = entry
        if mode not in {"100644", "100755"} or kind != "blob":
            raise BundleError(f"Git entry is not a regular file: {name}")
        path = repo / name
        try:
            _no_links(path)
            if not stat.S_ISREG(path.lstat().st_mode):
                raise BundleError(f"Working-tree entry is not a regular file: {name}")
        except FileNotFoundError as error:
            raise BundleError(
                f"Required working-tree file is missing: {name}"
            ) from error
        # Compare normalized bytes even if a local index flag hides changes from
        # `git diff` (assume-unchanged / skip-worktree). This never writes objects.
        if (
            _git(repo, "hash-object", f"--path={name}", str(path)).decode().strip()
            != object_id
        ):
            raise BundleError(f"Allowlisted working-tree file has changes: {name}")
        payloads[name] = _git(repo, "cat-file", "blob", object_id)
    # Git applies its committed attributes/line-ending rules; payload bytes above
    # come from immutable blobs, never from CRLF checkout contents.
    if _git(repo, "diff", "--cached", "--name-only", "HEAD", "--", *ALLOWLIST) or _git(
        repo, "diff", "--name-only", "--", *ALLOWLIST
    ):
        raise BundleError("Allowlisted files have staged or working-tree changes")
    if _git(repo, "rev-parse", "HEAD").decode().strip() != commit:
        raise BundleError("Checkout HEAD changed during verification")
    return payloads


def build_bundle(repo: Path, commit: str, output: Path) -> dict[str, Any]:
    repo = Path(os.path.abspath(repo))
    output = Path(os.path.abspath(output))
    _no_links(output.parent)
    payloads = _verified_sources(repo, commit)
    payloads["release.sha"] = f"{commit}\n".encode("ascii")
    manifest = {
        "formatVersion": 1,
        "commit": commit,
        "files": [
            {
                "path": name,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size": len(payload),
                "mode": "0755" if name.endswith(".sh") else "0644",
            }
            for name, payload in sorted(payloads.items())
        ],
    }
    payloads["deploy-manifest.json"] = (
        json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    # Never overwrite an existing output, including a symlink or earlier partial
    # archive. No cleanup/deletion occurs on failure.
    with output.open("xb") as destination:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=destination, mtime=0
        ) as compressed:
            with tarfile.open(
                fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT
            ) as archive:
                for name, payload in sorted(payloads.items()):
                    member = tarfile.TarInfo(name)
                    member.size = len(payload)
                    member.mode = 0o755 if name.endswith(".sh") else 0o644
                    member.uid = member.gid = member.mtime = 0
                    member.uname = member.gname = ""
                    archive.addfile(member, io.BytesIO(payload))
    return {
        "commit": commit,
        "output": str(output),
        "files": len(payloads),
        "bytes": output.stat().st_size,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--repo", type=Path, default=Path(__file__).resolve().parents[1]
    )
    options = parser.parse_args()
    try:
        result = build_bundle(options.repo, options.commit, options.output)
    except (BundleError, OSError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"Bundle refused: {error}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
