[CmdletBinding()]
param(
    [switch]$SkipInfrastructure
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
$apiProject = Join-Path $repoRoot "services\api"

if (-not $SkipInfrastructure) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker is required to start local PostgreSQL and MinIO."
    }
    docker compose up -d postgres minio
}

$ensurePython = Join-Path $PSScriptRoot "ensure-trusted-python.ps1"
& $ensurePython
if ($LASTEXITCODE -ne 0) {
    throw "Trusted Python environment preparation failed (exit $LASTEXITCODE)."
}

$projectPython = Join-Path $apiProject ".venv\Scripts\python.exe"
& $projectPython -m uvicorn fleet_api.main:app --reload --host 0.0.0.0 --port 8000
if ($LASTEXITCODE -ne 0) {
    throw "API development server failed (exit $LASTEXITCODE)."
}
