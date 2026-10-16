#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

internal_only=false
if [[ "${1:-}" == "--internal-only" ]]; then
  internal_only=true
elif [[ $# -ne 0 ]]; then
  die "Usage: $0 [--internal-only]"
fi

require_command curl
require_command docker
require_production_files

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
