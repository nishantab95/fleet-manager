# Native Docker build-context inventory

Measured locally on 2026-10-16 in `D:\Git\fleet maneger\fleet manager`,
on `main` with base HEAD `06ecbc457d7e2fc0795310636fea0064f47ab0ff` and
the reviewed Dockerfile/ignore changes and final Phase 8 Alembic logging fix.
Web/marketing retain their unchanged Phase 6 measurements. This is a dated
measurement, not a promise that future source changes have the same size.

## Result

| Component | COPY-visible files | Logical file bytes | Dockerfile + effective ignore bytes |
| --- | ---: | ---: | ---: |
| api | 106 | 1,379,422 | 3,256 |
| web | 38 | 656,019 | 3,132 |
| marketing | 32 | 1,137,641 | 3,301 |
| Total | 176 | 3,173,082 | 9,689 |

All 176 exported files were in the Git index, and every exported file's SHA-256
matched its current checkout counterpart. There were no untracked exported
files, symlink/reparse entries, or detected protected/generated artifact names.
The JSON manifests retain the per-file hashes locally; this guide intentionally
records only source paths and logical sizes.

These numbers are **not** image sizes, compressed registry downloads, allocated
disk usage, or exact network-transfer bytes. They measure regular files visible
to `COPY . /` in Docker's native filtered context. Dockerfile and effective
Dockerfile-specific ignore files were not COPY-visible and are accounted for
separately. BuildKit metadata, framing, caching and incremental transfer overhead
are not included. See [Docker build-context rules](https://docs.docker.com/build/concepts/context/)
and [local exporter behavior](https://docs.docker.com/build/exporters/local-tar/).

## Method and scope

Each production Dockerfile has an independent initial
`FROM scratch AS context-audit` / `COPY . /` stage. The final `runtime` stage
remains the default and has no dependency on this audit target. The local
measurement used Docker BuildKit's actual Dockerfile-specific filtering, not
a custom approximation of ignore patterns. No application-stage commands,
container startup, image publication or VPS operations were needed to export
the filtered context.

From the checkout root, the command shape was:

```powershell
# Choose a fresh, nonexistent destination; never reuse an old export.
$contextDestination = ".tmp/context-audit-api-<unique-run>"
if (Test-Path -LiteralPath $contextDestination) { throw "Export destination already exists" }
docker buildx build --platform linux/amd64 --target context-audit --file services/api/Dockerfile --output "type=local,dest=$contextDestination" .
if ($LASTEXITCODE -ne 0) { throw "Native context export failed" }
.\services\api\.venv\Scripts\python.exe scripts/maintenance/build_context_manifest.py --component api --export $contextDestination
if ($LASTEXITCODE -ne 0) { throw "Context verification failed" }
```

Use `apps/web/Dockerfile` / `--component web` or
`apps/marketing/Dockerfile` / `--component marketing` with separate fresh
destinations for the other components. These commands are manual diagnostics,
not part of startup, deployment or automatic cleanup.

The [manifest reader](../../scripts/maintenance/build_context_manifest.py) is
read-only, accepts an existing export below checkout `.tmp`, emits JSON to
stdout, refuses protected names/links/special files/read errors and compares
exported hashes against the current checkout. It reports untracked inputs
explicitly; filename checks and Git tracking do not replace secret scanning.
Use a quiescent, trusted checkout: the reader detects ordinary file changes but
does not attest the producing Docker command or defend against hostile
filesystem races. Fresh destinations and the recorded native export command
are part of the verification procedure.

The [manifest and stage tests](../../scripts/maintenance/test_build_contexts.py)
and [ignore-policy contract tests](../../scripts/maintenance/test_dockerignore_contract.py)
passed together: **54 tests**. Ruff checks/formatting and strict mypy for the two
manifest files passed. Native exports provide the separate Docker-semantic
verification.

Local retained exports:

| Component | Export directory | JSON manifest |
| --- | --- | --- |
| api | `.tmp/context-audit-api-20261016-212221` | `.tmp/context-manifest-api-final-20261016.json` |
| web | `.tmp/context-audit-web-20261016-203330` | `.tmp/manifests-web-20261016.json` |
| marketing | `.tmp/context-audit-marketing-20261016-203337` | `.tmp/manifests-marketing-20261016.json` |

Local exports and manifests remain ignored; they are audit artifacts, not
deployment inputs. Do not infer permission to delete them or other `.tmp`
contents from this guide.

## Included and excluded boundaries

The API context contains its locked project inputs, migrations and source.
Each browser context contains its package lock/configuration and reviewed
application/source/public-asset directories. The authenticated
`apps/web/app/evidence/[event_id]/page.tsx` is legitimate source and is included;
stored evidence photographs are not.

The deny-by-default policies exclude unrelated monorepo content, laptop/Pilot
runtime, local dependencies/caches, tests/reports, documentation, credentials,
environment files, signing identities, APK/AAB releases, databases, backups and
stored uploads. `next-env.d.ts` is deliberately excluded: it is a local generated,
Git-ignored declaration which Next.js regenerates during a clean build.
No authentication behavior, offline data, schema or signing identity was changed
by this measurement. Final API input adds 32 bytes for the Alembic flag preventing
embedded migration checks from disabling existing application/server loggers.
The earlier API export (1,379,390 bytes) remains retained as Phase 6 evidence.

Per-Dockerfile ignore files take precedence over root `.dockerignore`; each
therefore carries the complete terminal exclusion policy. Contract tests guard
that duplication. For runtime image, VPS transfer and release approval context,
use [production deployment](../production-deployment.md) and the
[production readiness report](../production-readiness-report.md).

## Docker control files

| Component | Control path | Logical bytes |
| --- | --- | ---: |
| api | `services/api/Dockerfile` | 1,339 |
| api | `services/api/Dockerfile.dockerignore` | 1,917 |
| web | `apps/web/Dockerfile` | 1,158 |
| web | `apps/web/Dockerfile.dockerignore` | 1,974 |
| marketing | `apps/marketing/Dockerfile` | 1,239 |
| marketing | `apps/marketing/Dockerfile.dockerignore` | 2,062 |

## COPY-visible source inventory

### api

| Source path | Logical bytes |
| --- | ---: |
| `services/api/alembic.ini` | 582 |
| `services/api/migrations/env.py` | 1,569 |
| `services/api/migrations/script.py.mako` | 609 |
| `services/api/migrations/versions/0001_foundation.py` | 540 |
| `services/api/migrations/versions/0002_core_domain.py` | 27,627 |
| `services/api/migrations/versions/0003_authentication.py` | 6,498 |
| `services/api/migrations/versions/0004_evidence_objects.py` | 2,654 |
| `services/api/migrations/versions/0005_phase6_reporting.py` | 8,104 |
| `services/api/migrations/versions/0006_pc_emergency_alerts.py` | 836 |
| `services/api/migrations/versions/0007_local_pilot_role_context.py` | 1,303 |
| `services/api/migrations/versions/0008_driver_duty_sessions.py` | 7,455 |
| `services/api/migrations/versions/0009_membership_business_display_names.py` | 622 |
| `services/api/migrations/versions/0010_link_events_to_duty_sessions.py` | 1,182 |
| `services/api/migrations/versions/0011_fleet_assets.py` | 11,111 |
| `services/api/migrations/versions/0012_owner_people_sites.py` | 2,114 |
| `services/api/migrations/versions/0013_asset_site_deployments.py` | 4,883 |
| `services/api/migrations/versions/0014_driver_asset_assignments.py` | 3,773 |
| `services/api/migrations/versions/0015_machinery_hmr.py` | 4,809 |
| `services/api/migrations/versions/0016_report_templates.py` | 8,831 |
| `services/api/migrations/versions/0017_internal_codes_site_short_names.py` | 1,738 |
| `services/api/migrations/versions/0018_fleet_asset_contacts.py` | 1,193 |
| `services/api/migrations/versions/0019_asset_meter_capabilities.py` | 4,682 |
| `services/api/migrations/versions/0020_maintenance_v2.py` | 23,395 |
| `services/api/migrations/versions/0021_maintenance_responsibility.py` | 11,983 |
| `services/api/migrations/versions/0022_maintenance_starter_catalog.py` | 5,730 |
| `services/api/migrations/versions/0023_user_auth_identity.py` | 3,186 |
| `services/api/migrations/versions/0024_company_pin_auth.py` | 5,376 |
| `services/api/pyproject.toml` | 1,469 |
| `services/api/src/fleet_api/__init__.py` | 56 |
| `services/api/src/fleet_api/api/__init__.py` | 55 |
| `services/api/src/fleet_api/api/admin.py` | 14,784 |
| `services/api/src/fleet_api/api/auth.py` | 23,772 |
| `services/api/src/fleet_api/api/dependencies.py` | 9,646 |
| `services/api/src/fleet_api/api/driver.py` | 16,563 |
| `services/api/src/fleet_api/api/maintenance_schemas.py` | 11,151 |
| `services/api/src/fleet_api/api/owner.py` | 8,403 |
| `services/api/src/fleet_api/api/owner_assignments.py` | 5,939 |
| `services/api/src/fleet_api/api/owner_deployments.py` | 6,324 |
| `services/api/src/fleet_api/api/owner_maintenance.py` | 21,896 |
| `services/api/src/fleet_api/api/owner_operations.py` | 4,530 |
| `services/api/src/fleet_api/api/owner_people_sites.py` | 13,196 |
| `services/api/src/fleet_api/api/owner_report_templates.py` | 4,945 |
| `services/api/src/fleet_api/api/pilot_releases.py` | 13,512 |
| `services/api/src/fleet_api/api/reports.py` | 47,633 |
| `services/api/src/fleet_api/api/schemas.py` | 29,807 |
| `services/api/src/fleet_api/api/simple_site_workbook.py` | 29,882 |
| `services/api/src/fleet_api/api/supervisor.py` | 21,563 |
| `services/api/src/fleet_api/auth/__init__.py` | 71 |
| `services/api/src/fleet_api/auth/company_pin.py` | 1,444 |
| `services/api/src/fleet_api/auth/firebase.py` | 4,936 |
| `services/api/src/fleet_api/auth/phone.py` | 894 |
| `services/api/src/fleet_api/auth/providers.py` | 4,659 |
| `services/api/src/fleet_api/auth/service.py` | 49,325 |
| `services/api/src/fleet_api/auth/tokens.py` | 5,152 |
| `services/api/src/fleet_api/bootstrap/__init__.py` | 44 |
| `services/api/src/fleet_api/bootstrap/pilot.py` | 14,659 |
| `services/api/src/fleet_api/bootstrap/reset_pilot.py` | 5,090 |
| `services/api/src/fleet_api/core/__init__.py` | 60 |
| `services/api/src/fleet_api/core/config.py` | 12,576 |
| `services/api/src/fleet_api/core/rate_limit.py` | 2,798 |
| `services/api/src/fleet_api/core/request_id.py` | 1,560 |
| `services/api/src/fleet_api/core/structured_logging.py` | 2,577 |
| `services/api/src/fleet_api/db/__init__.py` | 31 |
| `services/api/src/fleet_api/db/base.py` | 503 |
| `services/api/src/fleet_api/db/models/__init__.py` | 2,433 |
| `services/api/src/fleet_api/db/models/assignment.py` | 3,217 |
| `services/api/src/fleet_api/db/models/audit.py` | 1,555 |
| `services/api/src/fleet_api/db/models/auth.py` | 7,884 |
| `services/api/src/fleet_api/db/models/closure.py` | 3,934 |
| `services/api/src/fleet_api/db/models/common.py` | 803 |
| `services/api/src/fleet_api/db/models/company.py` | 3,199 |
| `services/api/src/fleet_api/db/models/deployment.py` | 2,354 |
| `services/api/src/fleet_api/db/models/device.py` | 1,469 |
| `services/api/src/fleet_api/db/models/duty.py` | 5,569 |
| `services/api/src/fleet_api/db/models/events.py` | 7,145 |
| `services/api/src/fleet_api/db/models/evidence.py` | 1,790 |
| `services/api/src/fleet_api/db/models/fleet_asset.py` | 5,835 |
| `services/api/src/fleet_api/db/models/maintenance.py` | 25,974 |
| `services/api/src/fleet_api/db/models/membership.py` | 2,344 |
| `services/api/src/fleet_api/db/models/rental.py` | 3,526 |
| `services/api/src/fleet_api/db/models/report_template.py` | 1,673 |
| `services/api/src/fleet_api/db/session.py` | 905 |
| `services/api/src/fleet_api/domain/__init__.py` | 51 |
| `services/api/src/fleet_api/domain/admin.py` | 22,670 |
| `services/api/src/fleet_api/domain/assets.py` | 9,093 |
| `services/api/src/fleet_api/domain/assignments.py` | 5,373 |
| `services/api/src/fleet_api/domain/audit.py` | 1,197 |
| `services/api/src/fleet_api/domain/deployments.py` | 20,145 |
| `services/api/src/fleet_api/domain/driver.py` | 49,025 |
| `services/api/src/fleet_api/domain/driver_assignments.py` | 17,019 |
| `services/api/src/fleet_api/domain/enums.py` | 6,761 |
| `services/api/src/fleet_api/domain/errors.py` | 3,450 |
| `services/api/src/fleet_api/domain/events.py` | 10,398 |
| `services/api/src/fleet_api/domain/maintenance.py` | 65,873 |
| `services/api/src/fleet_api/domain/maintenance_proof.py` | 18,140 |
| `services/api/src/fleet_api/domain/maintenance_starters.py` | 18,598 |
| `services/api/src/fleet_api/domain/owner_assets.py` | 25,276 |
| `services/api/src/fleet_api/domain/owner_operations.py` | 110,750 |
| `services/api/src/fleet_api/domain/owner_people_sites.py` | 46,394 |
| `services/api/src/fleet_api/domain/report_templates.py` | 21,208 |
| `services/api/src/fleet_api/domain/reporting.py` | 56,051 |
| `services/api/src/fleet_api/domain/supervisor.py` | 17,722 |
| `services/api/src/fleet_api/main.py` | 6,905 |
| `services/api/src/fleet_api/storage/__init__.py` | 50 |
| `services/api/src/fleet_api/storage/objects.py` | 13,246 |
| `services/api/uv.lock` | 208,528 |

### web

| Source path | Logical bytes |
| --- | ---: |
| `apps/web/app/api/backend/[...path]/route.ts` | 3,831 |
| `apps/web/app/driver-test/page.tsx` | 1,133 |
| `apps/web/app/evidence/[event_id]/page.tsx` | 3,445 |
| `apps/web/app/globals.css` | 72,619 |
| `apps/web/app/icon.svg` | 414 |
| `apps/web/app/lab/page.tsx` | 393 |
| `apps/web/app/layout.tsx` | 611 |
| `apps/web/app/login/page.tsx` | 322 |
| `apps/web/app/owner/page.tsx` | 875 |
| `apps/web/app/page.tsx` | 132 |
| `apps/web/app/providers.tsx` | 545 |
| `apps/web/app/robots.ts` | 182 |
| `apps/web/app/supervisor/page.tsx` | 910 |
| `apps/web/features/auth/AccessDenied.tsx` | 597 |
| `apps/web/features/auth/AuthProvider.tsx` | 4,956 |
| `apps/web/features/auth/LoginWorkspace.tsx` | 6,261 |
| `apps/web/features/driver-test/DriverQaWorkspace.tsx` | 12,123 |
| `apps/web/features/lab/TestLabHome.tsx` | 4,418 |
| `apps/web/features/owner/catalogs.ts` | 1,949 |
| `apps/web/features/owner/FleetAmbientScene.tsx` | 2,395 |
| `apps/web/features/owner/Maintenance.tsx` | 36,558 |
| `apps/web/features/owner/OwnerManagement.tsx` | 52,994 |
| `apps/web/features/owner/OwnerOperations.tsx` | 23,399 |
| `apps/web/features/owner/OwnerRelationshipManager.tsx` | 38,181 |
| `apps/web/features/owner/OwnerRelationshipWizard.tsx` | 28,975 |
| `apps/web/features/owner/OwnerUi.tsx` | 5,562 |
| `apps/web/features/owner/OwnerWorkspace.tsx` | 14,705 |
| `apps/web/features/owner/ReportTemplates.tsx` | 11,988 |
| `apps/web/features/shared/EvidenceViewer.tsx` | 1,536 |
| `apps/web/features/shared/Ui.tsx` | 1,878 |
| `apps/web/features/supervisor/SupervisorWorkspace.tsx` | 20,680 |
| `apps/web/lib/api/client.ts` | 3,744 |
| `apps/web/lib/auth/config.ts` | 652 |
| `apps/web/lib/types.ts` | 13,788 |
| `apps/web/next.config.ts` | 990 |
| `apps/web/package-lock.json` | 280,765 |
| `apps/web/package.json` | 872 |
| `apps/web/tsconfig.json` | 641 |

### marketing

| Source path | Logical bytes |
| --- | ---: |
| `apps/marketing/app/contact/page.tsx` | 2,185 |
| `apps/marketing/app/features/page.tsx` | 5,468 |
| `apps/marketing/app/health/route.ts` | 239 |
| `apps/marketing/app/how-it-works/page.tsx` | 3,399 |
| `apps/marketing/app/icon.svg` | 414 |
| `apps/marketing/app/layout.tsx` | 2,510 |
| `apps/marketing/app/manifest.ts` | 421 |
| `apps/marketing/app/marketing.css` | 66,745 |
| `apps/marketing/app/opengraph-image.tsx` | 2,045 |
| `apps/marketing/app/page.tsx` | 14,945 |
| `apps/marketing/app/pricing/page.tsx` | 4,846 |
| `apps/marketing/app/privacy/page.tsx` | 5,007 |
| `apps/marketing/app/public/leads/route.ts` | 3,899 |
| `apps/marketing/app/robots.ts` | 346 |
| `apps/marketing/app/sitemap.ts` | 410 |
| `apps/marketing/app/solutions/page.tsx` | 4,749 |
| `apps/marketing/components/ContactForm.tsx` | 8,384 |
| `apps/marketing/components/content.ts` | 2,625 |
| `apps/marketing/components/MarketingChrome.tsx` | 3,276 |
| `apps/marketing/components/MarketingUi.tsx` | 8,367 |
| `apps/marketing/lib/leads.ts` | 4,945 |
| `apps/marketing/next.config.ts` | 954 |
| `apps/marketing/package-lock.json` | 276,168 |
| `apps/marketing/package.json` | 962 |
| `apps/marketing/public/brand/fleet-ai-systems-logo.svg` | 827 |
| `apps/marketing/public/brand/fleet-ai-systems-mark.svg` | 592 |
| `apps/marketing/public/product/driver-operations.png` | 112,694 |
| `apps/marketing/public/product/driver-start-duty.png` | 127,356 |
| `apps/marketing/public/product/maintenance-review.png` | 89,645 |
| `apps/marketing/public/product/owner-operations.png` | 276,138 |
| `apps/marketing/public/product/supervisor-review.png` | 106,498 |
| `apps/marketing/tsconfig.json` | 582 |
