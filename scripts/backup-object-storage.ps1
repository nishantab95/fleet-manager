[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Alias,
    [Parameter(Mandatory = $true)]
    [string]$Bucket,
    [Parameter(Mandatory = $true)]
    [string]$DestinationDirectory
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command mc -ErrorAction SilentlyContinue)) {
    throw "mc is required. Configure the MinIO client alias outside this repository."
}

New-Item -ItemType Directory -Path $DestinationDirectory -Force | Out-Null
& mc mirror --overwrite "$Alias/$Bucket" $DestinationDirectory
if ($LASTEXITCODE -ne 0) {
    throw "Object-storage export failed with exit code $LASTEXITCODE."
}

Write-Output "Evidence export completed to $DestinationDirectory."
