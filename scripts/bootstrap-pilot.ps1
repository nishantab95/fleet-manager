[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
$cacheDir = Join-Path $repoRoot ".uv-cache"
$apiProject = Join-Path $repoRoot "services\api"

if (-not (Test-Path -LiteralPath (Join-Path $repoRoot ".env"))) {
    throw "A local .env is required. Configure the explicit pilot role OTPs before running this command."
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required to run the pilot bootstrap."
}

uv --cache-dir $cacheDir run --project $apiProject python -m fleet_api.bootstrap.pilot
