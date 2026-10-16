#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
COMPOSE_FILE="$REPO_ROOT/infra/production/docker-compose.yml"
ENV_FILE="${FLEET_PRODUCTION_ENV_FILE:-/etc/fleet-ai/production.env}"
STATE_DIR="${FLEET_PRODUCTION_STATE_DIR:-/var/lib/fleet-ai/deploy}"
STATE_FILE="$STATE_DIR/current.env"
HISTORY_FILE="$STATE_DIR/history.tsv"
LOCK_FILE="$STATE_DIR/deploy.lock"
RESTIC_ENV_FILE="${FLEET_RESTIC_ENV_FILE:-/etc/fleet-ai/restic.env}"

die() {
  printf '[FAILED] %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command is unavailable: $1"
}

env_value() {
  local key="$1"
  local value
  value="$(sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n 1 | tr -d '\r')"
  [[ -n "$value" ]] || die "Missing ${key} in ${ENV_FILE}"
  printf '%s' "$value"
}

file_env_value() {
  local file="$1"
  local key="$2"
  local value
  value="$(sed -n "s/^${key}=//p" "$file" | tail -n 1 | tr -d '\r')"
  [[ -n "$value" ]] || die "Missing ${key} in ${file}"
  printf '%s' "$value"
}

optional_file_env_value() {
  local file="$1"
  local key="$2"
  sed -n "s/^${key}=//p" "$file" | tail -n 1 | tr -d '\r'
}

state_value() {
  local key="$1"
  [[ -f "$STATE_FILE" ]] || return 0
  sed -n "s/^${key}=//p" "$STATE_FILE" | tail -n 1 | tr -d '\r'
}

current_image_tag() {
  local tag="${FLEET_IMAGE_TAG:-}"
  if [[ -z "$tag" ]]; then
    tag="$(state_value FLEET_IMAGE_TAG)"
  fi
  if [[ -z "$tag" ]]; then
    tag="$(env_value FLEET_IMAGE_TAG)"
  fi
  [[ "$tag" =~ ^[0-9a-f]{40}$ ]] || die "The current image tag is not a full lowercase Git commit SHA."
  printf '%s' "$tag"
}

fleet_compose() {
  local tag
  tag="$(current_image_tag)"
  FLEET_IMAGE_TAG="$tag" docker compose \
    --project-name "${FLEET_COMPOSE_PROJECT_NAME:-fleet-ai-production}" \
    --env-file "$ENV_FILE" \
    --file "$COMPOSE_FILE" \
    --project-directory "$REPO_ROOT/infra/production" \
    "$@"
}

write_deploy_state() {
  local tag="$1"
  local previous_tag="${2:-}"
  local action="${3:-deploy}"
  local registry
  registry="$(env_value FLEET_IMAGE_REGISTRY)"
  local api_digest web_digest marketing_digest deployed_at
  api_digest="$(docker image inspect --format '{{index .RepoDigests 0}}' "$registry/fleet-api:$tag")"
  web_digest="$(docker image inspect --format '{{index .RepoDigests 0}}' "$registry/fleet-web:$tag")"
  marketing_digest="$(docker image inspect --format '{{index .RepoDigests 0}}' "$registry/fleet-marketing:$tag")"
  [[ "$api_digest" == *@sha256:* && "$web_digest" == *@sha256:* && "$marketing_digest" == *@sha256:* ]] || \
    die "Pulled application images do not have registry digests."
  deployed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  install -d -m 0700 "$STATE_DIR"
  local temporary="$STATE_FILE.new"
  {
    printf 'FLEET_IMAGE_TAG=%s\n' "$tag"
    printf 'FLEET_PREVIOUS_IMAGE_TAG=%s\n' "$previous_tag"
    printf 'FLEET_DEPLOYED_AT=%s\n' "$deployed_at"
    printf 'FLEET_API_IMAGE=%s\n' "$api_digest"
    printf 'FLEET_WEB_IMAGE=%s\n' "$web_digest"
    printf 'FLEET_MARKETING_IMAGE=%s\n' "$marketing_digest"
  } >"$temporary"
  chmod 0600 "$temporary"
  mv -f -- "$temporary" "$STATE_FILE"
  if [[ ! -f "$HISTORY_FILE" ]]; then
    printf 'deployed_at\taction\timage_tag\tprevious_tag\tapi_image\tweb_image\tmarketing_image\n' >"$HISTORY_FILE"
    chmod 0600 "$HISTORY_FILE"
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$deployed_at" "$action" "$tag" "$previous_tag" \
    "$api_digest" "$web_digest" "$marketing_digest" >>"$HISTORY_FILE"
}

require_production_files() {
  [[ -f "$ENV_FILE" ]] || die "Production environment file is missing: $ENV_FILE"
  [[ -f "$COMPOSE_FILE" ]] || die "Production Compose file is missing: $COMPOSE_FILE"
  [[ -f "$REPO_ROOT/infra/production/Caddyfile" ]] || die "Production Caddyfile is missing."
}
