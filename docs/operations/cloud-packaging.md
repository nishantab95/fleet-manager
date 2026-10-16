# Cloud packaging and disk-capacity review

Status: local packaging/build verification completed on 2026-10-16; no live
deployment or Play publication. This guide describes the checked-in pipelines and storage
costs. Use [production deployment](../production-deployment.md) and
[migration/rollback](../production-migration-and-rollback.md) as the command
authority, and the [readiness report](../production-readiness-report.md) for
external release gates.

## What moves where

| Path | Actual behavior | Not transferred by this path |
| --- | --- | --- |
| Laptop to repository | Only explicitly committed/pushed Git content is available to remote workflows | Ignored local dependencies, Flutter/Next outputs, `.runtime`, local evidence, signing files, and Docker Desktop storage |
| [CI](../../.github/workflows/ci.yml) | Checks source, tests, migrations and three image builds on GitHub runners; uploads backend XML and mobile LCOV coverage with 14-day retention | No VPS deployment; no production image push; no signed Play publication |
| [Approved server release](../../.github/workflows/production-deploy.yml) | Builds/pushes API, web and marketing images to GHCR; uses pinned-host SSH to run the selected revision on the VPS | No laptop working-tree copy and no Android release |
| [Approved Play release](../../.github/workflows/google-play-release.yml) | Tests/builds signed production AAB, validates identity, uploads that AAB as a 30-day Actions artifact, then commits the selected Play edit | No backend deployment, Pilot APK update, or private signing-key artifact upload |

The approximately 8.44 GiB pre-cleanup checkout in the
[disk audit](local-disk-audit.md) is not a deployable artifact and is never
uploaded wholesale by these workflows. Its generated builds, dependencies,
historical runtime material and local Docker export are not application source.
Git-tracked files measured 5,716,037 bytes at the baseline revision; subsequent
documentation/tooling changes alter that number. Git object storage and image
layers are separate accounting categories.

### VPS operations-only delivery

The production workflow creates an explicitly allowlisted operations archive
with [the builder](../../scripts/build_deploy_bundle.py), transfers it using
pinned-host SSH/SCP, and runs
[the receiver](../../scripts/production/receive-deploy-bundle.sh). There is no
VPS Git clone/fetch, full-checkout archive, `rsync`, or on-server application build.
The receiver itself is a reviewed CI helper sent over SSH stdin, not an extra
file in the runtime archive.

The builder requires the requested full SHA to equal HEAD, rejects changed,
untracked/missing/nonregular/link/reparse allowlist paths, reads committed Git
blobs and creates a deterministic new archive without overwrite. It adds
`release.sha` and a JSON manifest containing commit, path, SHA-256, size and mode.
Shell files are 0755; nonsecret configuration is 0644. Secrets, example
environments, Git, application source, tests, local smoke and Play upload helpers
are excluded by the fixed allowlist, not merely by ignore patterns.

The receiver verifies the archive SHA-256 transmitted over authenticated SSH,
extracts into a new `/opt/fleet-ai/releases/<SHA>` using GNU tar's
`--keep-old-files --no-same-owner --no-same-permissions`, and refuses existing
release paths. It trusts the fixed builder plus approved checksum; it is not a
general-purpose safe unpacker for arbitrary archives. The shared deployment lock
remains held through child deployment and atomic activation of the stable
`/opt/fleet-ai/repository` symlink. Real checkouts, unmanaged/dangling symlinks and
symlinked deployment directories are refused. Failed incoming archives and
partial/older release directories remain for review, never automatic deletion.

The Phase 6 rehearsal packaged 20 operations files: **40,871 bytes**, or
**45,027 bytes** including manifest/release marker (22 entries). The gzip archive
was **12,913 bytes**, SHA-256
`77e6affd08f33cd7ac866d793d7a48f6735f5163e0121bddb2994f8c44a6a541`.
Only copied files were committed in an isolated synthetic repository:
`8d91a0863f9ba57ac9093e0c352b133181c216ca` is a **fixture SHA, not an approved
release SHA**. Later maintenance edits/final commit require a new measurement;
these numbers describe this dated rehearsal only.

