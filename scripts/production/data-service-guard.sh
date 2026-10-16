#!/usr/bin/env bash
# Sourced after common.sh. Routine application releases never reconcile data
# services; their existing Compose configuration must still match exactly.

require_unchanged_data_services() {
  local service container recorded_hash hash_service expected_hash
  for service in postgres minio; do
    container="$(fleet_compose ps --all --quiet "$service")"
    [[ -n "$container" && "$container" != *$'\n'* ]] || \
      die "Expected one established ${service} container; recover it through reviewed maintenance."
    [[ "$(docker inspect --format '{{.State.Running}}' "$container")" == true ]] || \
      die "Established ${service} is stopped; routine deployment will not restart or replace it."
    recorded_hash="$(docker inspect --format '{{index .Config.Labels "com.docker.compose.config-hash"}}' "$container")"
    read -r hash_service expected_hash <<<"$(fleet_compose config --hash "$service")"
    [[ "$hash_service" == "$service" && "$expected_hash" =~ ^[0-9a-f]{64}$ ]] || \
      die "Could not verify the ${service} Compose configuration."
    [[ "$recorded_hash" == "$expected_hash" ]] || \
      die "${service} configuration/image changed; use separately reviewed data-service maintenance."
  done
}

require_empty_data_bootstrap() {
  local service volume existing expected_volume candidate
  [[ ! -e "$STATE_FILE" ]] || die "Deployment state exists without a valid release; reviewed recovery is required."
  for service in postgres minio; do
    [[ -z "$(fleet_compose ps --all --quiet "$service")" ]] || \
      die "Existing ${service} container without deployment state; reviewed recovery is required."
  done
  for volume in postgres_data minio_data; do
    existing="$(docker volume ls --quiet \
      --filter "label=com.docker.compose.project=${FLEET_COMPOSE_PROJECT_NAME:-fleet-ai-production}" \
      --filter "label=com.docker.compose.volume=$volume")"
    [[ -z "$existing" ]] || \
      die "Existing ${volume} without deployment state; refusing to bootstrap over preserved data."
    # Compose can reuse its default volume name even when a pre-existing volume
    # has no Compose labels. A label-only search would miss that preserved data.
    expected_volume="${FLEET_COMPOSE_PROJECT_NAME:-fleet-ai-production}_${volume}"
    existing="$(docker volume ls --quiet --filter "name=$expected_volume")"
    while IFS= read -r candidate; do
      [[ "$candidate" != "$expected_volume" ]] || \
        die "Existing named data volume ${volume}; refusing automatic adoption."
    done <<<"$existing"
  done
}
