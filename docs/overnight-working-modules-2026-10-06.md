# Overnight working modules — 2026-10-06

## Outcome

OVERNIGHT STATUS: **PARTIAL**

Substantial high-priority working modules are implemented behind flags:
maintenance, compliance/documents, durable in-app notifications, simulated
telematics, fuel CSV reconciliation, per-asset multi-meter support,
multi-trigger maintenance, workforce/payroll, and attendance-location backend
corroboration. The exceptions and UI boundaries are itemized below.
Toll/expense remains contract-only. The current mobile Pilot was deliberately
not changed to add multi-meter or phone-location UI/permissions.

Starting commit: `fd2e4ecdef91146de7b946e2ff471fac8a11b9ab` on `main`.
All changes remain uncommitted.

## Acceptance summary

| Area | Status | Evidence / boundary |
| --- | --- | --- |
| Historical migration safety | PASS | Existing online semantics preserved; additive work is in 0018, 0019, and 0020. |
| Fresh DB → head | PASS | Dedicated local `fleet_fresh_test`. |
| 0017 → 0019 → 0020 | PASS | Dedicated local `fleet_upgrade_test`. |
| Offline SQL generation/application | PASS | Generated full SQL applied to empty `fleet_offline_test`. |
| Schema equivalence | PASS | Online/offline dumps: 2,906 lines each, zero differences. |
| Backend | PASS | Ruff, Ruff format, mypy, and 178 tests. |
| Web | PASS | ESLint, TypeScript, 36 Vitest tests, production build, 3 Playwright tests. |
| Mobile compatibility | PASS | Flutter analyze and 112 tests; no mobile source changes. |
| Full requested product scope | PARTIAL | Toll/expense, portions of fuel reconciliation, mobile location lab, maintenance attachment HTTP/UI, and live-database browser E2E remain. |

## Feature flags

All defaults in `.env.example` are `false`:

| Module | Flag |
| --- | --- |
| Maintenance | `FLEET_MAINTENANCE_ENABLED` |
| Asset compliance | `FLEET_ASSET_DOCUMENTS_ENABLED` |
| In-app notifications | `FLEET_NOTIFICATIONS_ENABLED` |
| Telematics | `FLEET_TELEMATICS_ENABLED` |
| Fuel reconciliation | `FLEET_FUEL_INTEGRATIONS_ENABLED` |
| Toll/expense contract | `FLEET_TOLL_EXPENSES_ENABLED` |
| Per-asset/dual meters | `FLEET_MULTI_METER_ENABLED` |
| Workforce/payroll | `FLEET_PAYROLL_ENABLED` |
| Attendance location | `FLEET_ATTENDANCE_LOCATION_ENABLED` |

Flags control visibility and availability, not authorization. Owner APIs still
require `OWNER_ADMIN`; Driver location/meter-capture APIs require `DRIVER`.
Company identity always comes from the authenticated session.

## Database changes

- `0018_future_foundations.py`: schedules/records, asset documents/revisions,
  and tenant-safe evidence relationships.
- `0019_working_future_modules.py`: work orders/attachments, document policies,
  notifications, telematics mappings/positions/geofences/transitions, fuel
  imports/reconciliation, audit and query indexes.
- `0020_multi_meter_workforce_location.py` (revision
  `0020_multi_meter_workforce`): asset meter flags, capture grouping,
  multi-trigger criteria, completion meter fields, telemetry engine
  hours/voltage/discrepancies, compensation, payroll, and attendance location.

Existing assets receive safe type-based capability defaults; legacy schedule
columns remain. Existing schedules are backfilled with one matching criterion.
No historical KM or HMR value is fabricated.

## Maintenance

STATUS: **PARTIAL** because attachment transport/UI and full-stack browser E2E
are incomplete; the remaining listed maintenance functions pass.

- Schedules: PASS
- KM: PASS
- HMR: PASS
- Date: PASS
- Due engine (`UNKNOWN`, `NOT_DUE`, `DUE_SOON`, `DUE`, `OVERDUE`): PASS
- Work-order lifecycle: PASS
- Immutable service records: PASS
- Attachments: PARTIAL — durable model/domain audit exists; no Owner HTTP/UI
  upload/list/download surface was completed.