After the Phase 7 retention/resource changes, the final local rehearsal measured
**46,725 bytes** in the same 20 runtime files, **50,882 bytes** including the
manifest/marker, and **14,939 bytes** compressed. Archive SHA-256:
`c3723609714b9f0aebb532af7c4bf93d09ff7f99c06c1fd15cce4ff1c0d3f68b`.
Its synthetic fixture SHA is `ef233cfda1b9acd551df7ac25bcdd7aa9bfd8fe1`, not
the final repository commit. PostgreSQL/MinIO configuration hashes still matched.
The final approved commit must generate its own archive; commit markers and
gzip size/checksum change with that commit. See the
[consolidated audit report](repository-readiness-report.md) for final verification.

The allowlist comprises four Compose/Caddy/MinIO files, four systemd units and
twelve runtime shell helpers. The builder's `ALLOWLIST` and each actual manifest
are authoritative. Native Compose `config --hash` for PostgreSQL and MinIO was
identical between checkout and extracted rehearsal paths, verifying stable
data-service identity across bundle roots. No containers were started by that check.

Exact Phase 6 rehearsal allowlist (normalized Git payload bytes):

| Archive path | Bytes |
| --- | ---: |
| `infra/production/Caddyfile` | 1,668 |
| `infra/production/docker-compose.yml` | 8,506 |
| `infra/production/init-minio.sh` | 755 |
| `infra/production/minio-evidence-policy.json` | 445 |
| `infra/production/systemd/fleet-ai-backup.service` | 539 |
| `infra/production/systemd/fleet-ai-backup.timer` | 215 |
| `infra/production/systemd/fleet-ai-health.service` | 463 |
| `infra/production/systemd/fleet-ai-health.timer` | 203 |
| `scripts/production/backup-and-verify.sh` | 528 |
| `scripts/production/backup.sh` | 3,404 |
| `scripts/production/common.sh` | 4,589 |
| `scripts/production/data-service-guard.sh` | 2,552 |
| `scripts/production/deploy.sh` | 2,980 |
| `scripts/production/healthcheck.sh` | 2,529 |
| `scripts/production/offsite-backup.sh` | 1,596 |
| `scripts/production/prune-local-backups.sh` | 989 |
| `scripts/production/rollback.sh` | 1,320 |
| `scripts/production/validate-config.sh` | 3,220 |
| `scripts/production/verify-backup.sh` | 2,934 |
| `scripts/production/verify-offsite-backup.sh` | 1,436 |
| Generated `release.sha` | 41 |
| Generated `deploy-manifest.json` | 4,115 |
| **Total payload, excluding tar/gzip framing** | **45,027** |

## Application image boundaries

| Image | Recipe and copied build inputs | Final runtime contents |
| --- | --- | --- |
| API | [Dockerfile](../../services/api/Dockerfile): locked Python metadata, `alembic.ini`, migrations and API `src` | Linux production dependency environment, API source and migrations; non-root application user |
| Owner/Supervisor web | [Dockerfile](../../apps/web/Dockerfile): web package/lock files and web source; runner performs `npm ci` and Next build | Next standalone runtime and static assets, not the Windows `node_modules` or `.next/dev` cache |
| Marketing | [Dockerfile](../../apps/marketing/Dockerfile): separate marketing package/lock files and source | Separate Next standalone runtime, static/public assets; lead storage is an external mount |

All builds use the repository root as context, with Dockerfile-specific ignore
files restricting each context independently. The root
[`.dockerignore`](../../.dockerignore) is hardened as a fallback. Context exclusion
and runtime inspection are separate checks: a small image alone does not prove
secrets were absent from the builder. See the
[exact native context inventory](build-context-inventory.md) for all paths,
measurement method and Docker control-file caveats.

### Local verification measurements

