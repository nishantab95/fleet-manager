[CmdletBinding()]
param(
    [switch]$ConfirmPilotReset
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

if (-not $ConfirmPilotReset) {
    throw "Refusing reset. Re-run with -ConfirmPilotReset; this affects only the named Pilot Construction fixture."
}
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot ".env"))) {
    throw "A local .env is required."
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required to reset the pilot fixture."
}

$cacheDir = Join-Path $repoRoot ".uv-cache"
$apiProject = Join-Path $repoRoot "services\api"
uv --cache-dir $cacheDir run --project $apiProject python -m fleet_api.bootstrap.reset_pilot --confirm-pilot-reset --yes
