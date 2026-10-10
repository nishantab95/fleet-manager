[CmdletBinding()]
param(
    [string]$ConfigPath = (Join-Path $env:USERPROFILE ".fleetaisystems\firebase-mobile.ps1"),
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot "services\api\.venv\Scripts\python.exe"
$buildScript = Join-Path $PSScriptRoot "build-firebase-staging-apk.ps1"
$fingerprintScript = Join-Path $PSScriptRoot "android_signer_fingerprints.py"
$senderScript = Join-Path $PSScriptRoot "send_pilot_release.py"
$logDirectory = Join-Path $repoRoot ".runtime\mobile-release"
$logFile = Join-Path $logDirectory ("firebase-company-{0}.log" -f [DateTime]::UtcNow.ToString("yyyyMMdd-HHmmss"))
$allowed = @(
    "FLEET_AUTH_MODE",
    "FLEET_API_BASE_URL",
    "FIREBASE_ANDROID_API_KEY",
    "FIREBASE_ANDROID_APP_ID",
    "FIREBASE_MESSAGING_SENDER_ID",
    "FIREBASE_PROJECT_ID"
)
$sendStarted = $false

function Write-ReleaseStatus {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Output $Message
    if (Test-Path -LiteralPath $logDirectory) {
        Add-Content -LiteralPath $logFile -Value $Message -Encoding UTF8
    }
}

function Read-SafeMobileConfig {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Mobile Firebase configuration is missing: $Path"
    }
    $values = @{}
    $lineNumber = 0
    foreach ($line in Get-Content -LiteralPath $Path) {
        $lineNumber++
        if ([string]::IsNullOrWhiteSpace($line) -or $line.TrimStart().StartsWith("#")) {
            continue
        }
        $name = $null
        $value = $null
        if ($line -match '^\s*\$env:([A-Z0-9_]+)\s*=\s*''([^'']*)''\s*$') {
            $name = $Matches[1]
            $value = $Matches[2]
        }
        elseif ($line -match '^\s*\$env:([A-Z0-9_]+)\s*=\s*"([^"]*)"\s*$') {
            $name = $Matches[1]
            $value = $Matches[2]
        }
        else {
            throw "Unsupported configuration syntax on line $lineNumber."
        }
        if ($allowed -notcontains $name) {
            throw "Unsupported mobile configuration value on line ${lineNumber}: $name"
        }
        if ($values.ContainsKey($name)) {
            throw "Duplicate mobile configuration value: $name"
        }
        $values[$name] = $value.Trim()
    }
    return $values
}