| Measurement | Evidence status |
| --- | --- |
| API COPY-visible context | 106 files, 1,379,422 bytes after final logging fix; controls separately 3,256 bytes |
| Web COPY-visible context | 38 files, 656,019 bytes; controls separately 3,132 bytes |
| Marketing COPY-visible context | 32 files, 1,137,641 bytes; controls separately 3,301 bytes |
| Final API image logical size after logging-bootstrap fix | 877,659,278 bytes |
| Fresh web image logical size | 305,548,804 bytes |
| Fresh marketing image logical size | 312,619,148 bytes |
| Runtime inspection | All three Linux/amd64, UID 10001; no tested `.env`, signing-key, APK/AAB or dump paths under `/app`; API pytest/Ruff/mypy and Next ESLint/Vitest/Playwright packages absent |
| Container image/OS CVE scan | Not established by dependency audits or image-size checks; external release gate remains |

Native context exports contain 176 tracked files totaling 3,173,082 bytes; each
matched its source hash, with no untracked file exported. Six Docker control
files add 9,689 bytes but are not ordinary `COPY .` inputs. These are logical
contents, not network-compressed transfer measurements.

The three verified application images sum to 1,495,827,230 logical bytes
(approximately 1.496 GB). Shared layers reduce unique storage; registry
compression, container writable layers, and Docker's physical allocation differ.
Do not equate this sum with download traffic or exact VPS disk consumption.

Final local image IDs (not pushed registry digests): API
`sha256:443e66713ccc9318cd9b4bf9dc99195541635e04c045b3df9dc1926d8628a678`, web
`sha256:d28315f909e28a4d4b7a8a7528c391c1433de7ea89df22a288be932708bd00a0`, marketing
`sha256:e05dee832c087e1bfd7604e7eae79d99b2b5a22a093513474923f2c75ec9dd27`.
Only API was rebuilt after the final Alembic logger-preservation correction.
Its read-only, no-network container generated migration SQL through head and
verified existing loggers remained enabled. Unchanged browser builds were reused.

## Approval, image identity and credentials

The server workflow is `workflow_dispatch` only, requires the confirmation text,
checks the requested 40-character SHA against the checkout and `main` ancestry,
and requires successful push CI for that exact SHA. The `production` environment
must actually be configured with the required reviewers/restrictions; a YAML
environment name alone does not create human approval protection.

It refuses to publish an already existing full-SHA application tag. GHCR writes
use the runner's package-scoped GitHub token. The VPS separately needs
no Git access, only a GHCR package-read credential configured for its
deployment account. SSH uses the owner-supplied known-host identity and private
key, not trust-on-first-use. These credentials must not be committed or placed
in an image/context.

Application pulls use full-SHA **tags**; successful deployment records their
resolved registry digests. The current pipeline does not pin the Compose pull
to a preapproved digest or verify an image signature/attestation. Tag immutability
therefore relies on workflow refusal and registry write-access policy, not an
immutable-registry guarantee. Upstream PostgreSQL/MinIO/Caddy and builder images
also use version tags. Review registry permissions, actual resolved images and
image-CVE results before live approval; do not claim bit-for-bit reproducibility
from source/lockfile checks alone.

Play has a separate protected environment, upload identity, scoped Android
Publisher token and explicit track/status selection. It fixes cloud HTTPS and
`company_pin` and disables private APK sideload updating. Its signing credentials
remain runner-temporary/external inputs; the uploaded artifact is the AAB only.
See [Play instructions](../google-play-release.md) for the distinct Pilot package
and controlled device migration.

## Runtime state and exposure

Production [Compose](../../infra/production/docker-compose.yml) has no application
`build` definitions. Only Caddy publishes 80/TCP and 443/TCP/UDP by default.
PostgreSQL, MinIO API/console, FastAPI, and Next.js ports are not host-published.
Caddy's admin listener is container-loopback-only. The Docker backend bridge is
shared; do not describe the marketing container as being on a separately isolated
network. Authentication and the private routing rules remain necessary.

Persistent state is outside application images:

- Named volumes: PostgreSQL data, MinIO evidence, Caddy data and configuration.
- Host directories: marketing leads, backup generations, deployment state/history.
- External private files: production environment, Restic settings/password and
  registry/SSH credentials.

