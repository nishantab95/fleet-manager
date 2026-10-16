# Production engineering audit

Audit date: 2026-10-16. Scope: the existing `main` working tree prepared for one
Linux VPS, two PC users and thirty Android drivers. This is a source and local
verification assessment, not a penetration-test certificate or approval to
deploy. The authoritative release decision and exact final revision are in
[the readiness report](production-readiness-report.md). Start documentation
navigation at [the index](index.md).

Evidence boundary: the original sections below, through "Safe next maintenance
sequence", record the earlier production preparation at implementation commit
`789dd878ec7dc5880899f520f24246463983d81c` and report follow-up
`06ecbc457d7e2fc0795310636fea0064f47ab0ff`. Their phrases "this task" and their
test/build counts refer to that earlier work, not fresh application checks in
the subsequent repository audit. The dated re-audit appendix records the new
read-only assessment separately.

## Assessment and method

**Engineering status: PARTIAL.** The reviewed architecture, transaction
boundaries, offline contracts and local regressions support continuing release
preparation. External release gates and the bounded follow-up work below remain.
No confirmed P0 defect was identified in the reviewed paths. That statement does
not mean the entire repository is free of security defects.

The review used `PROJECT_RULES.md`, README, architecture, domain and security
documents; the production/Play runbooks; source and test inspection; and the
actual local test results from this task. It examined the named mobile hotspots,
authentication and owner-operation services, maintenance/reporting boundaries,
large owner/supervisor React surfaces, Windows server management, production
containers/routing, and approval workflows. Findings distinguish demonstrated
defects, source-level risks, maintainability debt and unverified external gates.
This was not an exhaustive line-by-line review of every generated file or a
complete static import-cycle analysis.

Priorities: P0 = immediate compromise/data-loss blocker; P1 = release gate or
material reliability/security defect; P2 = bounded engineering debt; P3 = minor
clarity/maintenance improvement. A priority is not a claim of exploitability.

## Architecture and ownership

| Area | Existing responsibility and boundary | Assessment |
| --- | --- | --- |
| `services/api/src/fleet_api/api` | Versioned FastAPI input/output, dependency-injected identity and transaction completion | Domain logic generally remains in services. Authentication intentionally commits some rejected attempts to preserve lockout/replay state. |
| `domain`, `auth`, `db` | Effective-dated assignments, tenant-aware operations, reporting, activation/device sessions, SQLAlchemy persistence | Modular monolith remains appropriate. No additional infrastructure is justified by this workload. |
| `apps/mobile/lib/data` | HTTP/auth adapter, secure credentials, durable SQLite queue and synchronization | Public interfaces and persisted formats remain intact. Network-attempt deadline was the smallest justified reliability correction. |
| `apps/mobile/lib/app.dart`, `role_screens.dart` | Session/onboarding/driver shell and owner/supervisor screens | Cohesive subareas exist, but several responsibilities share large files. Extract only behind existing characterization tests. |
| `apps/web/features`, `lib` | Owner/supervisor presentation and same-origin API/auth access | Typed boundaries and server-enforced authorization are present; some large forms mix state, requests and presentation. |
| `apps/marketing` | Public website, privacy and lead/contact surface | Separate build/runtime; no database or evidence browsing authority. |
| `infra/production`, `scripts/production` | Linux deployment, HTTPS, persistence, migration, backup and recovery | Provider-neutral containers and explicit persistent state. Windows Pilot controls are separate. |
| `scripts/server_manager.py`, Windows launchers | Existing laptop/Pilot service, private updates and backups | Windows-specific by design. These are not the Linux production deployment entry point. |

Dependency direction remains predominantly routes → services → models/storage,
and UI → client interfaces → network/SQLite. Tests and builds import the relevant
modules successfully; that does not prove an acyclic graph. Cross-domain
orchestration in `owner_operations.py` is intentional and should not be replaced
with many independently committing services. Legacy `tipper` names coexist with
asset types because installed clients, response contracts and history still use
them; bulk renaming would be a compatibility change.

## Findings and smallest safe remedies

### P1 — bounded transport waits (fixed and tested)

