# Safe change workflows

[Development index](index.md) · [Documentation home](../index.md)

## Before changing an existing feature

Read the [project rules](../../PROJECT_RULES.md), the relevant
[architecture/domain guides](../architecture/index.md), and the existing feature's
implementation and tests. Follow one real request from UI through transport,
authorization, domain service, and persistence before choosing an edit location.
Inspect Git status and recent verification evidence; preserve unrelated changes.

State the smallest requested behavior change, affected clients, schema/auth/offline
impact, tests, and release channel. Work on the existing `main` branch. Do not
combine a feature or bug fix with unrelated module splits, dependency upgrades,
renaming, or business-logic rewrites. An identified design problem can be recorded
for a separately approved, tested change.

## Source map

Paths are current entry points, not a requirement to change every listed layer.

| Area | Source entry points | Existing checks |
| --- | --- | --- |
| Flutter Driver and offline data | [app.dart](../../apps/mobile/lib/app.dart), [Driver models](../../apps/mobile/lib/domain/driver_models.dart), [data layer](../../apps/mobile/lib/data/) | [Mobile tests](../../apps/mobile/test/) |
| Owner/Supervisor browser | [features](../../apps/web/features/), [API client](../../apps/web/lib/api/client.ts), [route shells](../../apps/web/app/) | Colocated feature tests and [browser scenarios](../../apps/web/e2e/) |
| FastAPI transport and business rules | [API routes/schemas](../../services/api/src/fleet_api/api/), [domain services](../../services/api/src/fleet_api/domain/), [dependencies](../../services/api/src/fleet_api/api/dependencies.py) | [Backend tests](../../services/api/tests/) |
| Database | [SQLAlchemy models](../../services/api/src/fleet_api/db/models/), [Alembic revisions](../../services/api/migrations/versions/) | [Migration/history regressions](../../services/api/tests/test_fleet_asset_migration.py) |
| Authentication | [Backend auth](../../services/api/src/fleet_api/auth/), [mobile auth](../../apps/mobile/lib/auth/), [browser auth](../../apps/web/features/auth/) | [Company-PIN tests](../../services/api/tests/test_company_pin_auth.py), mobile/browser auth tests |
| Public website | [Marketing app](../../apps/marketing/), [package commands](../../apps/marketing/package.json) | Colocated tests and [marketing E2E](../../apps/marketing/e2e/) |
| Deployment and distribution | [Production configuration](../../infra/production/), [server scripts](../../scripts/production/), [Actions](../../.github/workflows/) | [Deployment-control tests](../../scripts/test_production_deploy.py), [AAB validation tests](../../scripts/test_validate_play_aab.py) |

## 1. Flutter Driver change

Trace the existing action through `app.dart`,
[ApiClient](../../apps/mobile/lib/data/api_client.dart),
[SyncEngine](../../apps/mobile/lib/data/sync_engine.dart), and
[LocalDatabase](../../apps/mobile/lib/data/local_database.dart). Reuse capability,
assignment, duty-state, and private-evidence rules. Persist event UUID and payload
before networking; retries must reuse that UUID and retain photographs.

Add the smallest widget/domain regression, plus affected
[cold-restart](../../apps/mobile/test/cold_restart_offline_test.dart),
[sync-recovery](../../apps/mobile/test/sync_recovery_test.dart), or
[handover](../../apps/mobile/test/device_handover_test.dart) cases. A local schema
change needs an upgrade test preserving existing queue rows and file references;
do not hand-edit generated `local_database.g.dart`. Android binary changes need
the separate Play release/real-device checks, not a backend-only deployment.

## 2. Owner or Supervisor change

Inspect the matching `features/owner` or `features/supervisor` flow and its
backend endpoint. Keep browser access tokens in the existing auth boundary and
use the shared client/proxy; hiding a control is not authorization. Mobile
Owner/Supervisor behavior lives separately in
[role_screens.dart](../../apps/mobile/lib/role_screens.dart) and the existing
Owner-specific mobile files; assess it when a shared API changes.

