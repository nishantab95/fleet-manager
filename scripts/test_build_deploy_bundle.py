"""Exercise bundle contents and refusals against isolated synthetic Git repositories."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import build_deploy_bundle as bundle


def git(repo: Path, *args: str, data: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        input=data,
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout


@pytest.fixture
def checkout(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "synthetic checkout"
    repo.mkdir()
    git(repo, "init", "--initial-branch=main")
    git(repo, "config", "user.name", "Synthetic Bundle Test")
    git(repo, "config", "user.email", "bundle-test@example.invalid")
    git(repo, "config", "core.autocrlf", "false")
    (repo / ".gitattributes").write_bytes(b"*.sh text eol=lf\n")
    for name in bundle.ALLOWLIST:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"synthetic fixture: {name}\n".encode())
    for name in (
        ".env",
        "apps/mobile/lib/main.dart",
        "scripts/production/local-smoke.sh",
        "scripts/production/receive-deploy-bundle.sh",
        "infra/production/.env.example",
        "signing/private.jks",
    ):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic excluded fixture\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "synthetic fixture")
    return repo, git(repo, "rev-parse", "HEAD").decode().strip()


def output_path(repo: Path, name: str = "bundle.tar.gz") -> Path:
    return repo.parent / name


def test_exact_allowlist_manifest_modes_and_no_source_or_secrets(
    checkout: tuple[Path, str],
) -> None:
    repo, commit = checkout
    output = output_path(repo)
    result = bundle.build_bundle(repo, commit, output)
    with tarfile.open(output, "r:gz") as archive:
        members = archive.getmembers()
        expected = {*bundle.ALLOWLIST, "release.sha", "deploy-manifest.json"}
        assert [member.name for member in members] == sorted(expected)
        payloads = {}
        for member in members:
            assert member.isfile()
            assert member.mode == (0o755 if member.name.endswith(".sh") else 0o644)
            assert member.uid == member.gid == member.mtime == 0
            assert member.uname == member.gname == ""
            extracted = archive.extractfile(member)
            assert extracted is not None
            payloads[member.name] = extracted.read()
        assert payloads["release.sha"] == f"{commit}\n".encode()
        manifest = json.loads(payloads["deploy-manifest.json"])
        assert manifest["formatVersion"] == 1 and manifest["commit"] == commit
        assert [entry["path"] for entry in manifest["files"]] == sorted(
            expected - {"deploy-manifest.json"}
        )
        for entry in manifest["files"]:
            payload = payloads[entry["path"]]
            assert entry["size"] == len(payload)
            assert entry["sha256"] == hashlib.sha256(payload).hexdigest()
            assert entry["mode"] == (
                "0755" if entry["path"].endswith(".sh") else "0644"
            )
        for name in bundle.ALLOWLIST:
            assert payloads[name] == git(repo, "show", f"HEAD:{name}")
    assert result["files"] == 22
    assert result["bytes"] == output.stat().st_size
    assert result["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()


def test_bundle_is_deterministic_despite_output_filename_and_checkout_mtime(
    checkout: tuple[Path, str],
) -> None:
    repo, commit = checkout
    first, second = output_path(repo, "one.tar.gz"), output_path(repo, "two.tar.gz")
    bundle.build_bundle(repo, commit, first)
    for name in bundle.ALLOWLIST:
        os.utime(repo / name, (1_000_000, 1_000_000))
    bundle.build_bundle(repo, commit, second)
    assert first.read_bytes() == second.read_bytes()


def test_git_normalized_blob_is_used_for_crlf_checkout(
    checkout: tuple[Path, str],
) -> None:
    repo, commit = checkout
    name = "scripts/production/deploy.sh"
    path = repo / name
    committed = git(repo, "show", f"HEAD:{name}")
    path.write_bytes(committed.replace(b"\n", b"\r\n"))
    output = output_path(repo)
    bundle.build_bundle(repo, commit, output)
    with tarfile.open(output, "r:gz") as archive:
        extracted = archive.extractfile(name)
        assert extracted is not None and extracted.read() == committed


@pytest.mark.parametrize("invalid", ["abc123", "A" * 40, "g" * 40, "0" * 39, "0" * 41])
def test_invalid_commit_refused_before_output(
    checkout: tuple[Path, str], invalid: str
) -> None:
    repo, _ = checkout
    output = output_path(repo)
    with pytest.raises(bundle.BundleError, match="40-character"):
        bundle.build_bundle(repo, invalid, output)
    assert not output.exists()


def test_commit_must_equal_head(checkout: tuple[Path, str]) -> None:
    repo, _ = checkout
    with pytest.raises(bundle.BundleError, match="equal checkout HEAD"):
        bundle.build_bundle(repo, "0" * 40, output_path(repo))


def test_repo_must_be_actual_root(checkout: tuple[Path, str]) -> None:
    repo, commit = checkout
    with pytest.raises(bundle.BundleError, match="actual Git checkout root"):
        bundle.build_bundle(repo / "scripts", commit, output_path(repo))


def test_missing_worktree_file_refused(checkout: tuple[Path, str]) -> None:
    repo, commit = checkout
    (repo / bundle.ALLOWLIST[0]).rename(repo / "synthetic-saved-file")
    with pytest.raises(bundle.BundleError, match="working-tree file is missing"):
        bundle.build_bundle(repo, commit, output_path(repo))


def test_untracked_required_file_refused(checkout: tuple[Path, str]) -> None:
    repo, _ = checkout
    git(repo, "rm", "--cached", "--", bundle.ALLOWLIST[0])
    git(repo, "commit", "-m", "remove fixture from index only")
    commit = git(repo, "rev-parse", "HEAD").decode().strip()
    assert (repo / bundle.ALLOWLIST[0]).is_file()
    with pytest.raises(bundle.BundleError, match="missing or untracked"):
        bundle.build_bundle(repo, commit, output_path(repo))


@pytest.mark.parametrize("change", ["unstaged", "staged", "index_only", "hidden"])
def test_dirty_allowlisted_file_refused(
    checkout: tuple[Path, str], change: str
) -> None:
    repo, commit = checkout
    name = bundle.ALLOWLIST[0]
    path = repo / name
    original = path.read_bytes()
    if change == "hidden":
        git(repo, "update-index", "--assume-unchanged", "--", name)
    path.write_bytes(original + b"synthetic change\n")
    if change in {"staged", "index_only"}:
        git(repo, "add", "--", name)
    if change == "index_only":
        path.write_bytes(original)
    with pytest.raises(bundle.BundleError, match="changes"):
        bundle.build_bundle(repo, commit, output_path(repo))


def test_unrelated_local_change_is_not_packaged(checkout: tuple[Path, str]) -> None:
    repo, commit = checkout
    (repo / ".env").write_text(
        "different synthetic excluded fixture\n", encoding="utf-8"
    )
    bundle.build_bundle(repo, commit, output_path(repo))


def test_nonregular_worktree_file_refused(checkout: tuple[Path, str]) -> None:
    repo, commit = checkout
    path = repo / bundle.ALLOWLIST[0]
    path.rename(repo / "synthetic-saved-file")
    path.mkdir()
    with pytest.raises(bundle.BundleError, match="not a regular file"):
        bundle.build_bundle(repo, commit, output_path(repo))


def test_git_symlink_mode_refused_without_requiring_windows_symlink_privilege(
    checkout: tuple[Path, str],
) -> None:
    repo, _ = checkout
    object_id = (
        git(repo, "hash-object", "-w", "--stdin", data=b"synthetic-target")
        .decode()
        .strip()
    )
    git(
        repo,
        "update-index",
        "--add",
        "--cacheinfo",
        f"120000,{object_id},{bundle.ALLOWLIST[0]}",
    )
    git(repo, "commit", "-m", "synthetic symbolic link entry")
    commit = git(repo, "rev-parse", "HEAD").decode().strip()
    with pytest.raises(bundle.BundleError, match="Git entry is not a regular file"):
        bundle.build_bundle(repo, commit, output_path(repo))


def test_reparse_ancestor_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    child = tmp_path / "parent" / "child"
    child.mkdir(parents=True)
    original = Path.lstat

    def lstat(path: Path) -> object:
        if path == child.parent:
            return SimpleNamespace(
                st_mode=stat.S_IFDIR, st_file_attributes=bundle.REPARSE_POINT
            )
        return original(path)

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(bundle.BundleError, match="Symlink/reparse"):
        bundle._no_links(child)


def test_existing_output_is_never_overwritten(checkout: tuple[Path, str]) -> None:
    repo, commit = checkout
    output = output_path(repo)
    output.write_bytes(b"preserve synthetic prior artifact")
    with pytest.raises(FileExistsError):
        bundle.build_bundle(repo, commit, output)
    assert output.read_bytes() == b"preserve synthetic prior artifact"


def test_partial_archive_is_preserved_on_failure(
    checkout: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, commit = checkout
    output = output_path(repo)

    def fail_write(*args: object, **kwargs: object) -> None:
        raise OSError("synthetic write failure")

    monkeypatch.setattr(tarfile.TarFile, "addfile", fail_write)
    with pytest.raises(OSError, match="synthetic write failure"):
        bundle.build_bundle(repo, commit, output)
    assert output.is_file() and output.stat().st_size > 0


def test_cli_emits_metadata_and_nonzero_on_refusal(checkout: tuple[Path, str]) -> None:
    repo, commit = checkout
    import sys

    command = [
        sys.executable,
        str(Path(bundle.__file__)),
        "--repo",
        str(repo),
        "--commit",
        commit,
        "--output",
        str(output_path(repo)),
    ]
    success = subprocess.run(command, capture_output=True, check=False, timeout=30)
    assert success.returncode == 0, success.stderr.decode()
    assert json.loads(success.stdout)["commit"] == commit
    refused = subprocess.run(command, capture_output=True, check=False, timeout=30)
    assert refused.returncode == 1 and b"Bundle refused:" in refused.stderr
