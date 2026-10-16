#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

[[ $# -eq 2 ]] || die "Usage: $0 <restic-snapshot-id-or-latest> /absolute/empty/restore-directory"
require_command restic
require_command find
snapshot="$1"
target="$2"
[[ "$target" == /* && "$target" != "/" ]] || die "Restore target must be an absolute non-root path."
install -d -m 0700 "$target"
[[ -z "$(find "$target" -mindepth 1 -print -quit)" ]] || die "Restore target must be empty."
target="$(cd -- "$target" && pwd -P)"

export RESTIC_REPOSITORY
export RESTIC_PASSWORD_FILE
RESTIC_REPOSITORY="$(file_env_value "$RESTIC_ENV_FILE" RESTIC_REPOSITORY)"
RESTIC_PASSWORD_FILE="$(file_env_value "$RESTIC_ENV_FILE" RESTIC_PASSWORD_FILE)"
for key in AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_DEFAULT_REGION; do
  value="$(optional_file_env_value "$RESTIC_ENV_FILE" "$key")"
  if [[ -n "$value" ]]; then export "$key=$value"; fi
done

restic restore "$snapshot" --target "$target"
mapfile -t manifests < <(find "$target" -type f -name manifest.txt -print)
[[ ${#manifests[@]} -eq 1 ]] || die "Restored snapshot must contain exactly one Fleet backup manifest."
backup_path="$(dirname -- "${manifests[0]}")"
bash "$SCRIPT_DIR/verify-backup.sh" "$backup_path"
printf 'OFFSITE_RESTORE_VERIFY=PASS\n'
printf 'RESTORED_BACKUP_PATH=%s\n' "$backup_path"
