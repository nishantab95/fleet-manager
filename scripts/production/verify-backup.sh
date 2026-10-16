#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
  printf 'Usage: %s /absolute/path/to/backup\n' "$0" >&2
  exit 2
fi

backup_path="$(cd -- "$1" && pwd -P)"
database_dump="$backup_path/postgres.dump"
evidence_path="$backup_path/evidence"

[[ -f "$database_dump" ]] || { printf '[FAILED] PostgreSQL dump is missing.\n' >&2; exit 1; }
[[ -f "$backup_path/postgres.sha256" ]] || { printf '[FAILED] PostgreSQL checksum is missing.\n' >&2; exit 1; }
[[ -d "$evidence_path" ]] || { printf '[FAILED] Evidence backup is missing.\n' >&2; exit 1; }
[[ -f "$backup_path/evidence.sha256" ]] || { printf '[FAILED] Evidence checksum list is missing.\n' >&2; exit 1; }
[[ -f "$backup_path/evidence.present" ]] || { printf '[FAILED] Evidence presence marker is missing.\n' >&2; exit 1; }

(
  cd -- "$backup_path"
  sha256sum --check postgres.sha256
)
if [[ -s "$backup_path/evidence.present" ]]; then
  [[ -s "$backup_path/evidence.sha256" ]] || { printf '[FAILED] Evidence checksums are unexpectedly empty.\n' >&2; exit 1; }
  (
    cd -- "$evidence_path"
    sha256sum --check ../evidence.sha256
  )
else
  [[ ! -s "$backup_path/evidence.sha256" ]] || { printf '[FAILED] Empty evidence backup has unexpected checksums.\n' >&2; exit 1; }
  [[ -z "$(find "$evidence_path" -type f -print -quit)" ]] || { printf '[FAILED] Empty evidence marker does not match backup contents.\n' >&2; exit 1; }
fi

container="fleet-restore-verify-$$-$(date +%s)"
password="restore-verification-only"
cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker run --detach --name "$container" \
  --env POSTGRES_PASSWORD="$password" \
  --env POSTGRES_DB=fleet_restore_verify \
  --tmpfs /var/lib/postgresql/data:rw,size=2g \
  postgres:17.6-bookworm >/dev/null

ready=false
for _ in $(seq 1 60); do
  if docker exec "$container" pg_isready -U postgres -d fleet_restore_verify >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done
[[ "$ready" == true ]] || { printf '[FAILED] Disposable restore database did not become ready.\n' >&2; exit 1; }

docker exec -i "$container" pg_restore \
  --exit-on-error --no-owner --username postgres --dbname fleet_restore_verify \
  <"$database_dump"

has_revision_table="$(docker exec "$container" psql --tuples-only --no-align \
  --username postgres --dbname fleet_restore_verify \
  --command "SELECT to_regclass('public.alembic_version') IS NOT NULL;")"
if [[ "$has_revision_table" == "t" ]]; then
  revision_count="$(docker exec "$container" psql --tuples-only --no-align \
    --username postgres --dbname fleet_restore_verify \
    --command 'SELECT count(*) FROM alembic_version;')"
  [[ "$revision_count" == "1" ]] || { printf '[FAILED] Restored database has an invalid Alembic revision table.\n' >&2; exit 1; }
else
  printf 'DATABASE_RESTORE_SCHEMA=EMPTY_INITIAL_DATABASE\n'
fi

printf 'DATABASE_RESTORE_VERIFY=PASS\n'
printf 'EVIDENCE_CHECKSUM_VERIFY=PASS\n'
