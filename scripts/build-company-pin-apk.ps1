[CmdletBinding()]
param(
    [string]$ConfigPath = (Join-Path $env:USERPROFILE ".fleetaisystems\firebase-mobile.ps1"),
    [string]$TargetPlatforms = "android-arm,android-arm64,android-x64"
)

$ErrorActionPreference = "Stop"
$buildScript = Join-Path $PSScriptRoot "build-firebase-staging-apk.ps1"

if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "Company mobile configuration is missing: $ConfigPath"
}

$apiBaseUrl = $null
foreach ($line in Get-Content -LiteralPath $ConfigPath) {
    if ($line -match '^\s*\$env:FLEET_API_BASE_URL\s*=\s*''([^'']+)''\s*$' -or
        $line -match '^\s*\$env:FLEET_API_BASE_URL\s*=\s*"([^"]+)"\s*$') {
        $apiBaseUrl = $Matches[1].Trim()
    }
}
if ([string]::IsNullOrWhiteSpace($apiBaseUrl)) {
    throw "FLEET_API_BASE_URL is missing from the external mobile configuration."
}
$parsed = $null
if (-not [Uri]::TryCreate($apiBaseUrl, [UriKind]::Absolute, [ref]$parsed) -or
    $parsed.Scheme -ne "https" -or
    [string]::IsNullOrWhiteSpace($parsed.Host)) {
    throw "FLEET_API_BASE_URL must be an absolute HTTPS URL."
}

$previousAuthMode = [Environment]::GetEnvironmentVariable("FLEET_AUTH_MODE", "Process")
$previousApiBaseUrl = [Environment]::GetEnvironmentVariable("FLEET_API_BASE_URL", "Process")
try {
    $env:FLEET_AUTH_MODE = "company_pin"
    $env:FLEET_API_BASE_URL = $apiBaseUrl
    & $buildScript -CompanyPin -TargetPlatforms $TargetPlatforms
    if ($LASTEXITCODE -ne 0) {
        throw "Company PIN APK build failed with exit code $LASTEXITCODE."
    }
}
finally {
    [Environment]::SetEnvironmentVariable("FLEET_AUTH_MODE", $previousAuthMode, "Process")
    [Environment]::SetEnvironmentVariable("FLEET_API_BASE_URL", $previousApiBaseUrl, "Process")
}
