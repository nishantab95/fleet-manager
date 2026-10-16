# Production readiness report — 2026-10-16

## Release decision

**PHASE STATUS: PARTIAL.** The repository candidate is prepared and locally
tested. It is not yet approved for live cutover or Google Play publication.
No VPS, DNS, installed Pilot, production data, permanent signing key or
application identifier was changed. No changes were pushed remotely.

Work resumed on the existing `main` working tree at
`e7a19e61be0e91065ebe55962b8eced8f5819267`. Existing changes were preserved.
Git status, the latest test failures, project rules, ordered instructions,
README, architecture/security guides, deployment scripts, mobile update and
signing code, and GitHub Actions were inspected first.

## Ordered phase results

| Phase | Status | Evidence / remaining boundary |
| --- | --- | --- |
| 1. Cloud deployment | PASS locally; live BLOCKED | Three Linux application images built; isolated Compose startup, HTTPS routing, private ports, health and restart persistence passed. Public DNS/ACME/VPS not exercised. |
| 2. Authentication | PASS automated; device acceptance NOT VERIFIED | Company-PIN activation expiry, single use, replay denial, hashing, lockout, binding, sessions, logout/reactivation and tenant/role permissions covered by passing tests. |
| 3. Google Play | PARTIAL | Production debug AAB compilation and release validation checks passed. Signed release AAB and actual Play installation require owner-controlled signing/Console access. |
| 4. Deployment/updates | PARTIAL | Manual SHA/CI/approval gates, history, backup/migration/health gates and image rollback implemented; workflow lint passed. Live GitHub protection, SSH and GHCR deployment not exercised. |
| 5. Security/backups/portability | PARTIAL | Dependency/secret scans, private routes, Linux backup permissions, local DB restore and evidence hashes passed. Image CVE scan, offsite recovery, host controls and alert delivery remain gates. |
| 6. Regression/capacity | PASS for listed local checks; field performance NOT VERIFIED | Component regressions below. Thirty distinct drivers synchronize sequentially; no concurrent VPS/photo-burst benchmark claimed. |
| 7. Enterprise audit/docs | PASS for scoped work | Documentation/ADR/history indexes, duplicate-ID repairs, source audit and narrow release-blocker fixes. Broad refactoring deferred. |
| 8. Final verification/handover | PARTIAL | Prepared repository with explicit external blockers. No live activation or publishing. |

## Implementation and preserved contracts

- Separate production stack: FastAPI, PostgreSQL, private MinIO, Owner/Supervisor
  web, marketing and Caddy. Only Caddy publishes host ports.
- `fleetaisystems.com` serves marketing; `app.fleetaisystems.com` serves browser
  workspaces through the same-origin proxy; `api.fleetaisystems.com` exposes
  required mobile auth/Driver/Supervisor routes. Public mobile API routing
  rejects legacy admin, Pilot publishing, Owner/report families and docs.
  Backend authorization remains authoritative.
- Cloud clients use fixed HTTPS without Tailscale/manual server address.
  Windows/Tailscale Pilot launchers and configuration remain independent.
- Production and Play explicitly use `company_pin`: owner-issued activation
  enrolls the existing person/company, then existing PIN/device authentication.
  Optional Firebase code remains; no SMS or Firebase Phone credential is needed.
- Offline SQLite records, photographs, event UUIDs, assignments, authentication
  records and device-registration contracts are preserved. No Alembic migration
  was added or edited.
- Manual GitHub dispatch selects a reviewed full `main` SHA with successful CI
  and protected-environment approval. Pushes only run CI. Server components
  release together as one tested revision; Android has a separate Play approval.
- Routine deploy/rollback refuses changed, missing or stopped data-service
  configurations. It never reconciles established PostgreSQL/MinIO services;
  their maintenance is a separate reviewed operation. Existing backups identify
  the running image tag, before candidate migration/application replacement.
- DB/evidence backup artifacts, hashes, isolated restore, encrypted Restic
  offsite commands, retention guards, systemd timers and bounded logs exist.

## Actual verification

Commands ran in the corresponding component directory. PostgreSQL fixtures use
the test-only database; their migrations do not touch Pilot or production.

