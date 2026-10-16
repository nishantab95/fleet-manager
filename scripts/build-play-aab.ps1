[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9]+$')]
    [string]$BuildNumber,
    [string]$BuildName = '',
    [string]$ConfigPath = (Join-Path $env:USERPROFILE '.fleetaisystems\google-play-mobile.ps1'),
    [string]$GradlePropertiesPath = (Join-Path $env:USERPROFILE '.gradle\gradle.properties'),
    [switch]$ValidateOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$mobileRoot = Join-Path $repoRoot 'apps\mobile'
$validator = Join-Path $PSScriptRoot 'validate_play_aab.py'
$pilotSigner = 'fd25115e20ac18a8a7cda91b9f4d5f6153f54b4d79c751b5005a3ac734cc3c29'
$allowedConfig = @(
    'FLEET_API_BASE_URL',
    'FLEET_PLAY_UPLOAD_CERT_SHA256'
)

function Read-SafeKeyValueFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string[]]$Allowed,
        [string]$Prefix = '',
        [switch]$IgnoreUnknown
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Configuration is missing: $Path"
    }
    $values = @{}
    $lineNumber = 0
    foreach ($line in Get-Content -LiteralPath $Path) {
        $lineNumber++
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#') -or $trimmed.StartsWith('!')) { continue }
        $candidate = $trimmed
        if ($Prefix -and $candidate.StartsWith($Prefix)) {
            $candidate = $candidate.Substring($Prefix.Length)
        }
        if ($candidate -notmatch '^([A-Za-z0-9_]+)\s*=\s*(.*)$') {
            throw "Unsupported configuration syntax on line $lineNumber in $Path"
        }
        $name = $Matches[1]
        $value = $Matches[2].Trim().Trim('"').Trim("'")
        if ($Allowed -notcontains $name) {
            if ($Prefix -or $IgnoreUnknown) { continue }
            throw "Unsupported configuration value on line ${lineNumber}: $name"
        }
        $values[$name] = $value
    }
    return $values
}

$config = Read-SafeKeyValueFile -Path $ConfigPath -Allowed $allowedConfig -Prefix '$env:'
$missing = @($allowedConfig | Where-Object { -not $config.ContainsKey($_) -or [string]::IsNullOrWhiteSpace($config[$_]) })
if ($missing.Count -gt 0) { throw "Missing Google Play mobile values: $($missing -join ', ')" }
if ($config['FLEET_API_BASE_URL'] -ne 'https://api.fleetaisystems.com') {
    throw 'Google Play production builds must use https://api.fleetaisystems.com.'
}
$signingNames = @(
    'fleetPlayStoreFile',
    'fleetPlayStorePassword',
    'fleetPlayKeyAlias',
    'fleetPlayKeyPassword'
)
$signing = Read-SafeKeyValueFile -Path $GradlePropertiesPath -Allowed $signingNames -IgnoreUnknown
$missingSigning = @($signingNames | Where-Object { -not $signing.ContainsKey($_) -or [string]::IsNullOrWhiteSpace($signing[$_]) })
if ($missingSigning.Count -gt 0) { throw "Missing Google Play signing properties: $($missingSigning -join ', ')" }
$keystore = $signing['fleetPlayStoreFile']
if (-not [IO.Path]::IsPathRooted($keystore)) {
    $keystore = Join-Path $mobileRoot "android\app\$keystore"
}
if (-not (Test-Path -LiteralPath $keystore -PathType Leaf)) { throw "Google Play upload keystore is unavailable: $keystore" }

$expectedSigner = $config['FLEET_PLAY_UPLOAD_CERT_SHA256'].Replace(':', '').ToLowerInvariant()
if ($expectedSigner -notmatch '^[0-9a-f]{64}$') { throw 'FLEET_PLAY_UPLOAD_CERT_SHA256 is invalid.' }
if ($expectedSigner -eq $pilotSigner) { throw 'Google Play upload signing must not reuse the Pilot signer.' }

