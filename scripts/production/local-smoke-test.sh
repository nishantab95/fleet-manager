#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
COMPOSE_FILE="$REPO_ROOT/infra/production/docker-compose.yml"
SMOKE_TAG="1111111111111111111111111111111111111111"
SMOKE_REGISTRY="fleet-smoke"
HTTP_PORT="${FLEET_SMOKE_HTTP_PORT:-18080}"
HTTPS_PORT="${FLEET_SMOKE_HTTPS_PORT:-18443}"
die() { printf '[FAILED] %s\n' "$*" >&2; exit 1; }
reuse_images=false
if [[ $# == 1 && "$1" == "--reuse-images" ]]; then
  reuse_images=true
elif [[ $# != 0 ]]; then
  printf 'Usage: %s [--reuse-images]\n' "$0" >&2
  exit 1
fi

for port in "$HTTP_PORT" "$HTTPS_PORT"; do
  [[ "$port" =~ ^[0-9]{1,5}$ ]] && (( 10#$port >= 1 && 10#$port <= 65535 )) ||
    die "Smoke ports must be numeric TCP/UDP ports between 1 and 65535."
done
HTTP_PORT="$((10#$HTTP_PORT))"
HTTPS_PORT="$((10#$HTTPS_PORT))"
[[ "$HTTP_PORT" != "$HTTPS_PORT" ]] || die "Smoke HTTP and HTTPS ports must differ."

for command in docker curl mktemp readlink; do
  command -v "$command" >/dev/null 2>&1 || {
    printf '[FAILED] Required command is unavailable: %s\n' "$command" >&2
    exit 1
  }
done

# Respect Docker's context-over-host precedence, but never use a remote daemon.
# This inspects the selected endpoint without changing the user's context.
if [[ -n "${DOCKER_CONTEXT:-}" ]]; then
  docker_endpoint="$(docker context inspect --format '{{.Endpoints.docker.Host}}' "$DOCKER_CONTEXT")"
elif [[ -n "${DOCKER_HOST:-}" ]]; then
  docker_endpoint="$DOCKER_HOST"
else
  docker_context="$(docker context show)"
  docker_endpoint="$(docker context inspect --format '{{.Endpoints.docker.Host}}' "$docker_context")"
fi
case "$docker_endpoint" in
  unix:///*|npipe:////./pipe/*) ;;
  *) die "Smoke testing requires a local Unix socket or Windows named-pipe Docker endpoint." ;;
esac
# Pin this process to the verified local endpoint even if another terminal
# changes the global active context while the smoke run is in progress.
export DOCKER_HOST="$docker_endpoint"
unset DOCKER_CONTEXT

temp_root="$(mktemp -d "$REPO_ROOT/.production-smoke.XXXXXX")"
[[ ! -L "$temp_root" && "$(readlink -f -- "$temp_root")" == "$temp_root" ]] ||
  die "Smoke artifact directory must be a physical checkout directory."
smoke_suffix="${temp_root##*/.production-smoke.}"
[[ "$smoke_suffix" =~ ^[a-zA-Z0-9]{6}$ ]] || die "Unexpected smoke artifact directory name."
SMOKE_PROJECT="fleet-ai-smoke-${smoke_suffix,,}"
env_file="$temp_root/production.env"
mkdir -p "$temp_root/leads" "$temp_root/backups"
startup_authorized=false

cleanup() {
  exit_code=$?
  trap - EXIT INT TERM
  set +e
  stop_status=NOT_STARTED
  if [[ "$startup_authorized" == true ]]; then
    stop_status=PASS
    # Query and validate exact IDs first. Never pass an empty list to Docker or
    # stop a pre-existing project when collision checking failed.
    if stopped_ids="$(docker container ls --all --quiet --no-trunc --filter "label=com.docker.compose.project=$SMOKE_PROJECT")"; then
      stop_ids=()
      while IFS= read -r container_id; do
        [[ -n "$container_id" ]] || continue
        if [[ ! "$container_id" =~ ^[0-9a-f]{64}$ ]]; then
          stop_status=FAILED_ID_VALIDATION
          break
        fi
        container_project="$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$container_id")"
        if [[ $? != 0 || "$container_project" != "$SMOKE_PROJECT" ]]; then
          stop_status=FAILED_PROJECT_VALIDATION
          break
        fi
        stop_ids+=("$container_id")
      done <<<"$stopped_ids"
      if [[ "$stop_status" == PASS && ${#stop_ids[@]} -gt 0 ]]; then
        docker stop --time 30 -- "${stop_ids[@]}" >/dev/null 2>&1 || stop_status=FAILED_STOP
      fi
    else
      stop_status=FAILED_ENUMERATION
    fi
    [[ "$stop_status" == PASS ]] || {
      printf '[FAILED] Smoke containers could not be safely stopped; inspect the retained project manually.\n' >&2
      (( exit_code != 0 )) || exit_code=1
    }
  fi
  printf 'SMOKE_PROJECT=%s\n' "$SMOKE_PROJECT"
  printf 'SMOKE_ARTIFACT_ROOT=%s\n' "$temp_root"
  printf 'SMOKE_ENV_FILE=%s\n' "$env_file"
  printf 'SMOKE_STOP_STATUS=%s\n' "$stop_status"
  printf 'SMOKE_RETENTION=VOLUMES_CONTAINERS_ARTIFACTS_AND_BACKUPS_PRESERVED\n'
  printf 'SMOKE_MANUAL_REVIEW=Review only this exact project and artifact directory; cleanup requires a separate measured approval. Do not print environment contents or prune Docker resources.\n'
  exit "$exit_code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# A fresh filesystem name does not prove its case-normalized Docker project is
# unused. Refuse both labeled resources and unlabelled default persistent names.
for resource in container volume network; do
  if [[ "$resource" == container ]]; then
    existing="$(docker container ls --all --quiet --filter "label=com.docker.compose.project=$SMOKE_PROJECT")"
  else
    existing="$(docker "$resource" ls --quiet --filter "label=com.docker.compose.project=$SMOKE_PROJECT")"
  fi
  [[ -z "$existing" ]] || die "Smoke project already has Docker resources; no startup was attempted."
done
for volume in postgres_data minio_data caddy_data caddy_config; do
  expected_name="${SMOKE_PROJECT}_$volume"
  existing="$(docker volume ls --quiet --filter "name=$expected_name")"
  while IFS= read -r found; do
    [[ "$found" != "$expected_name" ]] || die "Smoke volume name already exists; no startup was attempted."
  done <<<"$existing"
done
expected_name="${SMOKE_PROJECT}_backend"
existing="$(docker network ls --format '{{.Name}}' --filter "name=$expected_name")"
while IFS= read -r found; do
  [[ "$found" != "$expected_name" ]] || die "Smoke network name already exists; no startup was attempted."
done <<<"$existing"

cat >"$env_file" <<EOF
FLEET_IMAGE_REGISTRY=$SMOKE_REGISTRY
FLEET_IMAGE_TAG=$SMOKE_TAG
FLEET_TLS_EMAIL=smoke@fleetaisystems.invalid
FLEET_CADDY_LOCAL_OPTIONS=local_certs
FLEET_HTTP_PORT=127.0.0.1:$HTTP_PORT
FLEET_HTTPS_PORT=127.0.0.1:$HTTPS_PORT
POSTGRES_DB=fleet
POSTGRES_USER=fleet
POSTGRES_PASSWORD=smoke-database-password
FLEET_DATABASE_URL=postgresql+psycopg://fleet:smoke-database-password@postgres:5432/fleet
MINIO_ROOT_USER=smoke-minio-root
MINIO_ROOT_PASSWORD=smoke-minio-root-password
FLEET_S3_BUCKET=fleet-evidence
FLEET_S3_REGION=us-east-1
FLEET_S3_ACCESS_KEY_ID=smoke-api-access
FLEET_S3_SECRET_ACCESS_KEY=smoke-api-secret-password
FLEET_AUTH_MODE=company_pin
FLEET_PHONE_DEFAULT_REGION=IN
FLEET_JWT_SIGNING_KEY=smoke-only-jwt-signing-key-longer-than-32-characters
FLEET_LOG_LEVEL=INFO
FLEET_EVIDENCE_MAX_BYTES=5000000
FLEET_DATABASE_POOL_SIZE=5
FLEET_DATABASE_MAX_OVERFLOW=2
FLEET_DATABASE_POOL_TIMEOUT_SECONDS=10
FLEET_RATE_LIMIT_REQUESTS_PER_MINUTE=600
FLEET_AUTH_RATE_LIMIT_REQUESTS_PER_MINUTE=60
FLEET_RATE_LIMIT_MAX_CLIENTS=10000
FLEET_LEAD_DIR=$temp_root/leads
FLEET_BACKUP_DIR=$temp_root/backups
EOF
chmod 0600 "$env_file"
# Compose gives process environment precedence over --env-file. Export these
# synthetic values without source/eval so ambient laptop production settings
# cannot redirect a smoke migration, evidence storage or image selection.
while IFS='=' read -r key value; do
  export "$key=$value"
done <"$env_file"
export FLEET_COMPOSE_PROJECT_NAME="$SMOKE_PROJECT"
startup_authorized=true

if [[ "$reuse_images" == true ]]; then
  for component in api web marketing; do
    docker image inspect "$SMOKE_REGISTRY/fleet-$component:$SMOKE_TAG" >/dev/null
  done
else
  docker build --file "$REPO_ROOT/services/api/Dockerfile" \
  --tag "$SMOKE_REGISTRY/fleet-api:$SMOKE_TAG" "$REPO_ROOT"
  docker build --file "$REPO_ROOT/apps/web/Dockerfile" \
  --tag "$SMOKE_REGISTRY/fleet-web:$SMOKE_TAG" "$REPO_ROOT"
  docker build --file "$REPO_ROOT/apps/marketing/Dockerfile" \
  --tag "$SMOKE_REGISTRY/fleet-marketing:$SMOKE_TAG" "$REPO_ROOT"
fi

compose=(docker compose --project-name "$SMOKE_PROJECT" --env-file "$env_file" --file "$COMPOSE_FILE")
"${compose[@]}" config --quiet
"${compose[@]}" up --detach --wait postgres minio
"${compose[@]}" up --no-deps --force-recreate --abort-on-container-exit \
  --exit-code-from minio-init minio-init
"${compose[@]}" --profile tools run migrate
"${compose[@]}" up --detach --no-build api web marketing caddy

healthy=false
for _ in $(seq 1 90); do
  if curl --noproxy '*' --connect-timeout 3 --max-time 10 --insecure --fail --silent --resolve "api.fleetaisystems.com:$HTTPS_PORT:127.0.0.1" \
    "https://api.fleetaisystems.com:$HTTPS_PORT/ready" | grep -q '"status":"ready"'; then
    healthy=true
    break
  fi
  sleep 1
done
[[ "$healthy" == true ]] || { printf '[FAILED] Smoke stack did not become ready.\n' >&2; exit 1; }

for service in postgres minio api web marketing; do
  container_id="$("${compose[@]}" ps --quiet "$service")"
  [[ -n "$container_id" && -z "$(docker port "$container_id")" ]] || {
    printf '[FAILED] Private service publishes a host port: %s\n' "$service" >&2
    exit 1
  }
done

curl --noproxy '*' --connect-timeout 3 --max-time 10 --insecure --fail --silent --resolve "fleetaisystems.com:$HTTPS_PORT:127.0.0.1" \
  "https://fleetaisystems.com:$HTTPS_PORT/privacy" | grep -q 'Privacy'
curl --noproxy '*' --connect-timeout 3 --max-time 10 --insecure --fail --silent --resolve "app.fleetaisystems.com:$HTTPS_PORT:127.0.0.1" \
  "https://app.fleetaisystems.com:$HTTPS_PORT/api/backend/health" | grep -q '"status":"ok"'
for private_url in \
  "https://api.fleetaisystems.com:$HTTPS_PORT/docs" \
  "https://api.fleetaisystems.com:$HTTPS_PORT/openapi.json" \
  "https://api.fleetaisystems.com:$HTTPS_PORT/api/v1/admin/pilot-releases" \
  "https://api.fleetaisystems.com:$HTTPS_PORT/api/v1/owner/assets"; do
  status="$(curl --noproxy '*' --connect-timeout 3 --max-time 10 --insecure --silent --output /dev/null --write-out '%{http_code}' \
    --resolve "api.fleetaisystems.com:$HTTPS_PORT:127.0.0.1" "$private_url")"
  [[ "$status" == "404" ]] || { printf '[FAILED] Private route returned HTTP %s: %s\n' "$status" "$private_url" >&2; exit 1; }
done

"${compose[@]}" exec -T postgres psql --username fleet --dbname fleet --set ON_ERROR_STOP=1 \
  --command 'CREATE TABLE smoke_persistence (id integer PRIMARY KEY); INSERT INTO smoke_persistence VALUES (1);' >/dev/null
"${compose[@]}" exec -T minio sh -ec \
  'mc alias set smoke http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null; printf evidence-persistence | mc pipe "smoke/fleet-evidence/smoke/persistence.txt" >/dev/null'
"${compose[@]}" restart postgres minio api >/dev/null
"${compose[@]}" exec -T postgres psql --tuples-only --no-align --username fleet --dbname fleet \
  --command 'SELECT count(*) FROM smoke_persistence;' | grep -qx '1'
"${compose[@]}" exec -T minio sh -ec \
  'mc alias set smoke http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null; mc stat "smoke/fleet-evidence/smoke/persistence.txt" >/dev/null'

export FLEET_PRODUCTION_ENV_FILE="$env_file"
export FLEET_PRODUCTION_STATE_DIR="$temp_root/state"
export FLEET_COMPOSE_PROJECT_NAME="$SMOKE_PROJECT"
export FLEET_LOCAL_SMOKE_WINDOWS_ACL=1
bash -ec 'source "$1/common.sh"; source "$1/data-service-guard.sh"; require_unchanged_data_services' \
  _ "$SCRIPT_DIR"
backup_output="$(bash "$SCRIPT_DIR/backup.sh")"
printf '%s\n' "$backup_output"
backup_path="$(printf '%s\n' "$backup_output" | sed -n 's/^BACKUP_PATH=//p' | tail -n 1)"
bash "$SCRIPT_DIR/verify-backup.sh" "$backup_path"
bash "$SCRIPT_DIR/healthcheck.sh" --internal-only

printf 'LOCAL_RESOURCE_SNAPSHOT (idle local Docker Desktop; not a VPS load test)\n'
running_ids="$("${compose[@]}" ps --quiet --status running)"
[[ -n "$running_ids" ]] || die "No smoke containers were available for the resource snapshot."
mapfile -t running_containers <<<"$running_ids"
docker stats --no-stream "${running_containers[@]}"
printf 'PERSISTENT_DISK_KIB\n'
"${compose[@]}" exec -T postgres sh -ec 'du -sk /var/lib/postgresql/data'
"${compose[@]}" exec -T minio sh -ec 'du -sk /data'
printf 'APPLICATION_IMAGE_BYTES\n'
for component in api web marketing; do
  docker image inspect --format '{{.RepoTags}} {{.Size}}' \
    "$SMOKE_REGISTRY/fleet-$component:$SMOKE_TAG"
done

printf 'PRODUCTION_SMOKE=PASS\n'
printf 'PERSISTENCE_RESTART=PASS\n'
printf 'PRIVATE_PORTS=PASS\n'
printf 'CADDY_PRIVATE_ROUTES=PASS\n'
printf 'DATA_SERVICE_GUARD=PASS\n'
printf 'LOCAL_BACKUP_RESTORE=PASS\n'
