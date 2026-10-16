# OVHcloud single-VPS production deployment

## Status and boundary

This repository is **prepared, not deployed**. No OVHcloud account, VPS, DNS
record, firewall, GitHub environment, certificate, or live
service was created or changed while preparing this deployment.

The production topology is:

```text
Internet TCP 80/443 + UDP 443
                  |
                Caddy
      +-----------+----------------+
      |                            |
fleetaisystems.com          app.fleetaisystems.com
marketing:3001              web:3000 (Owner + Supervisor)
                                   |
                              api:8000
                                   |
                     +-------------+-------------+
                     |                           |
                postgres:5432              minio:9000

api.fleetaisystems.com -> API health/auth/Driver/Supervisor only
                          (Owner/admin/report/docs paths refused by Caddy)
```

Only Caddy has host port mappings. PostgreSQL, MinIO, the MinIO console, API,
web, and marketing processes are Docker-network-only. The existing root
`docker-compose.yml`, Windows launchers, and Tailscale Pilot remain independent
and unchanged.

## Capacity and host prerequisites

The approved initial envelope is one OVHcloud Singapore Ubuntu LTS VPS with
**2 vCPU, 4 GB RAM, and 40 GB disk**, serving two browser users and about 30
Android phones. Compose container ceilings total 2,816 MiB (2.75 GiB), leaving
roughly 1.25 GiB for Ubuntu, Docker, page cache, and short-lived deployment tools. The
API uses one process, a five-connection database pool with two overflow
connections, and bounded public/auth request rates. CI builds images off-server.

This is a conditional starting point, not a high-availability or disk-fit claim.
See [packaging and capacity](operations/cloud-packaging.md) for actual image/context
sizes, evidence growth, full backup copies and restore-memory assumptions. Keep at least
10 GB and 20% disk free. Alert at 70% sustained memory, 75% disk, load average
above 1.5 for 15 minutes, API p95 above one second, repeated container restarts,
or a backup exceeding two hours. Scale vertically before these limits are
sustained. See `docs/production-operations.md` for scaling and provider moves.

Required host software:

- Docker Engine from Docker's Ubuntu repository and the Compose plugin;
- Bash, GNU coreutils (`timeout`, `df`), tar, awk, util-linux (`flock`), curl,
  ca-certificates, and OpenSSH;
- Restic from the Ubuntu repository or its verified official package;
- an unprivileged `fleetdeploy` user in the Docker group;
- time synchronization and automatic security updates;
- SSH key authentication, with password/root login disabled after recovery
  access is proven.

Allow inbound TCP 22 only from approved administration addresses where
possible, TCP 80/443 publicly, and UDP 443 if HTTP/3 is desired. Do not allow
5432, 9000, 9001, 2019, 3000, 3001, or 8000 through the OVH firewall or UFW.

## One-time VPS preparation

These commands are examples to run only after reviewing them on the purchased
server. They are not executed by this repository.

```bash
sudo install -d -m 0750 -o fleetdeploy -g fleetdeploy /opt/fleet-ai
sudo install -d -m 0750 -o fleetdeploy -g fleetdeploy /opt/fleet-ai/releases
sudo install -d -m 0700 -o fleetdeploy -g fleetdeploy /opt/fleet-ai/incoming
sudo install -d -m 0700 -o fleetdeploy -g fleetdeploy /var/lib/fleet-ai/deploy
sudo install -d -m 0700 -o 10001 -g 10001 /var/lib/fleet-ai/leads
sudo install -d -m 0700 -o fleetdeploy -g fleetdeploy /var/backups/fleet-ai
sudo install -d -m 0750 -o root -g fleetdeploy /etc/fleet-ai
sudo install -m 0600 -o fleetdeploy -g fleetdeploy \
  /secure/operator-staging/production.env \
  /etc/fleet-ai/production.env
```

Prepare that private `production.env` from the reviewed revision's
`infra/production/production.env.example` outside the deployment bundle. Do not
upload the checkout or clone Git on the VPS. Leave `/opt/fleet-ai/repository`
absent: the first successful approved deployment creates a symlink to
`/opt/fleet-ai/releases/<full-SHA>`. These paths must be physical directories,
not symlinked ancestors. An existing real `repository` checkout or an unmanaged
symlink is refused, never replaced automatically. For an older prepared layout,
first obtain a separate operator-reviewed transition plan that preserves that
checkout and persistent state, establishes the release layout, and verifies the
unchanged Compose project/data-service hashes; do not delete it to bypass refusal.

