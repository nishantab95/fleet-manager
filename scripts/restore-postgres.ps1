[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile,
    [Parameter(Mandatory = $true)]
    [string]$TargetDatabase,
    [string]$PgHost = $(if ($env:PGHOST) { $env:PGHOST } else { "127.0.0.1" }),
    [int]$Port = $(if ($env:PGPORT) { [int]$env:PGPORT } else { 5432 }),
    [string]$User = $(if ($env:PGUSER) { $env:PGUSER } else { "fleet" })
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command pg_restore -ErrorAction SilentlyContinue)) {
    throw "pg_restore is required. Install PostgreSQL client tools and rerun this script."
}
if (-not (Test-Path -LiteralPath $BackupFile -PathType Leaf)) {
    throw "Backup file does not exist: $BackupFile"
}
if ($TargetDatabase -notmatch "(?i)(test|restore|sandbox|pilot)") {
    throw "Refusing to restore over a database that is not clearly non-production: $TargetDatabase"
}

$arguments = @(
    "--clean",
    "--if-exists",
    "--exit-on-error",
    "--no-owner",
    "--host", $PgHost,
    "--port", $Port,
    "--username", $User,
    "--dbname", $TargetDatabase,
    $BackupFile
)

& pg_restore @arguments
if ($LASTEXITCODE -ne 0) {
    throw "pg_restore failed with exit code $LASTEXITCODE."
}

Write-Output "Restore completed into $TargetDatabase."
