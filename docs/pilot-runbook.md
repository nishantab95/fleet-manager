# Owned-Tipper Pilot Runbook

This runbook is for a controlled pilot. Never place real passwords, OTPs,
database credentials, signing keys, or object-storage keys in this document or
in the repository.

## Start and stop

From the repository root:

```powershell
Copy-Item .env.example .env
# Fill local/test values; use secret management for pilot values.
.\scripts\bootstrap.ps1
.\scripts\dev.ps1
```

Stop the API with `Ctrl+C`. Stop local services with
`docker compose stop`; use `docker compose down` only when removing the
development stack is intended. Do not delete production volumes as a routine
stop operation.

## Health and logs

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready
docker compose ps
docker compose logs --tail 100 postgres minio
```

`/health` is liveness. `/ready` checks PostgreSQL and returns `503` when the
API should not receive traffic. The API returns a request ID and structured
JSON logs; logs must not contain OTPs, JWTs, refresh tokens, or signed object
URLs.

Local Compose publishes MinIO's S3 API on `http://localhost:19000` and its
console on `http://localhost:19001` by default. These host ports intentionally
avoid TallyPrime's port 9000. If they are changed, update
`FLEET_S3_ENDPOINT_URL`, `MINIO_API_PORT`, and `MINIO_CONSOLE_PORT` together;
keep MinIO's container-internal ports at 9000/9001.

## Backup and restore

Set `PGHOST`, `PGPORT`, `PGUSER`, and `PGPASSWORD` outside the repository (or
use an approved PostgreSQL password mechanism), then run:

```powershell
.\scripts\backup-postgres.ps1 -DatabaseName fleet -BackupDirectory D:\fleet-backups
createdb -h $env:PGHOST -p $env:PGPORT -U $env:PGUSER fleet_restore_test
.\scripts\restore-postgres.ps1 -BackupFile D:\fleet-backups\<file>.dump -TargetDatabase fleet_restore_test
```

Run migrations/checks and representative queries against the restore database.
Never restore over the normal development or production database during a
restore test. Delete only the explicitly named temporary restore database
after verification.

Evidence objects are a separate backup domain. Configure an `mc` alias using
credentials held outside this repository and export with:

```powershell
.\scripts\backup-object-storage.ps1 -Alias pilot -Bucket fleet-local -DestinationDirectory D:\fleet-evidence-backups
```

Verify that the database backup and evidence export are timestamped and stored
under separate retention policies.

## Onboarding

1. Create or verify the owner membership.
2. Create the driver and supervisor as `DRIVER` and `SUPERVISOR` memberships.
3. Create the site and owned tipper.
4. Grant the supervisor access to that site.
5. Create an effective-dated assignment.
6. Sign in as the driver and confirm the active assignment.
7. Sign in as the supervisor and confirm only the granted site is available.
8. Sign in as the owner and confirm dashboard, reports, exceptions, closure,
   and Excel export.

## If the driver cannot sync

1. Do not uninstall or clear app data.
2. Open Diagnostics and record app version, device registration ID, pending
   event count, last successful sync, and last sync error category.
3. Check `/ready`, PostgreSQL, object storage, and the device network.
4. If the category is `AUTH_REQUIRED` or `ACCESS_REVOKED_OR_DENIED`, stop
   retries and have the owner verify membership/device status.
5. If the category is `BACKEND_UNAVAILABLE`, restore service and retry sync.
6. Keep the device database until the owner confirms the event is visible and
   reconciled in reporting.

## If photo upload fails

The event remains local and is not marked synced. Check object-storage health,
available device storage, camera permissions, and the evidence MIME/size
policy. Retry after storage recovery; do not manually create a public object
URL.

## If authentication fails

OTP delivery is provider-dependent and development OTP is never a production
fallback. Verify the phone/membership is active, wait for the resend cooldown,
and inspect the generic API error with its request ID. Do not ask a driver to
send an OTP through chat or record it in logs.

For the one-tipper internal pilot, an explicitly enabled development/test OTP
provider is acceptable only on the controlled local test network. Production
and public deployments must use a real provider and remain fail-closed when it
is unavailable. Do not expose plaintext HTTP authentication traffic to the
public Internet; HTTPS/TLS is required before broader rollout. A later manual
pilot test should use an emulator/ADB reverse or another controlled local
connection rather than public exposure.

Evidence uploads use MIME and magic-byte validation, a size limit, generated
private object keys, private MinIO/S3 storage, and authorization checks. Malware
scanning/content inspection is required before broader rollout but is
non-blocking for this controlled one-tipper internal pilot.
