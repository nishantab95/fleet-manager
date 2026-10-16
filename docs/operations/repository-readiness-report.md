# Repository engineering and release-readiness report

Date: 2026-10-16. Overall **PARTIAL**: local engineering work is verified as
listed below; external security, VPS and Google Play acceptance gates remain.
This is not deployment approval, proof of live operation, or Play publication.

## Scope and preserved baseline

The actual checkout is `D:\Git\fleet maneger\fleet manager`, not its parent.
Work continued on existing `main`, starting at
`06ecbc457d7e2fc0795310636fea0064f47ab0ff`. The prior implementation commit
`789dd878ec7dc5880899f520f24246463983d81c` and its completed production work
were preserved. The earlier 69-file working set was already committed at this
baseline; it was not reset or reconstructed. Initial status was clean.

First inspected: root/branch/status/history/remotes/ignored files/Git object
usage, primary project rules, README, prior readiness/change reports,
architecture/security, agent instructions, deployment/release scripts and
available local test artifacts. Phases 0–7 were completed in sequence before
the final verification phase. Parallel reviewers worked within the same phase.

No application business logic, API contract, database model/schema migration, Android
data format, authentication implementation, package identifier, signing identity
or Windows server-manager code changed. Diff checks confirmed this. The final
regression identified an Alembic logging-initialization issue, described below;
the correction does not alter migration versions or schema history. No new
migration is introduced; head remains `0024_company_pin_auth`.

## A. Disk usage and safe cleanup

The reported 8.42 GB was approximately **8.439 GiB / 9.061 GB logical** at the
measured baseline, not 8 GB of source. Parent and checkout had identical totals.
Flutter intermediates, Next development caches, dependencies, protected runtime
history/releases and a Docker export explain the footprint. Tracked source was
only **5,716,037 bytes**; ignored files were **8,819,456,770 bytes**. The
[full disk audit](local-disk-audit.md) contains top 25 directories, top 30 files,
immediate children, allocation measurements and protected/unknown classifications.

These are paired pre/post-cleanup snapshots, not a claim that later tests create
no files. Positive reclaimed values mean net reduction; negatives mean growth.

| Category | Before bytes | After bytes | Reclaimed bytes | Class |
| --- | ---: | ---: | ---: | --- |
| Tracked source | 5,716,037 | 5,716,037 | 0 | A, essential |
| Development dependencies | 1,326,585,797 | 1,326,585,797 | 0 | B, retained |
| Generated/cache output | 4,327,022,562 | 2,279,252,794 | 2,047,769,768 | C, only allowlist removed |
| Protected state/Git | 1,518,635,614 | 1,518,635,931 | -317 | D, retained |
| Release/signing artifacts | 1,562,137,171 | 1,562,137,225 | -54 | E, retained |
| Initially unknown, including inspected tar | 321,148,297 | 121,888,156 | 199,260,141 | F, retain unless verified |
| **Total logical** | **9,061,245,478** | **6,814,215,940** | **2,247,029,538** | All |
| Referenced allocation | 9,179,024,528 | 6,931,644,656 | 2,247,379,872 | Not volume-free-space measurement |

Exactly 260 regenerable files totaling **2,250,645,823 bytes** were removed:

- `.tmp/fleet-api-ci.tar`: 202,826,240 bytes, verified Docker image export.
- `apps/web/.next/dev/cache`: 487,800,317 bytes.
- `apps/marketing/.next/dev/cache`: 169,203,546 bytes.
- `apps/mobile/build/app/intermediates/merged_native_libs/productionDebug`:
  1,390,815,720 bytes; engine/plugin prerequisites and full AAB retained.

Removal was direct, not through the Recycle Bin; the outputs can be regenerated.
The net reduction is lower because audit evidence/fixtures added 3,616,285 bytes.
No unique data was deleted. Before/after hashes and sizes of 23 protected files
matched. A later mobile verification also matched all 15 mobile/release sentinels.
The external configured Pilot certificate was independently revalidated; no
before/after hash comparison of an unrecorded external keystore is claimed.