Routine releases verify established data-service configuration, pull application
images, back up the running release, verify restore/checksums/offsite copy, then
run forward migration and application-only starts. Rollback retains schema/data
and the invoking bundle's configuration; explicit configuration rollback uses a
reviewed previous bundle and pointer reconciliation. It does not make a
destructive downgrade safe.
No source/image-size optimization authorizes deleting these persistent stores.

## Can 40 GB support two PCs and thirty phones?

It is a conditional starting envelope, **not an unconditional fit**. User counts
alone do not establish evidence growth, retained history, reporting load, backup
duration or peak memory. A provider's 40 GB disk is about 37.25 GiB before its
filesystem/OS overhead. Apply the existing runbook's free-space reserve, and
measure on the actual host before acceptance.

The baseline local smoke used only tiny synthetic data: PostgreSQL 66,476 KiB
and MinIO 156 KiB, with an approximately 317 MiB idle container-memory snapshot.
Those figures do not predict production storage or sustained concurrent uploads.
The two active laptop Pilot Docker volumes are also not the future VPS dataset.

### Storage budget that must be measured

Let `E` be live evidence bytes, `D` live PostgreSQL bytes, and `B` the compressed
database dump size. They are different measurements.

- Three rebuilt application images total about 1.50 GB logically. Keeping current
  and previous application sets plus the measured PostgreSQL/MinIO/Caddy images
  totals 3,934,374,838 bytes before layer sharing, writable layers and metadata
  (infrastructure images alone: 942,720,378 bytes).
  Deployment does not automatically prune older image versions; repeated releases
  can retain more than two sets.
- [Backup creation](../../scripts/production/backup.sh) makes a full local evidence
  mirror for every generation. Restic deduplication offsite does not deduplicate
  those local mirrors. With `N` retained local generations, steady data/backup
  storage is approximately `D + (N+1)E + NB`.
- A new generation is created and verified/offsite-copied before separately
  approved retention. Peak storage is approximately `D + (N+2)E + (N+1)B`.
  With exactly two retained completed generations, this is `D + 4E + 3B`, not
  just `D + E`. Retention is not permission for automatic deletion: completed
  and failed generations can grow without bound until reviewed maintenance.
  The hygiene change removes legacy release-triggered local pruning under
  the owner's no-automatic-cleanup rule. The legacy-named
  `prune-local-backups.sh` is report-only; see [manual maintenance](local-maintenance.md).
- An offsite restore drill into a new host path adds another restored generation
  (`E+B`) until separately reviewed cleanup. Allow room for Restic cache, logs,
  temporary transfers, OS updates, Docker metadata and retained images as well.
- [Database restore verification](../../scripts/production/verify-backup.sh) uses
  a fixed 2 GiB tmpfs. It consumes RAM and possibly swap rather than ordinary
  persistent backup disk; the restored database must fit. Measure verification
  alongside application memory on the 4 GB host. Container ceilings totaling
  2.75 GiB are not proof that the restore can safely consume another 2 GiB.
- Marketing lead data needs a separately approved backup/retention policy; it
  is not included in the database/evidence backup calculation.

Illustrations only, not observed photo behavior: thirty drivers uploading four
1 MB photos each day produce 120 MB/day, or about 3.6 GB in thirty days. Live
evidence plus three full local backup copies is already about 14.4 GB. At twelve
1 MB photos per driver/day the same thirty-day evidence alone is 10.8 GB, and
the four-copy peak is 43.2 GB before database, images or OS. The configured
5,000,000-byte upload limit is a per-file ceiling, not an average image size.

Before accepting 40 GB, record actual photos/day, average/high-percentile photo
size, evidence/database retention, backup-generation sizes, peak restore memory,
free disk and measured recovery time. If the budget fails, enlarge storage or
use separately configured private object storage/backup capacity with explicit
approval; do not silently delete operational history or reduce retention.

## Boundaries and open gates

This phase does not purchase a VPS, upload the laptop checkout, alter DNS,
modify Pilot volumes, change signing identity, deploy, or publish to Play.
Local packaging success does not close image-CVE, offsite restore, host firewall,
TLS, registry/SSH access, real-phone migration, signing or Console gates.