- Decimal costs: PASS
- Owner UI: PASS for Overview, Due, Work Orders, Schedules, and History
- Separate Excel export: PASS
- Playwright UI flow: PARTIAL — it passes with mocked Owner API responses, not
  a live local API/database

One schedule may contain odometer, hour-meter, and calendar criteria. Each is
calculated independently and overall status is the highest severity; any one
criterion can make service due. Completion updates only supplied legitimate
meter baselines and always uses the supplied completion date for calendar
criteria.

## Compliance / documents

STATUS: **PARTIAL** under the strict end-to-end definition: the database,
domain, API, private upload/download, Owner UI, export, and automated API/UI
tests pass, but the browser flow uses mocked API responses.

- Per-company applicability policies: PASS
- Required `MISSING` calculation: PASS
- `VALID`, `EXPIRING_SOON`, `EXPIRED`, `MISSING`, `NOT_REQUIRED`, `UNKNOWN`: PASS
- Private PNG/JPEG/PDF upload: PASS
- Append-only replacement/revision history: PASS
- Authorized private download: PASS
- Owner UI and Excel: PASS
- Tenant isolation/RBAC: PASS
- Full-stack browser E2E: PARTIAL

## Notifications

STATUS: **PARTIAL** under the strict end-to-end definition because its browser
coverage uses mocked Owner API responses.

- Durable in-app notification/recipient state: YES
- Maintenance alerts: PASS
- Missing/expiring/expired document alerts: PASS
- Idempotent deduplication: PASS
- Read/unread and mark-all-read: PASS
- Owner bell/drawer/deep link: PASS
- External push/SMS/email: NO

Evaluation is synchronous and deterministic on refresh/mutation; there is no
Celery/Redis dependency and provider failure cannot roll back the business
mutation.

## Telematics

STATUS: **PARTIAL** under the strict end-to-end definition. The local simulator
and ingestion path are implemented and the API/database behavior is tested,
but the simulator was not run against a live authenticated local server during
this run. A real provider is not connected.

- Durable positions and mapping: PASS
- Circular geofence and Haversine distance: PASS
- ENTER/EXIT and duplicate suppression: PASS
- Out-of-order and stale indication: PASS
- Optional odometer, engine hours, ignition, speed, heading, voltage: PASS
- Manual-vs-telemetry discrepancy rows: PASS
- Owner assets/latest/transitions/meter checks UI: PASS
- Deterministic loopback-only simulator implementation: PASS
- Live authenticated simulator execution: NOT RUN
- Real GPS provider: NO
- Google Maps/API key: NO

The simulator sends outside → approaching → inside → inside → leaving →
outside through the real ingestion API. Reusing `--run-id` proves provider
idempotency. Telemetry never overwrites Supervisor-verified manual readings.
Current explicit comparison tolerances are 5.00 km and 1.00 engine hour.

## Fuel

STATUS: **PARTIAL**. Durable import/reconciliation, Owner UI, exports, and core
matching behavior work, but the complete requested CSV metadata and manual
match/unmatch workflow were not finished.

- Durable external transactions and batches: PASS
- Strict UTF-8 CSV import, 5 MB cap, exact headers: PASS
- Asset mapping without ambiguous guessing: PASS
- Duplicate row state: PASS
- Exact/tolerance/mismatch/insufficient-data reconciliation: PASS
- Manual reasoned review resolution and audit: PASS
- Manual pair/re-pair/unmatch: FAIL
- Owner tables/upload/export: PASS
- Excel formula-injection protection: PASS
- Optional amount/station/reference CSV fields: FAIL
- Explicit unmatched-Driver reconciliation rows: FAIL
- Real bunk/card provider: NO

Published CSV columns, in exact order:

```text
external_transaction_id,occurred_at,litres,asset_identifier,source_type
```

Timestamps require an offset. `asset_identifier` must uniquely match canonical
asset code or normalized registration. Supported source types include
`BUNK_DISPENSER`, `FUEL_CARD`, `TANK_SENSOR`, `SUPPLIER`, and `OTHER`.
The requested `amount`, `station`, and `reference` metadata are not accepted by
this version of the importer.

## Expense / FASTag

STATUS: **PARTIAL**