Retained: both `node_modules`, Python `.venv`, SDK/Gradle caches, complete release
APKs/AAB, `.runtime` (1.282 GB), its historical release checkout (1.240 GB),
`dist`, evidence, configuration and all Git objects. The 200.9 MB loose Git
object matching the Docker tar is preserved, even though no current ref/reflog
was found for it. Unknown does not mean disposable. No Git GC or Docker prune.

Docker Desktop is separate: baseline images 4.23 GB, cache 6.669 GB, volumes
172.8 MB. Image/cache categories overlap and must not be summed. The active
Pilot PostgreSQL/MinIO volumes remain untouched. New isolated smoke-test state
is deliberately retained and stopped, not silently deleted.

Future hygiene is manual: read-only inventories, report-only default cleanup,
fixed verified cache allowlist, link/lock/tracked/protected-file safeguards and
weekly review. Backup retention reports candidates but never deletes them.
No normal development, CI, startup or release invokes a cache/backup janitor.
See [manual maintenance](local-maintenance.md).

Final verification snapshot at 16:01:53 UTC: parent/checkout each
**6,902,939,448 logical bytes**, allocation 7,028,281,376 bytes; zero scan errors,
only two skipped synthetic test junctions. This is a **2,158,306,030-byte net
reduction** from baseline after retained verification outputs added 88,723,508
bytes since immediate cleanup. No second cleanup occurred. Docker Desktop now
reports images 4.689 GB, cache 7.344 GB and volumes 240.8 MB separately; the two
Pilot containers are still the only running containers. See the disk audit for
snapshot scope; report/Git metadata written afterward is not included.

## B. Repository structure

No existing source folder or document was moved in this audit. Existing archive
and ADR history were retained. New documentation folders are navigation indexes,
not duplicate systems or decorative architecture.

```text
Before (all retained)                 After (additions)
apps/{mobile,web,marketing}/          scoped AGENTS.md / CLAUDE.md guidance
services/api/                        scoped agent guidance
infra/production/                    unchanged production topology
scripts/production/                  guarded operations-bundle receiver
scripts/                             bundle builder + regression tests
                                     maintenance/ audit/context/cleanup checks
docs/                                authoritative guides remain in place
  adr/                               ADR 0019 + existing index
  archive/                           existing historical index retained
                                     architecture/index.md
                                     development/{index,agent-onboarding,
                                       change-workflows}.md
                                     operations/ measured reports/runbooks
                                     security/index.md
                                     releases/index.md
.github/workflows/                   manual deployment transports ops only
PROJECT_RULES.md, README.md           updated to verified implementation
                                     AGENTS.md, CLAUDE.md
```

## C. Agent readiness

Root [AGENTS.md](../../AGENTS.md) navigates to the primary
[PROJECT_RULES.md](../../PROJECT_RULES.md); [CLAUDE.md](../../CLAUDE.md) imports
the same concise contract. [Onboarding](../development/agent-onboarding.md)
documents root-to-scope loading, explicit rules reading and trust boundaries.
Mobile, API, web and marketing scopes each have AGENTS/CLAUDE entry files.
Existing generated Next.js instructions and the useful web Claude guide remain.

Static checks verified ten entry files, five resolvable imports without cycles,
consistent company-PIN/Pilot/main-only restrictions and instruction sizes below
the documented default context limit. A fresh interactive Claude Code session
was **NOT VERIFIED**. Instructions guide behavior; they are not a security sandbox.
The OpenAI documentation skill informed the concise shared contract and
scope-loading guidance; it did not authorize deployment or application changes.

A new agent must inspect Git first, read rules and the relevant indexed
contracts/ADRs, inspect existing implementation, identify auth/schema/offline
impact, make the smallest change, test and report evidence. The
[nine change workflows](../development/change-workflows.md) cover driver,
owner/supervisor, API, model/migration, reporting, bug, authentication, deployment
and Android release changes. Documentation updates accompany behavior changes;
ADRs are for meaningful decisions, not every edit.

