#!/bin/sh
set -eu

mc alias set fleet-local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc mb --ignore-existing "fleet-local/$FLEET_S3_BUCKET" >/dev/null
mc anonymous set none "fleet-local/$FLEET_S3_BUCKET" >/dev/null

if ! mc admin user info fleet-local "$FLEET_S3_ACCESS_KEY_ID" >/dev/null 2>&1; then
  mc admin user add fleet-local "$FLEET_S3_ACCESS_KEY_ID" "$FLEET_S3_SECRET_ACCESS_KEY" >/dev/null
fi

# `policy create` deliberately overwrites an existing policy of the same name,
# so repeated deploys also reconcile policy changes.
mc admin policy create fleet-local fleet-evidence /config/minio-evidence-policy.json >/dev/null
mc admin policy attach fleet-local fleet-evidence --user "$FLEET_S3_ACCESS_KEY_ID" >/dev/null
