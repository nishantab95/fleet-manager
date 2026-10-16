# Production preparation change inventory

This inventory is relative to base `e7a19e61be0e91065ebe55962b8eced8f5819267` on
`main`. It includes the preserved earlier work and the final corrections made
during resumption. See the [readiness report](production-readiness-report.md) for
the verified implementation revision and release gates. Generated test output,
local caches, `.env`, runtime data and signing material are not committed.

Status: **A** added, **M** modified, **R** renamed (old and new paths shown).
The two old duplicate ADR paths are renames, not discarded historical decisions.
There are 94 changed-file entries including this inventory; Git rename
similarity heuristics may display those two as separate additions/deletions.

## Build, CI and repository hygiene

Manual protected release workflows, expanded regression/security CI, build context exclusions and updated entry-point documentation.

| Status | File |
| --- | --- |
| A | [.dockerignore](../.dockerignore) |
| M | [.github/workflows/ci.yml](../.github/workflows/ci.yml) |
| A | [.github/workflows/google-play-release.yml](../.github/workflows/google-play-release.yml) |
| A | [.github/workflows/production-deploy.yml](../.github/workflows/production-deploy.yml) |
| M | [.gitignore](../.gitignore) |
| A | [.gitleaks.toml](../.gitleaks.toml) |
| M | [README.md](../README.md) |

## Marketing website

Linux image, privacy disclosure/navigation and production browser-test configuration. Existing contact/lead business behavior remains.

| Status | File |
| --- | --- |
| M | [apps/marketing/app/marketing.css](../apps/marketing/app/marketing.css) |
| A | [apps/marketing/app/privacy/page.tsx](../apps/marketing/app/privacy/page.tsx) |
| M | [apps/marketing/components/content.ts](../apps/marketing/components/content.ts) |
| M | [apps/marketing/components/MarketingChrome.tsx](../apps/marketing/components/MarketingChrome.tsx) |
| M | [apps/marketing/components/MarketingSite.test.tsx](../apps/marketing/components/MarketingSite.test.tsx) |
| A | [apps/marketing/Dockerfile](../apps/marketing/Dockerfile) |
| M | [apps/marketing/playwright.config.ts](../apps/marketing/playwright.config.ts) |

## Android application

Separate Play signing configuration, explicit company-PIN/Firebase compatibility, fixed cloud default, bounded network waits and preservation regressions. Pilot package/key unchanged.

| Status | File |
| --- | --- |
| M | [apps/mobile/android/app/build.gradle.kts](../apps/mobile/android/app/build.gradle.kts) |
| M | [apps/mobile/lib/auth/login_auth_provider.dart](../apps/mobile/lib/auth/login_auth_provider.dart) |
| M | [apps/mobile/lib/data/api_client.dart](../apps/mobile/lib/data/api_client.dart) |
| A | [apps/mobile/test/api_client_timeout_test.dart](../apps/mobile/test/api_client_timeout_test.dart) |
| M | [apps/mobile/test/firebase_login_test.dart](../apps/mobile/test/firebase_login_test.dart) |
| M | [apps/mobile/test/pilot_login_test.dart](../apps/mobile/test/pilot_login_test.dart) |

## Owner and supervisor web

Standalone Linux image, browser security headers and production-mode E2E runner.

| Status | File |
| --- | --- |
| A | [apps/web/Dockerfile](../apps/web/Dockerfile) |
| M | [apps/web/next.config.ts](../apps/web/next.config.ts) |
| M | [apps/web/playwright.config.ts](../apps/web/playwright.config.ts) |

## Documentation and ADRs

Deployment/release/recovery/data guidance, actual evidence report, source audit, navigation indexes and optional Firebase scope. Duplicate ADR IDs renumbered with content retained.

| Status | File |
| --- | --- |
| M | [docs/adr/0003-authentication-and-rbac.md](../docs/adr/0003-authentication-and-rbac.md) |
| M | [docs/adr/0011-firebase-phone-authentication.md](../docs/adr/0011-firebase-phone-authentication.md) |
| A | [docs/adr/0015-single-vps-production-deployment.md](../docs/adr/0015-single-vps-production-deployment.md) |
| A | [docs/adr/0016-google-play-and-pilot-release-separation.md](../docs/adr/0016-google-play-and-pilot-release-separation.md) |
| R | `docs/adr/0005-supervisor-operations-verification.md` → [docs/adr/0017-supervisor-operations-verification.md](../docs/adr/0017-supervisor-operations-verification.md) |
| R | `docs/adr/0012-public-brand-and-marketing-site.md` → [docs/adr/0018-public-brand-and-marketing-site.md](../docs/adr/0018-public-brand-and-marketing-site.md) |
| A | [docs/adr/README.md](../docs/adr/README.md) |
| M | [docs/architecture.md](../docs/architecture.md) |
| A | [docs/archive/README.md](../docs/archive/README.md) |
| M | [docs/development.md](../docs/development.md) |
| M | [docs/firebase-auth-setup.md](../docs/firebase-auth-setup.md) |
| M | [docs/firebase-company-setup.md](../docs/firebase-company-setup.md) |
| M | [docs/firebase-staging-runbook.md](../docs/firebase-staging-runbook.md) |
| A | [docs/google-play-release.md](../docs/google-play-release.md) |
| A | [docs/index.md](../docs/index.md) |
| M | [docs/mobile-pilot-signing-backup.md](../docs/mobile-pilot-signing-backup.md) |
| A | [docs/production-change-inventory.md](../docs/production-change-inventory.md) |
| A | [docs/production-data-handling.md](../docs/production-data-handling.md) |
| A | [docs/production-deployment.md](../docs/production-deployment.md) |
| A | [docs/production-engineering-audit.md](../docs/production-engineering-audit.md) |
| A | [docs/production-migration-and-rollback.md](../docs/production-migration-and-rollback.md) |
| A | [docs/production-operations.md](../docs/production-operations.md) |
| A | [docs/production-readiness-report.md](../docs/production-readiness-report.md) |
| M | [docs/security.md](../docs/security.md) |

