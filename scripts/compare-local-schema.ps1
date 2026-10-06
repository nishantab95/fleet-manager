param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("test")]
    [string]$FreshDatabase,

    [Parameter(Mandatory = $true)]
    [ValidatePattern("test")]
    [string]$UpgradedDatabase,

    [string]$Container = "fleet-manager-postgres-1",
    [string]$DatabaseUser = "fleet"
)

$ErrorActionPreference = "Stop"

function Get-NormalizedSchemaDump {
    param([Parameter(Mandatory = $true)][string]$Database)

    $dump = & docker exec $Container pg_dump `
        -U $DatabaseUser `
        --schema-only `
        --no-owner `
        --no-privileges `
        $Database
    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump failed for $Database"
    }

    return @(
        $dump | Where-Object {
            $_ -notmatch "^(--|\\restrict|\\unrestrict)"
        }
    )
}

$fresh = Get-NormalizedSchemaDump -Database $FreshDatabase
$upgraded = Get-NormalizedSchemaDump -Database $UpgradedDatabase
$difference = @(
    Compare-Object `
        -ReferenceObject $fresh `
        -DifferenceObject $upgraded `
        -SyncWindow 0
)

Write-Output "FRESH_LINES=$($fresh.Count)"
Write-Output "UPGRADED_LINES=$($upgraded.Count)"
Write-Output "SCHEMA_DIFF_LINES=$($difference.Count)"

if ($difference.Count -gt 0) {
    $difference | Select-Object -First 40 | Format-Table -AutoSize
    exit 1
}
