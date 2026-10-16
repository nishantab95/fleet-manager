#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"
umask 077

require_command docker
require_command find
require_command sha256sum
require_command id
require_command mktemp
require_production_files

backup_root="$(env_value FLEET_BACKUP_DIR)"
backup_path="$(mktemp -d "$backup_root/fleet-$(date -u +%Y%m%d-%H%M%SZ)-XXXXXX")"
backup_id="$(basename -- "$backup_path")"
database_tmp="$backup_path/postgres.dump.partial"
database_dump="$backup_path/postgres.dump"
evidence_path="$backup_path/evidence"

allow_windows_acl_smoke=false
if [[ "${FLEET_LOCAL_SMOKE_WINDOWS_ACL:-}" == "1" && "$(uname -s)" == MINGW* ]]; then
  allow_windows_acl_smoke=true
fi

secure_chmod() {
  chmod "$@" || [[ "$allow_windows_acl_smoke" == true ]] || \
    die "Could not apply required backup permissions."
}

if ! install -d -m 0700 "$backup_path" "$evidence_path"; then
  [[ "$allow_windows_acl_smoke" == true ]] || die "Could not create secure backup directories."
  mkdir -p "$backup_path" "$evidence_path"
fi

preserve_failed_backup() {
  local status=$?
  if (( status != 0 )); then
    printf '[FAILED] Incomplete backup preserved for review: %s\n' "$backup_path" >&2
  fi
}
trap preserve_failed_backup EXIT

fleet_compose exec -T postgres sh -ec \
  'exec pg_dump --format=custom --no-owner --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"' \
  >"$database_tmp"
[[ -s "$database_tmp" ]] || die "PostgreSQL backup is empty."
mv -- "$database_tmp" "$database_dump"
secure_chmod 0600 "$database_dump"
(
  cd -- "$backup_path"
  sha256sum postgres.dump >postgres.sha256
)

FLEET_BACKUP_ID="$backup_id" fleet_compose --profile tools run --rm --no-deps \
  --user "$(id -u):$(id -g)" \
  -e FLEET_BACKUP_ID="$backup_id" backup-tools -ec '
    # The bind mount is mode 0700 and belongs to the deployment account. Use
    # that same UID/GID so Linux permissions remain private and operators can
    # inspect the backup without broadening access to protected evidence.
    mc --config-dir /tmp/fleet-backup-mc alias set fleet-local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
    mkdir -p "/backups/$FLEET_BACKUP_ID/evidence"
    mc --config-dir /tmp/fleet-backup-mc mirror --overwrite "fleet-local/$FLEET_S3_BUCKET" "/backups/$FLEET_BACKUP_ID/evidence" >/dev/null
  '

(
  cd -- "$evidence_path"
  find . -type f -print0 | sort -z | xargs -0 -r sha256sum
) >"$backup_path/evidence.sha256"
find "$evidence_path" -type f -printf '.' -quit >"$backup_path/evidence.present"

image_tag="$(current_image_tag)"
git_commit="unknown"
if [[ -f "$REPO_ROOT/release.sha" && ! -L "$REPO_ROOT/release.sha" ]]; then
  git_commit="$(<"$REPO_ROOT/release.sha")"
  [[ "$git_commit" =~ ^[0-9a-f]{40}$ ]] || die "Invalid operations bundle release marker."
elif command -v git >/dev/null 2>&1 && git -C "$REPO_ROOT" rev-parse --verify HEAD >/dev/null 2>&1; then
  git_commit="$(git -C "$REPO_ROOT" rev-parse HEAD)"
fi
{
  printf 'format_version=1\n'
  printf 'created_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'image_tag=%s\n' "$image_tag"
  printf 'source_commit=%s\n' "$git_commit"
  printf 'database_file=postgres.dump\n'
  printf 'evidence_directory=evidence\n'
} >"$backup_path/manifest.txt"
secure_chmod 0600 "$backup_path"/*.sha256 "$backup_path/evidence.present" "$backup_path/manifest.txt"

trap - EXIT
printf 'BACKUP_PATH=%s\n' "$backup_path"
printf 'DATABASE_BACKUP=CREATED\n'
printf 'EVIDENCE_BACKUP=CREATED\n'