Before this audit, `ApiClient` used a plain HTTP client and awaited request send
and full response bodies without a deadline. `SyncEngine.syncPending()` holds
its in-progress guard until those operations finish
(`apps/mobile/lib/data/sync_engine.dart:543`). A stalled connection could prevent
later sync attempts completing; logout also awaited the remote call before
clearing local credentials (`apps/mobile/lib/app.dart:320`). This is a
reliability defect, not evidence of lost records.

The correction is contained in `apps/mobile/lib/data/api_client.dart`: a
configurable 45-second deadline covers each complete network attempt, including
response materialization. The existing HTTP 1.5.0 abortable request types signal
cancellation; a retryable `408 / REQUEST_TIMEOUT` also bounds clients that ignore
the signal. Authentication is not expired because of a network timeout.

`apps/mobile/test/api_client_timeout_test.dart` verifies stalled JSON and
multipart sends/bodies, abort signaling, preserved sessions, durable queue/photo
retention, the original UUID on retry, released synchronization, and actual
logout UI clearing credentials without deleting queued records. The existing
auth, MIME, recovery and cold-restart tests also pass. No business rule, SQLite
schema or backend response contract changed.

An upload taking longer than 45 seconds can now fail and retry; this value should
be checked on representative field connectivity. A timeout cannot establish
whether the server already committed a mutation. Existing event/evidence UUID
idempotency remains essential. The client does not automatically replay owner
mutations after a timeout; users should refresh authoritative state before
repeating an ambiguous management operation.

### P1 — exception text may bypass the no-secret-logging contract (fixed and tested)

The initial audit found `JsonFormatter.format()` serializing full exception text
in `services/api/src/fleet_api/core/structured_logging.py`, reached by the
unhandled-request logger in `services/api/src/fleet_api/main.py:127`.
`db/session.py` did not hide SQLAlchemy bound parameters. An unexpected exception
can therefore carry values that routine structured request logging omits. This
is an identified logging boundary weakness; no actual credential disclosure was
observed or asserted.

The correction emits exception class and safe frame locations without arbitrary
messages, source lines, locals, chained exceptions or cached exception text.
SQLAlchemy hides parameters as defense in depth, and Uvicorn's error handlers
use the same safe JSON policy. Request IDs and operational categories remain.
Five new regression tests exercise representative secret-bearing SQL exception
chains, the HTTP 500 boundary, Uvicorn propagation and the engine configuration.
All five pass; the final combined logging/health/configuration/rate-limit/auth
run passed 36 tests. Ruff and mypy also pass. This closes the demonstrated
exception-serialization defect, not every possible application logging risk.

### P1 — data-service changes before backup (fixed and tested)

Final release review found that the initial deployment helper could reconcile
PostgreSQL/MinIO before creating its pre-deploy snapshot; ordinary Compose
dependency traversal could also reach MinIO from the backup helper. The candidate
image tag was incorrectly available to the old-data snapshot manifest.

Routine application releases now require established, running data containers
whose Compose configuration hashes match. They leave data services untouched,
back up using the running release tag, and use no-dependency migration/application
and rollback commands. Fresh bootstrap refuses existing containers or labeled
and unlabeled default-named data volumes. A failed bootstrap retains its data
and requires reviewed recovery; no automatic delete/retry reset exists.

Isolated control-flow regressions verify ordering, refusal and failure rollback.
The real Docker smoke test also passed the data configuration-hash guard and the
no-dependency backup/restore path. Data-image/configuration upgrades are a separate
reviewed maintenance procedure, not an ordinary application release.

### P1 — release verification and external evidence gates

The AAB validator originally accepted non-strict `jar verified` output, which can
coexist with unsigned entries. `scripts/validate_play_aab.py` now trusts only the
approved public certificate in a disposable verification keystore and uses
strict per-entry signer verification. The 20 validator tests include real JDK
self-signed acceptance, unsigned appended content rejection, and content signed
only by a different identity rejection. No Pilot/private release key is read or
changed by this validation.

