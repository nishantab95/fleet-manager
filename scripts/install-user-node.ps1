[CmdletBinding()]
param(
    [string]$Version = "24.19.0"
)

$ErrorActionPreference = "Stop"
$toolsRoot = Join-Path $env:USERPROFILE "Tools"
$archiveRoot = Join-Path $toolsRoot "node-v$Version-win-x64"
$archivePath = Join-Path $toolsRoot "node-v$Version-win-x64.zip"
$downloadUrl = "https://nodejs.org/dist/v$Version/node-v$Version-win-x64.zip"

New-Item -ItemType Directory -Force -Path $toolsRoot | Out-Null

if (-not (Test-Path -LiteralPath (Join-Path $archiveRoot "node.exe"))) {
    Invoke-WebRequest -Uri $downloadUrl -OutFile $archivePath
    Expand-Archive -LiteralPath $archivePath -DestinationPath $toolsRoot -Force
}

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$pathEntries = @($userPath -split ";" | Where-Object { $_ })
if ($pathEntries -notcontains $archiveRoot) {
    [Environment]::SetEnvironmentVariable("Path", (($pathEntries + $archiveRoot) -join ";"), "User")
}

& (Join-Path $archiveRoot "node.exe") --version
& (Join-Path $archiveRoot "npm.cmd") --version

