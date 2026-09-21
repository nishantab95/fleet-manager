[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
$cacheDir = Join-Path $repoRoot ".uv-cache"
$apiProject = Join-Path $repoRoot "services\api"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/ and rerun this script."
}

if (-not (Test-Path -LiteralPath (Join-Path $repoRoot ".env"))) {
    Copy-Item -LiteralPath (Join-Path $repoRoot ".env.example") -Destination (Join-Path $repoRoot ".env")
    Write-Host "Created .env from .env.example. Review local values before production use."
}

Write-Host "Synchronizing pinned backend dependencies..."
uv --cache-dir $cacheDir sync --project $apiProject --all-groups
Write-Host "Bootstrap complete."