- Typed provider-neutral validation/idempotency foundation: PASS
- Durable persistence: FAIL
- CSV API: FAIL
- Owner UI: FAIL
- Excel: FAIL
- Real FASTag provider: NO

The planned provider-neutral expense CSV contract is
`transaction_id,asset_identifier,occurred_at,amount,merchant,category,reference`;
there is no working importer behind that contract.

No working expense module is claimed.

## Multi-meter

STATUS: **PARTIAL** because the backend capability/capture/reporting flow works,
but Driver Pilot capture UI and Supervisor grouped rendering were not added.

- Asset capability model: PASS
- Odometer-only: PASS
- Hour-meter-only: PASS
- Dual-meter: PASS
- Neither configured: PASS (Owner edit rejects an invalid all-off edit; legacy
  unknown records continue through safe type fallback)
- Driver capture API: PASS
- Driver Pilot UI: PARTIAL — legacy Pilot stays unchanged; no new primary
  buttons were added.
- Atomic paired capture and stable retry IDs: PASS
- Supervisor grouped display: PARTIAL — the API exposes a shared
  `capture_group_uuid` and both records remain under METER, but the current UI
  still renders the two rows independently.
- Reporting separation (`distance_km`, `machine_hours`, explicit state): PASS

The verified dual-meter flow captured 12,500→12,560 km and
3,000.0→3,008.5 HMR as 60 km and 8.5 operating hours. A 10.5-hour duty with an
8-hour configured standard day independently produced 150 overtime minutes;
HMR did not affect payroll time.

## Maintenance multi-trigger

- KM: PASS
- Hours: PASS
- Calendar: PASS
- KM + HMR + calendar: PASS
- Whichever-first/highest severity: PASS
- Completion resets valid supplied baselines only: PASS
- Unknown meter remains unknown: PASS
- Capability mismatch rejection: PASS

## Workforce / payroll

STATUS: **PARTIAL** under the requested full scope. Operational pay calculation,
review/finalization, Owner UI, and payroll export pass; the detailed attendance
export and mobile location orchestration are incomplete. This is not statutory
payroll.

- Effective-dated non-overlapping salary profiles: PASS
- Monthly salary: PASS (full October ₹25,000 case)
- Daily and hourly bases: PASS
- Duty-session time union without overlap double-counting: PASS
- Open/overlap/missing states: PASS
- Explicit daily OT threshold and rupees/hour rate: PASS
- Decimal money and rounding: PASS
- DRAFT → REVIEWED → FINALIZED: PASS
- Frozen calculation snapshot/history immutability: PASS
- Reasoned positive/negative adjustments before finalization: PASS
- Owner-only RBAC/tenant scoping: PASS
- Owner Workforce tabs: PASS
- Payroll Excel/formula safety: PASS
- Detailed attendance Excel with Site/asset/start/end: FAIL; current Owner table
  and location-evidence table are the review surfaces.
- PF/ESI/TDS/professional tax/payment transfer: NOT IMPLEMENTED by design

The result is labelled Calculated Gross Pay / Draft Payroll, never net salary
or statutory compliance.

## Attendance location

STATUS: **PARTIAL**. The backend snapshot/confidence/privacy system works; the
current mobile Pilot and any isolated lab flavor do not collect snapshots.

- Duty-start source: PASS (backend contract)
- Duty-end source: PASS (backend contract)
- Meter/diesel/trip/emergency event source: PASS (backend contract)
- Site geofence comparison: PASS
- Fresh asset-GPS proximity: PASS
- Stale telemetry exclusion: PASS
- Deterministic confidence engine: PASS
- GPS denied/unavailable/low-accuracy persistence: PASS
- Core operational event survives GPS failure: PASS by decoupled API design
- No automatic payroll penalty: PASS
- Off-duty tracking: NO
- Current mobile automatic capture: NO
- Lab-only mobile implementation: NO

Stored context is company, membership, duty/assignment, asset, Site, optional
event, device/server timestamps, coordinates, accuracy, source, status, and
permission state. The server derives tenant and assignment context. Default
settings are 100 m asset proximity, 900-second freshness, 100 m maximum
accuracy, and 30-day retention; Owners can configure these locally.

