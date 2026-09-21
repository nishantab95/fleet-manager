[CmdletBinding()]
param(
    [switch]$SkipInfrastructure
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
$cacheDir = Join-Path $repoRoot ".uv-cache"
$apiProject = Join-Path $repoRoot "services\api"

if (-not $SkipInfrastructure) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker is required to start local PostgreSQL and MinIO."
    }
    docker compose up -d postgres minio
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required to run the API."
}

uv --cache-dir $cacheDir run --project $apiProject uvicorn fleet_api.main:app --reload --host 0.0.0.0 --port 8000