Extend colocated component tests and relevant Playwright scenarios. For access or
workflow changes, add backend role/tenant/site-scope assertions too. Owner and
Supervisor share one web artifact delivered through the tested server release;
an Android UI change requires a new Android artifact.

## 3. FastAPI endpoint change

Start with the neighboring route, [schemas](../../services/api/src/fleet_api/api/schemas.py),
and domain service. Preserve `/api/v1` contracts and existing error semantics;
keep domain rules out of route handlers. Derive company/membership from the
authenticated context, never from an untrusted client identifier.

Test permitted calls, wrong role/company/device/assignment, invalid input, and
repeat requests where idempotency applies. Review both Flutter and browser
consumers. Prefer compatible additive changes while installed mobile versions
remain in use; document a staged client/server transition before removing fields.

## 4. Database migration

Inspect current Alembic heads, model constraints, existing revisions, and the
affected record lifecycle. Add a new revision when needed; never rewrite applied
history. Preserve company ownership, historical assignments, event UUIDs,
memberships, devices, evidence keys, and audit records. Backfills must reject
ambiguous data instead of inventing relationships.

Use a disposable, explicitly selected test database to verify fresh installation,
upgrade from the previous schema with representative existing rows, and model
agreement. The [test fixture](../../services/api/tests/conftest.py) requires a
database name containing `test`, but that name alone is not proof that its data
is disposable. Never aim destructive migration tests at Pilot or production.
Review forward compatibility with the previous application image and update the
[migration/rollback plan](../production-migration-and-rollback.md); application
rollback does not imply a safe schema downgrade.

## 5. Report or workbook change

Trace [reporting](../../services/api/src/fleet_api/domain/reporting.py),
[report templates](../../services/api/src/fleet_api/domain/report_templates.py),
and the related [report routes](../../services/api/src/fleet_api/api/reports.py).
Reuse backend calculations for JSON and workbook exports. Preserve verified-data
filters, historical assignments, company timezone/day boundaries, zero/missing
denominators, and role-scoped evidence links. Recorded diesel is not measured
fuel consumption.

Extend [report API](../../services/api/tests/test_reports_api.py),
[metric](../../services/api/tests/test_reporting_metrics.py), and affected
[template](../../services/api/tests/test_report_templates_api.py) tests, including
workbook cells/totals and access denial. Check browser labels/download behavior
when the returned contract changes.

## 6. Bug fix

Reproduce the failure with minimal non-sensitive fixtures and add a regression
that fails for the actual defect. Trace the cause before editing, fix the narrow
boundary, then run affected tests and neighboring integration checks. Do not
delete failing assertions, hide exceptions, or reset real data to obtain a PASS.
Record what was verified, what was reused from prior evidence, and what remains
unverified. Choose the release channel from changed runtime code, not the bug's
screen location alone.

## 7. Authentication or security change

Production remains `FLEET_AUTH_MODE=company_pin`: owner-issued expiring/single-use
activation and the existing PIN/device/session mechanism. Inspect
[company_pin.py](../../services/api/src/fleet_api/auth/company_pin.py) and
[auth service](../../services/api/src/fleet_api/auth/service.py) before editing.
Do not replace it with SMS/Firebase login or weaken tenant, role, device, or
assignment checks. Existing optional Firebase compatibility must not be removed
without evidence that doing so is safe.

Cover expiration/replay, hashed secrets, PIN lockout, device binding, refresh,
logout, owner reset/reactivation, and offline-data preservation as affected.
Include [safe logging regressions](../../services/api/tests/test_structured_logging.py)
for secret-bearing failures. Update [security guidance](../security.md) and
[data handling](../production-data-handling.md) when the boundary changes; never
place tokens, PINs, activation codes, signing secrets, or real driver data in logs.

## 8. Cloud deployment change

