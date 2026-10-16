"""Policy-shape checks, not a substitute for Docker's native context matching.

The context-audit Docker stage/export verifies actual BuildKit inclusion. These
tests guard reviewed allowlists and the final shared exclusion policy from drift.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMPONENTS = {
    "services/api": {
        "files": {"pyproject.toml", "uv.lock", "alembic.ini"},
        "directories": {"src", "migrations"},
    },
    "apps/web": {
        "files": {
            "package.json",
            "package-lock.json",
            "next.config.ts",
            "tsconfig.json",
        },
        "directories": {"app", "features", "lib", "public"},
    },
    "apps/marketing": {
        "files": {
            "package.json",
            "package-lock.json",
            "next.config.ts",
            "tsconfig.json",
        },
        "directories": {"app", "components", "lib", "public"},
    },
}
MARKER = "# Terminal exclusions are intentionally repeated:"


def rules(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.startswith("#")
    ]


def expected_inclusions(components: list[str]) -> set[str]:
    expected: set[str] = set()
    for component in components:
        expected.update({f"!{component.split('/')[0]}/", f"!{component}/"})
        expected.update(
            f"!{component}/{name}" for name in COMPONENTS[component]["files"]
        )
        for directory in COMPONENTS[component]["directories"]:
            expected.update(
                {f"!{component}/{directory}/", f"!{component}/{directory}/**"}
            )
    return expected


@pytest.mark.parametrize("component", list(COMPONENTS))
def test_component_context_reopens_only_reviewed_build_inputs(component: str) -> None:
    text = (ROOT / component / "Dockerfile.dockerignore").read_text(encoding="utf-8")
    policy = rules(text)
    assert policy[0] == "**"
    assert {line for line in policy if line.startswith("!")} == expected_inclusions(
        [component]
    )
    parent = component.split("/")[0]
    assert policy.index(f"!{parent}/") < policy.index(f"{parent}/**")
    assert policy.index(f"{parent}/**") < policy.index(f"!{component}/")
    assert policy.index(f"!{component}/") < policy.index(f"{component}/**")


def test_root_fallback_is_only_the_three_production_components() -> None:
    policy = rules((ROOT / ".dockerignore").read_text(encoding="utf-8"))
    assert policy[0] == "**"
    assert {line for line in policy if line.startswith("!")} == expected_inclusions(
        list(COMPONENTS)
    )


@pytest.mark.parametrize("component", list(COMPONENTS))
def test_each_specific_policy_keeps_identical_terminal_security_exclusions(
    component: str,
) -> None:
    root_tail = (ROOT / ".dockerignore").read_text(encoding="utf-8").split(MARKER, 1)[1]
    specific_tail = (
        (ROOT / component / "Dockerfile.dockerignore")
        .read_text(encoding="utf-8")
        .split(MARKER, 1)[1]
    )
    assert specific_tail == root_tail
    assert not any(line.startswith("!") for line in rules(specific_tail))


def test_terminal_policy_covers_nested_generated_private_and_release_material() -> None:
    tail = (ROOT / ".dockerignore").read_text(encoding="utf-8").split(MARKER, 1)[1]
    required = {
        "**/.git",
        "**/.runtime",
        "**/.tmp",
        "**/node_modules",
        "**/.venv",
        "**/.next",
        "**/.dart_tool",
        "**/.gradle",
        "**/.kotlin",
        "**/build",
        "**/__pycache__",
        "**/*.py[cod]",
        "**/*.tsbuildinfo",
        "**/tests",
        "**/e2e",
        "**/*.test.*",
        "**/*.spec.*",
        "**/test-results",
        "**/coverage",
        "**/*.md",
        "**/.env",
        "**/.env.*",
        "**/*.env",
        "**/key.properties",
        "**/local.properties",
        "**/google-services.json",
        "**/*service-account*.json",
        "**/*firebase-adminsdk*.json",
        "**/*credentials*.json",
        "**/secrets",
        "**/credentials",
        "**/*.jks",
        "**/*.keystore",
        "**/*.p12",
        "**/*.pfx",
        "**/*.pem",
        "**/*.crt",
        "**/*.key",
        "**/*.apk",
        "**/*.aab",
        "**/backups",
        "evidence",
        "infra/data",
        "**/uploads",
        "**/*.db",
        "**/*.sqlite*",
        "**/*.dump",
        "**/*.sql",
        "**/*.tar",
        "**/*.tar.*",
        "**/*.tgz",
        "**/*.zip",
        "**/*.log",
    }
    assert required <= set(rules(tail))


def test_evidence_source_route_is_not_confused_with_persistent_evidence_data() -> None:
    assert (ROOT / "apps/web/app/evidence/[event_id]/page.tsx").is_file()
    for policy_path in [
        ROOT / ".dockerignore",
        ROOT / "apps/web/Dockerfile.dockerignore",
    ]:
        policy = rules(policy_path.read_text(encoding="utf-8"))
        assert "!apps/web/app/**" in policy
        assert "**/evidence" not in policy
        assert "apps/web/app/evidence" not in policy
        assert "evidence" in policy and "infra/data" in policy


@pytest.mark.parametrize("component", list(COMPONENTS))
def test_reviewed_build_inputs_exist_in_the_actual_component(component: str) -> None:
    for filename in COMPONENTS[component]["files"]:
        assert (ROOT / component / filename).is_file()
    for directory in COMPONENTS[component]["directories"]:
        assert (ROOT / component / directory).is_dir()