try {
    $values = Read-SafeMobileConfig -Path $ConfigPath
    $missing = @(
        $allowed | Where-Object {
            -not $values.ContainsKey($_) -or
            [string]::IsNullOrWhiteSpace($values[$_]) -or
            $values[$_] -match '[<>]' -or
            $values[$_] -match '^(CHANGE_ME|REPLACE_ME)$'
        }
    )
    if ($missing.Count -gt 0) {
        throw "Missing or placeholder mobile values: $($missing -join ', ')"
    }
    if ($values["FLEET_AUTH_MODE"].ToLowerInvariant() -ne "firebase") {
        throw "FLEET_AUTH_MODE must be firebase."
    }
    $apiUri = $null
    if (-not [Uri]::TryCreate($values["FLEET_API_BASE_URL"], [UriKind]::Absolute, [ref]$apiUri) -or
        $apiUri.Scheme -ne "https" -or
        [string]::IsNullOrWhiteSpace($apiUri.Host) -or
        -not [string]::IsNullOrWhiteSpace($apiUri.Query) -or
        -not [string]::IsNullOrWhiteSpace($apiUri.Fragment)) {
        throw "FLEET_API_BASE_URL must be an absolute HTTPS URL without query or fragment."
    }
    if ($values["FIREBASE_MESSAGING_SENDER_ID"] -notmatch '^[0-9]+$') {
        throw "FIREBASE_MESSAGING_SENDER_ID must contain digits only."
    }
    if ($values["FIREBASE_PROJECT_ID"] -notmatch '^[a-z0-9][a-z0-9-]{4,28}[a-z0-9]$') {
        throw "FIREBASE_PROJECT_ID does not have a valid Firebase project-id shape."
    }
    foreach ($name in $allowed) {
        [Environment]::SetEnvironmentVariable($name, $values[$name], "Process")
    }

    New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
    Write-ReleaseStatus "Fleet AI Systems company mobile release"
    Write-ReleaseStatus "CONFIG=READY"

    $fingerprintOutput = @(& $python $fingerprintScript --json 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "Signer validation failed: $($fingerprintOutput -join ' ')"
    }
    $fingerprints = ($fingerprintOutput -join "`n") | ConvertFrom-Json
    Write-ReleaseStatus "SIGNER=VERIFIED"
    Write-ReleaseStatus "SIGNER_SHA1=$($fingerprints.sha1)"
    Write-ReleaseStatus "SIGNER_SHA256=$($fingerprints.sha256)"

    if ($ValidateOnly) {
        $toolingOutput = @(& $buildScript -Company -ToolingOnly 2>&1)
        if ($LASTEXITCODE -ne 0) {
            throw "Build tooling validation failed: $($toolingOutput -join ' ')"
        }
        $version = ($toolingOutput | Where-Object { $_ -like "VERSION=*" } | Select-Object -Last 1)
        $versionCode = ($toolingOutput | Where-Object { $_ -like "VERSION_CODE=*" } | Select-Object -Last 1)
        Write-ReleaseStatus $version
        Write-ReleaseStatus $versionCode
        Write-ReleaseStatus "VALIDATION_ONLY=PASS"
        Write-ReleaseStatus "Nothing was built, sent, or published."
        exit 0
    }

    Write-ReleaseStatus "BUILD=STARTED"
    $buildOutput = @(& $buildScript -Company 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "Company APK build failed: $($buildOutput -join ' ')"
    }
    $apkLine = $buildOutput | Where-Object { $_ -like "APK_PATH=*" } | Select-Object -Last 1
    $versionLine = $buildOutput | Where-Object { $_ -like "VERSION=*" } | Select-Object -Last 1
    $versionCodeLine = $buildOutput | Where-Object { $_ -like "VERSION_CODE=*" } | Select-Object -Last 1
    if (-not $apkLine) {
        throw "Company APK build did not report an output path."
    }
    $apkPath = $apkLine.Substring("APK_PATH=".Length)
    Write-ReleaseStatus "BUILD=OK"
    Write-ReleaseStatus $versionLine
    Write-ReleaseStatus $versionCodeLine
    Write-ReleaseStatus "PACKAGE=com.fleetmanager.fleet_manager_mobile.pilot"
    Write-ReleaseStatus "SIGNATURE=VERIFIED"

    Write-ReleaseStatus "SEND=STARTED"
    $sendStarted = $true
    $sendOutput = @(
        & $python $senderScript $apkPath --require-firebase-company 2>&1
    )
    if ($LASTEXITCODE -ne 0) {
        throw "Private send or publication failed: $($sendOutput -join ' ')"
    }
    Write-ReleaseStatus "SEND=OK"
    Write-ReleaseStatus "SERVER_VALIDATION=OK"
    Write-ReleaseStatus "PUBLICATION=OK"
    Write-ReleaseStatus "Company APK was published through the private update channel."
    exit 0
}
catch {
    $publicationMessage = if ($sendStarted) {
        "Publication was not confirmed. Check the server before retrying."
    }
    else {
        "Nothing new was published."
    }
    Write-Output "CONFIG_OR_RELEASE=FAILED"
    Write-Output $_.Exception.Message
    Write-Output $publicationMessage
    if (Test-Path -LiteralPath $logDirectory) {
        Add-Content -LiteralPath $logFile -Value "CONFIG_OR_RELEASE=FAILED" -Encoding UTF8
        Add-Content -LiteralPath $logFile -Value $_.Exception.Message -Encoding UTF8
        Add-Content -LiteralPath $logFile -Value $publicationMessage -Encoding UTF8
    }
    exit 1
}
