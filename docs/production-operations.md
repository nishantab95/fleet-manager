# Production operations, hardening, scaling, and provider migration

## Operating boundary

The initial topology is intentionally one Ubuntu VPS: 2 vCPU, 4 GB RAM, and
40 GB disk in Singapore. It is sized for two browser users and approximately
30 Android phones, not for high availability. Only Caddy exposes host ports.
The API, PostgreSQL, MinIO, browser applications, and Caddy remain replaceable
containers; persistent state is PostgreSQL, MinIO evidence, marketing leads,
deployment history, and external secrets.

The provisional service objectives are a 24-hour recovery point and four-hour
recovery time. They are not accepted objectives until a timed offsite restore
drill proves them and the Owner signs off. Mobile offline queues reduce the
impact of a short outage but are not a server backup.

## Ubuntu provisioning and hardening checklist

Perform these on the purchased host only after reviewing the current Ubuntu,
Docker, OVH, and Restic guidance.

1. Install a supported Ubuntu LTS image and immediately apply all security
   updates. Enable time synchronisation and `unattended-upgrades`.
2. Create the unprivileged `fleetdeploy` account. Use a dedicated SSH key,
   disable password authentication, and disable direct root login only after
   console/recovery access is proven. Treat Docker-group membership as
   root-equivalent access.
3. Install Docker Engine and Compose from Docker's signed Ubuntu repository.
   Install Git, curl, ca-certificates, OpenSSH, Restic, and basic monitoring
   tools. Do not install a database or web server on the host.
4. Configure the OVH network firewall and UFW to allow public TCP 80/443,
   optional UDP 443, and administrative SSH only from approved source
   addresses. Explicitly deny public 5432, 9000, 9001, 2019, 3000, 3001, and
   8000.
5. Create the paths and ownership documented in
   `docs/production-deployment.md`. Put secrets only in mode-600 files outside
   Git. Store the Restic password in a second owner-controlled secret system.
6. Enable an OVH volume/snapshot only as an additional recovery layer. It does
   not replace the independently encrypted offsite PostgreSQL/evidence backup.
7. Set DNS only after internal health, restore, resource, and port-exposure
   tests pass. Use a low TTL during migration and remove stale records after
   the acceptance window.

Before enabling production traffic, record `ss -lntup`, UFW status, OVH
firewall rules, Compose config, image digests, disk encryption/provider
controls, system time, the successful restore drill, and an external port scan.

## Monitoring and routine checks

The checked-in systemd timers run daily backup/verification and five-minute
health checks. Docker JSON logs are size-bounded. Send timer failures and disk,
memory, container restart, TLS, and external health alarms to an owner-approved
channel before go-live; alert delivery is not configured by this repository.

Normal `healthcheck.sh` also checks the filesystems containing `/`, Docker's
reported `DockerRootDir`, and the configured backup directory: each must have
at least 10 GB available and be below 75% used. `/proc/meminfo` must report
instantaneous `MemAvailable` above 30% of total memory, and 15-minute load must
not exceed 1.5. Unreadable/unparseable resource data fails closed. These are
local script output/journal gates, not configured external alert delivery or
a sustained-memory measurement. `--internal-only` explicitly skips host and
external checks; its success is not proof that a VPS is production-ready.

Review at least weekly:

- backup timer success, offsite snapshot age, and a sample Restic check;
- disk use by Docker, PostgreSQL, MinIO, logs, and every retained local backup;
- memory pressure/OOM events, CPU/load, container restarts, API p50/p95/p99,
  HTTP 429/5xx rates, and database pool waits;
- certificate expiry, firewall exposure, dependency/security findings, and
  failed authentication/activation/lockout patterns without logging secrets;
- PostgreSQL and evidence growth compared with the 40 GB envelope.

Run an offsite restore drill at least quarterly and before a provider move:

```bash
bash scripts/production/verify-offsite-backup.sh <snapshot-id> /var/tmp/fleet-restore-drill
```

The target must be new and empty. The script restores into that isolated path,
checks evidence hashes, restores PostgreSQL into a disposable container, and
never targets live data.

## Backup retention and disk pressure

Backups are protected data. Daily backup/verification, application deployment
and rollback never delete a backup generation. Failed dumps remain as private
`postgres.dump.partial` files in their incomplete generation for investigation;
they must not be mistaken for completed recovery points. There is no automatic
local rotation, Restic forget/prune, volume prune or database/evidence cleanup.

