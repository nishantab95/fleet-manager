# Repository audit change inventory

Scope: the sequential repository engineering task starting at
`06ecbc457d7e2fc0795310636fea0064f47ab0ff` on existing `main`.
This list is separate from the preserved [production implementation inventory](../production-change-inventory.md).
See the [consolidated report](repository-readiness-report.md) for purpose, tests,
limitations and release gates. Ignored audit logs, regenerated test artifacts
and the explicitly documented cache removals are not committed source changes.

78 files: 39 added, 39 modified; no tracked-file deletions or renames.

| Status | Exact checkout-relative path |
| --- | --- |
| M | `.dockerignore` |
| M | `.gitattributes` |
| M | `.github/workflows/ci.yml` |
| M | `.github/workflows/production-deploy.yml` |
| M | `.gitignore` |
| A | `AGENTS.md` |
| M | `apps/marketing/AGENTS.md` |
| A | `apps/marketing/CLAUDE.md` |
| M | `apps/marketing/Dockerfile` |
| A | `apps/marketing/Dockerfile.dockerignore` |
| A | `apps/mobile/AGENTS.md` |
| A | `apps/mobile/CLAUDE.md` |
| M | `apps/web/AGENTS.md` |
| M | `apps/web/Dockerfile` |
| A | `apps/web/Dockerfile.dockerignore` |
| A | `CLAUDE.md` |
| M | `docs/adr/0015-single-vps-production-deployment.md` |
| A | `docs/adr/0019-operations-only-deployment-bundles.md` |
| M | `docs/adr/README.md` |
| M | `docs/architecture.md` |
| A | `docs/architecture/index.md` |
| M | `docs/development.md` |
| A | `docs/development/agent-onboarding.md` |
| A | `docs/development/change-workflows.md` |
| A | `docs/development/index.md` |
| M | `docs/domain-model.md` |
| M | `docs/firebase-company-setup.md` |
| M | `docs/index.md` |
| M | `docs/mobile-pilot-runbook.md` |
| A | `docs/operations/build-context-inventory.md` |
| A | `docs/operations/cloud-packaging.md` |
| A | `docs/operations/index.md` |
| A | `docs/operations/local-disk-audit.md` |
| A | `docs/operations/local-maintenance.md` |
| A | `docs/operations/repository-change-inventory.md` |
| A | `docs/operations/repository-readiness-report.md` |
| M | `docs/pc-role-lab.md` |
| M | `docs/phase7-e2e-matrix.md` |
| M | `docs/pilot-checklist.md` |
| M | `docs/pilot-runbook.md` |
| M | `docs/production-deployment.md` |
| M | `docs/production-engineering-audit.md` |
| M | `docs/production-migration-and-rollback.md` |
| M | `docs/production-operations.md` |
| A | `docs/releases/index.md` |
| A | `docs/security/index.md` |
| M | `PROJECT_RULES.md` |
| M | `README.md` |
| A | `scripts/build_deploy_bundle.py` |
| A | `scripts/maintenance/build_context_manifest.py` |
| A | `scripts/maintenance/cleanup-generated.ps1` |
| A | `scripts/maintenance/disk_audit.py` |
| A | `scripts/maintenance/test_build_contexts.py` |
| A | `scripts/maintenance/test_cleanup_generated.py` |
| A | `scripts/maintenance/test_disk_audit.py` |
| A | `scripts/maintenance/test_dockerignore_contract.py` |
| A | `scripts/maintenance/test_repository_hygiene.py` |
| M | `scripts/production/backup-and-verify.sh` |
| M | `scripts/production/backup.sh` |
| M | `scripts/production/common.sh` |
| M | `scripts/production/deploy.sh` |
| M | `scripts/production/healthcheck.sh` |
| M | `scripts/production/local-smoke-test.sh` |
| M | `scripts/production/prune-local-backups.sh` |
| A | `scripts/production/receive-deploy-bundle.sh` |
| M | `scripts/production/rollback.sh` |
| A | `scripts/test_backup_retention.py` |
| A | `scripts/test_build_deploy_bundle.py` |
| A | `scripts/test_host_resources.py` |
| A | `scripts/test_local_smoke_safety.py` |
| M | `scripts/test_production_deploy.py` |
| A | `scripts/test_receive_deploy_bundle.py` |
| A | `services/api/AGENTS.md` |
| A | `services/api/CLAUDE.md` |
| M | `services/api/Dockerfile` |
| A | `services/api/Dockerfile.dockerignore` |
| M | `services/api/migrations/env.py` |
| M | `services/api/tests/test_fleet_asset_migration.py` |

A = added; M = modified. Final commit SHA is supplied in the handover after
commit creation; use `git log -1 --format=%H -- docs/operations/repository-readiness-report.md`
to identify this report's revision. No remote push, live deployment or Play
publication is part of this inventory.
