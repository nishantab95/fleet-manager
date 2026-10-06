# Overnight future foundations — 2026-10-06

## Status

PASS. All six foundations are present, all six flags default to false, and no
new feature is visible in current navigation. No commit, push, deployment,
remote database operation, APK build/publication, Play Store action, real
provider call, Android permission, or current Driver/Supervisor/Owner workflow
activation occurred.

Starting commit: `fd2e4ecdef91146de7b946e2ff471fac8a11b9ab` on `main`.

## What was built

- A typed, server-authoritative `FeatureRegistry` covering maintenance, asset
  documents, notifications, telematics, fuel integrations, and toll/expenses.
- Owner-only, tenant-scoped maintenance schedule and service-record APIs with
  KM/HMR/date validation, calculated next-due values, audit events, and
  append-only record history.
- Owner-only, tenant-scoped asset-document APIs with private uploads, stable
  document identity, append-only replacement revisions, explicit warning-day
  policy, deterministic expiry calculation, and private authorized download.
- Provider-independent notification contracts with recipient tenancy,
  idempotency, disabled/null behavior, provider-failure isolation, delivery
  status, and route-neutral deep-link metadata.
- Vendor-neutral telematics contracts with company/asset mapping and normalized
  position validation. Only fake providers are used in tests.
- Fuel-provider transaction contracts and explicit deterministic litre
  reconciliation (`MATCHED`, `WITHIN_TOLERANCE`, `MISMATCH`, and
  `INSUFFICIENT_DATA`). No result is labelled fraud or theft.
- Vendor-neutral external expense transaction contracts for toll, parking,
  fuel, repair, Site expense, and other categories, with explicit external-ID
  idempotency and tenant mapping.

## What is real and persisted

Migration `0018_future_foundations` adds:

- `maintenance_schedules`
- `maintenance_records`
- `asset_documents`
- `asset_document_revisions`
- composite `(company_id, id)` uniqueness on `evidence_objects`, allowing
  tenant-consistent document revision references
- `maintenance_basis_enum` and `maintenance_schedule_status_enum`

Maintenance schedules and records, asset-document metadata/revisions, audit
events, and existing private evidence metadata are real PostgreSQL records.

## What is contract-only

Notifications, telematics, fuel-provider import/reconciliation, and
toll/expense import are typed domain contracts only. They have no production
tables, scheduled jobs, credentials, active API routes, or current-workflow
hooks. Their in-memory coordinators/importers exist for deterministic contract
tests, not as durable production queues or ledgers.

## What is feature-gated

| Module | Flag | Default | Persistence | Visible UI |
| --- | --- | --- | --- | --- |
| Maintenance | `FLEET_MAINTENANCE_ENABLED` | `false` | Yes | No |
| Asset documents | `FLEET_ASSET_DOCUMENTS_ENABLED` | `false` | Yes | No |
| Notifications | `FLEET_NOTIFICATIONS_ENABLED` | `false` | No | No |
| Telematics | `FLEET_TELEMATICS_ENABLED` | `false` | No | No |
| Fuel integrations | `FLEET_FUEL_INTEGRATIONS_ENABLED` | `false` | No | No |
| Toll/expenses | `FLEET_TOLL_EXPENSES_ENABLED` | `false` | No | No |

No environment name auto-enables a feature. When a persisted module is
disabled, an authenticated request receives HTTP 404 with
`FEATURE_UNAVAILABLE`; no mutation occurs. When enabled, normal authentication,
`OWNER_ADMIN` RBAC, and authenticated-company scoping still apply.

## What is not activated

- No Owner, Supervisor, or Driver navigation was changed.
- No active business workflow emits notifications.
- No GPS/location collection, map page, geofence creation, Android permission,
  or foreground service exists.
- No SMS, push, email, telematics, fuel, FASTag, bank, payment, or accounting
  provider is connected.
- Existing Diesel entry and approval/reporting remain authoritative and
  unchanged.
- Flutter was not modified.

## New Owner API endpoints

All endpoints below require the relevant feature flag and authenticated
`OWNER_ADMIN` role. Company scope is derived from the session.

Maintenance:

- `GET /api/v1/owner/maintenance/schedules`
- `POST /api/v1/owner/maintenance/schedules`
- `GET /api/v1/owner/maintenance/schedules/{schedule_id}/records`
- `POST /api/v1/owner/maintenance/schedules/{schedule_id}/records`

Asset documents:

- `POST /api/v1/owner/asset-documents/evidence`
- `GET /api/v1/owner/asset-documents`
- `POST /api/v1/owner/asset-documents`
- `GET /api/v1/owner/asset-documents/{document_id}/revisions`
- `POST /api/v1/owner/asset-documents/{document_id}/revisions`
- `GET /api/v1/owner/asset-documents/{document_id}/file`

Notifications, telematics, fuel, and toll/expenses intentionally expose no API
endpoint yet.

## Security notes

- Maintenance and document foreign references use composite company foreign
  keys, and all service lookups include the authenticated company.
- Driver and Supervisor sessions receive `403` on enabled Owner endpoints.
- Foreign asset/document/schedule identifiers produce tenant-scoped `404`
  responses.
- Document uploads reuse the existing private `ObjectStorage` and
  `EvidenceObject` abstractions. Bytes are size-, MIME-, and magic-signature
  checked; PDF and the existing image formats are allowed.
