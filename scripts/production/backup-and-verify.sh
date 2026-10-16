#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
output="$(bash "$SCRIPT_DIR/backup.sh")"
printf '%s\n' "$output"
backup_path="$(printf '%s\n' "$output" | sed -n 's/^BACKUP_PATH=//p' | tail -n 1)"
[[ -n "$backup_path" ]] || { printf '[FAILED] Backup path was not reported.\n' >&2; exit 1; }
bash "$SCRIPT_DIR/verify-backup.sh" "$backup_path"
bash "$SCRIPT_DIR/offsite-backup.sh" "$backup_path"
# Retention is a separately reviewed manual operation, never part of backup,
# deployment, rollback or the scheduled timer.
printf 'SCHEDULED_BACKUP=PASS\n'
