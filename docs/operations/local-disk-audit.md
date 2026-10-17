# Local disk audit — 2026-10-16

## Scope and measurement

Baseline revision: `06ecbc457d7e2fc0795310636fea0064f47ab0ff`, branch `main`.
Actual checkout: `D:\Git\fleet maneger\fleet manager`; parent: `D:\Git\fleet maneger`.
The parent contains this checkout and an empty `.phase7-backups` directory.
No source or release changes preceded this measurement; audit scripts, fixtures and JSON
reports were added locally during measurement.

`scripts/maintenance/disk_audit.py` scans metadata, including hidden and ignored files,
without following reparse points. The verified baseline `.tmp/disk-audit-before-final.json`
has **73,364 files, zero scan errors and zero skipped links**. Earlier experimental
inventories are superseded. Long Windows paths and hard links have regression tests.
Reports contain paths and sizes, not file contents; keep detailed local inventories private.

| Measurement | Parent | Checkout |
| --- | ---: | ---: |
| Logical bytes | 9,061,245,478 | 9,061,245,478 |
| Referenced file allocation bytes | 9,179,024,528 | 9,179,024,528 |
| Unique file allocation bytes within scan | 9,179,024,336 | 9,179,024,336 |

Logical size is 9.061 GB / 8.439 GiB, consistent with the reported approximately 8.42 GB
Windows footprint, with later audit activity accounting for some variation. Allocation
uses Windows `FILE_STANDARD_INFO.AllocationSize`, not rounded logical sizes;
[Microsoft documents this field](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_standard_info).
Small NTFS resident files can have sub-cluster allocations. Directory metadata, filesystem
overhead and hard links outside the scan are not measured: this is not a free-volume-space
reading. Overlapping directory totals below must not be added together.

## Classification and immediate children

A = tracked source; B = development dependencies; C = regenerable output;
D = protected state/metadata; E = release/signing artifacts; F = investigate/retain.
Conservative scanner categories are not deletion permission. `.runtime` is protected
even when some descendants resemble build outputs. Pilot intermediates remain untouched.

| Baseline category | Logical bytes | Decision |
| --- | ---: | --- |
| A | 5,716,037 | Retain all tracked files |
| B | 1,326,585,797 | Retain useful installed dependencies |
| C | 4,327,022,562 | Only individually verified allowlisted targets may be removed |
| D | 1,518,635,614 | Retain all |
| E | 1,562,137,171 | Retain all |
| F | 321,148,297 | Retain except inspected Docker export reclassified C |

Git-ignored files total **8,819,456,770 bytes** (overlaps categories above). Main `.git`
is **236,043,045 bytes**. Tracked source is only **5,716,037 bytes**, not a multi-GB deployment.

| Immediate checkout child | Logical bytes | Dominant class / interpretation |
| --- | ---: | --- |
| `apps` | 5,870,044,398 | B/C/E; Flutter builds and both Next applications |
| `.runtime` | 1,282,348,557 | D; protected historical checkout, logs and QA evidence |
| `dist` | 1,042,136,162 | E/F; versioned Pilot releases, retain |
| `services` | 295,290,258 | B/C/A; API venv 211,852,468 bytes plus caches/source |
| `.tmp` | 246,244,750 | F/D; includes verified 202,826,240-byte Docker export |
| `.git` | 236,043,045 | D; retain, no garbage collection |
| `.mypy_cache` | 74,292,966 | C; retained |
| `outputs` | 10,709,054 | F; retain QA/release evidence |
| `.pytest_cache` | 2,147,437 | C; retained |
| `scripts` | 1,338,232 | A/C; source and Python caches |
| `docs` | 362,312 | A |
| `__pycache__` | 71,621 | C |
| `.github` | 18,447 | A |
| `infra` | 16,533 | A |
| `.uv-cache`, `.tmp-uv-cache`, `.ruff_cache` | 3,344 / 1,694 / 918 | C |
| `.pytest-build28`, two `pytest-cache-files-*` directories | 0 | Empty; retained |