Edit `/etc/fleet-ai/production.env`; replace every placeholder with an
independently generated value. Keep
`FLEET_S3_BUCKET=fleet-evidence`, because the checked-in MinIO policy is scoped
to that exact bucket. URL-encode the database password inside
`FLEET_DATABASE_URL`. Keep `FLEET_AUTH_MODE=company_pin`; production uses the
owner-issued, expiring, single-use activation code and device PIN/authentication
flow. It needs no Firebase service account, Firebase Phone Authentication, or
SMS service.

Create an independent Restic repository with server-side access controls. Copy
`infra/production/restic.env.example` to `/etc/fleet-ai/restic.env`, create a
separate random `/etc/fleet-ai/restic-password`, and set both files to mode 600.
Own both files as `fleetdeploy:fleetdeploy`, matching `production.env`, so the
deployment and scheduled jobs can read them without granting group access.
Escrow the password outside the VPS. Initialise the repository explicitly with
`restic init` only after verifying its destination; deployment scripts never
initialise or prune the remote repository.

The `fleetdeploy` user needs read access to the environment and Restic files,
write access to the state/backup directories, access to the Docker socket, and
read/write access to the releases/incoming directories. It should not own `/etc/fleet-ai`.
Log the VPS Docker client into the repository's GHCR namespace with a token that
has package-read access only.

Once an approved bundle exists, validate it without starting services (the first
workflow deployment also performs this validation before Docker mutations):

```bash
cd /opt/fleet-ai/repository
bash scripts/production/validate-config.sh
```

## DNS and TLS

Point these records to the VPS public address:

- apex `fleetaisystems.com`;
- `www.fleetaisystems.com`;
- `app.fleetaisystems.com`;
- `api.fleetaisystems.com`.

Create `AAAA` records only if IPv6 firewalling and routing have been tested.
Caddy obtains and renews certificates after public 80/443 reach the VPS. Keep
the initial TTL low until external health checks pass. Do not weaken TLS
verification in any client.

## GitHub production environment

Create a GitHub Environment named `production` and require at least one owner
reviewer. Prevent administrators from bypassing the protection where the
repository plan permits. Add these environment secrets:

- `OVH_HOST`
- `OVH_PORT`
- `OVH_USER` (`fleetdeploy`)
- `OVH_SSH_PRIVATE_KEY`
- `OVH_SSH_KNOWN_HOSTS` (the independently verified host-key line; never use a
  runtime `ssh-keyscan` result as trust-on-first-use)

The VPS needs no Git repository credential. The production workflow has no
`push` trigger. A normal push runs CI only.

## Approved one-command deployment request

Before requesting live deployment, the reviewer must close the external gates
in [the readiness report](production-readiness-report.md), including container
image CVE verification and a verified independent offsite restore. Green CI
alone does not satisfy these gates. After that review and successful CI on the
selected `main` commit:

```powershell
$sha = (git rev-parse HEAD).Trim()
gh workflow run production-deploy.yml --ref main `
  -f git_ref=$sha `
  -f 'confirmation=DEPLOY fleetaisystems.com'
```

The command requests a deployment; the protected GitHub `production`
environment still requires reviewer approval. The workflow rechecks the full
SHA, `main` ancestry, and the successful push CI run. It builds and publishes
`fleet-api`, `fleet-web`, and `fleet-marketing` images tagged with the full commit
and refuses existing tags. It creates a deterministic operations-only archive
from an explicit allowlist of approved Git blobs, with file hashes and a release
marker. No application source, Git history, environment file or signing material
is in that archive. See [the exact package inventory](operations/cloud-packaging.md).

Pinned-host SSH prepares a unique incoming run directory; SCP transfers the
archive, whose SHA-256 is checked on the server before extraction into a new
`/opt/fleet-ai/releases/<full-SHA>` directory. Existing release paths are refused.
The approved receiver then runs, from that bundle:

```bash
bash scripts/production/deploy.sh --image-tag <40-character-commit>
```

Only after its health/state gates pass does the receiver atomically switch the
`repository` symlink. It holds the same deployment lock as manual deploy/rollback
through activation, preventing concurrent rollback from racing the pointer.
The fixed Compose project name preserves named volumes across release paths.
Application configuration binds (notably Caddy) may reconcile to the new path;
established PostgreSQL/MinIO must still have unchanged service hashes.

If image publication succeeds but a later SSH/deployment step fails, redispatch
intentionally refuses the already-published SHA tags. Do not delete or retag
those artifacts to bypass the check. Confirm the approved revision, registry
digests and current deployment/backup state, obtain renewed owner approval, then
use the direct VPS command above from the retained, hash-verified release bundle
as a reviewed recovery action. Verify and reconcile the `repository` symlink only
after successful health/state checks; direct `deploy.sh` does not switch it.
Incoming archives, failed/partial release directories and older bundles are
preserved for review, never automatically overwritten or deleted. If deployment
succeeds but pointer activation fails, reconcile actual container/state/bundle
identity manually; do not claim the old pointer proves old images are running.
A partial first
bootstrap may additionally require the preserved-data recovery procedure below;
automatic same-SHA workflow retry is not implemented.

