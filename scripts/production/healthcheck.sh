#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

internal_only=false
if [[ "$#" == 1 && "${1:-}" == "--internal-only" ]]; then
  internal_only=true
elif [[ $# -ne 0 ]]; then
  die "Usage: $0 [--internal-only]"
fi

require_command curl
require_command docker
require_production_files

check_host_resources() {
  [[ "$(uname -s)" == Linux ]] || die "Production host resource checks require Linux."
  for required in timeout df awk; do
    require_command "$required"
  done
  local docker_root backup_root label path reading available used extra
  docker_root="$(timeout 10s docker info --format '{{.DockerRootDir}}' 2>/dev/null)" ||
    die "Could not read Docker storage location within 10 seconds."
  [[ "$docker_root" == /* && -d "$docker_root" ]] || die "Docker storage location is unavailable."
  backup_root="$(env_value FLEET_BACKUP_DIR)"
  [[ "$backup_root" == /* && -d "$backup_root" ]] || die "Backup filesystem is unavailable."
  for label in root docker backups; do
    case "$label" in
      root) path=/ ;;
      docker) path="$docker_root" ;;
      backups) path="$backup_root" ;;
    esac
    reading="$(timeout 5s df --block-size=1 --output=avail,pcent -- "$path" 2>/dev/null)" ||
      die "Could not read ${label} filesystem capacity within 5 seconds."
    reading="$(awk 'NR == 2 && NF == 2 { print $1, $2 } END { if (NR != 2) exit 1 }' <<<"$reading")" ||
      die "Invalid ${label} filesystem capacity response."
    read -r available used extra <<<"$reading"
    [[ "$available" =~ ^(0|[1-9][0-9]*)$ && "$used" =~ ^(0|[1-9][0-9]*)%$ && -z "$extra" ]] ||
      die "Invalid ${label} filesystem capacity values."
    used="${used%%%}"
    printf 'HOST_DISK_%s_AVAILABLE_BYTES=%s\nHOST_DISK_%s_USED_PERCENT=%s\n' "$label" "$available" "$label" "$used"
    (( used < 75 && available >= 10000000000 )) ||
      die "${label} filesystem requires less than 75% used and at least 10 GB free."
  done

  local memory total load
  memory="$(timeout 5s awk '
    $1 == "MemTotal:" { total=$2; totals++; if (NF != 3 || $3 != "kB" || $2 !~ /^[0-9]+$/) bad=1 }
    $1 == "MemAvailable:" { available=$2; availables++; if (NF != 3 || $3 != "kB" || $2 !~ /^[0-9]+$/) bad=1 }
    END {
      if (bad || totals != 1 || availables != 1 || total <= 0 || available < 0 || available > total) exit 1
      printf "%.0f %.0f\n", total, available
    }' /proc/meminfo 2>/dev/null)" || die "Linux available-memory measurement failed."
  read -r total available <<<"$memory"
  printf 'HOST_MEMORY_TOTAL_KIB=%s\nHOST_MEMORY_AVAILABLE_KIB=%s\n' "$total" "$available"
  (( available * 100 > total * 30 )) || die "Host available memory must exceed 30% of total."

  load="$(timeout 5s awk 'NR == 1 && NF >= 3 && $3 ~ /^[0-9]+([.][0-9]+)?$/ { print $3; valid=1 } END { if (!valid || NR != 1) exit 1 }' \
    /proc/loadavg 2>/dev/null)" || die "Linux 15-minute load measurement failed."
  printf 'HOST_LOAD_15_MINUTES=%s\n' "$load"
  awk -v load="$load" 'BEGIN { exit !(load <= 1.5) }' || die "15-minute load exceeds the 2-vCPU envelope of 1.5."
  printf 'HOST_RESOURCES=PASS\n'
}

if [[ "$internal_only" == true ]]; then
  printf 'HOST_RESOURCES=SKIPPED_INTERNAL_ONLY\n'
else
  check_host_resources
fi

# Bound every external probe and allow short startup/ACME transients to settle.
public_curl=(curl --connect-timeout 5 --max-time 15 --retry 4 --retry-delay 2 --retry-all-errors)

for service in postgres minio api web marketing caddy; do
  container_id="$(fleet_compose ps --quiet "$service")"
  [[ -n "$container_id" ]] || die "${service} has no running container."
  running="$(docker inspect --format '{{.State.Running}}' "$container_id")"
  [[ "$running" == "true" ]] || die "${service} is not running."
done

api_health="$(fleet_compose exec -T api python -c "import json,urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3))['status'])")"
api_ready="$(fleet_compose exec -T api python -c "import json,urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3))['status'])")"
[[ "$api_health" == "ok" && "$api_ready" == "ready" ]] || die "Internal API health/readiness failed."

if [[ "$internal_only" == false ]]; then
  [[ "$("${public_curl[@]}" --fail --silent --show-error https://api.fleetaisystems.com/health | tr -d '\r\n')" == *'"status":"ok"'* ]] || die "Public API health failed."
  [[ "$("${public_curl[@]}" --fail --silent --show-error https://app.fleetaisystems.com/api/backend/health | tr -d '\r\n')" == *'"status":"ok"'* ]] || die "Owner dashboard proxy health failed."
  [[ "$("${public_curl[@]}" --fail --silent --show-error https://fleetaisystems.com/health | tr -d '\r\n')" == *'"status":"ok"'* ]] || die "Marketing health failed."

  for url in \
    https://api.fleetaisystems.com/docs \
    https://api.fleetaisystems.com/openapi.json \
    https://api.fleetaisystems.com/api/v1/admin/company \
    https://api.fleetaisystems.com/api/v1/owner/assets \
    https://fleetaisystems.com/owner; do
    status="$("${public_curl[@]}" --silent --output /dev/null --write-out '%{http_code}' "$url")"
    [[ "$status" == "404" ]] || die "Private-route check failed for ${url}: HTTP ${status}."
  done
fi

printf 'PRODUCTION_HEALTH=PASS\n'
printf 'EXTERNAL_CHECKS=%s\n' "$([[ "$internal_only" == true ]] && printf SKIPPED || printf PASS)"