The inventory also includes root-level files. `.dart_tool`, Android Gradle outputs,
coverage and Playwright results were inspected; they are included above, not omitted.
No second useful Python environment was identified within the scan. External SDKs,
user Gradle/Playwright caches and Docker Desktop's virtual disk are outside these totals.

## Top 25 directories

Paths are checkout-relative; parent and checkout totals are shown above instead of
duplicating them in this ranked list. Descendant rows overlap their ancestors.

| Directory | Logical bytes | Class |
| --- | ---: | --- |
| `apps` | 5,870,044,398 | A/B/C/E |
| `apps/mobile` | 3,834,207,619 | A/C/E |
| `apps/mobile/build` | 3,483,669,673 | C/E/F |
| `apps/mobile/build/app` | 3,307,386,239 | C/E/F |
| `apps/mobile/build/app/intermediates` | 2,989,026,864 | C/E |
| `apps/mobile/build/app/intermediates/merged_native_libs` | 1,914,845,980 | C |
| `apps/mobile/build/app/intermediates/merged_native_libs/productionDebug` | 1,390,815,720 | C |
| `apps/mobile/build/app/intermediates/merged_native_libs/productionDebug/mergeProductionDebugNativeLibs` | 1,390,815,720 | C |
| `apps/mobile/build/app/intermediates/merged_native_libs/productionDebug/mergeProductionDebugNativeLibs/out` | 1,390,815,720 | C |
| `apps/mobile/build/app/intermediates/merged_native_libs/productionDebug/mergeProductionDebugNativeLibs/out/lib` | 1,390,815,720 | C |
| `.runtime` | 1,282,348,557 | D |
| `apps/web` | 1,265,179,025 | A/B/C |
| `.runtime/release-build28-20261012-064216` | 1,239,780,354 | D/E |
| `.runtime/release-build28-20261012-064216/apps` | 1,233,656,944 | D |
| `.runtime/release-build28-20261012-064216/apps/mobile` | 1,231,645,533 | D |
| `.runtime/release-build28-20261012-064216/apps/mobile/build` | 1,073,330,463 | D |
| `dist` | 1,042,136,162 | E/F |
| `.runtime/release-build28-20261012-064216/apps/mobile/build/app` | 980,315,996 | D |
| `apps/marketing` | 770,657,754 | A/B/C |
| `.runtime/release-build28-20261012-064216/apps/mobile/build/app/intermediates` | 755,433,381 | D |
| `apps/mobile/build/app/intermediates/merged_native_libs/productionDebug/mergeProductionDebugNativeLibs/out/lib/arm64-v8a` | 646,036,080 | C |
| `apps/web/.next` | 644,551,859 | C/F |
| `apps/web/node_modules` | 619,635,744 | B |
| `apps/web/.next/dev` | 598,716,932 | C |
| `apps/mobile/build/app/intermediates/merged_native_libs/pilotRelease` | 524,030,260 | C; protected Pilot scope |

## Top 30 individual files

Aliases below only shorten paths in this table:
`M=apps/mobile/build/app/intermediates`, `R=.runtime/release-build28-20261012-064216/apps/mobile/build`,
`N=merged_native_libs`, `P=productionDebug/mergeProductionDebugNativeLibs/out/lib`,
`L=pilotRelease/mergePilotReleaseNativeLibs/out/lib`,
`W=apps/web/.next/dev/cache/turbopack/v16.3.5-ca2c75eb`.

