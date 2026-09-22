[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$DatabaseName,
    [string]$BackupDirectory = (Join-Path (Get-Location) "backups"),
    [string]$PgHost = $(if ($env:PGHOST) { $env:PGHOST } else { "127.0.0.1" }),
    [int]$Port = $(if ($env:PGPORT) { [int]$env:PGPORT } else { 5432 }),
    [string]$User = $(if ($env:PGUSER) { $env:PGUSER } else { "fleet" })
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command pg_dump -ErrorAction SilentlyContinue)) {
    throw "pg_dump is required. Install PostgreSQL client tools and rerun this script."
}

New-Item -ItemType Directory -Path $BackupDirectory -Force | Out-Null
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmssZ")
$backupFile = Join-Path $BackupDirectory "fleet-$DatabaseName-$timestamp.dump"

$arguments = @(
    "--format=custom",
    "--no-owner",
    "--file", $backupFile,
    "--host", $PgHost,
    "--port", $Port,
    "--username", $User,
    "--dbname", $DatabaseName
)

& pg_dump @arguments
if ($LASTEXITCODE -ne 0) {
    if (Test-Path -LiteralPath $backupFile) {
        Remove-Item -LiteralPath $backupFile -Force
    }
    throw "pg_dump failed with exit code $LASTEXITCODE."
}

if (-not (Test-Path -LiteralPath $backupFile)) {
    throw "pg_dump reported success but did not create the backup file."
}

Write-Output (Resolve-Path -LiteralPath $backupFile)