## D. Documentation authority

| Authority | Purpose |
| --- | --- |
| [Documentation index](../index.md) and section indexes | Entry points; current versus historical evidence |
| [Architecture](../architecture.md), [domain model](../domain-model.md), [ADRs](../adr/README.md) | Boundaries, tenant/auth/offline/data contracts and 19 unique decisions |
| [Development](../development.md), [change workflows](../development/change-workflows.md) | Windows setup, tests, dependency updates and safe feature/fix sequence |
| [Security](../security.md), [data handling](../production-data-handling.md) | Device/session/role/evidence controls, secrets and privacy gates |
| [Production deployment](../production-deployment.md) | Ubuntu setup, domains, approval and one-command release request |
| [Migration/rollback](../production-migration-and-rollback.md) | Independent backups, restore, source/phone migration and non-destructive rollback |
| [Production operations](../production-operations.md) | Health, logs, resources, alerts, incidents and provider portability |
| [Cloud packaging](cloud-packaging.md), [context inventory](build-context-inventory.md) | Exact contexts, runtime bundle, image footprint and capacity budget |
| [Disk audit](local-disk-audit.md), [manual maintenance](local-maintenance.md) | Measured cleanup, protected state and manual retention |
| [Google Play release](../google-play-release.md) | Signing separation, activation onboarding, submission checklist and controlled phone migration |
| [Pilot runbook](../pilot-runbook.md), [mobile Pilot](../mobile-pilot-runbook.md), [signing backup](../mobile-pilot-signing-backup.md) | Preserved Windows/private-APK operations |
| [Engineering audit](../production-engineering-audit.md) | Source-backed maintainability findings and incremental follow-ups |
| [Previous readiness](../production-readiness-report.md), [previous inventory](../production-change-inventory.md), [archive](../archive/README.md) | Dated prior implementation/build evidence, not fresh release approval |

