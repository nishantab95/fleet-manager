#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 5 ]]; then
  printf 'Usage: %s <bundle.aab> <package> <version-name> <version-code> <track:status>\n' "$0" >&2
  exit 2
fi

bundle="$1"
package="$2"
version_name="$3"
version_code="$4"
track_status="$5"
track="${track_status%%:*}"
status="${track_status#*:}"

[[ -f "$bundle" ]] || { printf '[FAILED] AAB does not exist.\n' >&2; exit 1; }
[[ "$package" == "com.fleetmanager.fleet_manager_mobile" ]] || { printf '[FAILED] Unexpected Play package.\n' >&2; exit 1; }
[[ "$version_name" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { printf '[FAILED] Invalid version name.\n' >&2; exit 1; }
[[ "$version_code" =~ ^[1-9][0-9]*$ ]] || { printf '[FAILED] Invalid version code.\n' >&2; exit 1; }
[[ "$track" =~ ^(internal|alpha|beta|production)$ ]] || { printf '[FAILED] Invalid Play track.\n' >&2; exit 1; }
[[ "$status" =~ ^(draft|completed)$ ]] || { printf '[FAILED] Invalid Play release status.\n' >&2; exit 1; }

for command in curl python3; do
  command -v "$command" >/dev/null 2>&1 || { printf '[FAILED] Required command is unavailable: %s\n' "$command" >&2; exit 1; }
done

token="${PLAY_ACCESS_TOKEN:-}"
[[ -n "$token" ]] || { printf '[FAILED] PLAY_ACCESS_TOKEN with the Android Publisher OAuth scope is required.\n' >&2; exit 1; }
api="https://androidpublisher.googleapis.com/androidpublisher/v3/applications/$package"
upload_api="https://androidpublisher.googleapis.com/upload/androidpublisher/v3/applications/$package"
temporary="$(mktemp -d)"
edit_id=""

discard_edit() {
  if [[ -n "$edit_id" ]]; then
    curl --silent --request DELETE \
      --header "Authorization: Bearer $token" \
      "$api/edits/$edit_id" >/dev/null 2>&1 || true
  fi
  rm -rf -- "$temporary"
}
trap discard_edit EXIT

curl --fail-with-body --silent --show-error --request POST \
  --header "Authorization: Bearer $token" \
  --header 'Content-Type: application/json' \
  --data '{}' \
  "$api/edits" >"$temporary/edit.json"
edit_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["id"])' "$temporary/edit.json")"
[[ -n "$edit_id" ]] || { printf '[FAILED] Google Play did not create an edit.\n' >&2; exit 1; }

curl --fail-with-body --silent --show-error --request POST \
  --header "Authorization: Bearer $token" \
  --header 'Content-Type: application/octet-stream' \
  --data-binary "@$bundle" \
  "$upload_api/edits/$edit_id/bundles?uploadType=media" >"$temporary/bundle.json"
uploaded_version="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["versionCode"])' "$temporary/bundle.json")"
[[ "$uploaded_version" == "$version_code" ]] || { printf '[FAILED] Google Play returned a different versionCode.\n' >&2; exit 1; }

python3 - "$temporary/track.json" "$version_name" "$version_code" "$status" <<'PY'
import json
import sys

path, version_name, version_code, status = sys.argv[1:]
with open(path, "w", encoding="utf-8") as handle:
    json.dump(
        {
            "releases": [
                {
                    "name": f"Fleet AI Systems {version_name} ({version_code})",
                    "status": status,
                    "versionCodes": [version_code],
                }
            ]
        },
        handle,
        separators=(",", ":"),
    )
PY

curl --fail-with-body --silent --show-error --request PUT \
  --header "Authorization: Bearer $token" \
  --header 'Content-Type: application/json' \
  --data-binary "@$temporary/track.json" \
  "$api/edits/$edit_id/tracks/$track" >"$temporary/track-response.json"

curl --fail-with-body --silent --show-error --request POST \
  --header "Authorization: Bearer $token" \
  --header 'Content-Type: application/json' \
  --data '{}' \
  "$api/edits/$edit_id:commit" >"$temporary/commit.json"

edit_id=""
printf 'GOOGLE_PLAY_UPLOAD=PASS\n'
printf 'PACKAGE=%s\n' "$package"
printf 'VERSION=%s\n' "$version_name"
printf 'VERSION_CODE=%s\n' "$version_code"
printf 'TRACK=%s\n' "$track"
printf 'STATUS=%s\n' "$status"
