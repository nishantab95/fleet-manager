#!/usr/bin/env bash
# CI transport helper, sent over pinned SSH stdin; not part of the runtime bundle.
set -Eeuo pipefail
umask 077

DEPLOY_ROOT="/opt/fleet-ai"
STATE_ROOT="/var/lib/fleet-ai/deploy"
die() { printf '[FAILED] %s\n' "$*" >&2; exit 1; }

[[ "$#" == 2 || "$#" == 4 ]] || die "Expected prepare RUN_ID or install RUN_ID COMMIT ARCHIVE_SHA256."
action="$1"
run_id="$2"
[[ "$run_id" =~ ^[0-9]+-[0-9]+$ ]] || die "Invalid workflow run identifier."
[[ "$action" == prepare || "$action" == install ]] || die "Unknown transport action."

for required in bash flock readlink sha256sum tar mkdir ln mv; do
  command -v "$required" >/dev/null 2>&1 || die "Required command unavailable: $required"
done

require_directory() {
  [[ -d "$1" && ! -L "$1" && "$(readlink -f -- "$1")" == "$1" ]] ||
    die "Expected an existing physical deployment directory: $1"
}
require_directory "$DEPLOY_ROOT"
require_directory "$DEPLOY_ROOT/releases"
require_directory "$DEPLOY_ROOT/incoming"
require_directory "$STATE_ROOT"

# Hold the same lock as direct deploy/rollback until pointer activation finishes.
# The child verifies the inherited descriptor's inode before reusing it.
lock_file="$STATE_ROOT/deploy.lock"
[[ ! -L "$lock_file" && ( ! -e "$lock_file" || -f "$lock_file" ) ]] || die "Deployment lock must be a regular file."
exec 9>"$lock_file"
flock -n 9 || die "Another production deploy or rollback is already running."

current="$DEPLOY_ROOT/repository"
current_target() {
  local target release_id
  if [[ ! -e "$current" && ! -L "$current" ]]; then
    printf '\n'
    return
  fi
  [[ -L "$current" ]] || die "Existing repository must be transitioned manually; refusing to replace it."
  target="$(readlink -f -- "$current")" || die "Current release link is invalid."
  release_id="${target##*/}"
  [[ "$release_id" =~ ^[0-9a-f]{40}$ && "$target" == "$DEPLOY_ROOT/releases/$release_id" ]] ||
    die "Current release link is outside the managed release layout."
  require_directory "$target"
  [[ -f "$target/release.sha" && ! -L "$target/release.sha" && "$(<"$target/release.sha")" == "$release_id" ]] ||
    die "Current release marker is missing or inconsistent."
  printf '%s\n' "$target"
}
previous_target="$(current_target)"
incoming="$DEPLOY_ROOT/incoming/$run_id"

if [[ "$action" == prepare ]]; then
  [[ "$#" == 2 ]] || die "Unexpected prepare arguments."
  [[ ! -e "$incoming" && ! -L "$incoming" ]] || die "Incoming run directory already exists; inspect it manually."
  mkdir -m 0700 -- "$incoming"
  printf 'OPERATIONS_BUNDLE_INCOMING=%s\n' "$incoming"
  exit 0
fi

[[ "$#" == 4 ]] || die "Missing install arguments."
commit="$3"
archive_sha="$4"
[[ "$commit" =~ ^[0-9a-f]{40}$ ]] || die "Invalid release commit."
[[ "$archive_sha" =~ ^[0-9a-f]{64}$ ]] || die "Invalid archive SHA256."
require_directory "$incoming"
archive="$incoming/deploy.tar.gz"
[[ -f "$archive" && ! -L "$archive" ]] || die "Expected a regular uploaded archive."
actual_sha="$(sha256sum -- "$archive")"
[[ "${actual_sha%% *}" == "$archive_sha" ]] || die "Uploaded archive checksum mismatch."

release="$DEPLOY_ROOT/releases/$commit"
[[ ! -e "$release" && ! -L "$release" ]] || die "Release path already exists; inspect/retry the retained bundle manually."
mkdir -m 0750 -- "$release"
# The trusted CI builder permits only fixed regular paths, never symlinks or
# traversal. Its archive digest is checked above. Public config files must stay
# readable inside cap_drop=ALL containers when bind-mounted; secrets are absent.
umask 022
tar --extract --gzip --file "$archive" --directory "$release" \
  --keep-old-files --no-same-owner --no-same-permissions
umask 077
[[ -f "$release/release.sha" && ! -L "$release/release.sha" && "$(<"$release/release.sha")" == "$commit" ]] ||
  die "Release marker does not match the approved commit."
[[ -f "$release/deploy-manifest.json" && ! -L "$release/deploy-manifest.json" ]] || die "Missing bundle manifest."
[[ -f "$release/scripts/production/deploy.sh" && ! -L "$release/scripts/production/deploy.sh" ]] || die "Missing deployment entry point."

FLEET_PRODUCTION_STATE_DIR="$STATE_ROOT" FLEET_DEPLOY_LOCK_INHERITED=1 \
  bash "$release/scripts/production/deploy.sh" --image-tag "$commit"

# Do not overwrite an operator's concurrent pointer change. A failure here can
# leave healthy new containers with the old pointer: retain both and reconcile.
updated_target="$(current_target)"
[[ "$updated_target" == "$previous_target" ]] || die "Current release changed during deployment; manual reconciliation required."
next_link="$DEPLOY_ROOT/.repository-$run_id"
[[ ! -e "$next_link" && ! -L "$next_link" ]] || die "Activation link already exists; manual reconciliation required."
ln -s -- "$release" "$next_link"
mv -T -- "$next_link" "$current"
printf 'OPERATIONS_BUNDLE_DEPLOY=PASS\n'
printf 'OPERATIONS_BUNDLE_RELEASE=%s\n' "$release"