| Check | Actual result |
| --- | --- |
| Full backend: `.venv\Scripts\python.exe -m pytest --basetemp .pytest-approved-final-20261016 -p no:cacheprovider --cov=fleet_api --cov-report=term --cov-report=xml -q` | **283 passed**, 50 warnings, 299.65 s; **85%** statement coverage. |
| Affected backend API/auth suites after type compatibility fixes | **89 passed**, 3 warnings, 105.48 s. |
| Final logging/health/configuration/rate-limit/auth regressions | **36 passed**, 3 warnings, 34.77 s; includes five new secret-bearing exception regressions. |
| Python Ruff lint/format and `mypy src tests` | PASS on final Python source; **130 files** formatted and **105 modules** typed. |
| Migration/model checks | PASS in backend regression; fresh Docker database migrated through `0001`–`0024`. No migration-history edits. |
| Thirty-driver company-PIN workload | PASS: 30 distinct drivers, real service activation, installation binding, authenticated HTTP event submission, same-UUID replay; exactly 30 events retained. Sequential, synthetic local workload. |
| Web lint/typecheck/build/unit tests | PASS: 15 test files / 71 tests; production Docker/Next build passed. |
| Owner browser regressions against production image | **8 passed**, 18.0 s; mocked API responses for workstation and maintenance. Not proof of real backend/browser onboarding. |
| Marketing lint/typecheck/build/unit tests | PASS: 3 test files / 11 tests; production Docker/Next build passed. |
| Marketing browser regressions against production image | **17 passed**, 41.9 s; routes, responsive layouts, lead UI, discovery and private-route refusal. Form submission is intercepted; server lead logic has separate unit tests. |
| Android update contract + strict AAB validator | **25 passed**, 10.34 s. Real temporary JDK fixtures accept approved self-signed cert and reject unsigned/differently signed appended entries. |
| Final combined release helpers | **37 passed**, 22.91 s: AAB validator, mobile update contract and **12 deployment-control regressions**. Command doubles exercise backup/migration failures, application-only rollback and bootstrap refusal without real Docker/data mutation. |
| Flutter | Full suite after bounded-request change: **164 passed**, 25 s; **34 affected tests passed**; analysis and formatting passed. Production-flavor debug AAB with cloud HTTPS + company PIN built in 39.6 s. This is not a signed release AAB. |
| Actions, shell, Compose | Pinned actionlint PASS; every production shell script and MinIO init syntax PASS; both PowerShell release/test entry points parse PASS; Compose configuration/runtime PASS. |
| Locked Python production dependency audit | `pip-audit==2.10.1`: no known vulnerabilities after targeted FastAPI/Starlette, PyJWT and multipart updates. |
| JavaScript production dependency audits | `npm audit --omit=dev --audit-level=high`: zero vulnerabilities for web and marketing. |
| Secret scans | Pinned Gitleaks: 93-commit history PASS; final **10.46 MB** working-tree source scan PASS. Generated caches/runtime excluded. |
| Documentation navigation | **196 local links**, **18 unique ADR IDs** checked: PASS; exact-file inventory included. |
| Local production smoke | `PRODUCTION_SMOKE`, `PERSISTENCE_RESTART`, `PRIVATE_PORTS`, `CADDY_PRIVATE_ROUTES`, `DATA_SERVICE_GUARD`, `LOCAL_BACKUP_RESTORE`: **PASS**, including rerun with the final safe-logging API image and no-dependency backup helper. |
| Linux backup permissions | Original dropped-capability root write failed on private Linux storage; caller UID/GID + writable mc config passed. |
| Container OS/image CVEs | **NOT VERIFIED**. Dependency audits do not establish image safety. |

### Failures resolved and test limits

A root-directory test attempt inherited the laptop's Pilot `.env`; correct
service-directory execution resolved that contamination. Sandboxed runs then
failed before 25 fixture setups with Windows `WinError 5` on global and local
pytest temp roots. The approved non-sandboxed test-only run passed all 283 tests.
No failing assertions were removed or tests skipped to obtain that result.

Security dependency updates exposed typing changes: a redundant PyJWT cast was
removed and four test helpers now assert the expected response type. All 89
affected tests passed afterward; final typing covers 105 modules including the
logging regression additions.

The exception-logging correction removes arbitrary exception/chained messages,
source lines and locals, routes Uvicorn errors through the safe JSON formatter,
and hides SQLAlchemy parameters. Five focused tests plus the combined 36-test
integration run passed. The API image was rebuilt after this source change;
unchanged successful web/marketing builds were reused.

