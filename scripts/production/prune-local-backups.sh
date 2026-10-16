#!/usr/bin/env bash
# Historical command name; REPORT ONLY. There is deliberately no deletion mode.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_command find
require_command realpath
require_command stat
require_command sort
keep=2
if (( $# != 0 )); then
  [[ $# -eq 2 && "$1" == --keep && "$2" =~ ^[0-9]{1,6}$ ]] || \
    die "Usage: $0 [--keep N>=2] (report only; no deletion mode)"
  keep=$((10#$2))
fi
(( keep >= 2 )) || die "At least two completed offsite-backed generations must be retained."
backup_root="$(env_value FLEET_BACKUP_DIR)"
[[ "$backup_root" == /* && "$backup_root" != / && "$backup_root" != *$'\n'* &&
   "$backup_root" != *$'\r'* && "$backup_root" != *$'\t'* ]] || \
  die "FLEET_BACKUP_DIR must be an absolute non-root canonical path."
resolved="$(realpath -e -- "$backup_root")"
[[ "$resolved" == "$backup_root" && -d "$backup_root" && -r "$backup_root" && -x "$backup_root" ]] || \
  die "Backup root must be an accessible canonical directory without symlink ancestors."
device="$(stat -c '%d' -- "$backup_root")"
completed=()
shopt -s nullglob dotglob
printf 'LOCAL_BACKUP_RETENTION=REPORT_ONLY keep=%s\n' "$keep"
for backup_path in "$backup_root"/*; do
  name="${backup_path##*/}"
  reason=''
  if [[ -L "$backup_path" || ! -d "$backup_path" ]]; then
    reason=link_or_non_directory
  elif [[ "$(stat -c '%d' -- "$backup_path")" != "$device" ]]; then
    reason=mounted_generation
  elif [[ ! "$name" =~ ^fleet-[0-9]{8}-[0-9]{6}Z-[[:alnum:]]{6}$ ]]; then
    reason=unknown_generation_name
  else
    for required in postgres.dump postgres.sha256 evidence.sha256 evidence.present manifest.txt .offsite-complete; do
      [[ -f "$backup_path/$required" && ! -L "$backup_path/$required" ]] || reason=incomplete_or_linked
    done
    [[ -d "$backup_path/evidence" && ! -L "$backup_path/evidence" &&
       -s "$backup_path/postgres.dump" && -s "$backup_path/postgres.sha256" &&
       -s "$backup_path/manifest.txt" && -s "$backup_path/.offsite-complete" ]] || reason=incomplete_or_linked
    for child in "$backup_path"/*; do
      case "${child##*/}" in
        postgres.dump|postgres.sha256|evidence|evidence.sha256|evidence.present|manifest.txt|.offsite-complete) ;;
        *) reason=unknown_or_partial_content ;;
      esac
    done
  fi
  if [[ -z "$reason" ]]; then
    unsafe="$(find -P "$backup_path" -xdev \( -type l -o -type f -links +1 -o ! \( -type f -o -type d \) \) -print -quit)"
    devices="$(find -P "$backup_path" -xdev -type d -printf '%D\n' | sort -u)"
    [[ -z "$unsafe" && "$devices" == "$device" ]] || reason=linked_nonregular_or_mounted_content
  fi
  if [[ -n "$reason" ]]; then
    printf 'LOCAL_BACKUP_PRESERVED reason=%s path=%q\n' "$reason" "$backup_path"
    continue
  fi
  sizes="$(find -P "$backup_path" -xdev -type f -printf '%s\n')"
  bytes=0
  while IFS= read -r size; do bytes=$((bytes + size)); done <<<"$sizes"
  stamp="$(stat -c '%Y' -- "$backup_path/.offsite-complete")"
  completed+=("$(printf '%020d\t%s\t%s' "$stamp" "$bytes" "$backup_path")")
done
if (( ${#completed[@]} )); then
  sorted="$(printf '%s\n' "${completed[@]}" | sort -r)"
  index=0
  while IFS=$'\t' read -r stamp bytes backup_path; do
    status=RETAIN
    if (( index >= keep )); then status=REVIEW_CANDIDATE; fi
    printf 'LOCAL_BACKUP_%s logical_bytes=%s path=%q\n' "$status" "$bytes" "$backup_path"
    index=$((index + 1))
  done <<<"$sorted"
fi
printf 'OPERATOR_APPROVAL_REQUIRED=YES; verify independent offsite restore and preserve at least two verified generations before separately approving any removal.\n'
printf 'LOCAL_BACKUPS_REMOVED=0\n'
