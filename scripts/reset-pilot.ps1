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
$apiProject = Join-Path $repoRoot "services\api"
$ensurePython = Join-Path $PSScriptRoot "ensure-trusted-python.ps1"
& $ensurePython
if ($LASTEXITCODE -ne 0) {
    throw "Trusted Python environment verification failed (exit $LASTEXITCODE)."
}

$projectPython = Join-Path $apiProject ".venv\Scripts\python.exe"
& $projectPython -m fleet_api.bootstrap.reset_pilot --confirm-pilot-reset --yes
if ($LASTEXITCODE -ne 0) {
    throw "Pilot test data reset failed (exit $LASTEXITCODE)."
}