API/auth labels emitted by the validator explicitly describe build-contract
inputs: bundletool manifest inspection does not prove compiled Dart values.
`scripts/build-play-aab.ps1` and `.github/workflows/google-play-release.yml`
enforce `company_pin` and `https://api.fleetaisystems.com`. The real signed release
AAB, Play App Signing registration and installed-device migration remain
unverified until owner-controlled credentials and test-track access exist.
Image CVE verification, independent offsite restore, actual VPS/DNS/TLS and
real-phone field acceptance are release gates, not completed source checks.

### P2 — mobile shell, role screens and transport coupling

`app.dart` contains dependency assembly (`:50`), session lifecycle (`:162`),
onboarding (`:430`), driver queue/UI coordination (`:1213`) and capture dialogs
(`:2569`). `role_screens.dart` combines supervisor navigation/review (`:20`,
`:303`, `:688`), owner dashboard (`:1227`) and shared role presentation (`:2230`).
`api_client.dart:184` implements driver, owner, report, maintenance and assignment
interfaces alongside token refresh and network transport.

Smallest later refactor: first extract pure capture widgets and role-specific
screens while preserving imports/public entry classes; then isolate the common
transport/refresh implementation behind existing interfaces. Use
`company_pin_login_test.dart`, `api_client_auth_test.dart`, `app_test.dart`,
`role_screens_test.dart` and owner management tests as characterization gates.
Do not create a new state framework or rewrite every call site for file length.

### P2 — queue error and corrupted-payload diagnostics

`sync_engine.dart:630` persists `error.toString()` for unexpected errors; this can
include device paths or third-party diagnostic details. It is not proof that
activation codes/PINs are currently logged. `_decodeStoredPayload` at `:756`
returns an empty map for malformed data, and `_readingValue` at `:748` defaults
unparseable content to zero for local state. Backend validation still governs
accepted business data, and rows remain durable, but support diagnostics should
distinguish corruption from a valid empty payload or real zero.

Smallest later remedy: add malformed stored-payload and diagnostic-redaction
characterization tests, then produce an explicit local error category without
rewriting/deleting the row, UUID or photograph. Avoid broad catch removal that
would break offline recovery or legacy snapshot migration.

### P2 — backend orchestration and report/maintenance cohesion

`domain/owner_operations.py:2011` dispatches the full owner lifecycle and
relationship orchestration after rebuilding a locked preview and checking its
state token. It also contains tenant-scoped loading, preview text, change plans
and mutation/audit logic. Its size creates review coupling, but the single
transaction is valuable: `api/owner_operations.py:115` commits only after the
complete operation. Tests cover stale previews, cross-tenant/role denial and
rollback after audit failure (`tests/test_owner_operations_api.py:711`, `:920`,
`:949`, `:1742`).

`domain/maintenance.py:297` contains pure criterion evaluation as well as plan
and work-order services (`:386`, `:837`, `:1524`, `:1595`).
`domain/reporting.py:282` combines tenant-aware query loading, metric assembly,
daily/period reporting and closure mutations. Decimal metrics and historical
assignment joins are deliberate correctness boundaries.

Smallest later remedies: move pure criterion evaluation and immutable result
types first, then extract owner preview formatting or reporting query assembly
without changing transaction ownership. Preserve one canonical reporting
calculation path. Run maintenance, reporting metrics/reports and orchestration
regressions after each extraction. No broad source reorganization was performed
in this release-preparation task.

### P2 — React form state and text-coupled feedback

`apps/web/features/owner/Maintenance.tsx:184` owns several maintenance panels and
many independent state values (`:198` onward), API calls and presentation.
`OwnerRelationshipManager.tsx:131` has a useful shared operation runner but
duplicates blocked-reason-to-field classification at `:295` and `:584` using
English substring checks. Backend authorization is unaffected; wording changes
can send a valid error to the wrong UI field.

Smallest later remedy: extract cohesive maintenance panels with their existing
tests; centralize field-feedback classification as a pure tested presentation
helper. A typed backend error-target field would need a compatible API extension
and should not be slipped into a deployment-only change. Supervisor effects use
an active guard and evidence URLs are revoked (`SupervisorWorkspace.tsx:118`,
`:146`); preserve those cleanup behaviors during extraction.