$keytool = Get-Command keytool.exe -ErrorAction SilentlyContinue
if (-not $keytool) { $keytool = Get-Command keytool -ErrorAction Stop }
$oldPassword = [Environment]::GetEnvironmentVariable('FLEET_PLAY_STORE_PASSWORD', 'Process')
try {
    $env:FLEET_PLAY_STORE_PASSWORD = $signing['fleetPlayStorePassword']
    $keyOutput = @(& $keytool.Source -list -v -keystore $keystore -alias $signing['fleetPlayKeyAlias'] -storepass:env FLEET_PLAY_STORE_PASSWORD 2>&1)
    if ($LASTEXITCODE -ne 0) { throw 'Java keytool could not inspect the configured Google Play upload signer.' }
} finally {
    [Environment]::SetEnvironmentVariable('FLEET_PLAY_STORE_PASSWORD', $oldPassword, 'Process')
}
$shaLine = $keyOutput | Where-Object { $_ -match 'SHA256:\s*([0-9A-Fa-f:]+)' } | Select-Object -First 1
if (-not $shaLine) { throw 'Java keytool did not report the Google Play signer SHA-256.' }
$null = $shaLine -match 'SHA256:\s*([0-9A-Fa-f:]+)'
$actualSigner = $Matches[1].Replace(':', '').ToLowerInvariant()
if ($actualSigner -ne $expectedSigner) { throw 'Configured Google Play keystore does not match FLEET_PLAY_UPLOAD_CERT_SHA256.' }

if (-not $BuildName) {
    $pubspecVersion = Get-Content -LiteralPath (Join-Path $mobileRoot 'pubspec.yaml') | Where-Object { $_ -match '^version:\s*([^+\s]+)' } | Select-Object -First 1
    if (-not $pubspecVersion) { throw 'Could not determine the mobile version name.' }
    $null = $pubspecVersion -match '^version:\s*([^+\s]+)'
    $BuildName = $Matches[1]
}
if ($BuildName -notmatch '^\d+\.\d+\.\d+$') { throw 'BuildName must use numeric semantic version form, for example 1.1.0.' }
if ([int64]$BuildNumber -le 0) { throw 'BuildNumber must be positive.' }

Write-Output 'PLAY_PACKAGE=com.fleetmanager.fleet_manager_mobile'
Write-Output "VERSION=$BuildName"
Write-Output "VERSION_CODE=$BuildNumber"
Write-Output "PLAY_UPLOAD_SIGNER_SHA256=$($config['FLEET_PLAY_UPLOAD_CERT_SHA256'].ToUpperInvariant())"
Write-Output 'PILOT_IDENTITY_CHANGED=NO'
if ($ValidateOnly) {
    Write-Output 'VALIDATION_ONLY=PASS'
    Write-Output 'Nothing was built or uploaded.'
    exit 0
}

$flutter = Get-Command flutter.bat -ErrorAction SilentlyContinue
if (-not $flutter) { $flutter = Get-Command flutter -ErrorAction Stop }
$arguments = @(
    'build', 'appbundle',
    '--flavor', 'production',
    '--release',
    '--build-name', $BuildName,
    '--build-number', $BuildNumber,
    "--dart-define=FLEET_AUTH_MODE=company_pin",
    "--dart-define=FLEET_API_BASE_URL=$($config['FLEET_API_BASE_URL'])"
)
Push-Location $mobileRoot
try {
    & $flutter.Source @arguments
    if ($LASTEXITCODE -ne 0) { throw "Flutter production AAB build failed with exit code $LASTEXITCODE." }
} finally {
    Pop-Location
}

$bundle = Join-Path $mobileRoot 'build\app\outputs\bundle\productionRelease\app-production-release.aab'
$python = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command python -ErrorAction Stop }
& $python.Source $validator $bundle --version-name $BuildName --version-code $BuildNumber --signer-sha256 $expectedSigner
if ($LASTEXITCODE -ne 0) { throw 'Google Play AAB validation failed.' }

$releaseDirectory = Join-Path $repoRoot 'dist'
New-Item -ItemType Directory -Force -Path $releaseDirectory | Out-Null
$releaseBundle = Join-Path $releaseDirectory "FleetAI-Systems-GooglePlay-$BuildName-code$BuildNumber.aab"
Copy-Item -LiteralPath $bundle -Destination $releaseBundle -Force
Write-Output "AAB_PATH=$releaseBundle"
Write-Output 'AAB_BUILD=PASS'
Write-Output 'AAB_UPLOADED=NO'