The historically named command below is a read-only inventory, not a prune:

```bash
bash scripts/production/prune-local-backups.sh --keep 2
```

It reports exact recognized generation paths and logical bytes, marks the newest
N offsite-completion markers for retention (`N >= 2`), and lists older completed
generations only as review candidates. Unknown/incomplete directories, extra
partial content, links/hardlinks, nonregular files and cross-filesystem mounts
are preserved. Same-filesystem bind mounts require independent operator inspection
before any removal approval; this metadata report is not a mount audit.
No Apply/delete option exists. Completion markers record the earlier verification
and offsite check; they do not prove a fresh independent restore or authorize
removal. Do not run the report concurrently with backup/restore maintenance when
using its measurements to plan a retirement.

Owner-approved retention must preserve at least two verified local generations
and two independently verified offsite generations, the agreed recovery window,
and every incident/legal hold. Before approving any retired generation's removal,
restore an independent offsite snapshot into a new isolated path and verify both
database restoration and evidence hashes. Retain the report, exact approved paths,
generation IDs and current/previous release references. Revalidate them before a
separately authorized operation; this repository supplies no backup deletion tool.

Full copies accumulate with each daily run and deployment/rollback. Monitor all
retained generations, partial failures and restore drills; the two-generation
capacity estimate is a minimum planning floor, not an enforced storage limit.
Escalate disk-pressure alerts early, expand storage or obtain a reviewed retention
decision before the backup fails. Never solve space pressure by deleting live
volumes, evidence, signing material, recovery points or logs needed for incidents.
See [manual local maintenance](operations/local-maintenance.md) for the distinct
Windows generated-cache helper and exact-image-ID review boundaries.

## Incident response

For suspected compromise or data loss:

1. Record the incident time, reporter, affected host/image digests, and current
   health without printing secrets or evidence.
2. Restrict traffic at the firewall or stop application writes if continued
   operation could worsen loss. Preserve database/evidence and logs.
3. Rotate only credentials known or reasonably suspected to be exposed. Do not
   replace Android signing keys as an incident reflex; follow Google/Pilot key
   recovery rules.
4. Take a new forensic backup to a separate generation. Never overwrite the
   recovery point selected for investigation.
5. Restore and verify in an isolated environment, reconcile company,
   membership, assignment, event UUID, device, and evidence counts, then obtain
   explicit approval before any live restore.
6. Use application rollback only for a backward-compatible release. Never run
   an improvised Alembic downgrade.
7. Preserve a timeline and determine contractual/regulatory notification duties
   with qualified counsel. Close the incident only after credentials,
   monitoring, backup integrity, and the root cause are addressed.

## Capacity and scale triggers

Container memory ceilings are 768 MiB each for PostgreSQL and MinIO, 512 MiB
for API, 384 MiB for the authenticated web app, 256 MiB for marketing, and
128 MiB for Caddy. These are safety ceilings, not reservations. The API pool is
five plus two overflow connections and Uvicorn runs one worker so the in-memory
rate limiter is consistent.

Upgrade the VPS before sustained memory exceeds 70%, disk exceeds 75%, swap or
OOM events occur, load exceeds 1.5 for 15 minutes, API p95 exceeds one second,
or backup/restore no longer fits the approved objective. Moving to multiple API
processes/hosts requires a shared rate-limit store and an explicit session/load
balancing design. Move PostgreSQL or evidence storage only after testing backup,
network, IAM, latency, and cost consequences.

## Provider migration

There is no OVH-specific runtime dependency. To move providers:

1. Provision and harden a new supported Ubuntu host with equivalent or greater
   resources; do not reuse secrets blindly.
2. Pull the exact recorded image digests and restore the latest independently
   verified Restic generation into isolated PostgreSQL and S3-compatible
   storage.
3. Reconcile migrations, row/object counts, hashes, authentication/device
   records, and representative tenant-scoped reads.
4. Lower DNS TTL, schedule a write freeze, drain mobile queues, take and offsite
   a final backup, restore the matching database/evidence generation, and run
   health/security acceptance.
5. Switch DNS, monitor, and keep the old server read-only and recoverable until
   acceptance closes. Then revoke old credentials and follow the approved data
   disposal process.

Recurring cost categories are the VPS, independent backup storage/requests,
domain/DNS, monitoring/alert delivery, Google Play developer account, and any
future support or managed services. Firebase SMS is not a production cost for
this release. Confirm current provider prices before purchase; none were
purchased or configured by this work.
