# Production migration, backup, and rollback runbook

## Non-destructive migration policy

Production migrations are Alembic forward migrations against the existing
database. Every release must satisfy all of these before approval:

1. `alembic upgrade head` succeeds from a clean database and the current
   production revision.
2. `alembic check` reports no ungenerated model changes.
3. The new schema remains usable by the immediately previous application image
   until the new health gate passes (expand/migrate/contract discipline).
4. A database dump and independent evidence mirror complete and verify before
   migration.
5. No reset, fixture bootstrap, destructive cleanup, or automatic downgrade is
   part of the deployment command.

Schema/data contracts that remain unchanged in this production preparation
include Assignment history, client event UUID uniqueness, event timestamps,
EvidenceObject references, authentication sessions, Users, memberships, and
device registrations. No Alembic migration is added by this infrastructure
phase.

## Pilot server to VPS data move

Do not reset either environment. Schedule a maintenance window and stop writes
to the Pilot server only after every phone has synced its offline queue and all
active duties are ended.

1. Record the source Alembic revision, row counts for companies, memberships,
   assignments, devices, operational events, evidence objects, and the object
   count/bytes.
2. Take the existing Windows PostgreSQL and evidence backups and verify their
   manifests before transfer.
3. Transfer copies over an authenticated encrypted channel into a non-public
   staging directory on the VPS. Keep the source originals unchanged.
4. Restore PostgreSQL into a disposable/staging database first. Run the current
   API test/migration checks against that copy.
5. Import evidence into the private `fleet-evidence` bucket while preserving
   object keys and image extensions. Compare every checksum and object count.
6. Restore the verified database into the new, empty production PostgreSQL
   volume during the approved window. Run `alembic upgrade head` once.
7. Check `/ready`, tenant/role access, a representative historical report, and
   authorized evidence reads before allowing clients to connect.
8. Keep the old Pilot server read-only and recoverable until the acceptance
   window closes. Do not delete it as part of cutover.

Production uses the existing `company_pin` records and workflows. Before
cutover, create a fresh owner-issued activation code for each authorised person
only when that person's new Play installation is ready. Activation must resolve
the existing User and company membership; it must not create replacement
business records. A device reset or hand-over deliberately revokes the previous
credential and sessions while leaving fleet, assignment, event, and evidence
records intact.

## Application rollback

Routine deployment and rollback require established PostgreSQL and MinIO to be
running with unchanged Compose configuration hashes. They never recreate these
services, and migration/application/backup containers start with `--no-deps`.
The pre-deployment backup records the running image tag before the candidate
migration. An automatic application rollback is attempted only if application
replacement started; failed backup/preflight does not restart applications.

For a bad application release whose migration is backward-compatible:

```bash
cd /opt/fleet-ai/repository
bash scripts/production/rollback.sh
```

The default target is the recorded previous image SHA. An explicitly reviewed
SHA may be supplied as the only argument. Rollback creates and verifies a fresh
backup, pulls the prior images, restarts API/web/marketing, and reruns health
checks. PostgreSQL and evidence volumes are not replaced, and the script
reports `DATABASE_DOWNGRADE_ATTEMPTED=NO`.

This command rolls back application images only. It retains the active bundle's
Compose, Caddy, deployment scripts and secret configuration; automatic failure
rollback likewise uses the candidate configuration. For a configuration
regression, review the previous retained bundle's `release.sha`, manifest and
configuration diff, and run the explicitly approved image rollback **from that
previous bundle**, for example:

```bash
cd /opt/fleet-ai/releases/<reviewed-previous-40-character-SHA>
bash scripts/production/rollback.sh <reviewed-previous-40-character-SHA>
```

The same data-service hash gate and backup still apply. After successful health
checks, the operator must separately reconcile the stable `repository` symlink
to that verified existing bundle, while holding the deployment lock and checking
the current state has not changed. Direct rollback does not switch the pointer.
Do not improvise an overwrite of a real directory, delete a retained bundle or
reuse an unverified partial extraction. Do not assume image/configuration
rollback reverses firewall, schema, secrets or data-service maintenance.

The SSH receiver holds the shared deployment lock across deployment and atomic
bundle activation. Failed uploads/extraction/deployments retain incoming and
release paths and leave the old pointer unchanged. A failure after state commit
but before pointer activation requires reconciliation of state, actual images
and bundle identity; retrying the same workflow refuses already-published image
tags or existing release directories rather than overwriting them.

If the old image is not compatible with the migrated schema, keep the new image
offline or in maintenance and follow the data-restore incident procedure. Do
not improvise an Alembic downgrade.

## Data-service maintenance and interrupted first bootstrap

PostgreSQL/MinIO version, configuration, credentials, volume and policy changes
are separate maintenance operations. Keep the currently deployed configuration
available, stop writes as appropriate, take and verify an offsite backup using
that running configuration, and test the proposed change against a restored
copy. Obtain explicit approval before changing a live data service. Routine
application deployment rejects changed data-service configuration rather than
implicitly applying it before a backup. Do not edit Docker config-hash labels
or deployment state to bypass this gate.

An initial deployment can create data services only when deployment state,
managed data containers and managed data volumes are all absent. If it fails
after bootstrap, retain those volumes and inspect the database revision,
evidence, container configuration, and any backup output. Recovery is reviewed
maintenance: establish a verified running release and its real deployment
state, or restore into a separately approved empty target. The deployment
script never assumes that an unrecorded volume is disposable and never deletes
it to make a retry pass.

## Data restore incident procedure

Data restore is destructive to the selected target and is intentionally not a
one-command deployment action.

1. Declare an incident, stop application writes, and record the exact current
   image tag, Alembic revision, database/evidence counts, and timestamps.
2. Take a final forensic backup without overwriting the backup selected for
   restore.
3. Run `bash scripts/production/verify-backup.sh <backup-directory>` again.
4. Restore first into a disposable database and a separate MinIO bucket. Check
   Alembic revision, tenant counts, event UUID counts, evidence counts and
   hashes, and representative authorized reads.
5. Obtain explicit owner approval for the named backup and recovery point.
6. Replace production data only in the documented maintenance window. Restore
   database and evidence from the same backup generation; never mix them.
7. Run only reviewed forward migrations needed by the selected application
   image, then run internal and external health/security checks.
8. Preserve the failed data set and all incident logs until review is complete.

## Backup retention and disaster recovery

Database and evidence artifacts are independent but form one consistency
generation through `manifest.txt`. Its `image_tag` identifies the running image
being backed up; `source_commit` identifies the operations bundle executing the
backup (which can be the candidate bundle before migration), not necessarily
that running image. Restic encrypts and stores that generation
off-host before any separately approved local retirement is considered. Releases
and timers never delete backup generations. Retain at least two verified local
recovery points and obtain explicit approval after offsite restore verification
before retiring an exact older generation; the legacy-named
`prune-local-backups.sh` only reports candidates. See
[manual maintenance](operations/local-maintenance.md). Marketing lead PII is a third data
class and requires its own encrypted backup/retention policy. Caddy certificates
and image layers are reproducible; environment, JWT, MinIO, and Restic secret
recovery must come from the owner-controlled secret store, not from Git.

Restore verification proves backup readability, not the business recovery
time. Measure full transfer and restore duration during staging and record the
accepted recovery point objective and recovery time objective before go-live.