### P2 — authentication transport coverage and race characterization

The backend run reports 85% overall line coverage, 88% for `auth/service.py`,
100% for `auth/company_pin.py`, and 42% for `api/auth.py`. This is meaningful
service coverage, not complete auth assurance. Routes deliberately commit failed
activation/PIN attempts and refresh-family revocation, while ordinary failures
roll back (`api/auth.py`, company routes and refresh handlers). Generic
transaction cleanup must not erase this security state.

Existing tests exercise activation expiration/replay/regeneration, PIN lockout,
device binding, logout/reactivation, legacy credential reuse and company/role
switching (`tests/test_company_pin_auth.py`). Follow-up should target missing
HTTP response/cookie/error branches and concurrent requests using independent
database sessions. The thirty-driver test is a representative functional sync
and idempotency workload; it is not a simultaneous thirty-phone stress test.
Do not inflate coverage by testing dataclass getters.

### P2 — Firebase/Kotlin build compatibility

Production startup initializes Firebase only under explicit Firebase auth mode
(`apps/mobile/lib/main.dart:27`); the production contract is company PIN. Firebase
and share plugins remain pinned for compatible legacy paths. The actual Android
build warns that `firebase_auth`, `firebase_core` and `share_plus` apply the
Kotlin Gradle Plugin and will need compatible Built-in Kotlin versions for future
Flutter releases. Track that upgrade separately and rerun legacy/Firebase/Pilot
checks before removing dependencies. No SMS service or billing was introduced.

### P3 — Windows-only assumptions need clear operational labels

`scripts/server_manager.py:95`/`:96` use existing Windows backup roots, and `:98`
uses the Tailscale executable location. Its update path (`:1983`) verifies clean
`main`, fast-forward eligibility, backup, dependencies, migration and restart;
the backup manifest honestly says a restore was not performed. The Windows
owner launcher still reports Tailscale guidance (`start-owner-web.ps1:44`) and
runs a loopback development server. These are Pilot/laptop contracts, not
provider-neutral production automation.

Keep them intact while marking the documentation clearly. Production operators
must use the Linux runbooks, tested private S3 interface and Caddy deployment.
Do not run the Windows update helpers during cloud preparation. Historical
reports and legacy names should remain discoverable through documentation
indexes rather than being deleted or silently presented as current guidance.

## Verified controls and verification limits

| Area | Evidence in this task | Status and limit |
| --- | --- | --- |
| Backend/domain/auth | 283 regression tests; 85% coverage; affected 89 after type fixes | PASS for executed tests. Route coverage and production-scale race testing remain incomplete. |
| Offline integrity | UUID before enqueue; atomic local event/duty updates; account-scoped queue; backend unique UUID/savepoint (`domain/events.py:104`); cold-restart, handover, sync and new timeout tests | PASS locally. Real installed phones and Pilot-to-Play queue-drain acceptance remain blocked. |
| Company PIN | Salted PBKDF2 and constant-time comparison (`auth/company_pin.py`); locked activation/credential rows, expiration, consumed state and bounded attempts (`auth/service.py:519`, `:585`, `:627`, `:730`) | PASS for local tests. Google Play distribution adds no authentication provider. |
| Owner/supervisor authorization | Authenticated company context, role checks, tenant-scoped rows; owner transaction tests | PASS for covered paths. UI hiding is not the enforcement boundary. |
| Web | 71 unit tests previously passed; 8 E2E against production image with mocked API | PASS locally; mocked API E2E is not a real authenticated browser-to-production-backend test. |
| Marketing | 11 unit tests; 17 E2E | PASS locally; live domain/email/privacy contact must be owner-confirmed. |
| Mobile | 164 tests with coverage and analyzer passed after timeout correction | PASS locally; no physical-device rollout or Play-signed artifact is claimed. |
| Play validator | 20 tests including real JDK signing checks | PASS tooling; real signed production candidate remains BLOCKED. |
| Linux stack | Isolated Docker routing, health, private ports, persistence restart, migration and local backup/restore checks passed, rerun after logging correction | PASS locally. Final idle footprint around 317 MiB is a snapshot, not capacity proof for concurrent uploads/reporting. |
| Secrets/dependencies | Secret scan and locked Python/production npm audits run by the release task | See readiness report for exact results. A dependency audit is not an image/OS scan. |
| Container CVEs/offsite restore/live cutover | No verified image scanner result or owner-configured external restore target | NOT VERIFIED. No live infrastructure was touched. |