| File (expand aliases above) | Logical bytes | Class |
| --- | ---: | --- |
| `M/N/P/arm64-v8a/libflutter.so` | 395,316,440 | C |
| `M/N/P/x86_64/libflutter.so` | 390,001,840 | C |
| `M/N/P/armeabi-v7a/libflutter.so` | 348,884,936 | C |
| `M/N/P/arm64-v8a/libVkLayer_khronos_validation.so` | 248,644,248 | C |
| `W/00000264.sst` | 244,079,313 | C |
| `M/intermediary_bundle/productionDebug/packageProductionDebugBundle/intermediary-bundle.aab` | 242,982,604 | E; retain |
| `M/module_bundle/productionDebug/buildProductionDebugPreBundle/base.zip` | 242,181,302 | C; retain |
| `.tmp/fleet-api-ci.tar` | 202,826,240 | C after inspection |
| `.git/objects/62/14898fc7825f383a29923ac8643d5eafdd850b` | 200,899,387 | D |
| `M/N/L/x86_64/libflutter.so` | 165,996,904 | C; retain Pilot |
| `R/app/intermediates/N/L/x86_64/libflutter.so` | 165,996,904 | D |
| `M/N/L/arm64-v8a/libflutter.so` | 165,164,528 | C; retain Pilot |
| `R/app/intermediates/N/L/arm64-v8a/libflutter.so` | 165,164,528 | D |
| `W/00000263.sst` | 159,715,959 | C |
| `M/N/L/armeabi-v7a/libflutter.so` | 151,593,280 | C; retain Pilot |
| `R/app/intermediates/N/L/armeabi-v7a/libflutter.so` | 151,593,280 | D |
| `apps/web/node_modules/@next/swc-win32-x64-msvc/next-swc.win32-x64-msvc.node` | 110,263,296 | B |
| `apps/marketing/node_modules/@next/swc-win32-x64-msvc/next-swc.win32-x64-msvc.node` | 110,263,296 | B |
| `apps/web/node_modules/@next/.swc-win32-x64-msvc-PkAt0JZr/next-swc.win32-x64-msvc.node` | 106,188,800 | B; investigate before removal |
| `apps/mobile/build/app/outputs/bundle/productionDebug/app-production-debug.aab` | 82,018,870 | E; debug evidence, not Play release |
| `M/flutter/productionDebug/flutter_assets/kernel_blob.bin` | 73,635,136 | C |
| `M/assets/productionDebug/mergeProductionDebugAssets/flutter_assets/kernel_blob.bin` | 73,635,136 | C |
| `apps/mobile/.dart_tool/flutter_build/c8a17e53d9feac21fdf2fe3be1c3292b/app.dill` | 73,635,136 | C |
| `apps/mobile/build/test_cache/build/9a5e08a3f9d61706864f2c784f419fa5.cache.dill.track.dill` | 68,475,080 | C |
| `apps/mobile/build/release/FleetAI-Systems-Company-PIN-1.0.24-pilot-29.apk` | 64,623,060 | E |
| `apps/mobile/build/app/outputs/flutter-apk/app-pilot-release.apk` | 64,623,060 | E |
| `apps/mobile/build/app/outputs/apk/pilot/release/app-pilot-release.apk` | 64,623,060 | E |
| `R/release/FleetAI-Systems-Company-PIN-1.0.23-pilot-28.apk` | 63,840,903 | D/E |
| `R/app/outputs/flutter-apk/app-pilot-release.apk` | 63,840,903 | D/E |
| `R/app/outputs/apk/pilot/release/app-pilot-release.apk` | 63,840,903 | D/E |

## Protected and duplicate material

- Historical release checkout `.runtime/release-build28-20261012-064216` is clean at
  `ec14113e367a5530d4e6c85983f0c4bda483e611`, an ancestor of the current revision.
  Its release outputs and QA artifacts are protected, not an abandoned disposable clone.
  Tiny nested Git repositories under `.tmp/disk-audit-tests-approved*` are synthetic
  audit tests, not additional application checkouts; their Git directories are retained.
- `.runtime` contains screenshots, UI dumps and acceptance evidence potentially carrying
  private data. No assumption that all runtime data is a cache is made.
- The large loose Git blob hashes to the same content as the inspected Docker image tar.
  No reference was found in current refs, reflogs or index; why it was created is unproven.
  It consumes about 85% of main `.git`, but is **not removed or garbage-collected**.
- The tar manifest identifies image `fleet-api:ci`, not a database/evidence backup.
- Coverage (`services/api/coverage.xml`, `.coverage`, mobile LCOV) and browser result
  markers are retained. XML shows 9,034/10,573 covered lines (85.44%). These files do not
  independently prove historical test counts. The committed readiness report records
  283 backend / 164 Flutter / 37 release-helper tests; those are prior-run evidence,
  not freshly executed results in this phase.
