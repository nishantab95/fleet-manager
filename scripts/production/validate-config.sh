#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_command docker
require_command sed
require_command stat
require_command restic
require_production_files

permissions="$(stat -c '%a' "$ENV_FILE")"
if (( (8#$permissions & 8#077) != 0 )); then
  die "Production environment file must not be readable or writable by group/other (expected chmod 600)."
fi

required=(
  FLEET_IMAGE_REGISTRY FLEET_IMAGE_TAG FLEET_TLS_EMAIL
  POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD FLEET_DATABASE_URL
  MINIO_ROOT_USER MINIO_ROOT_PASSWORD FLEET_S3_BUCKET
  FLEET_S3_ACCESS_KEY_ID FLEET_S3_SECRET_ACCESS_KEY
  FLEET_AUTH_MODE
  FLEET_JWT_SIGNING_KEY FLEET_LEAD_DIR FLEET_BACKUP_DIR
)

for key in "${required[@]}"; do
  value="$(env_value "$key")"
  [[ "$value" != *CHANGE_ME* ]] || die "${key} still contains a placeholder."
  [[ "$value" != *'<'* && "$value" != *'>'* ]] || die "${key} still contains a placeholder."
done

[[ "$(env_value FLEET_S3_BUCKET)" == "fleet-evidence" ]] || \
  die "FLEET_S3_BUCKET must remain fleet-evidence because the least-privilege policy is bucket-specific."
[[ "$(env_value FLEET_AUTH_MODE)" == "company_pin" ]] || \
  die "Production requires the owner-issued activation and device PIN flow: FLEET_AUTH_MODE=company_pin."
[[ "$(env_value FLEET_DATABASE_URL)" == postgresql+psycopg://*'@postgres:5432/'* ]] || \
  die "FLEET_DATABASE_URL must use psycopg and the internal postgres service."
[[ "$(env_value FLEET_IMAGE_REGISTRY)" == ghcr.io/* ]] || \
  die "FLEET_IMAGE_REGISTRY must be a ghcr.io namespace."

jwt_key="$(env_value FLEET_JWT_SIGNING_KEY)"
(( ${#jwt_key} >= 32 )) || die "FLEET_JWT_SIGNING_KEY must contain at least 32 characters."

lead_dir="$(env_value FLEET_LEAD_DIR)"
backup_dir="$(env_value FLEET_BACKUP_DIR)"
[[ "$lead_dir" == /* && -d "$lead_dir" ]] || die "FLEET_LEAD_DIR must be an existing absolute directory."
[[ "$backup_dir" == /* && -d "$backup_dir" ]] || die "FLEET_BACKUP_DIR must be an existing absolute directory."
[[ "$lead_dir" != "$backup_dir" ]] || die "Lead storage and backup storage must be separate directories."

[[ -f "$RESTIC_ENV_FILE" ]] || die "Encrypted offsite backup configuration is missing: $RESTIC_ENV_FILE"
restic_permissions="$(stat -c '%a' "$RESTIC_ENV_FILE")"
if (( (8#$restic_permissions & 8#077) != 0 )); then
  die "Restic environment file must not be readable or writable by group/other (expected chmod 600)."
fi
restic_repository="$(file_env_value "$RESTIC_ENV_FILE" RESTIC_REPOSITORY)"
restic_password_file="$(file_env_value "$RESTIC_ENV_FILE" RESTIC_PASSWORD_FILE)"
[[ "$restic_repository" != *CHANGE_ME* ]] || die "RESTIC_REPOSITORY still contains a placeholder."
[[ "$restic_password_file" == /* && -f "$restic_password_file" ]] || \
  die "RESTIC_PASSWORD_FILE must be an existing absolute file."
password_permissions="$(stat -c '%a' "$restic_password_file")"
if (( (8#$password_permissions & 8#077) != 0 )); then
  die "Restic password file must not be readable or writable by group/other (expected chmod 600)."
fi

fleet_compose config --quiet
printf 'PRODUCTION_CONFIG=VALID\n'
printf 'SECRETS_PRINTED=NO\n'