Final release review also corrected data-service reconciliation before backup,
dependency-driven MinIO restarts, and incorrect candidate-tag backup metadata.
Twelve isolated control-flow tests and the real unchanged-data Docker guard
passed. Existing data-service changes are refused; first bootstrap is allowed
only with no recorded state, existing containers or colliding data volumes.

An initial resource probe suffered Git Bash path conversion inside Docker. The
container-shell probe fixed it; runtime/restore checks reran using the just-built
images with `--reuse-images`. Local Windows ACL accommodation exists only in
the smoke path; actual Linux permissions have separate verification.

Image scanning did not complete. Automatic approval review rejected a Docker
socket-mounted scanner (host-control scope) and a cloud/SBOM scanner (external
data transmission). A restricted archive-based alternative and a diagnostic
public vulnerability-database download stalled; the diagnostic container was
stopped. No successful container-CVE report is claimed.

Known non-failing warnings include Starlette test-client/status-code
deprecations, Alembic path-separator configuration and the existing
duty/event foreign-key cycle warning. Record these for a separately tested
dependency/metadata cleanup; do not rewrite old migrations.

### Measured local resources

One post-rebuild idle snapshot after restart/restore on Docker Desktop with tiny
synthetic data (subsequent snapshots naturally vary):

| Container | Memory | CPU snapshot | Memory ceiling |
| --- | ---: | ---: | ---: |
| API | 116.60 MiB | 0.27% | 512 MiB |
| Caddy | 16.19 MiB | 0.00% | 128 MiB |
| Marketing | 40.11 MiB | 0.03% | 256 MiB |
| MinIO | 76.31 MiB | 0.09% | 768 MiB |
| PostgreSQL | 27.79 MiB | 0.04% | 768 MiB |
| Owner/Supervisor web | 40.24 MiB | 0.06% | 384 MiB |

Total: **317.24 MiB**. Test PostgreSQL disk: **66,476 KiB**; MinIO: **156 KiB**.
Logical image sizes at that snapshot: API **877,659,199 bytes**,
web **305,548,600 bytes**, marketing **312,618,865 bytes**. Shared layers and
physical Docker allocation differ. These are not OVH measurements, load
ceilings or a forecast of photo growth. Measure evidence volume, backup copies,
database growth, log retention and image history before accepting 40 GB.
No p95 latency or sustained 30-phone concurrency claim is made.

## Android identity and data migration

The permanent Pilot identity was inspected before signing changes:

- Package: `com.fleetmanager.fleet_manager_mobile.pilot`.
- SHA-1: `11:D4:B4:DC:04:F0:D3:06:89:03:E1:C3:33:C1:89:4E:7A:E4:7A:74`.
- SHA-256: `FD:25:11:5E:20:AC:18:A8:A7:CD:A9:1B:9F:4D:5F:61:53:F5:4B:4D:79:C7:51:B5:00:5A:3A:C7:34:CC:3C:29`.

The existing Play package is `com.fleetmanager.fleet_manager_mobile`.
**Different packages cannot upgrade in place.** Drain Pilot's event/photo
queue, reconcile server records, keep Pilot installed, install Play, issue a
fresh activation/reset for the same existing User and verify assignment/history.
Only retire Pilot after acceptance. Play cannot read the other package's private
SQLite/photo/secure-store sandbox.

No Pilot key was generated, replaced, exported or reused for Play. Release
validation requires the separate approved upload cert and rejects Pilot/debug
signing, debuggable manifests, cleartext traffic and APK install permission.
Bundletool validates AAB structure/manifest; strict JAR checks use only the
approved public certificate. API/auth Dart defines are enforced by the build
workflow and labelled honestly as build-contract metadata, not binary inspection.

Onboarding is **Google Play → install → owner-issued activation → device
activation → application**. The existing flow may request the registered phone
identifier to locate the authorised person; no SMS is sent. No Tailscale, manual
server address or extra Firebase login is needed. Real-device upgrade, restart,
camera/evidence, biometric/PIN, queue drain and Play-delivered signing acceptance
remain external tests.

## Recovery, security and remaining engineering work

Local DB restore and evidence checksum verification passed. Deployment requires
an independently encrypted offsite generation, but real offsite credentials
and a timed external restore drill are missing. Marketing lead PII needs its
separate approved backup/retention policy. Remote pruning is owner-controlled.