- Environment files, local Android configuration, signing files, all APK/AAB releases,
  database/evidence storage and unknown files remain protected.

## Docker Desktop storage — separate from checkout

`docker system df` snapshot: images **4.23 GB** (15, 2 active; 2.544 GB reclaimable),
build cache **6.669 GB** (78, 9 active; 6.044 GB reclaimable), containers **77.82 kB**
(2 active), local volumes **172.8 MB** (4, 2 active; reported reclaimable 0).
Image/cache accounting can overlap; do not add these figures as unique physical usage.
Docker's Linux root is `/var/lib/docker`; Windows virtual-disk allocation was not measured.

Protected active volumes: `fleet-manager_postgres_data` approximately 154.8 MB and
`fleet-manager_minio_data` approximately 18.06 MB. PostgreSQL and MinIO remain running;
their published ports are loopback-only. The two small additional volumes are retained.
No Docker prune, volume deletion, service shutdown or live infrastructure change is authorized.

## Verified cleanup plan (Phase 1 conclusion)

| Exact checkout-relative target | Files | Logical bytes | Regeneration cost |
| --- | ---: | ---: | --- |
| `.tmp/fleet-api-ci.tar` | 1 | 202,826,240 | Export retained/rebuilt Docker image again |
| `apps/web/.next/dev/cache` | 164 | 487,800,317 | Cold Next development compilation/image cache |
| `apps/marketing/.next/dev/cache` | 79 | 169,203,546 | Cold Next development compilation/image cache |
| `apps/mobile/build/app/intermediates/merged_native_libs/productionDebug` | 16 | 1,390,815,720 | Gradle native-library merge from retained engine/plugin caches |
| Total | 260 | 2,250,645,823 | Dependencies, complete AAB and Pilot outputs retained |

All targets were inspected for tracked files, protected names, reparse points and exclusive
file-open conflicts. No Next/Flutter/Gradle build client was detected; the Gradle daemon's
last explicit state was idle. Activity and locks must be checked again immediately before
removal. Native engine JARs with matching library sizes remain in Gradle's dependency cache.
Phase 1 only measured and classified; the subsequent authorized cleanup is recorded below.

## Phase 2 — guarded cleanup and verification

On 2026-10-16, the four exact targets above were removed using the reviewed manual
`scripts/maintenance/cleanup-generated.ps1 -Apply` utility. Its default mode is report-only.
It rejects non-allowlisted paths, tracked files, unexpected/protected content, reparse
points, hardlinks, open handles, changing inventories and detected build clients.
The Docker export additionally requires the exact audited size and SHA-256. Directory
removal is guaranteed nonrecursive, including when an unexpected child appears.
The script is not a concurrent janitor: any retained Gradle daemon must independently
be confirmed idle. This was refreshed at 14:29:54 UTC immediately before application.

The command completed successfully and removed **260 files / 2,250,645,823 logical
bytes (2.251 GB / 2.096 GiB)**. These files had **2,251,017,944 referenced allocation
bytes** at baseline and single links at removal. This does not claim an equivalent
free-volume-space increase, because NTFS metadata and concurrent volume activity differ.
Removal is not recycle-bin recoverable; the documented build/export operations regenerate
the outputs. No database, photograph, unsynchronised record, release, signing material,
Git object, dependency environment or Docker volume was removed.

Verification:

- 37 read-only inventory tests and 29 cleanup safety tests passed (including default
  report-only behavior, Git failures, protected files, locks, links and directory races).
- Independent comparison of 23 protected files: identical SHA-256 and sizes; absent
  `android/key.properties` remained absent. Main and historical Pilot APKs, debug AAB,
  Android/package configuration and coverage evidence survived unchanged.
- All four targets are absent; `git diff --exit-code HEAD` and `git diff --check` passed.
  Only this task's new maintenance scripts and operations documentation were untracked.
