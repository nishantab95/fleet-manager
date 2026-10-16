# Manual maintenance and protected retention

Read [PROJECT_RULES.md](../../PROJECT_RULES.md) and the measured
[local disk audit](local-disk-audit.md) first. Maintenance is separate from
development, startup, tests, CI, backups and release execution. Nothing in this
guide authorizes a live-server operation or deletion of protected data.

## Narrow Windows generated-artifact cleanup

From the verified checkout root, the existing guarded helper defaults to reporting:

```powershell
powershell -NoProfile -File scripts/maintenance/cleanup-generated.ps1
```

It has an immutable four-target allowlist, not a general path argument:

| Target | Why generated; regeneration cost |
| --- | --- |
| `.tmp/fleet-api-ci.tar` | One independently audited image export, pinned by size and SHA-256. Re-export requires the corresponding image; a replacement archive is refused. |
| `apps/web/.next/dev/cache` | Recognized Next development cache only; subsequent development startup recompiles/warms it. |
| `apps/marketing/.next/dev/cache` | Same isolated marketing development cache; warm-up work repeats. |
| `apps/mobile/build/app/intermediates/merged_native_libs/productionDebug` | Recognized Gradle debug merge outputs only; the next affected build repeats merging. |

Close development/build clients first and independently confirm any remaining
Gradle daemon is idle. Review exact paths, file counts and logical bytes. The tool
refuses changed/unknown content, tracked files, protected names, links/reparse
points, hardlinks, locked files and failed Git/process checks. It never terminates
processes. Missing targets are reported; the earlier one-time cleanup does not
authorize removing newly created artifacts.

Only after explicit approval of that inventory, a human may invoke the same
command with `-Apply`. Removal is direct, not Recycle Bin recovery; rebuilding or
re-exporting is required. The script never recursively deletes an unchecked tree.
Retain before/after inventory and results. Logical bytes are not guaranteed
filesystem space reclaimed; use the independent allocated-size disk audit.

Do not connect this tool to CI, startup, application builds or release workflows.
Do not broaden its allowlist to make a refusal disappear.

## Keep temporary growth visible

Run the read-only [disk audit utility](../../scripts/maintenance/disk_audit.py)
after a substantial build/test cycle and review `.tmp`, `.production-smoke.*`,
test reports and Docker's separate `docker system df` inventory weekly. Use
`--help` for the exact inventory options; a JSON output path must be new.
Do not assume age alone makes a directory disposable. Preserve reports needed
to support a release or incident, then approve exact measured artifacts for
manual retirement. The four-target helper intentionally cannot remove arbitrary
new test directories; expanding maintenance scope requires a fresh safety review.

The isolated smoke helper stops only its validated, uniquely named test
containers on exit. It retains those stopped containers, networks, named volumes,
environment file and backup evidence, and prints their exact project/directory.
This is test-process teardown, not automatic disk cleanup. Inspect the printed
identity before any separately approved maintenance; never remove a broad
`fleet-*` selection or touch the working Pilot project. Ephemeral restore workers
use tmpfs rather than persistent database volumes; their lifecycle is separate
from retiring retained backup generations.

## Protected paths and release artifacts

Never blanket-delete `.git`, environment files, signing material, Pilot releases,
APK/AAB deliverables, production bundles, dependencies, `.runtime`, databases,
evidence, backups, restore drills or incident records. Existing fixtures under
`.tmp` are not all disposable: retain audit/build evidence until individually
reviewed. Do not use `git clean`, destructive Git maintenance, `docker system
prune`, volume prune or `docker compose down -v` on the working Pilot/production.

Container-image maintenance requires a separate exact-ID inventory and approval.
Preserve the currently deployed and previous known-good release digests, incident
hold tags/digests, all images required by retained recovery points, and established
PostgreSQL/MinIO images. Verify registry availability before retiring an unused
local image. Remove only an individually reviewed unreferenced image ID after
approval; no broad/dangling-image prune or automatic garbage collection. Image
removal can require a network pull or reproducible rebuild and is not a backup.

## Production backup retention is report-only

`scripts/production/prune-local-backups.sh` retains its historical name but has
**no deletion mode**, even when called directly. It accepts only optional
`--keep N` with `N >= 2`; it reports exact recognized completed generation paths
and logical bytes, retaining the newest N offsite-completion markers in its plan.
It preserves unknown/incomplete generations, partial dumps, links/hardlinks,
nonregular content and cross-filesystem mounts. Same-filesystem bind mounts
require independent operator inspection before any removal approval.
A marker is not proof of a fresh offsite
restore; the report is an inventory, not permission to delete.

Routine backup, timer, deploy and rollback paths never invoke retention cleanup.
All local generations remain until a separate Owner-approved exact-path review.
Maintain at least two independently verified offsite generations and two
verified local generations, plus required recovery-window and incident holds.
Before approving retirement of any generation, restore an independent offsite
snapshot to a new isolated path, verify PostgreSQL and evidence, and preserve the
report. Recheck the exact target and recovery holds immediately before any
separately authorized removal. Deletion is irreversible without another verified
copy; free-space pressure is an alert/escalation condition, not deletion approval.

See [production operations](../production-operations.md#backup-retention-and-disk-pressure)
for the authoritative server retention policy. No automatic Restic forget/prune,
Docker volume cleanup, or database/evidence garbage collection is configured.