The post-fix Flutter LCOV artifact contains 4,715 hit lines of 6,782 measured
lines (69.52%, including generated database code). Excluding
`local_database.g.dart`, measured source files have 4,488/6,071 (73.92%). This is
coverage of files present in LCOV, not a claim that every source file was
instrumented. Critical measured files are `sync_engine.dart` 472/560 (84.29%),
`local_database.dart` 303/340 (89.12%), and `api_client.dart` 270/485 (55.67%).
`device_authenticator.dart` is 0/6 because tests replace the OS authentication
boundary; real Android device security still needs field verification.

The production Caddy configuration routes public marketing, browser dashboard
and driver API separately, blocks private administration/Pilot publishing paths,
and keeps database/S3/admin listeners unexposed. Browser security headers and
same-origin proxy controls were exercised by the production smoke checks.
The API and S3 use private container networking; Caddy terminates external TLS.
The single-VPS design is intentionally not highly available.

## Safe next maintenance sequence

1. Close the remaining release gates listed in the readiness report, including
   image verification, external restore and real-device onboarding/offline tests.
2. Add HTTP auth-branch and corruption/redaction characterization where coverage
   is demonstrably missing; retain all existing assertions.
3. Extract one cohesive pure/UI responsibility at a time from the hotspots above;
   preserve constructors, public imports, API payloads, SQLite tables and UUIDs.
4. Run affected unit/integration tests, type/analyzer checks and the relevant
   production build after each extraction. Compare observable behavior before
   combining the next change.
5. Release only an approved `main` SHA with successful CI using the documented
   manual production or Google Play workflow. Pushes alone must not deploy.

No architecture, persisted identifiers, package/certificate identity or migration
history was reorganized by this audit. The only audit-driven mobile source change
is the bounded HTTP transport operation and its regression tests. The separate
release work contains deployment, documentation and security corrections; its
complete changed-file inventory belongs to the final readiness report.

## Repository maintainability re-audit — 2026-10-16

Scope: the subsequent sequential repository-quality task, starting from
`06ecbc457d7e2fc0795310636fea0064f47ab0ff`. Reviewers read the updated project and
component instructions, existing contracts, source, tests, and prior evidence.
Application source, migrations, and Windows server-management behavior remain
unchanged. No application tests/builds were rerun for this source/documentation
review; the earlier PASS results above are retained evidence only.

### Responsibility inventory, not a file-size verdict

| Existing hotspot | Measured size | Responsibilities / extraction boundary |
| --- | --- | --- |
| `apps/mobile/lib/app.dart` | 2,917 lines; 98,033 bytes | Assembly `:50`, session `:162`, onboarding `:430`, Driver `:1213`, diagnostics `:2090`, capture widgets `:2569` |
| `apps/mobile/lib/role_screens.dart` | 2,514 lines; 82,481 bytes | Supervisor `:20`, review `:303`, maintenance `:688`, Owner `:1227`, shared presentation `:2230` |
| `apps/mobile/lib/data/api_client.dart` | 1,400 lines; 42,536 bytes | Seven role/domain interfaces at `:184`, shared refresh coordinator `:211`, HTTP/evidence transport |
| `apps/mobile/lib/data/sync_engine.dart` | 1,103 lines; 39,893 bytes | Durable enqueue, duty recovery, ordered sync, payload translation and diagnostics |
| `services/api/src/fleet_api/domain/owner_operations.py` | 2,619 lines | Locked preview/state tokens, lifecycle planning, relationship mutations and audit |
| `services/api/src/fleet_api/domain/maintenance.py` | 1,704 lines | Pure due-state evaluation, plans, work orders, proof/history queries |
| `services/api/src/fleet_api/domain/reporting.py` | 1,383 lines | Scoped query assembly, canonical metrics, daily/period reporting and closure |
| `apps/web/features/owner/OwnerManagement.tsx` | 52,994 bytes | Shared action state `:39`, Fleet `:284`, People/activation `:421`, Sites `:509` |
| `apps/web/features/owner/OwnerRelationshipManager.tsx` | 38,181 bytes | Shared preview/execute runner `:131`, asset/person forms and confirmation flows |
| `apps/web/features/owner/Maintenance.tsx` | 36,558 bytes | Overview/plans/history, request state `:198`, loading `:219`, mutations `:272`, forms |
| `scripts/server_manager.py` | 2,119 lines; 79,557 bytes | Process ownership/start-stop `:216`–`:1060`, signing/APK `:1075`–`:1446`, backup `:1464`–`:1752`, update `:1759`–`:2066` |

