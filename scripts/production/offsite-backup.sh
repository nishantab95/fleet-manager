#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

[[ $# -eq 1 ]] || die "Usage: $0 /absolute/path/to/verified-backup"
require_command restic
require_command stat

backup_root="$(cd -- "$(env_value FLEET_BACKUP_DIR)" && pwd -P)"
backup_path="$(cd -- "$1" && pwd -P)"
[[ "$backup_root" != "/" && "$backup_path" == "$backup_root"/fleet-* ]] || \
  die "Offsite backup path must be a Fleet backup generation under FLEET_BACKUP_DIR."
bash "$SCRIPT_DIR/verify-backup.sh" "$backup_path"

export RESTIC_REPOSITORY
export RESTIC_PASSWORD_FILE
RESTIC_REPOSITORY="$(file_env_value "$RESTIC_ENV_FILE" RESTIC_REPOSITORY)"
RESTIC_PASSWORD_FILE="$(file_env_value "$RESTIC_ENV_FILE" RESTIC_PASSWORD_FILE)"
for key in AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_DEFAULT_REGION; do
  value="$(optional_file_env_value "$RESTIC_ENV_FILE" "$key")"
  if [[ -n "$value" ]]; then
    export "$key=$value"
  fi
done

# Never initialize or prune the remote repository automatically. Operators create
# it once and retention is controlled independently from local backup rotation.
restic snapshots --json >/dev/null
backup_id="$(basename -- "$backup_path")"
restic backup --tag fleet-ai --tag database-and-evidence --tag "$backup_id" "$backup_path"
restic check --read-data-subset=5%
printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$backup_path/.offsite-complete"
chmod 0600 "$backup_path/.offsite-complete"
printf 'OFFSITE_BACKUP=PASS\n'
printf 'OFFSITE_BACKUP_ID=%s\n' "$backup_id"