- Object keys are generated by the server. Uploaded filenames are ignored.
- Document APIs never expose object keys or public URLs, and download responses
  use `private, no-store`.
- No provider secrets, production shortcuts, public evidence URLs, API keys,
  or `verify=False` were added.

## Baseline CI hygiene

The initial baseline had no Ruff lint or mypy errors, but `ruff format --check`
reported 30 pre-existing unformatted backend files. Ruff formatting was applied
as required. The final Ruff lint and formatting checks pass. Most of that batch
is formatting-only; functional work in previously unformatted files is limited
to `0011_fleet_assets.py`, `0014_driver_asset_assignments.py`, and
`domain/driver.py`.

The other formatter-only files are:

- migrations `0012`, `0013`, and `0015`
- Owner/Supervisor/Driver-assignment API modules
- auth service and existing deployment/duty/event models
- existing admin, deployment, assignment, owner, and reporting domain modules
- existing admin, deployment, Driver, filesystem-storage, fleet-asset, health,
  Owner-asset, and Owner-People/Sites tests

## Migration verification

- Dedicated local database only:
  `postgresql+psycopg://fleet:fleet@127.0.0.1:5432/fleet_test`
- `alembic upgrade head`: PASS
- `alembic check`: PASS (`No new upgrade operations detected`)
- `alembic upgrade head --sql`: PASS
- Full pytest migration setup/teardown: PASS

Offline SQL generation exposed old live-query assumptions in migrations
`0011`, `0014`, and `0016`. Their online behavior was preserved; deterministic
offline branches now emit code backfill, assignment validation, and built-in
report-template seeding SQL.

## Test results

- Backend Ruff lint: PASS
- Backend Ruff format check: PASS
- Backend mypy: PASS, 74 source files
- Backend pytest: PASS, 166 tests
- Focused future-foundation subset: PASS, 15 tests (included in the 166)
- Alembic online upgrade/check/offline SQL: PASS
- Web ESLint: PASS
- Web TypeScript: PASS
- Web Vitest: PASS, 34 tests in 12 files
- Web production build: PASS
- Flutter: NOT TOUCHED; no Flutter command was required
- `git diff --check`: PASS

Warnings observed are existing Starlette `BlockingPortal`, Alembic
`path_separator`, and SQLAlchemy cyclic-FK sorting warnings; no test failed.

## Known limitations

- Maintenance currently models schedules and records, not work orders, vendors,
  parts, costs, reminders, or automatic actions. One schedule has one basis;
  combined meter/date policies can be represented as separate schedules.
- Asset document types are safe normalized company-defined strings. There is no
  applicability matrix or required-document catalog yet, so `MISSING` is domain
  vocabulary but not automatically derived for absent requirements.
- Document uploads have signature validation but no malware scanning/content
  inspection.
- The four contract-only modules need durable repositories, provider-specific
  adapters, operational retry policy, and reviewed APIs before activation.
- No hidden web pages were added; manual review uses API clients/tests only.

## Morning manual test plan

Use only a local/test environment and return each flag to `false` after its
check.

1. Confirm all six flags are absent or `false`; open Driver, Supervisor, and
   Owner applications and verify navigation is unchanged.
2. Set only `FLEET_MAINTENANCE_ENABLED=true`, restart the local API, create a
   Tipper KM schedule and machinery HMR schedule, reject the wrong basis for
   each, add two records, confirm both remain in history, attempt Tenant B and
   Driver/Supervisor access, then disable the flag.
3. Set only `FLEET_ASSET_DOCUMENTS_ENABLED=true`, upload a test image/PDF,
   create a document, replace it, confirm both revisions and expiry status,
   fetch the private file as Owner, deny another role/tenant, then disable the
   flag.
4. Enable notifications only in a unit/local harness, use the null/fake
   provider, retry the same idempotency key, simulate provider failure, verify
   no active workflow emitted anything, then disable it.
5. Enable telematics only in a unit/local harness, use the fake provider,
   validate a position and wrong-company mapping, and confirm Android location
   permissions remain unchanged; then disable it.
6. Enable fuel integrations only in a unit/local harness, submit fake external
   transactions, verify duplicate handling and the explicit tolerance results,
   and confirm Driver Diesel data/reports are unchanged; then disable it.
7. Enable toll/expenses only in a unit/local harness, submit fake transactions,
   verify amount/currency/mapping/idempotency rules, and confirm Owner reports
   are unchanged; then disable it.
8. Re-run Ruff, mypy, pytest, Alembic checks, web checks, and `git diff --check`.

## How to enable later

For local review, set exactly one `FLEET_*_ENABLED=true` value in the untracked
local `.env`, restart the API, and authenticate as an Owner. Maintenance and
asset documents then expose the endpoints above. The other flags only permit
their domain coordinators; a later reviewed phase must add durable adapters/API
surfaces before any production use. Never use a client/UI flag as authorization.

## How to roll back these local changes

The starting worktree was clean and nothing was committed. First preserve a
patch if desired with `git diff` and copy the untracked new files. After owner
review, tracked changes can be discarded with `git restore -- .`; inspect
untracked paths with `git clean -nd` and delete only the files listed in this
report (or use a reviewed, path-specific `git clean`). Do not use a broad clean
command if any unrelated untracked work has appeared since this run.