These sizes identify review and test surfaces, not defects by themselves.
Some React files compress substantial JSX into few physical lines. Existing
interfaces, domain services, shared UI components and focused production scripts
already provide useful boundaries. No microservices, new state framework,
generic service hierarchy, or wholesale file split is justified by this review.

### P2 — concrete UI error fallback and asynchronous characterization gaps

Source-confirmed fallback behavior: `OwnerWorkspace.tsx:91` substitutes zero
maintenance counts when that request fails; the rest of a successful reload then
shows zero alerts. `OwnerOperations.tsx:35` similarly maps failed duty/template
requests to empty arrays, while `:109` renders an empty-duty message. These paths
conflate unavailable data with an actual empty result. This is a bounded UI
correctness concern, not evidence of a backend authorization bypass, lost data,
or a newly demonstrated production outage. Add rejected-request tests and an
explicit unavailable state before changing the presentation contract.

`Maintenance.tsx:219`–`:243` loads an asset plan across several awaits without a
request-generation check; the effect at `:247` cancels only a pending timer.
Delayed responses during selection changes therefore need characterization.
Mobile `role_screens.dart:51`/`:1259` schedules loads at `:60`/`:1268` without an
in-flight/generation guard; mounted checks do not establish latest-response
ordering. Owner date reads at `:1271`, `:1274`, `:1288` can span the change at
`:1322`. Use delayed/reversed-response, date/asset-switch and disposal tests before
introducing a captured selection/date and latest-generation guard. These races
were identified from source, not reproduced in this audit.

Existing browser tests cover useful behavior: relationship stale-state handling
and safe retry (`OwnerRelationshipManager.test.tsx:349`, `:366`), blocked fields
(`:386`), force-close confirmation (`:413`), activation/reset
(`OwnerManagement.test.tsx:426`), and maintenance copy errors/rental read-only
state (`Maintenance.test.tsx:265`, `:278`). `OwnerWorkspace.test.tsx` primarily
covers navigation. Owner workstation and maintenance Playwright suites use
mocked API responses, not a real browser/backend activation session. Preserve
these tests and add failure/order cases; do not replace them with size-driven
component snapshots. The existing English-substring field classification remains
the earlier bounded presentation-coupling finding.

### P2 — backend duplication and query shape

`owner_operations.py:2169` and `:2536` repeat the end-assignment/deployment,
replacement deployment, KEEP-driver recreation and audit sequence for direct
movement versus site-deactivation movement. Characterize both callers, then
consider a helper receiving already locked records and one timestamp. Preserve
replanning with `lock=True` and state-token validation at `:2011`, one API-owned
commit (`api/owner_operations.py:115`–`:140`), and audit ordering. Relevant
regressions include `test_owner_operations_api.py:491`, `:548`, `:711`, `:949`,
`:1291`, `:1742`; do not split this into independently committing services.