## Machinery telematics

STATUS: **PASS** for the normalized backend capability and integration tests.

- Tipper: PASS
- Excavator: PASS
- Backhoe Loader: PASS
- Roller: PASS
- Grader: PASS
- External odometer: PASS
- External engine hours: PASS
- Battery voltage: PASS
- Manual-vs-telemetry reconciliation: PASS

One integration test maps and ingests a zero-speed, ignition-on position for
all five current asset types. Zero speed is not interpreted as an unused
machine.

## Owner API surface

All `/api/v1/owner/*` routes are Owner-only and tenant-derived.

- Maintenance: schedules, criteria, records/history, work orders/lifecycle,
  completion, and `export.xlsx`.
- Compliance: policies, compliance matrix, private evidence, documents,
  revisions, downloads, and `export.xlsx`.
- Notifications: list/evaluate, state changes, and mark-all-read.
- Telematics: mappings, geofences, positions, latest, transitions, and meter
  discrepancies.
- Fuel: template, imports, transactions, reconcile, reasoned resolve, and
  `export.xlsx`.
- Workforce: compensation, attendance, payroll periods/lines/status,
  adjustments, and payroll `export.xlsx`.
- Attendance location: settings, derived snapshots, and retention purge.

Driver-only additive routes are grouped capture at
`POST /api/v1/driver/meter-captures` and event-based location at
`POST /api/v1/driver/attendance-location/snapshots`.

## Index rationale

Indexes target actual lookup shapes: company/status/due date for maintenance,
company/status/scheduled date for work orders, company/expiry for document
revision review, recipient/state/time for notification inboxes, asset/time and
provider event identity for telemetry, asset/time for transitions, source plus
external transaction ID for fuel idempotency, and company/period or
membership/effective dates for workforce. They avoid indexing every payload
field.

## Security review

- Tenant isolation: PASS through authenticated company filters and composite
  foreign keys.
- RBAC: PASS; Owner management, Driver capture, and Supervisor review remain
  separate.
- Private files: PASS for document evidence; server keys and private no-store
  downloads only.
- CSV safety: PASS for strict header, UTF-8, size, row validation, and no path
  use.
- Excel formula injection: PASS for user-controlled exported text.
- Secrets/TLS bypass/public buckets: NONE ADDED.
- Location privacy: event snapshots only; no covert/background collection.

## Automated verification

Final verified gates:

- Ruff check: PASS
- Ruff format check: PASS
- mypy: PASS (82 source files)
- pytest: PASS (178 tests)
- Alembic fresh/upgrade/check/offline/equivalence: PASS
- ESLint: PASS
- TypeScript: PASS
- Vitest: PASS (36 tests in 13 files)
- Next production build: PASS
- Playwright Owner: PASS (3 tests)
- Flutter analyze: PASS
- Flutter test: PASS (112 tests)
- Android location-permission search: no matches
- `git diff --check`: PASS

The Playwright suite uses the repository's mocked Owner API interception. The
real API/domain/database paths are covered by PostgreSQL integration tests and
the local demo scripts; a non-mocked browser/database suite remains follow-up.

## Morning local test procedure

Work only against local PostgreSQL/MinIO. Do not copy these values to a remote
Pilot environment.

1. In the untracked local `.env`, set:

   ```dotenv
   FLEET_ENVIRONMENT=development
   FLEET_MAINTENANCE_ENABLED=true
   FLEET_ASSET_DOCUMENTS_ENABLED=true
   FLEET_NOTIFICATIONS_ENABLED=true
   FLEET_TELEMATICS_ENABLED=true
   FLEET_FUEL_INTEGRATIONS_ENABLED=true
   FLEET_TOLL_EXPENSES_ENABLED=false
   FLEET_MULTI_METER_ENABLED=true
   FLEET_PAYROLL_ENABLED=true
   FLEET_ATTENDANCE_LOCATION_ENABLED=true
   FLEET_OBJECT_STORAGE_PROVIDER=s3
   ```

2. Start the existing local stack and apply migrations:

   ```powershell
   .\scripts\dev.ps1
   Push-Location services/api
   .\.venv\Scripts\python.exe -m alembic upgrade head
   Pop-Location
   ```

