"""Isolated filesystem transport tests; no SSH, Docker or production paths."""

from __future__ import annotations

import hashlib
import io
import os
import shlex
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

SOURCE = Path(__file__).parent / "production" / "receive-deploy-bundle.sh"
COMMIT = "a" * 40
PREVIOUS = "b" * 40
RUN_ID = "12345-1"
pytestmark = pytest.mark.skipif(
    os.name == "nt",
    reason="Linux filesystem, native symlink and flock semantics are required",
)


def _bash_path(path: Path) -> str:
    if os.name == "nt":
        return f"/{path.drive[0].lower()}{path.as_posix()[2:]}"
    return str(path)


@pytest.fixture
def layout(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "fleet"
    root.mkdir()
    (root / "releases").mkdir()
    (root / "incoming").mkdir()
    (root / "state").mkdir()
    script = tmp_path / "receiver.sh"
    # This test-only copy changes the one fixed deployment root; the shipped
    # helper deliberately has no environment/argument override for that root.
    source = SOURCE.read_text(encoding="utf-8")
    assert source.count('DEPLOY_ROOT="/opt/fleet-ai"') == 1
    script.write_text(
        source.replace(
            'DEPLOY_ROOT="/opt/fleet-ai"',
            f"DEPLOY_ROOT={shlex.quote(_bash_path(root))}",
        ).replace(
            'STATE_ROOT="/var/lib/fleet-ai/deploy"',
            f"STATE_ROOT={shlex.quote(_bash_path(root / 'state'))}",
        ),
        encoding="utf-8",
        newline="\n",
    )
    return root, script


def _run(
    layout: tuple[Path, Path],
    *arguments: str,
    extra_environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    _, script = layout
    bash = shutil.which("bash")
    if os.name == "nt":
        bash = str(Path("C:/Program Files/Git/bin/bash.exe"))
    assert bash, "Bash is required for receiver tests"
    environment = os.environ.copy()
    environment["MSYS"] = "winsymlinks:nativestrict"
    environment.update(extra_environment or {})
    return subprocess.run(  # noqa: S603
        [bash, script.as_posix(), *arguments],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _symlink(source: Path, target: Path) -> None:
    try:
        target.symlink_to(source, target_is_directory=source.is_dir())
    except OSError as error:
        pytest.skip(f"Host cannot create native symlinks: {error}")


def _previous(root: Path) -> Path:
    release = root / "releases" / PREVIOUS
    release.mkdir()
    (release / "release.sha").write_text(f"{PREVIOUS}\n", encoding="ascii")
    _symlink(release, root / "repository")
    return release


def _archive(root: Path, *, marker: str = COMMIT, deploy_status: int = 0) -> str:
    incoming = root / "incoming" / RUN_ID
    incoming.mkdir(exist_ok=True)
    archive = incoming / "deploy.tar.gz"
    payloads = {
        "release.sha": f"{marker}\n".encode(),
        "deploy-manifest.json": b'{"formatVersion":1}\n',
        "scripts/production/common.sh": (SOURCE.parent / "common.sh").read_bytes(),
        "scripts/production/deploy.sh": (
            "#!/usr/bin/env bash\nset -eu\n"
            'source "$(dirname "$0")/common.sh"\n'
            "acquire_deploy_lock\n"
            'printf "%s\\n" "$*" >"$(dirname "$0")/invocation.txt"\n'
            f"exit {deploy_status}\n"
        ).encode(),
    }
    with tarfile.open(archive, "w:gz") as bundle:
        for name, payload in payloads.items():
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            member.mode = 0o755 if name.endswith(".sh") else 0o644
            bundle.addfile(member, io.BytesIO(payload))
    return hashlib.sha256(archive.read_bytes()).hexdigest()


def test_prepare_creates_unique_incoming_directory(layout: tuple[Path, Path]) -> None:
    root, _ = layout
    result = _run(layout, "prepare", RUN_ID)
    assert result.returncode == 0, result.stderr
    assert (root / "incoming" / RUN_ID).is_dir()
    repeated = _run(layout, "prepare", RUN_ID)
    assert repeated.returncode != 0
    assert "already exists" in repeated.stderr


@pytest.mark.parametrize("identifier", ["../1", "1", "1-2/3", "$(id)"])
def test_prepare_rejects_invalid_identifier(
    layout: tuple[Path, Path], identifier: str
) -> None:
    assert _run(layout, "prepare", identifier).returncode != 0
    assert list((layout[0] / "incoming").iterdir()) == []


def test_real_checkout_is_never_replaced(layout: tuple[Path, Path]) -> None:
    root, _ = layout
    (root / "repository").mkdir()
    result = _run(layout, "prepare", RUN_ID)
    assert result.returncode != 0
    assert "transitioned manually" in result.stderr
    assert (root / "repository").is_dir()


@pytest.mark.parametrize("dangling", [False, True])
def test_external_or_dangling_current_link_refused(
    layout: tuple[Path, Path], dangling: bool
) -> None:
    root, _ = layout
    outside = root.parent / "outside"
    if not dangling:
        outside.mkdir()
    _symlink(outside, root / "repository")
    assert _run(layout, "prepare", RUN_ID).returncode != 0
    assert (root / "repository").is_symlink()


def test_checksum_mismatch_prevents_extraction(layout: tuple[Path, Path]) -> None:
    root, _ = layout
    _archive(root)
    result = _run(layout, "install", RUN_ID, COMMIT, "0" * 64)
    assert result.returncode != 0
    assert "checksum mismatch" in result.stderr
    assert not (root / "releases" / COMMIT).exists()
    assert (root / "incoming" / RUN_ID / "deploy.tar.gz").is_file()


def test_existing_release_is_not_overwritten(layout: tuple[Path, Path]) -> None:
    root, _ = layout
    digest = _archive(root)
    release = root / "releases" / COMMIT
    release.mkdir()
    preserved = release / "preserve.txt"
    preserved.write_text("keep", encoding="ascii")
    assert _run(layout, "install", RUN_ID, COMMIT, digest).returncode != 0
    assert preserved.read_text(encoding="ascii") == "keep"
    assert not (release / "release.sha").exists()


def test_marker_mismatch_preserves_partial_release(layout: tuple[Path, Path]) -> None:
    root, _ = layout
    previous = _previous(root)
    digest = _archive(root, marker="c" * 40)
    result = _run(layout, "install", RUN_ID, COMMIT, digest)
    assert result.returncode != 0
    assert "marker" in result.stderr
    assert (root / "repository").resolve() == previous
    assert (root / "releases" / COMMIT / "release.sha").is_file()
    assert not (
        root / "releases" / COMMIT / "scripts/production/invocation.txt"
    ).exists()


def test_failed_deploy_preserves_current_and_new_bundle(
    layout: tuple[Path, Path],
) -> None:
    root, _ = layout
    previous = _previous(root)
    digest = _archive(root, deploy_status=23)
    result = _run(layout, "install", RUN_ID, COMMIT, digest)
    assert result.returncode == 23
    assert (root / "repository").resolve() == previous
    assert (root / "releases" / COMMIT / "scripts/production/invocation.txt").is_file()
    assert (root / "incoming" / RUN_ID / "deploy.tar.gz").is_file()
    assert "OPERATIONS_BUNDLE_DEPLOY=PASS" not in result.stdout


@pytest.mark.parametrize("existing", [False, True])
def test_success_activates_only_after_deploy(
    layout: tuple[Path, Path], existing: bool
) -> None:
    root, _ = layout
    if existing:
        _previous(root)
    else:
        # Establish native symlink support without altering the fixture layout.
        probe = root.parent / "symlink-probe"
        _symlink(root, probe)
    digest = _archive(root)
    result = _run(layout, "install", RUN_ID, COMMIT, digest)
    assert result.returncode == 0, result.stderr
    release = root / "releases" / COMMIT
    assert (root / "repository").is_symlink()
    assert (root / "repository").resolve() == release
    invocation = release / "scripts/production/invocation.txt"
    assert invocation.read_text().strip() == f"--image-tag {COMMIT}"
    assert (root / "incoming" / RUN_ID / "deploy.tar.gz").is_file()
    assert "OPERATIONS_BUNDLE_DEPLOY=PASS" in result.stdout


def test_archive_symlink_refused(layout: tuple[Path, Path]) -> None:
    root, _ = layout
    digest = _archive(root)
    archive = root / "incoming" / RUN_ID / "deploy.tar.gz"
    real_archive = root.parent / "archive.tar.gz"
    archive.rename(real_archive)
    _symlink(real_archive, archive)
    result = _run(layout, "install", RUN_ID, COMMIT, digest)
    assert result.returncode != 0
    assert "regular uploaded archive" in result.stderr
    assert not (root / "releases" / COMMIT).exists()


@pytest.mark.parametrize("descriptor", ["missing", "wrong", "invalid_flag"])
def test_invalid_inherited_lock_fails_closed(tmp_path: Path, descriptor: str) -> None:
    state = tmp_path / "state"
    state.mkdir()
    lock = state / "deploy.lock"
    lock.touch()
    other = tmp_path / "other.lock"
    other.touch()
    script = tmp_path / "lock-test.sh"
    opening = "exec 9>&-\n"
    if descriptor == "wrong":
        opening = f"exec 9>{shlex.quote(str(other))}\n"
    elif descriptor == "invalid_flag":
        opening = f"exec 9>{shlex.quote(str(lock))}\n"
    script.write_text(
        f"source {shlex.quote(str(SOURCE.parent / 'common.sh'))}\n"
        f"STATE_DIR={shlex.quote(str(state))}\nLOCK_FILE={shlex.quote(str(lock))}\n"
        f"FLEET_DEPLOY_LOCK_INHERITED={'bogus' if descriptor == 'invalid_flag' else '1'}\n"
        f"{opening}acquire_deploy_lock\n",
        encoding="utf-8",
    )
    bash = shutil.which("bash")
    assert bash
    result = subprocess.run(  # noqa: S603
        [bash, str(script)], capture_output=True, text=True, check=False, timeout=10
    )
    assert result.returncode != 0
    assert "Inherited deployment lock descriptor" in result.stderr


def test_direct_rollback_is_blocked_until_after_pointer_activation(
    layout: tuple[Path, Path],
) -> None:
    root, _ = layout
    digest = _archive(root)
    control = root.parent / "rollback-control"
    control.mkdir()
    for name in ("common.sh", "rollback.sh"):
        shutil.copyfile(SOURCE.parent / name, control / name)
    (control / "data-service-guard.sh").write_text(
        "# No service operations in fixture\n"
    )
    (control / "validate-config.sh").write_text("exit 0\n")
    (control / "docker-compose.yml").touch()
    (root / "environment").touch()
    # Override only file prerequisites in this synthetic common; preserve the
    # actual direct rollback's lock code and inherited-descriptor helper.
    with (control / "common.sh").open("a", encoding="utf-8") as stream:
        stream.write("\nrequire_production_files() { :; }\n")
    commands = root.parent / "commands"
    commands.mkdir()
    (commands / "docker").write_text("#!/usr/bin/env bash\nexit 0\n")
    (commands / "docker").chmod(0o755)
    trace = root.parent / "rollback.log"
    real_ln = shutil.which("ln")
    assert real_ln
    # This intercept is immediately after the child deploy has exited, exactly
    # where the old separate-lock implementation allowed a manual rollback race.
    (commands / "ln").write_text(
        "#!/usr/bin/env bash\nset -eu\n"
        f"if bash {shlex.quote(str(control / 'rollback.sh'))} {PREVIOUS} "
        f">{shlex.quote(str(trace))} 2>&1; then exit 91; fi\n"
        f"grep -q 'Another production deploy or rollback' {shlex.quote(str(trace))}\n"
        f'exec {shlex.quote(real_ln)} "$@"\n',
        encoding="utf-8",
    )
    (commands / "ln").chmod(0o755)
    result = _run(
        layout,
        "install",
        RUN_ID,
        COMMIT,
        digest,
        extra_environment={
            "PATH": f"{commands}:{os.environ['PATH']}",
            "FLEET_PRODUCTION_STATE_DIR": str(root / "state"),
        },
    )
    assert result.returncode == 0, result.stderr
    assert "Another production deploy or rollback" in trace.read_text()
    assert (root / "repository").resolve() == root / "releases" / COMMIT
    flock = shutil.which("flock")
    assert flock
    unlocked = subprocess.run(  # noqa: S603
        [flock, "-n", str(root / "state" / "deploy.lock"), "true"],
        check=False,
        timeout=10,
    )
    assert unlocked.returncode == 0
