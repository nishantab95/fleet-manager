#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_command find
backup_root="$(cd -- "$(env_value FLEET_BACKUP_DIR)" && pwd -P)"
[[ "$backup_root" != "/" ]] || die "FLEET_BACKUP_DIR may not be the filesystem root."

mapfile -t completed < <(
  find "$backup_root" -mindepth 2 -maxdepth 2 -type f -name .offsite-complete \
    -printf '%T@ %h\n' | sort -rn | cut -d' ' -f2-
)
if (( ${#completed[@]} <= 2 )); then
  printf 'LOCAL_BACKUP_PRUNE=NOT_NEEDED\n'
  exit 0
fi

for backup_path in "${completed[@]:2}"; do
  resolved="$(cd -- "$backup_path" && pwd -P)"
  [[ "$resolved" == "$backup_root"/fleet-* && -f "$resolved/.offsite-complete" ]] || \
    die "Refusing to prune an unexpected path: $resolved"
  rm -rf -- "$resolved"
  printf 'LOCAL_BACKUP_PRUNED=%s\n' "$(basename -- "$resolved")"
done
printf 'LOCAL_BACKUP_RETENTION=2_VERIFIED_OFFSITE_GENERATIONS\n'