Maintenance evaluation caches meters per asset but queries criteria per schedule
(`maintenance.py:622`–`:631`, `:717`–`:731`). History loading retrieves all rows
(`:949`–`:976`) and resolves related records inside the row loop (`:995`–`:1066`).
`reporting.py:1077`–`:1083` calls canonical daily reporting for each day, with an
explicit 366-day limit at `:1044`. These are measurable query-shape candidates,
not measured latency/SLA failures for thirty phones. Add SQL statement-count and
representative-volume tests before batching tenant-scoped loads; assert identical
results and authorization with the existing maintenance/report regressions.

Do not blindly unify similar metric loops: current KM approval filtering at
`reporting.py:585` differs from the accepted HMR states at `:618`. Capture that
state matrix before any shared extraction. Pure maintenance criteria/result
types are a safer first extraction than work-order completion, whose lock,
meter baselines, immutable history and audit must stay together (`:837`).

### P2 — mobile and Windows control boundaries to retain

The earlier mobile coupling/corruption findings remain valid. In addition,
`SyncEngine._toDomain` is called at `sync_engine.dart:581` before the per-row try
at `:582`; enum lookups at `:1083`/`:1088` warrant malformed-persisted-value tests.
There is no evidence here that real queues contain such corruption. Never clear
or rewrite a row, UUID or photograph to make a test pass. Preserve the sync guard
and `finally` release (`:543` onward), dependency order (`:570`), shared refresh
gate, and existing bounded transport. Any later extraction of the two 401 retry
branches (`api_client.dart:1139`, `:1230`) must retain that single coordinator.

Use the existing company-PIN, API auth/timeout, role-screen, recovery,
cold-restart and handover tests as characterization gates. Extract pure capture
widgets or queue translation/error policy before moving session/transport
ownership. OS authentication and real installed-device migration still require
external acceptance.

Windows `update_server` at `server_manager.py:1983` retains clean-main,
fast-forward and verified-backup gates before stopping services; there is no
automatic schema downgrade. Pure status/manifest/path helpers are safer future
extractions than process, backup or release ownership. Preserve the existing
server-manager, launch, Pilot-inbox and release-send tests. Console exception
text at `:2113` may contain third-party diagnostics; add redaction fault tests
before changing it. No credential leak is claimed from this source pattern.
The Windows website blue/green helpers remain separate from the Linux topology.

### P1 — verification-harness cleanup boundary (addressed in hygiene phase)

The inspected baseline `scripts/production/local-smoke-test.sh` automatically
removed its Compose volumes and temporary root. This conflicted with the new
task's explicit prohibition on automatic volume deletion; the old helper was
not run during this re-audit. This was an operator-policy/verification-harness
gap, not a new business-logic bug or evidence of deleted live volumes.

The hygiene change retains test containers, volumes and artifacts, stopping only
validated exact IDs from a fresh collision-checked synthetic project. It pins a
verified local Docker endpoint, binds test ingress to loopback and isolates
synthetic configuration from ambient production settings. Safety regressions
exercise refusal and retention paths; the final readiness report records the
actual fixture and full-stack verification results. No automatic janitor is added.

### Outcome and bounded follow-up

No new P0 or demonstrated runtime P1 was confirmed in the reviewed application
paths. The narrowly addressed harness-policy issue and existing external release
gates remain distinct from P2 maintainability work. Static inspection is not exhaustive
security testing, query benchmarking, or proof of an acyclic import graph.

Recommended follow-up order: characterize unavailable/error and response-order
cases; fix each confirmed behavior narrowly; extract one pure/cohesive helper
behind those tests; measure query counts before optimizing; revalidate affected
contracts and release artifacts. Use the
[change workflows](development/change-workflows.md) for the component-specific
verification/release boundary. No application logic, schema, authentication,
offline format, signing identity, installed Pilot, or live infrastructure was
modified by this re-audit.

### Final regression follow-through

The subsequent full verification found an order-dependent logging configuration
failure: embedded Alembic execution disabled existing Fleet/Uvicorn loggers.
The final audit changes only Alembic's `fileConfig` option to preserve existing
loggers and adds a regression; schema versions and business behavior remain
unchanged. See the [latest consolidated report](operations/repository-readiness-report.md)
for reproduction, corrected regression results and the affected API rebuild.
