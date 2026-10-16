"""Read-only Git ignore/line-ending checks; never run cleanup on the checkout."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "path",
    [
        "private.env",
        ".env.production",
        ".aws/credentials",
        ".ssh/id_ed25519",
        "apps/mobile/android/upload.jks",
        "apps/mobile/android/upload.keystore",
        "local/upload.pfx",
        "local/private.pem",
        "local/private.key",
        "apps/mobile/android/key.properties",
        "apps/mobile/android/.gradle/cache.bin",
        "apps/mobile/android/.kotlin/cache.bin",
        "apps/mobile/coverage/lcov.info",
        "services/api/.coverage.worker",
        "apps/web/.next/dev/cache/generated.bin",
        ".tmp/audit-output.json",
        "CLAUDE.local.md",
        ".claude/settings.local.json",
        ".codex/auth.json",
    ],
)
def test_generated_or_private_path_is_ignored(path: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "check-ignore", "--no-index", "-q", "--", path],
        check=False,
        capture_output=True,
    )
    assert result.returncode == 0, path


@pytest.mark.parametrize(
    "path",
    [
        "AGENTS.md",
        "CLAUDE.md",
        "PROJECT_RULES.md",
        "apps/web/package-lock.json",
        "apps/marketing/package-lock.json",
        "apps/mobile/pubspec.lock",
        "services/api/uv.lock",
        "apps/web/app/evidence/[event_id]/page.tsx",
        "services/api/src/fleet_api/main.py",
        ".env.example",
        "infra/production/production.env.example",
        ".claude/settings.json",
    ],
)
def test_source_and_shared_configuration_are_not_ignored(path: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "check-ignore", "--no-index", "-q", "--", path],
        check=False,
        capture_output=True,
    )
    assert result.returncode == 1, path


def test_release_shell_scripts_keep_lf_on_windows_checkout() -> None:
    paths = ["scripts/production/deploy.sh", "infra/production/init-minio.sh"]
    result = subprocess.run(
        ["git", "-C", str(ROOT), "check-attr", "eol", "--", *paths],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.splitlines() == [f"{path}: eol: lf" for path in paths]