- Installed Python 3.12.10 / pytest 8.4.1, Node 24.19.0 / npm 11.17.0 and Flutter 3.47.5 /
  Dart 3.13.4 remain available. npm still exposes both applications' normal development,
  lint, typecheck, test and build commands. No development service was started merely
  to recreate the deleted caches. Application regression results are reported separately.
- This host's inaccessible WindowsApps `pwsh` alias initially prevented Flutter startup;
  removing only that PATH entry in the check process made the version check pass.
  Global PATH, SDK configuration and installed Pilot were not changed.

Detailed local evidence (ignored, not uploaded): `.tmp/cleanup-apply-result.txt`,
`.tmp/cleanup-protected-before.json`, `.tmp/cleanup-protected-after.json` and the
before/after disk inventories. These paths may include private workstation metadata.

The post-cleanup snapshot completed at **14:33:30 UTC**, with **zero errors** and one
deliberately skipped synthetic junction created by the cleanup safety test. No real
application directory was skipped. Parent and checkout totals remain equal.

| Category / measurement | Before bytes | After bytes | Net reduction bytes | Class |
| --- | ---: | ---: | ---: | --- |
| Tracked source | 5,716,037 | 5,716,037 | 0 | A |
| Dependencies | 1,326,585,797 | 1,326,585,797 | 0 | B |
| Classified generated output | 4,327,022,562 | 2,279,252,794 | 2,047,769,768 | C |
| Protected state/metadata | 1,518,635,614 | 1,518,635,931 | -317 | D |
| Release/signing category | 1,562,137,171 | 1,562,137,225 | -54 | E |
| Initially unknown, including inspected tar | 321,148,297 | 121,888,156 | 199,260,141 | F |
| Total logical bytes | 9,061,245,478 | 6,814,215,940 | **2,247,029,538** | All |
| Referenced allocation bytes | 9,179,024,528 | 6,931,644,656 | **2,247,379,872** | All |

The net folder reduction is **2.247 GB**, slightly below the **2.251 GB actually removed**:
audit scripts/reports/test fixtures added a net 3,616,285 bytes between the two snapshots.
The tiny D/E increases are synthetic protected-name fixtures, not changes to real protected
assets. Metadata scans are point-in-time observations, not atomic filesystem snapshots;
their own newly written JSON output is not included until a subsequent scan.
After-scan source/report edits and later verification caches can change the final folder
size. No claim is made that development caches will never grow again.

## Final verification snapshot

At 16:01:53 UTC, after the final regressions and image/context work, parent and
checkout each measured **6,902,939,448 logical bytes**; referenced allocation
was **7,028,281,376 bytes**, unique allocation **7,028,281,056 bytes**, across
81,286 regular files. The scan had zero errors and skipped only two synthetic
junction fixtures under `.tmp`; no real application directory was skipped.
Evidence: `.tmp/disk-audit-final-verification-20261016.json` (ignored).

That is **2,158,306,030 fewer logical bytes than baseline**, after 88,723,508 bytes
of net verification/documentation growth since the immediate post-cleanup scan.
It does not change the measured 2,250,645,823 bytes actually removed. The final
scan's own report and subsequent report/Git metadata are naturally outside that
point-in-time count. No additional cleanup was performed.

A staged-source snapshot contained 513 files / 6,044,957 logical worktree bytes
before the final result annotations. Final Docker Desktop summary (separate
storage): 19 images / 4.689 GB, 98 cache records / 7.344 GB, 14 containers /
630.8 kB (only the two preserved Pilot containers running), nine volumes /
240.8 MB. Categories overlap; stopped retained containers can still reference
images/volumes. No resource was pruned to reduce these figures.

## Subsequent final safe cleanup (2026-10-16)

This is a later, separate cleanup of the same checkout. The previous snapshots
above remain historical measurements; this section records the latest verified
snapshot. The parent directory and checkout measured identically. The scans had
zero errors and skipped only two synthetic test junctions under `.tmp`.

