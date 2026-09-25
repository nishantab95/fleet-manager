[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
$apiProject = Join-Path $repoRoot "services\api"

if (-not (Test-Path -LiteralPath (Join-Path $repoRoot ".env"))) {
    throw "A local .env is required. Configure the explicit pilot role OTPs before running this command."
}

$ensurePython = Join-Path $PSScriptRoot "ensure-trusted-python.ps1"
& $ensurePython
if ($LASTEXITCODE -ne 0) {
    throw "Trusted Python environment verification failed (exit $LASTEXITCODE)."
}

$projectPython = Join-Path $apiProject ".venv\Scripts\python.exe"
& $projectPython -m fleet_api.bootstrap.pilot
if ($LASTEXITCODE -ne 0) {
    throw "Pilot bootstrap failed (exit $LASTEXITCODE)."
}