Resolved stale claims: OTP as current authentication, Firebase as a required Play
dependency, incomplete owner/supervisor/meter capability descriptions, incorrect
Pilot signer basename, old VPS Git-checkout delivery and automatic backup pruning.
Legacy OTP/Firebase/PC lab/build reports remain explicitly scoped historical or
optional, not deleted. Existing paths were retained to avoid broken references.
Internal Markdown path checks and unique ADR checks passed; external URL and
heading-anchor crawling is not claimed. The official Play target/testing/signing
pages were rechecked on 2026-10-16; configured target 36 remains consistent with
[Google's requirement](https://developer.android.com/google/play/requirements/target-sdk).
Account-specific [testing requirements](https://support.google.com/googleplay/android-developer/answer/14151465)
and [Play signing](https://support.google.com/googleplay/android-developer/answer/9842756)
still require Console verification.

## E. Cloud packaging and capacity

Native Docker context exports—not estimates based on ignore text—were compared
file-by-file with tracked source hashes. Exact paths/bytes are in the
[176-file inventory](build-context-inventory.md).

| Component | COPY-visible files | Context bytes | Docker controls, separate | Final image bytes |
| --- | ---: | ---: | ---: | ---: |
| API | 106 | 1,379,422 | 3,256 | 877,659,278 |
| Owner/Supervisor web | 38 | 656,019 | 3,132 | 305,548,804 |
| Marketing | 32 | 1,137,641 | 3,301 | 312,619,148 |
| **Total** | **176** | **3,173,082** | **9,689** | **1,495,827,230** |

These are logical contents/image sizes, not compressed traffic or unique layer
allocation. All images are Linux/amd64 and run as UID 10001. Runtime probes found
no tested secret/key/APK/AAB/dump paths under `/app` and no tested development
tool packages. This is not a complete image-content or OS-vulnerability audit.

Approved manual workflow: exact main SHA + successful push CI + protected
environment review → build/push three SHA-tagged images → pinned SSH transfers
only an allowlisted operations archive → VPS pulls images and runs guarded
backup/migration/health steps. No VPS source checkout, application build,
rsync of the laptop, Windows dependencies or private data transfer. The archive
has 20 runtime files plus manifest/release marker. Final synthetic rehearsal:
46,725 runtime bytes, 50,882 total payload bytes, 14,939 compressed bytes.
Its fixture SHA is not an approved release. Build the actual archive from the
final clean commit; [packaging](cloud-packaging.md) records checksum/provenance.

Receiver/deploy/rollback share one lock through atomic pointer activation.
Failed archives/releases remain for inspection. Full-SHA tags refuse overwrite
in this workflow, but registry immutability/signature enforcement is not proven;
resolved digests, registry permissions and image CVEs remain release checks.
Only Caddy is publicly published in production; database, S3, API/Next internal
ports and Caddy admin remain private. Persistent volumes and external private
configuration survive image replacement. No automatic schema downgrade.

**40 GB is conditional, not measured production capacity.** Two application
image sets plus measured infrastructure images total 3,934,374,838 logical bytes
before layer sharing, OS, writable layers and data. Each local backup contains
a full evidence mirror. With `N` retained generations, the next backup peak is
approximately `D + (N+2)E + (N+1)B`; with two generations, `D + 4E + 3B`.
Manual retention can leave more generations. Offsite restore adds another copy.
The 2 GiB database-restore tmpfs must fit alongside the app on a 4 GB host.
Thirty phones alone cannot prove photo growth or sustained performance. Keep
at least 10 GB free and below 75% disk use; measure actual load, recovery time,
photo sizes/rates and retention before accepting this VPS envelope.

## F. Verification and quality

Checks below ran locally on 2026-10-16 unless explicitly historical. Test
fixtures use synthetic data; they do not prove live acceptance.

| Check | Result / evidence |
| --- | --- |
| Backend Ruff/format/mypy | PASS; full initial checks and affected post-fix checks plus canonical `mypy src tests` |
| Backend regression / migrations | PASS: 289 tests, zero failures/errors/skips; dedicated PostgreSQL 17.6; upgrade/check/offline SQL through `0024_company_pin_auth` |
| Flutter format/analyze/tests | PASS: 36 files, zero format changes; no analyzer issues; 164 tests |
| Web lint/typecheck/unit tests | PASS: 71 tests, 15 files |
| Marketing lint/typecheck/unit tests | PASS: 11 tests, 3 files |
| Fresh Linux images | PASS: all three built in Phase 6; API rebuilt after the final Alembic logger fix; unchanged web/marketing builds reused |
| Native contexts/runtime inspection | PASS within the exact scope described above |
| Final API image migration/logging check | PASS: read-only/no-network container generated offline SQL through head and preserved Fleet/Uvicorn loggers; no DB connection |
| Windows release/maintenance helpers | PASS: 212 tests, zero skips; 37 affected disk tests passed again after equivalent test-only typing fixes |
| Linux receiver/shared deployment lock | PASS: 19 receiver + 12 existing deployment tests |
| Linux host-resource guards | PASS: 26 tests |
| Linux backup-retention report guards | PASS: 22 tests |
| Linux smoke-harness safety guards | PASS: 33 tests |
| Compose configuration / Bash syntax | PASS; all production shell scripts parsed |
| Revised real local Docker smoke | PASS: Caddy public/private routing, private ports, restart persistence, data-service guard, DB restore and evidence checksums |
| Gitleaks | PASS: 95 reachable commits (`--all`), 75-file pending-source snapshot and exact 78-file staged text; unreachable loose objects not scanned |
| Actionlint | PASS: all workflow files |
| npm production dependency audits | PASS: zero vulnerabilities in both apps |
| API locked dependency audit | PASS on supported Python 3.12: 69 applicable locked packages, zero known vulnerabilities; Linux-only uvloop metadata audit also zero |
| Image/OS vulnerability scan | NOT VERIFIED: installed Grype has no usable vulnerability database; no private SBOM uploaded |
| Pilot integrity/release checks | PASS: unchanged protected artifacts, configured permanent certificate and package split |
| Internal links / ADRs / agent imports | PASS: 483 local file links across 82 Markdown files including scoped guides; 19 unique ADRs; five imports without cycles; no fresh Claude session or universal external-link crawl |

Real smoke project `fleet-ai-smoke-fjrg5h` used only new synthetic volumes and
loopback ports. Its exact containers were stopped; volumes, containers,
`.production-smoke.fJRg5h`, environment and backups were retained. Log:
`.tmp/phase8-smoke-20261016-210240.log`. Windows ACL compatibility was explicitly
used for its bind-mounted backup directories; this does not prove Ubuntu file
permissions. Host-resource and public DNS/TLS probes were intentionally skipped
in the local smoke. Linux resource thresholds are separately regression-tested.
This full-stack run preceded the narrow Alembic logging fix; the rebuilt final
API has the separate runtime migration/logger check and final backend regressions.
Unchanged routing/storage smoke checks were not unnecessarily repeated.

Representative commands: `ruff check`, `ruff format --check`, `mypy`, `pytest`,
Alembic heads/upgrade/check/offline SQL; `dart format --output=none`,
`flutter analyze`, `flutter test`; each app's `npm run lint`, `npm run typecheck`,
`npm test`, `npm audit --omit=dev --audit-level=high`; native Docker builds/context
exports; `bash scripts/production/local-smoke-test.sh --reuse-images`;
`bash -n`; pinned Actionlint/Gitleaks. Ignored `.tmp/phase8-*` logs retain the
actual output. Sandbox child-process restrictions initially prevented some
commands; authorized reruns were used, not disabled checks. Default pip-audit
tool Python initially could not resolve the locked psycopg wheel; supported
Python 3.12 was selected instead of changing dependencies.

The initial full backend suite collected **288**, not the older reported 283:
the baseline had five later-added exception-logging tests. Both the original
isolated run and a fresh-empty-cwd run reproduced **286 passed / 2 failed**.
Standalone logging tests passed, but Alembic's default `fileConfig` disabled
pre-existing Fleet/Uvicorn loggers when invoked inside the test process. The
narrow fix is `disable_existing_loggers=False` in `migrations/env.py`, with a
new regression asserting those loggers stay enabled. No logger assertion was
removed, no schema revision changed and no production test bypass added. Final
full-suite results in the table replace these failed pre-fix runs, not their retained logs.

The corrected full run used a fresh empty working directory, absolute tests and
configuration, and an explicitly isolated PostgreSQL 17.6 tmpfs database at
`127.0.0.1:15439/fleet_repository_audit_test`. No plugin or Settings modification
was used. Evidence: `.tmp/backend-fixed-clean-cwd-20261016-tl_h32fk`; pytest stage
328.46 seconds (333.83 seconds including runner overhead), with 51 non-failing
warnings for existing Starlette/Alembic deprecations, HTTP status aliases and
cyclic foreign-key ordering. Teardown verified zero remaining public application tables in
that synthetic database and stopped only its own container. Pilot data was not
used. Company-PIN tests cover real service activation, expiration/replay denial,
PIN hashing/lockout, device binding/session revocation, logout/reactivation,
preserved domain records and sequential 30-driver UUID idempotency. This is
automated local coverage, not real-phone acceptance or concurrent load proof.

New tooling also passed Ruff lint/format and strict mypy across 13 Python files.
Four test-only monkeypatch targets now use their directly imported `os` or
`subprocess` modules (the same module objects), resolving strict export typing;
all 37 affected disk tests passed again. Formatter-only wrapping in two Linux
test files preserved identical parsed ASTs. No safety assertion was weakened.

Retained prior evidence, not rerun: 8 fixture-backed web and 17 marketing E2E
tests, and the 82,018,870-byte productionDebug AAB from the baseline. No signed
production AAB exists from this task. Repeating unchanged successful Android
builds was unnecessary. Real-phone activation/update/migration, Play delivery
and internet TLS are **NOT VERIFIED**.

Source-backed maintainability follow-ups are separate from release blockers:
large mobile async/state responsibilities, duplicated assignment logic,
maintenance/report query loops and dashboard error-to-empty fallbacks. These
are P2 risks with proposed boundaries and tests in the engineering audit, not
proven incidents or a reason for a broad rewrite. The immediate unsafe smoke
cleanup and automatic backup-pruning paths were corrected and regression-tested.

## G. Git and release state

Work remains on local `main`; no branch/history rewrite, reset or discarded
work. The [exact changed-file inventory](repository-change-inventory.md) lists
this audit, separate from the earlier production implementation inventory.
The final local commit SHA is provided in the handover after commit creation;
a commit cannot embed its own SHA in its content. Identify this report's commit
with `git log -1 --format=%H -- docs/operations/repository-readiness-report.md`.
Final status and actual bundle construction are checked after the commit.

Nothing was pushed during this task. No VPS was purchased/accessed/deployed,
no DNS changed, no existing Pilot installation or server altered, no signing
key generated/rotated and no Google Play upload/publication performed.

## H. Final decision and blockers

| Area | Decision |
| --- | --- |
| Disk audit, safe cleanup, structure and documentation | PASS within measured/local scope |
| Shared agent guidance | PASS static review; fresh Claude session NOT VERIFIED |
| Local production preparation | PARTIAL overall: implementation/local checks pass, image-CVE and external acceptance remain |
| Cloud deployment ready | BLOCKED by owner-controlled infrastructure/security setup below |
| Live production verified | NOT VERIFIED; no live action authorized or attempted |
| Google Play submission ready | BLOCKED; signing/Console/real-device/privacy gates remain |
| Google Play published | NOT PUBLISHED |

Remaining gates before any release:

1. Owner-provisioned Ubuntu VPS/access, capacity selection, firewall/SSH
   hardening, physical private directories/permissions, production secrets,
   registry read credentials and reviewed immutable-image/digest policy.
2. Approved push and successful CI on the final SHA; actual protected GitHub
   `production`/`google-play-production` reviewers and secrets, pinned host key,
   GHCR permissions and approved workflow dispatch. YAML alone cannot prove them.
3. DNS for the three domains, real certificate issuance/renewal, public/private
   route checks and real browser/phone HTTPS access without Tailscale.
4. Image/OS CVE scan and review, actual host resource/load acceptance, monitored
   disk growth, delivered alerts, external backup credentials, offsite encryption
   and a measured offsite recovery drill. Linux permission checks remain live gates.
5. Reviewed database/evidence cutover using real verified backups, application
   compatibility and rollback rehearsal; marketing-lead backup/retention decision.
   Never overwrite production data or stop the old Pilot as an inferred next step.
6. Separate owner-controlled Play upload credentials/config (currently absent),
   package ownership, Play App Signing and Console/API access. Keep permanent
   Pilot key/package unchanged. Build and validate the actual signed AAB only
   after these are supplied; debug AAB evidence is not a production release.
7. Real-device activation, expiration/replay rejection, PIN/device authentication,
   logout/reactivation, offline/restart/photo/sync and Pilot queue-drain migration
   acceptance. Play package differs: side-by-side controlled migration, not
   in-place upgrade or app-data clearing. Preserve existing driver memberships.
8. Owner-approved privacy/contact/retention/deletion and Data safety declarations,
   final genuine store artwork/screenshots, protected reviewer access and
   account-specific testing/production-access requirements in Play Console.

The intended onboarding remains: **Google Play → install → owner-issued
activation code → activate device → existing PIN/device access**. No SMS OTP,
required Firebase login, manual production server address or private APK updater
in Play. Optional Firebase compatibility stays intact.

Recommended next phase: owner reviews this report and supplies the external
prerequisites, then separately authorizes a staged cloud/device acceptance plan.
No live or publishing step is automatically authorized by this local handover.
