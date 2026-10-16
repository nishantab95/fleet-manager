"""Measure an existing native Docker context-audit local export, read-only.

This does not run Docker, implement Dockerignore matching, scan arbitrary source
trees, or delete files. Run the reviewed scratch target into a fresh directory
under this checkout's .tmp first. Report COPY-visible logical bytes, not network
transfer bytes. Filename guards are not a content-based secret scanner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
COMPONENTS = {"api": "services/api", "web": "apps/web", "marketing": "apps/marketing"}
REPARSE_POINT = 0x400
PROTECTED_PARTS = {
    ".git",
    ".github",
    ".runtime",
    ".tmp",
    "node_modules",
    ".venv",
    ".next",
    ".dart_tool",
    ".gradle",
    ".kotlin",
    "build",
    "dist",
    "outputs",
    "coverage",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".uv-cache",
    "test-results",
    "playwright-report",
    "blob-report",
    "backups",
    "uploads",
    "secrets",
    "credentials",
}
PROTECTED_SUFFIXES = {
    ".jks",
    ".keystore",
    ".p12",
    ".pfx",
    ".pem",
    ".crt",
    ".key",
    ".apk",
    ".aab",
    ".db",
    ".dump",
    ".sql",
    ".tar",
    ".tgz",
    ".zip",
    ".log",
    ".pyc",
    ".pyo",
    ".pyd",
    ".tsbuildinfo",
    ".env",
}


def is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & REPARSE_POINT
    )


def check_path(path: Path, *, directory: bool = False) -> os.stat_result:
    """Do not resolve away or traverse a pre-existing link/reparse ancestor."""
    for candidate in (*reversed(path.parents), path):
        info = candidate.lstat()
        if is_link(info):
            raise ValueError(f"Symlink/reparse point refused: {candidate}")
        if candidate != path and not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"Non-directory ancestor refused: {candidate}")
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode):
        raise ValueError(
            f"Non-{'directory' if directory else 'regular file'} refused: {path}"
        )
    return info


def protected_name(relative: Path) -> bool:
    parts = tuple(part.lower() for part in relative.parts)
    name = parts[-1]
    return (
        any(part in PROTECTED_PARTS for part in parts)
        # This is an authenticated source route, not stored evidence data.
        or any(
            part == "evidence"
            and not (index == 3 and parts[:3] == ("apps", "web", "app"))
            for index, part in enumerate(parts)
        )
        or name.startswith(".env")
        or name in {"key.properties", "local.properties", "google-services.json"}
        or Path(name).suffix in PROTECTED_SUFFIXES
        or ".sqlite" in name
        or ".tar." in name
        or (
            name.endswith(".json")
            and any(
                marker in name
                for marker in ("service-account", "firebase-adminsdk", "credentials")
            )
        )
    )


def file_metadata(path: Path) -> dict[str, Any]:
    before = check_path(path)
    digest = hashlib.sha256()
    with path.open("rb") as source:
        opened = os.fstat(source.fileno())
        if not stat.S_ISREG(opened.st_mode) or (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns):
            raise ValueError(f"File changed before hashing: {path}")
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    after = check_path(path)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ValueError(f"File changed during hashing: {path}")
    return {"bytes": before.st_size, "sha256": digest.hexdigest()}


def tracked_paths(repo: Path) -> set[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "--cached", "-z"],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise ValueError("Git tracked-file inventory failed")
    return {
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    }


def manifest(export: Path, component: str, repo: Path = ROOT) -> dict[str, Any]:
    repo = Path(os.path.abspath(repo))
    export = Path(os.path.abspath(export))
    check_path(repo, directory=True)
    temporary = repo / ".tmp"
    if export == temporary or not export.is_relative_to(temporary):
        raise ValueError("Export must be a dedicated directory below checkout .tmp")
    check_path(export, directory=True)
    component_path = Path(COMPONENTS[component])
    tracked = tracked_paths(repo)
    paths: list[Path] = []
    pending = [export]
    # Validate the entire export's names/types before hashing any contents.
    while pending:
        directory = pending.pop()
        check_path(directory, directory=True)
        with os.scandir(directory) as entries:
            for entry in entries:
                path = directory / entry.name
                relative = path.relative_to(export)
                if protected_name(relative):
                    raise ValueError(
                        f"Protected/generated material in export: {relative.as_posix()}"
                    )
                info = path.lstat()
                if is_link(info):
                    raise ValueError(
                        f"Symlink/reparse point in export: {relative.as_posix()}"
                    )
                if stat.S_ISDIR(info.st_mode):
                    pending.append(path)
                elif stat.S_ISREG(info.st_mode):
                    if not relative.is_relative_to(component_path):
                        raise ValueError(
                            f"Unexpected component in export: {relative.as_posix()}"
                        )
                    paths.append(path)
                else:
                    raise ValueError(
                        f"Non-regular entry in export: {relative.as_posix()}"
                    )
    if not paths:
        raise ValueError("Empty export cannot verify a production build context")
    files: list[dict[str, Any]] = []
    for path in sorted(paths):
        relative = path.relative_to(export)
        values = file_metadata(path)
        source_values = file_metadata(repo / relative)
        if values != source_values:
            raise ValueError(
                f"Export differs from current checkout: {relative.as_posix()}"
            )
        files.append(
            {
                "path": relative.as_posix(),
                **values,
                "git_tracked": relative.as_posix() in tracked,
            }
        )
    dockerfile = component_path / "Dockerfile"
    specific_ignore = component_path / "Dockerfile.dockerignore"
    effective_ignore = (
        specific_ignore if (repo / specific_ignore).exists() else Path(".dockerignore")
    )
    exported = {item["path"] for item in files}
    controls = [
        {
            "path": path.as_posix(),
            **file_metadata(repo / path),
            "included_in_copy_payload": path.as_posix() in exported,
        }
        for path in (dockerfile, effective_ignore)
    ]
    return {
        "component": component,
        "export_directory": export.relative_to(repo).as_posix(),
        "measurement": "Native Docker COPY-visible regular-file logical bytes; not network-transfer or image bytes",
        "copy_payload": {
            "files": len(files),
            "bytes": sum(item["bytes"] for item in files),
        },
        "checkout_hashes_match": True,
        "git_tracked_files": sum(item["git_tracked"] for item in files),
        "untracked_paths": [item["path"] for item in files if not item["git_tracked"]],
        "controls": controls,
        "control_bytes_not_in_copy_payload": sum(
            item["bytes"] for item in controls if not item["included_in_copy_payload"]
        ),
        "files": files,
        "limitations": [
            "Native Docker export must be freshly created by the reviewed context-audit target; this reader does not attest the producing command.",
            "Control files are measured separately; BuildKit transfer framing, caching, and metadata are not measured.",
            "Filename guards and Git tracking are not a content-based secret scan; untracked inputs require explicit review.",
            "Use a quiescent trusted checkout/export; metadata checks detect ordinary concurrent changes, not hostile filesystem races.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component", choices=COMPONENTS, required=True)
    parser.add_argument("--export", type=Path, required=True)
    options = parser.parse_args()
    try:
        result = manifest(options.export, options.component)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=True))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