The VPS command validates configuration and pulls application images. On an
established deployment it requires running PostgreSQL/MinIO containers whose
Compose configuration hashes match the requested data-service configuration;
it never recreates those services. It creates a database/evidence backup
generation labelled with the running release's image tag, restores the
database into a disposable PostgreSQL container, verifies evidence hashes,
copies the verified generation to the independently encrypted Restic
repository, and preserves local generations. Retention is a separate approved
operator task, never automatic release cleanup. It runs `alembic upgrade head`,
starts the application containers, and
checks health plus private-route refusal. If an application health gate fails
and a previous image tag exists, it restarts the previous application images.
It never runs `alembic downgrade`. The state directory records every deploy or
rollback with the Git SHA and pulled registry digests.

Only a first installation with no deployment state, managed data containers, or
managed data volumes may bootstrap PostgreSQL/MinIO and initialize the private
bucket. If initial bootstrap fails after creating persistent state, rerunning
deployment intentionally refuses automatic adoption. Preserve the volumes and
follow the reviewed recovery procedure in
[migration and rollback](production-migration-and-rollback.md).
Data-service version, configuration, credentials, storage mounts, and policy
changes require a separate reviewed maintenance window and verified backup
before any mutation; ordinary application deploy/rollback uses `--no-deps`.

## Scheduled health, backup, and logging

After the first successful bundle activation, review and install the systemd
units from its stable compatibility path (timers use that same symlink):

```bash
cd /opt/fleet-ai/repository
sudo cp infra/production/systemd/fleet-ai-* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fleet-ai-backup.timer fleet-ai-health.timer
systemctl list-timers 'fleet-ai-*'
```

The daily job creates separate `postgres.dump` and `evidence/` artifacts,
checks their SHA-256 manifests, performs a real database restore, uploads the
generation with client-side Restic encryption, checks repository readability,
and preserves completed and incomplete local generations. Keep at least two
verified offsite-backed local recovery points; use the report-only retention
helper and obtain explicit approval before retiring any older generation.
Local and remote retention are separate owner-reviewed operations. Follow
[manual maintenance](operations/local-maintenance.md), and monitor growth rather
than assuming an automatic two-generation cap. Before
go-live, restore an offsite snapshot into a new empty path and verify it:

```bash
bash scripts/production/verify-offsite-backup.sh latest /var/tmp/fleet-restore-drill
```

Do not point this command at live volumes. Remove the drill directory only
after its report has been retained.

Application and access logs are JSON on stdout and rotate through Docker's
bounded `json-file` configuration. systemd task results are in the journal:

```bash
journalctl -u fleet-ai-backup.service -u fleet-ai-health.service
docker compose --env-file /etc/fleet-ai/production.env \
  -f infra/production/docker-compose.yml logs --since 30m api web marketing caddy
```

Do not log environment files, Restic credentials, JWT keys, database URLs, MinIO
credentials, access/refresh tokens, or evidence bytes.

Normal Linux health checks also measure root, Docker and backup filesystem
capacity, available memory and 15-minute load. See the exact thresholds and
alert-delivery limitation in [production operations](production-operations.md).
`--internal-only` explicitly skips host-resource and external checks; it cannot
certify VPS capacity or public TLS.

## Deployment health and exposure checks

Run after DNS/TLS cutover:

```bash
bash scripts/production/healthcheck.sh
```

Expected public behavior:

- `https://fleetaisystems.com/health` is healthy;
- `https://app.fleetaisystems.com/api/backend/health` reaches the API through
  the same-origin web proxy;
- `https://api.fleetaisystems.com/health` is healthy;
- API docs, legacy `/api/v1/admin`, `/api/v1/owner`, `/api/v1/reports`, and
  marketing private paths return 404 at Caddy;
- PostgreSQL and MinIO have no public listener.

Also verify from an external network with `ss -lntup`, the OVH firewall, UFW,
and a port scan of the three hostnames. Backend authorization remains required
even for routes Caddy permits.

## Local development remains independent

Continue laptop development on `main` with the existing `.env`, root
`docker-compose.yml`, `launch.py`, PowerShell scripts, and optional Tailscale
Pilot. Production secrets live only on the VPS/GitHub environments. No local
command reads `/etc/fleet-ai`, and no production workflow runs on push.
