[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot ".env"))) {
    Copy-Item -LiteralPath (Join-Path $repoRoot ".env.example") -Destination (Join-Path $repoRoot ".env")
    Write-Host "Created .env from .env.example. Review local values before production use."
}

Write-Host "Preparing the locked backend environment with trusted Python 3.12..."
$ensurePython = Join-Path $PSScriptRoot "ensure-trusted-python.ps1"
& $ensurePython
if ($LASTEXITCODE -ne 0) {
    throw "Trusted Python environment preparation failed (exit $LASTEXITCODE)."
}
Write-Host "Bootstrap complete."
