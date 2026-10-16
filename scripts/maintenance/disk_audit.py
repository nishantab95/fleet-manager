"""Read-only disk inventory: no link traversal, deletion, cleanup, or content reads.

The optional JSON output is a new report, never an existing file overwrite.
Logical sizes count directory entries. Unique allocation deduplicates hard links
within the scan only; links elsewhere on the volume may still own the bytes.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import stat
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPARSE_POINT = 0x400


def is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & REPARSE_POINT
    )


def windows_extended_path(path: Path) -> str:
    name = str(path.absolute())
    return "\\\\?\\UNC\\" + name[2:] if name.startswith("\\\\") else "\\\\?\\" + name


def metadata(path: Path) -> os.stat_result:
    return os.stat(
        windows_extended_path(path) if os.name == "nt" else path,
        follow_symlinks=False,
    )


def allocation(path: Path, info: os.stat_result) -> int:
    if os.name != "nt":
        return int(getattr(info, "st_blocks") * 512)

    class FileStandardInfo(ctypes.Structure):
        _fields_ = [
            ("allocation_size", ctypes.c_longlong),
            ("end_of_file", ctypes.c_longlong),
            ("links", ctypes.c_ulong),
            ("delete_pending", ctypes.c_ubyte),
            ("directory", ctypes.c_ubyte),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
    ]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.GetFileInformationByHandleEx.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_ulong,
    ]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    # Extended-length paths support Gradle's long generated filenames.
    extended = windows_extended_path(path)
    handle = kernel.CreateFileW(extended, 0x80, 7, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        result = FileStandardInfo()
        if not kernel.GetFileInformationByHandleEx(
            handle, 1, ctypes.byref(result), ctypes.sizeof(result)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(result.allocation_size)
    finally:
        kernel.CloseHandle(handle)


def category(relative: str, tracked: bool) -> str:
    parts = tuple(part.lower() for part in Path(relative).parts)
    lower = relative.lower().replace("\\", "/")
    name = Path(relative).name.lower()
    if tracked:
        return "A"
    if ".git" in parts or ".runtime" in parts or lower.startswith("infra/data/"):
        return "D"
    if name.startswith(".env") or name in {"key.properties", "local.properties"}:
        return "D"
    if Path(name).suffix in {
        ".jks",
        ".keystore",
        ".p12",
        ".pem",
        ".pfx",
        ".crt",
        ".apk",
        ".aab",
    }:
        return "E"
    if any(part in {"node_modules", ".venv", "site-packages"} for part in parts):
        return "B"
    if any(part in {"outputs", "dist", "backups", "evidence"} for part in parts):
        return "F"
    caches = {
        ".next",
        ".dart_tool",
        ".gradle",
        ".kotlin",
        "build",
        ".uv-cache",
        ".tmp-uv-cache",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "__pycache__",
    }
    if any(
        part in caches
        or part.startswith((".pytest-", "pytest-cache-files-", "pytest-local-"))
        for part in parts
    ):
        return "C"
    return "F"


def git_paths(
    repo: Path, arguments: list[str], errors: list[dict[str, str]]
) -> set[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments], capture_output=True, check=False
    )
    if result.returncode or result.stderr:
        errors.append(
            {
                "path": str(repo),
                "operation": "git inventory",
                "error": result.stderr.decode(errors="replace"),
            }
        )
    return {
        value.decode("utf-8", errors="surrogateescape")
        for value in result.stdout.split(b"\0")
        if value
    }


def scan(root: Path, repo: Path) -> dict[str, Any]:
    root = root.absolute()
    repo = repo.absolute()
    for candidate in (root, *root.parents):
        if is_link(metadata(candidate)):
            raise ValueError(f"Audit root has a symlink/reparse ancestor: {candidate}")
    if not repo.is_relative_to(root):
        raise ValueError("The checkout must be inside the audit root")
    for candidate in (repo, *repo.parents):
        if is_link(metadata(candidate)):
            raise ValueError(f"Checkout has a symlink/reparse ancestor: {candidate}")
    errors: list[dict[str, str]] = []
    tracked = git_paths(repo, ["ls-files", "--cached", "-z"], errors)
    files: list[dict[str, Any]] = []
    directories: dict[str, dict[str, Any]] = {}
    skipped: list[str] = []
    git_roots: list[str] = []
    seen: set[tuple[int, int]] = set()
    allocated_identities: set[tuple[int, int]] = set()
    unique_allocated = 0
    hardlink_entries = 0
    stack = [root]
    while stack:
        directory = stack.pop()
        relative_dir = directory.relative_to(root).as_posix()
        directories.setdefault(
            relative_dir,
            {"logical": 0, "allocated": 0, "files": 0, "categories": Counter()},
        )
        try:
            if is_link(metadata(directory)):
                skipped.append(relative_dir)
                continue
            with os.scandir(
                windows_extended_path(directory) if os.name == "nt" else directory
            ) as entries:
                for entry in entries:
                    path = directory / entry.name
                    relative = path.relative_to(root).as_posix()
                    try:
                        info = entry.stat(follow_symlinks=False)
                        if is_link(info):
                            skipped.append(relative)
                            continue
                        if stat.S_ISDIR(info.st_mode):
                            if entry.name == ".git":
                                git_roots.append(
                                    path.parent.relative_to(root).as_posix()
                                )
                            stack.append(path)
                            continue
                        if not stat.S_ISREG(info.st_mode):
                            skipped.append(relative)
                            continue
                        # Windows DirEntry.stat may report st_ino=0; a fresh
                        # path stat supplies the actual file identity.
                        if not info.st_ino:
                            info = metadata(path)
                            if is_link(info):
                                skipped.append(relative)
                                continue
                        repo_relative = (
                            path.relative_to(repo).as_posix()
                            if path.is_relative_to(repo)
                            else None
                        )
                        kind = category(
                            repo_relative or relative, repo_relative in tracked
                        )
                        allocated: int | None = None
                        try:
                            allocated = allocation(path, info)
                        except OSError as error:
                            errors.append(
                                {
                                    "path": relative,
                                    "operation": "allocation",
                                    "error": str(error),
                                }
                            )
                        identity = (info.st_dev, info.st_ino)
                        if info.st_ino and identity in seen:
                            hardlink_entries += 1
                        else:
                            seen.add(identity)
                        if not info.st_ino:
                            errors.append(
                                {
                                    "path": relative,
                                    "operation": "identity",
                                    "error": "File identity unavailable; allocation counted without deduplication",
                                }
                            )
                            unique_allocated += allocated or 0
                        elif (
                            allocated is not None
                            and identity not in allocated_identities
                        ):
                            unique_allocated += allocated
                            allocated_identities.add(identity)
                        files.append(
                            {
                                "path": relative,
                                "logical": info.st_size,
                                "allocated": allocated,
                                "category": kind,
                                "repo_path": repo_relative,
                            }
                        )
                        ancestor = directory
                        while True:
                            key = ancestor.relative_to(root).as_posix()
                            total = directories.setdefault(
                                key,
                                {
                                    "logical": 0,
                                    "allocated": 0,
                                    "files": 0,
                                    "categories": Counter(),
                                },
                            )
                            total["logical"] += info.st_size
                            total["allocated"] += allocated or 0
                            total["files"] += 1
                            total["categories"][kind] += info.st_size
                            if ancestor == root:
                                break
                            ancestor = ancestor.parent
                    except OSError as error:
                        errors.append(
                            {"path": relative, "operation": "stat", "error": str(error)}
                        )
        except OSError as error:
            errors.append(
                {"path": relative_dir, "operation": "scandir", "error": str(error)}
            )

    repo_files = [item for item in files if item["repo_path"] is not None]
    ignored_result = subprocess.run(
        ["git", "-C", str(repo), "check-ignore", "--no-index", "--stdin", "-z"],
        input=b"".join(
            item["repo_path"].encode("utf-8", errors="surrogateescape") + b"\0"
            for item in repo_files
        ),
        capture_output=True,
        check=False,
    )
    if ignored_result.returncode not in (0, 1):
        errors.append(
            {
                "path": str(repo),
                "operation": "git check-ignore",
                "error": ignored_result.stderr.decode(errors="replace"),
            }
        )
    ignored = {
        value.decode("utf-8", errors="surrogateescape")
        for value in ignored_result.stdout.split(b"\0")
        if value
    }
    categories: Counter[str] = Counter()
    for item in files:
        categories[item["category"]] += item["logical"]
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "root": str(root),
        "repository": str(repo),
        "measurement": "logical directory-entry bytes; referenced allocation; unique allocation within scan (not volume-exclusive)",
        "total": directories["."],
        "unique_allocated_bytes": unique_allocated,
        "repeated_hardlink_entries": hardlink_entries,
        "categories": categories,
        "tracked_bytes": sum(
            item["logical"] for item in repo_files if item["repo_path"] in tracked
        ),
        "tracked_files": len(tracked),
        "ignored_bytes": sum(
            item["logical"]
            for item in repo_files
            if item["repo_path"] in ignored and item["repo_path"] not in tracked
        ),
        "directories": directories,
        "largest_files": sorted(files, key=lambda item: item["logical"], reverse=True)[
            :100
        ],
        "git_roots": git_roots,
        "skipped_links_or_special": skipped,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[2].parent
    )
    parser.add_argument(
        "--repo", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument(
        "--output", type=Path, help="Create a new JSON report (existing paths refused)"
    )
    options = parser.parse_args()
    result = scan(options.root, options.repo)
    serialized = json.dumps(result, indent=2, ensure_ascii=True)
    if options.output:
        with options.output.open("x", encoding="utf-8") as report:
            report.write(serialized + "\n")
        print(
            json.dumps(
                {
                    key: result[key]
                    for key in (
                        "root",
                        "total",
                        "unique_allocated_bytes",
                        "tracked_bytes",
                        "ignored_bytes",
                        "git_roots",
                    )
                }
            )
        )
        print(
            f"ERRORS={len(result['errors'])}; SKIPPED_LINKS={len(result['skipped_links_or_special'])}"
        )
    else:
        print(serialized)


if __name__ == "__main__":
    main()
