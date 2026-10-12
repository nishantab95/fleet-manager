[CmdletBinding()]
param(
    [string]$ConfigPath = (Join-Path $env:USERPROFILE ".fleetaisystems\firebase-mobile.ps1")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$buildScript = Join-Path $PSScriptRoot "build-company-pin-apk.ps1"
$senderScript = Join-Path $PSScriptRoot "send_pilot_release.py"
$python = Join-Path $repoRoot "services\api\.venv\Scripts\python.exe"
$logDirectory = Join-Path $repoRoot ".runtime\mobile-release"
$logFile = Join-Path $logDirectory (
    "company-pin-{0}.log" -f [DateTime]::UtcNow.ToString("yyyyMMdd-HHmmss")
)

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Fleet Manager backend Python is missing: $python"
}

function Write-ReleaseStatus {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Output $Message
    Add-Content -LiteralPath $logFile -Value $Message -Encoding UTF8
}

New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
try {
    Write-ReleaseStatus "Fleet AI Systems company PIN mobile release"
    Write-ReleaseStatus "BUILD=STARTED"
    $rawBuildOutput = @(& $buildScript -ConfigPath $ConfigPath 2>&1)
    $buildExitCode = $LASTEXITCODE
    $buildOutput = @($rawBuildOutput | ForEach-Object { [string]$_ })
    if ($buildExitCode -ne 0) {
        throw "Company PIN APK build failed: $($buildOutput -join ' ')"
    }
    $apkLine = $buildOutput | Where-Object { $_ -like "APK_PATH=*" } | Select-Object -Last 1
    if (-not $apkLine) {
        throw "Company PIN APK build did not report an output path."
    }
    $apkPath = $apkLine.Substring("APK_PATH=".Length)
    foreach ($name in @("VERSION=", "VERSION_CODE=", "SOURCE_GIT_COMMIT=")) {
        $line = $buildOutput | Where-Object { $_ -like "$name*" } | Select-Object -Last 1
        if ($line) {
            Write-ReleaseStatus $line
        }
    }
    Write-ReleaseStatus "BUILD=OK"
    Write-ReleaseStatus "PACKAGE=com.fleetmanager.fleet_manager_mobile.pilot"
    Write-ReleaseStatus "AUTH_MODE=company_pin"
    Write-ReleaseStatus "SIGNATURE=VERIFIED"
    Write-ReleaseStatus "SEND=STARTED"
    $rawSendOutput = @(& $python $senderScript $apkPath --require-company-pin 2>&1)
    $sendExitCode = $LASTEXITCODE
    $sendOutput = @($rawSendOutput | ForEach-Object { [string]$_ })
    if ($sendExitCode -ne 0) {
        throw "Private HTTPS/Taildrop publication failed: $($sendOutput -join ' ')"
    }
    foreach ($line in $sendOutput) {
        Write-ReleaseStatus $line
    }
    Write-ReleaseStatus "PUBLISHED SUCCESSFULLY"
    exit 0
}
catch {
    Write-ReleaseStatus "MOBILE_RELEASE=FAILED"
    Write-ReleaseStatus $_.Exception.Message
    exit 1
}
