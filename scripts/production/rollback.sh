#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"
# shellcheck source=data-service-guard.sh
source "$SCRIPT_DIR/data-service-guard.sh"

target_tag="${1:-$(state_value FLEET_PREVIOUS_IMAGE_TAG)}"
[[ "$target_tag" =~ ^[0-9a-f]{40}$ ]] || die "Usage: $0 [40-character-image-tag]"

require_command docker
require_command flock
require_production_files
bash "$SCRIPT_DIR/validate-config.sh"

install -d -m 0700 "$STATE_DIR"
exec 9>"$LOCK_FILE"
flock -n 9 || die "Another production deploy or rollback is already running."

current_tag="$(current_image_tag)"
export FLEET_IMAGE_TAG="$current_tag"
require_unchanged_data_services
backup_output="$(bash "$SCRIPT_DIR/backup-and-verify.sh")"
printf '%s\n' "$backup_output"
backup_path="$(printf '%s\n' "$backup_output" | sed -n 's/^BACKUP_PATH=//p' | tail -n 1)"
[[ -n "$backup_path" ]] || die "Backup helper did not report a backup path."

export FLEET_IMAGE_TAG="$target_tag"
fleet_compose pull api web marketing
fleet_compose up --detach --wait --wait-timeout 180 --no-build --no-deps api web marketing caddy
bash "$SCRIPT_DIR/healthcheck.sh"
write_deploy_state "$target_tag" "$current_tag" rollback

printf 'APPLICATION_ROLLBACK=PASS\n'
printf 'DATABASE_DOWNGRADE_ATTEMPTED=NO\n'
printf 'IMAGE_TAG=%s\n' "$target_tag"
printf 'PRE_ROLLBACK_BACKUP=%s\n' "$backup_path"