3. Sign in locally as Owner, then copy the short-lived Bearer access token from
   an authenticated browser Network request. Keep it in the current shell only:

   ```powershell
   $env:FLEET_DEMO_OWNER_TOKEN="<local-owner-access-token>"
   .\services\api\.venv\Scripts\python.exe .\scripts\seed_future_modules_demo.py
   ```

   The script refuses production mode and non-loopback API URLs. It creates or
   reuses three Sites, ten tippers, six machinery assets, deployments, available
   Driver assignments, maintenance states, compliance policies/documents,
   telematics mappings/geofences, fuel rows, compensation profiles, a draft
   payroll period, attendance settings, and evaluated notifications.

4. Copy the printed mapping command and run it, retaining the same token:

   ```powershell
   .\services\api\.venv\Scripts\python.exe .\scripts\telematics_simulator.py `
     --mapping-id <printed-mapping-id> `
     --site-latitude 12.971600 `
     --site-longitude 77.594600
   ```

5. In Owner web, verify Maintenance create/complete/history, Compliance
   upload/replace/history, notification read/deep link, Telematics ENTER/EXIT
   and meter checks, Fuel reconciliation/manual reason, asset meter settings,
   Workforce compensation/attendance/overtime/draft-review-finalize/export.

6. Reset local demo data with the existing reviewed local reset workflow when
   desired. The seeder is idempotent for named Sites/assets, schedules,
   policies, mappings, profiles, and the current-month payroll period; fuel
   reimports appear explicitly as duplicates.

7. Return every flag to `false`, remove the shell token, and restart:

   ```powershell
   Remove-Item Env:FLEET_DEMO_OWNER_TOKEN -ErrorAction SilentlyContinue
   ```

   ```dotenv
   FLEET_MAINTENANCE_ENABLED=false
   FLEET_ASSET_DOCUMENTS_ENABLED=false
   FLEET_NOTIFICATIONS_ENABLED=false
   FLEET_TELEMATICS_ENABLED=false
   FLEET_FUEL_INTEGRATIONS_ENABLED=false
   FLEET_TOLL_EXPENSES_ENABLED=false
   FLEET_MULTI_METER_ENABLED=false
   FLEET_PAYROLL_ENABLED=false
   FLEET_ATTENDANCE_LOCATION_ENABLED=false
   ```

## Known limitations

- Toll/FASTag/expense persistence, API, UI, and export are not built.
- Maintenance attachment persistence/domain logic exists, but its upload/list/
  download API and Owner UI are not exposed.
- The current Flutter Pilot has neither dual-meter capture UI nor attendance
  location collection. This preserves the mandated Pilot safety boundary.
- Attendance daily rows currently summarize duty and overtime; detailed
  Site/asset/start/end attendance Excel is not implemented.
- Location snapshots are submitted independently after operational events;
  there is no mobile orchestration in this worktree.
- Notification evaluation is request-driven, not scheduled.
- There is no malware scanning beyond size/MIME/magic-signature checks.
- Telematics/fuel scripts are simulators/importers, not vendor integrations.
- The demo seeder and telematics simulator compile and expose valid CLI help,
  but were not run against a live authenticated local API in this session.
- Playwright intercepts API calls; true full-stack browser E2E remains.

## Mobile safety

- CURRENT PILOT LOCATION PERMISSION ADDED: **NO**
- PRODUCTION LOCATION PERMISSION ADDED: **NO**
- LAB-ONLY LOCATION IMPLEMENTATION: **NO**
- BACKGROUND LOCATION: **NO**
- CURRENT PILOT BEHAVIOR WITH FLAGS OFF: **UNCHANGED**

## Confirmations

- NO COMMIT
- NO PUSH
- NO DEPLOYMENT
- NO SERVER UPDATE
- NO REMOTE DATABASE CHANGE
- NO APK BUILD OR PUBLICATION
- NO PLAY STORE ACTION
- NO REAL GPS OR MAP PROVIDER
- NO PUSH/SMS PROVIDER
- NO REAL BUNK OR FASTAG PROVIDER
- EXISTING OVERNIGHT WORK PRESERVED: YES
- ALL FUTURE FEATURE FLAGS DEFAULT FALSE: YES