| Checkout measurement | Before | After | Net reduction |
| --- | ---: | ---: | ---: |
| Logical bytes | 6,906,911,446 | 5,333,043,971 | **1,573,867,475 (1.574 GB)** |
| Referenced allocation bytes | 7,031,259,720 | 5,439,803,144 | 1,591,456,576 |
| Tracked source bytes | 6,047,965 | 6,047,965 | 0 |
| Regular files | 80,661 | 73,209 | 7,452 |

The before scan was at 16:17:52 UTC and the after scan at 16:50:49 UTC. These
are point-in-time file measurements, not a measurement of free space on the
Windows volume. The after scan excludes its own report and later metadata.

An exact-path, hash-checked initial pass removed **9,169 generated files across
81 measured roots (1,575,378,060 bytes)**. The principal groups were:

| Verified disposable group | Bytes | Reason |
| --- | ---: | --- |
| `apps/mobile/build/app/intermediates/*/productionDebug` | 833,722,356 | Generated debug Gradle intermediates; retained final AAB and Pilot outputs |
| Old Flutter build cache | 74,340,820 | Regenerable productionDebug compiler state |
| Flutter test cache and unit test assets | 70,506,378 | Regenerated by local tests |
| Two unreferenced retired native dependency copies in web `node_modules` | 125,579,264 | Active SWC and Sharp versions remained installed and passed builds |
| Python mypy/pytest/Ruff and Next development/cache output | 471,229,242 | Regenerated by the verified development and checking commands |

After verification regenerated build/test output, a second exact-path pass
removed **7,221 files across 88 measured roots (2,639,294,953 bytes)**. This
second gross deletion is **not additional net savings**: much of it recreated
files removed in the initial pass. Both deletion receipts matched their
individual file plans on path, size and file count. The ignored local evidence
is `.tmp/final-safe-cleanup-report.txt`, the two
`.tmp/final-cleanup-files-*-plan.json` files, their receipts, and before/after
inventories. The text report gives every nonempty removed root and the latest
top 20 directories; the plans retain every exact deleted file path and hash.
These workstation-specific inventories are not included in Git.

Docker Desktop was accounted for separately. The local Linux engine's cache
records decreased from **7,343,616,363 to 3,539,691,820 bytes** (a
3,803,924,543-byte accounting reduction). Exactly 42 reviewed old unused
cache records (3,803,527,231 recorded bytes) and eight unused records created
by the extra offline verification probe (290,000,896 recorded bytes) were
removed by exact ID. Record sizes changed during builds, so sums of deleted
record sizes must not be presented as host disk savings. Four dependency-held
old cache records were retained. Twelve stopped isolated test containers
(552,960 writable-layer bytes), five synthetic smoke-test volumes (68,032,510
recorded bytes), and one empty smoke network were removed by exact identity.
All 19 images were preserved. Both original Pilot PostgreSQL/MinIO containers
remained healthy with unchanged identities and mounts; their data volumes were
retained. Two unknown zero-byte volumes were also retained. The separate
`.tmp/final-cleanup-docker-deletions.txt` ledger lists every removed ID/name,
measured bytes and reason. There was no global prune or VHD compaction.

Verification after cleanup: Flutter analysis and **164 tests**; web build,
lint, typecheck and **71 tests**; marketing build, lint, typecheck and **11
tests**; Python Ruff/format/mypy checks; **134** packaging and release-contract
tests; isolated loopback Next development checks; offline Gradle intermediate
packaging; standard Linux/amd64 API, web and marketing Docker builds; and
Compose configuration. The extra API Docker build with `--network=none` failed
to resolve `hatchling` from the package index; the normal documented build
subsequently passed without changing source or locks. That offline-only probe
does not establish that an air-gapped build is supported.

All **2,957 unique protected/source paths** had identical before/after hashes.
The external permanent Pilot keystore hash, current/rollback release artifacts,
Pilot APK package and signer were verified. `.runtime`, `dist`, Git history,
signing material, active environments, business data, backups and unknown
artifacts remained. Old releases and the historical `.runtime` checkout are
archive candidates only until their recovery role is resolved. No source
changes or new release approval resulted from this cleanup; production and
Google Play gates remain in the [repository readiness report](repository-readiness-report.md).