## Linux infrastructure

Private Compose stack, HTTPS routing, least-privilege evidence identity, external configuration examples and backup/health timers.

| Status | File |
| --- | --- |
| A | [infra/production/Caddyfile](../infra/production/Caddyfile) |
| A | [infra/production/docker-compose.yml](../infra/production/docker-compose.yml) |
| A | [infra/production/init-minio.sh](../infra/production/init-minio.sh) |
| A | [infra/production/minio-evidence-policy.json](../infra/production/minio-evidence-policy.json) |
| A | [infra/production/production.env.example](../infra/production/production.env.example) |
| A | [infra/production/restic.env.example](../infra/production/restic.env.example) |
| A | [infra/production/systemd/fleet-ai-backup.service](../infra/production/systemd/fleet-ai-backup.service) |
| A | [infra/production/systemd/fleet-ai-backup.timer](../infra/production/systemd/fleet-ai-backup.timer) |
| A | [infra/production/systemd/fleet-ai-health.service](../infra/production/systemd/fleet-ai-health.service) |
| A | [infra/production/systemd/fleet-ai-health.timer](../infra/production/systemd/fleet-ai-health.timer) |
| M | [infra/README.md](../infra/README.md) |

## Release and verification scripts

Manual release helpers, safe migrations/image rollback, separate backups and isolated restore, strict AAB verification and regression tests.

| Status | File |
| --- | --- |
| A | [scripts/build-play-aab.ps1](../scripts/build-play-aab.ps1) |
| A | [scripts/production/backup-and-verify.sh](../scripts/production/backup-and-verify.sh) |
| A | [scripts/production/backup.sh](../scripts/production/backup.sh) |
| A | [scripts/production/common.sh](../scripts/production/common.sh) |
| A | [scripts/production/data-service-guard.sh](../scripts/production/data-service-guard.sh) |
| A | [scripts/production/deploy.sh](../scripts/production/deploy.sh) |
| A | [scripts/production/healthcheck.sh](../scripts/production/healthcheck.sh) |
| A | [scripts/production/local-smoke-test.sh](../scripts/production/local-smoke-test.sh) |
| A | [scripts/production/offsite-backup.sh](../scripts/production/offsite-backup.sh) |
| A | [scripts/production/prune-local-backups.sh](../scripts/production/prune-local-backups.sh) |
| A | [scripts/production/rollback.sh](../scripts/production/rollback.sh) |
| A | [scripts/production/upload-play-aab.sh](../scripts/production/upload-play-aab.sh) |
| A | [scripts/production/validate-config.sh](../scripts/production/validate-config.sh) |
| A | [scripts/production/verify-backup.sh](../scripts/production/verify-backup.sh) |
| A | [scripts/production/verify-offsite-backup.sh](../scripts/production/verify-offsite-backup.sh) |
| M | [scripts/test_mobile_update_contract.py](../scripts/test_mobile_update_contract.py) |
| A | [scripts/test_production_deploy.py](../scripts/test_production_deploy.py) |
| A | [scripts/test_validate_play_aab.py](../scripts/test_validate_play_aab.py) |
| M | [scripts/test.ps1](../scripts/test.ps1) |
| A | [scripts/validate_play_aab.py](../scripts/validate_play_aab.py) |

## FastAPI service and tests

Linux image, targeted dependency updates, production validation, bounded pool/rate controls, safe exception logs and regression/typing corrections. No migration changes.

| Status | File |
| --- | --- |
| A | [services/api/Dockerfile](../services/api/Dockerfile) |
| M | [services/api/pyproject.toml](../services/api/pyproject.toml) |
| M | [services/api/src/fleet_api/auth/tokens.py](../services/api/src/fleet_api/auth/tokens.py) |
| M | [services/api/src/fleet_api/core/config.py](../services/api/src/fleet_api/core/config.py) |
| A | [services/api/src/fleet_api/core/rate_limit.py](../services/api/src/fleet_api/core/rate_limit.py) |
| M | [services/api/src/fleet_api/core/structured_logging.py](../services/api/src/fleet_api/core/structured_logging.py) |
| M | [services/api/src/fleet_api/db/session.py](../services/api/src/fleet_api/db/session.py) |
| M | [services/api/src/fleet_api/main.py](../services/api/src/fleet_api/main.py) |
| M | [services/api/tests/test_asset_site_deployments_api.py](../services/api/tests/test_asset_site_deployments_api.py) |
| M | [services/api/tests/test_company_pin_auth.py](../services/api/tests/test_company_pin_auth.py) |
| M | [services/api/tests/test_config.py](../services/api/tests/test_config.py) |
| M | [services/api/tests/test_driver_api.py](../services/api/tests/test_driver_api.py) |
| M | [services/api/tests/test_owner_operations_api.py](../services/api/tests/test_owner_operations_api.py) |
| A | [services/api/tests/test_rate_limit.py](../services/api/tests/test_rate_limit.py) |
| A | [services/api/tests/test_structured_logging.py](../services/api/tests/test_structured_logging.py) |
| M | [services/api/uv.lock](../services/api/uv.lock) |

## Preserved boundaries

No Alembic/SQLite schema, business workflow, permanent signing key, package
identifier, installed Pilot data, Windows service/launcher configuration or
live infrastructure was replaced. No generic large-module refactor was mixed
into this preparation. The audit records incremental follow-up work separately.