Inspect Compose, Caddy, the affected server script, and both build/approval
workflows. Keep only intended HTTPS routing public; database, evidence storage,
and admin surfaces remain private. Routine deployment must not reconcile
established PostgreSQL/MinIO services, bypass previous-version backup/restore
verification, or perform destructive schema rollback.

Run affected deployment-control regressions, shell/Actions/configuration checks,
and the documented isolated local smoke/restore checks when behavior changes.
Inspect test cleanup first: do not invoke a harness that deletes Docker volumes
or protected state under a task that forbids those operations. Use a reviewed
isolated procedure and report any unexecuted checks instead. The current local
smoke helper retains its uniquely named project volumes and artifacts and stops
only its validated test containers; follow [manual maintenance](../operations/local-maintenance.md)
for separately approved retirement, never blanket cleanup.
Use [deployment](../production-deployment.md),
[operations](../production-operations.md), and
[rollback](../production-migration-and-rollback.md) as the command authority.
Do not run those commands against a VPS or change DNS during local preparation.
Server/web releases require exact-SHA CI and explicit protected-environment
approval; a push alone never deploys.

## 9. Google Play release

Read the [Play release guide](../google-play-release.md) and audited package/
certificate identities before touching Android release configuration. Use
[build-play-aab.ps1](../../scripts/build-play-aab.ps1) and
[validate_play_aab.py](../../scripts/validate_play_aab.py), with owner-controlled
signing inputs outside the checkout. Preserve the permanent Pilot key and both
existing package IDs; changing identity requires reporting migration consequences
before making the change.

Run [update-contract tests](../../scripts/test_mobile_update_contract.py), AAB
validator tests, relevant Flutter checks, and signed-artifact/device acceptance.
Play must use `https://api.fleetaisystems.com` and `company_pin`, without private
APK sideload updates. Distinct Pilot/Play packages require controlled queue/photo
drain and reactivation against existing driver records, not an in-place update.
Missing signing/Console/device access is a blocker; compilation is not proof of
a signed or published production release. Publishing needs separate approval.

## Verification commands and scope

Select relevant tests first; broaden checks when shared contracts change. The
following command names exist in the checked-in tool configuration. Run each
from its component directory with the documented local environment, not from
an arbitrary parent directory that may load a different `.env`.

| Working directory | Commands / selection |
| --- | --- |
| `services/api` | `.venv\Scripts\python.exe -m pytest tests/test_driver_api.py -q` (choose affected tests); `.venv\Scripts\python.exe -m ruff check src tests`; `.venv\Scripts\python.exe -m mypy src tests` |
| `apps/mobile` | `flutter test test/cold_restart_offline_test.dart` (choose affected tests); `flutter analyze`; `dart format --output=none --set-exit-if-changed lib test` |
| `apps/web` or `apps/marketing` | `npm test -- <existing-test-path>`; `npm run lint`; `npm run typecheck`; `npm run build`; `npm run test:e2e` with the component's Playwright setup |

The broader Windows entry point is [scripts/test.ps1](../../scripts/test.ps1).
Release checks additionally follow the existing release guides and
[CI workflow](../../.github/workflows/ci.yml). Report skips, unavailable databases,
tool permissions, and missing credentials explicitly. Do not rerun unchanged
successful builds merely for documentation edits, or call historical results a
new verification run.

## Documentation maintenance policy

Update documentation with the behavior change: implementation and regression
tests, schema/migration notes, API/client compatibility, configuration examples,
and affected operational/release runbooks must agree. Update the appropriate
section index when adding a guide. Keep one authoritative procedure and link
to it instead of copying commands into multiple competing guides.

Create an [ADR](../adr/README.md) only for a meaningful architectural or security
decision, with the next unused ID, rationale, alternatives, scope, and explicit
supersession. Routine fixes do not need a ceremonial ADR. Preserve historical
decisions and acceptance reports; label obsolete scope or supersession without
inventing dates/results or deleting context. Reconcile conflicting current
instructions before handing off, and validate changed relative links/source paths.
