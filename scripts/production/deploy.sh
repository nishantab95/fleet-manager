#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"
# shellcheck source=data-service-guard.sh
source "$SCRIPT_DIR/data-service-guard.sh"

usage() {
  printf 'Usage: %s --image-tag <40-character-main-commit>\n' "$0" >&2
  exit 2
}

new_tag=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --image-tag)
      [[ $# -ge 2 ]] || usage
      new_tag="$2"
      shift 2
      ;;
    *) usage ;;
  esac
done
[[ "$new_tag" =~ ^[0-9a-f]{40}$ ]] || usage

require_command docker
require_command flock
require_command curl
require_production_files
bash "$SCRIPT_DIR/validate-config.sh"

install -d -m 0700 "$STATE_DIR"
exec 9>"$LOCK_FILE"
flock -n 9 || die "Another production deploy or rollback is already running."

previous_tag="$(state_value FLEET_IMAGE_TAG)"
if [[ -n "$previous_tag" && ! "$previous_tag" =~ ^[0-9a-f]{40}$ ]]; then
  die "Recorded previous image tag is invalid."
fi

export FLEET_IMAGE_TAG="${previous_tag:-$new_tag}"
if [[ -n "$previous_tag" ]]; then
  require_unchanged_data_services
else
  require_empty_data_bootstrap
fi

application_changed=false
rollback_attempted=false
on_failure() {
  exit_code=$?
  trap - ERR
  if [[ "$application_changed" == true && -n "$previous_tag" ]]; then
    rollback_attempted=true
    printf 'DEPLOY_FAILED=ROLLING_BACK_APPLICATION_IMAGES\n' >&2
    export FLEET_IMAGE_TAG="$previous_tag"
    fleet_compose up --detach --wait --wait-timeout 180 --no-build --no-deps api web marketing caddy || true
    bash "$SCRIPT_DIR/healthcheck.sh" --internal-only || true
  fi
  printf 'DATABASE_DOWNGRADE_ATTEMPTED=NO\n' >&2
  printf 'AUTOMATIC_APPLICATION_ROLLBACK=%s\n' "$rollback_attempted" >&2
  exit "$exit_code"
}
trap on_failure ERR

export FLEET_IMAGE_TAG="$new_tag"
fleet_compose pull api web marketing caddy
if [[ -z "$previous_tag" ]]; then
  # Only a proven empty first installation may create data services. A failed
  # bootstrap preserves its volumes and requires reviewed recovery on retry.
  fleet_compose pull postgres minio minio-init
  fleet_compose up --detach --wait postgres minio
  fleet_compose up --no-deps --force-recreate --abort-on-container-exit \
    --exit-code-from minio-init minio-init
fi

# The snapshot represents the running release, not the candidate migration.
export FLEET_IMAGE_TAG="${previous_tag:-$new_tag}"
backup_output="$(bash "$SCRIPT_DIR/backup-and-verify.sh")"
printf '%s\n' "$backup_output"
backup_path="$(printf '%s\n' "$backup_output" | sed -n 's/^BACKUP_PATH=//p' | tail -n 1)"
[[ -n "$backup_path" ]] || die "Backup helper did not report a backup path."

export FLEET_IMAGE_TAG="$new_tag"
fleet_compose --profile tools run --rm --no-deps migrate
application_changed=true
fleet_compose up --detach --wait --wait-timeout 180 --no-build --no-deps api web marketing caddy
bash "$SCRIPT_DIR/healthcheck.sh"

write_deploy_state "$new_tag" "$previous_tag" deploy
trap - ERR
printf 'PRODUCTION_DEPLOY=PASS\n'
printf 'IMAGE_TAG=%s\n' "$new_tag"
printf 'PRE_DEPLOY_BACKUP=%s\n' "$backup_path"