Rollback changes application images and keeps data/schema. It does not reverse
Compose, Caddy, secrets or firewall configuration. Configuration incidents require
reviewed configuration rollback. No live rollback, data restore or schema
downgrade was executed.

Workflow redispatch intentionally refuses already-published immutable SHA tags.
If publication succeeds but SSH deployment fails, do not overwrite those tags:
obtain renewed approval and use the documented reviewed direct-VPS recovery
command after checking state/digests. Automatic same-SHA workflow retry is not
claimed.

The [engineering audit](production-engineering-audit.md) records source evidence
and priorities: large modules/coupling, missing real end-to-end activation and
concurrent sync tests, image scanning, malware/content inspection, operational
alerts and deprecations. Broad business-logic refactoring was deferred. The
targeted mobile request-deadline and safe exception-logging fixes are release
reliability/security corrections, not new business features.

## External release gates and exact activation sequence

1. Owner provisions the Ubuntu VPS. Follow [deployment](production-deployment.md)
   for directories, ownership, Docker, SSH/firewall and external secrets.
   Resolve the container-CVE verification gate and any required image updates.
2. Configure independent Restic storage/password escrow and alert delivery.
   Prove a timed offsite restore; approve RPO/RTO, retention and disk capacity.
   Confirm legal entity/privacy contact, evidence content controls and Play
   Data safety declarations.
3. Configure protected GitHub `production` and `google-play-production`
   environments/reviewers/secrets, SSH host-key pinning, repository access and
   GHCR permissions. Push reviewed `main` and obtain green exact-SHA CI.
   No push or remote CI run was performed here.
4. Restore a copy of Pilot DB/evidence in staging; reconcile companies,
   memberships, assignments, devices, event UUIDs and photo counts/hashes.
   Plan write freeze/queue drain; preserve originals.
5. After explicit live approval, set apex/`www`/`app`/`api` A records to the
   VPS. Add AAAA only after IPv6 routing/firewall verification. Allow public
   80/443 for Caddy ACME, then verify external TLS, routes and exposed ports.
   No DNS records were changed during preparation.
6. Request the approved server release from clean `main`:

   ```powershell
   $sha = (git rev-parse HEAD).Trim()
   gh workflow run production-deploy.yml --ref main -f git_ref=$sha -f 'confirmation=DEPLOY fleetaisystems.com'
   ```

   The environment reviewer must approve it. Backup, restore verification,
   offsite copy, forward migration and health gates then run.
   Follow [migration/rollback](production-migration-and-rollback.md); no reset
   or unverified data overwrite is part of deployment.
7. Supply Play Console/package registration, Play App Signing enrollment, a
   separate upload keystore/cert, scoped Android Publisher permissions, final
   artwork/screenshots, app-access/declaration answers and account-specific
   testing eligibility. Use `scripts/build-play-aab.ps1`, then real-device and
   Internal-track acceptance. Obtain separate approval before publication.
   [Google Play release](google-play-release.md) contains exact commands.

Missing access is a blocker, not a successful deployment result. Live ACME,
external port scans, SSH deploy/rollback, offsite recovery, signed Play release,
Play installation and actual Pilot-phone migration remain **NOT VERIFIED**.

## Documentation and files

Start at [documentation index](index.md), [ADR inventory](adr/README.md),
[history index](archive/README.md) and [engineering audit](production-engineering-audit.md).
Duplicate IDs are resolved: Supervisor verification is 0017; public branding is
0018. Original decision/history content is retained. Firebase guides are
explicitly optional.

The [change inventory](production-change-inventory.md) lists exact changed files
and purpose categories. No new schema migration or business feature was added.
All eight requested preparation phases were addressed; no live activation or
unrelated later feature phase was started.

## Git handover

Base: `e7a19e61be0e91065ebe55962b8eced8f5819267` on `main`.

Verified implementation commit:
`789dd878ec7dc5880899f520f24246463983d81c` — 94 files, including the
preserved earlier work and two history-preserving ADR renames. The working tree
was clean immediately after that commit; only this report is changed by the
metadata follow-up. No remote push is included.

All listed local checks are complete; externally blocked gates remain above.
The follow-up does not alter tested application or deployment code. Obtain its
exact final handover SHA with `git rev-parse HEAD`; the final user-facing handover
also records it. Remote CI has not run for either new commit and remains a
mandatory gate before any approved release.
