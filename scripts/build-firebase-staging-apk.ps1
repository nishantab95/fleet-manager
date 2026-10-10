[CmdletBinding()]
param(
    [switch]$ToolingOnly
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$mobileRoot = Join-Path $repoRoot "apps\mobile"
$flutterRoot = Join-Path $env:USERPROFILE "develop\flutter"
$jdkRoot = Join-Path $env:USERPROFILE "Tools\temurin-17"
$sdkRoot = Join-Path $env:LOCALAPPDATA "Android\Sdk"
$gradleHome = Join-Path $env:USERPROFILE ".gradle"
$signingConfig = Join-Path $gradleHome "gradle.properties"
$keystore = Join-Path $env:USERPROFILE ".fleet-manager\signing\fleet-pilot-release.jks"
$expectedPackage = "com.fleetmanager.fleet_manager_mobile.pilot"

function Get-RequiredProcessValue {
    param([Parameter(Mandatory = $true)][string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($value) -or $value -match "[<>]") {
        throw "Required process environment value is missing or still a placeholder: $Name"
    }
    return $value.Trim()
}

foreach ($requiredPath in @(
        (Join-Path $flutterRoot "bin\flutter.bat"),
        (Join-Path $jdkRoot "bin\java.exe"),
        (Join-Path $sdkRoot "platform-tools\adb.exe"),
        (Join-Path $sdkRoot "build-tools\36.0.0\aapt.exe"),
        (Join-Path $sdkRoot "build-tools\36.0.0\apksigner.bat"),
        (Join-Path $PSScriptRoot "pilot_release_common.py"),
        (Join-Path $PSScriptRoot "firebase_staging_apk.py")
    )) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required staging build component is missing: $requiredPath"
    }
}

$signingBlockers = [System.Collections.Generic.List[string]]::new()
if (-not (Test-Path -LiteralPath $signingConfig -PathType Leaf)) {
    $signingBlockers.Add("missing user Gradle signing configuration")
}
if (-not (Test-Path -LiteralPath $keystore -PathType Leaf)) {
    $signingBlockers.Add("missing protected Pilot keystore")
}
foreach ($propertyName in @(
        "fleetPilotStoreFile",
        "fleetPilotStorePassword",
        "fleetPilotKeyAlias",
        "fleetPilotKeyPassword"
    )) {
    if ((Test-Path -LiteralPath $signingConfig -PathType Leaf) -and
        -not (Select-String -LiteralPath $signingConfig -Pattern "^$propertyName=" -Quiet)) {
        $signingBlockers.Add("missing local signing property $propertyName")
    }
}

$pubspec = Get-Content -LiteralPath (Join-Path $mobileRoot "pubspec.yaml") -Raw
$versionMatch = [regex]::Match(
    $pubspec,
    "(?m)^version:\s*([0-9]+\.[0-9]+\.[0-9]+)\+([0-9]+)\s*$"
)
if (-not $versionMatch.Success) {
    throw "Unable to read the Flutter version from pubspec.yaml."
}
$versionName = $versionMatch.Groups[1].Value
$versionCode = [int]$versionMatch.Groups[2].Value

$env:JAVA_HOME = $jdkRoot
$env:ANDROID_HOME = $sdkRoot
$env:ANDROID_SDK_ROOT = $sdkRoot
$env:GRADLE_USER_HOME = $gradleHome
$env:FLUTTER_ROOT = $flutterRoot
$env:FLUTTER_SUPPRESS_ANALYTICS = "true"
$env:GIT_CONFIG_COUNT = "1"
$env:GIT_CONFIG_KEY_0 = "safe.directory"
$env:GIT_CONFIG_VALUE_0 = $flutterRoot.Replace("\", "/")
$env:Path = "$(Join-Path $flutterRoot 'bin');$(Join-Path $jdkRoot 'bin');$(Join-Path $sdkRoot 'platform-tools');$env:Path"
$env:PYTHONPATH = "$PSScriptRoot;$env:PYTHONPATH"

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Python is required by the APK inspection workflow."
}

if ($ToolingOnly) {
    Write-Output "STAGING_APK_TOOLING=READY"
    Write-Output "EXPECTED_PACKAGE=$expectedPackage"
    Write-Output "VERSION=$versionName-pilot"
    Write-Output "VERSION_CODE=$versionCode"
    Write-Output $(if ($signingBlockers.Count -eq 0) { "SIGNING=READY" } else { "SIGNING=NOT_CONFIGURED" })
    foreach ($blocker in $signingBlockers) {
        Write-Output "SIGNING_BLOCKER=$blocker"
    }
    Write-Output "FIREBASE_VALUES=NOT_SUPPLIED_OR_READ"
    return
}

if ($signingBlockers.Count -gt 0) {
    throw "Staging signing is not ready: $($signingBlockers -join '; ')"
}

$branch = (& git -C $repoRoot branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne "main") {
    throw "Firebase staging APKs must be built from main."
}
$status = @(& git -C $repoRoot status --porcelain --untracked-files=normal)
if ($LASTEXITCODE -ne 0 -or -not [string]::IsNullOrWhiteSpace(($status -join "`n"))) {
    throw "Firebase staging APKs require a clean source tree."
}
$commit = (& git -C $repoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $commit -notmatch "^[0-9a-f]{40}$") {
    throw "Unable to identify the source Git commit."
}

$authMode = Get-RequiredProcessValue "FLEET_AUTH_MODE"
if ($authMode.ToLowerInvariant() -ne "firebase") {
    throw "FLEET_AUTH_MODE must be firebase for this build."
}
$apiBaseUrl = Get-RequiredProcessValue "FLEET_API_BASE_URL"
$firebaseApiKey = Get-RequiredProcessValue "FIREBASE_ANDROID_API_KEY"
$firebaseAppId = Get-RequiredProcessValue "FIREBASE_ANDROID_APP_ID"
$firebaseSenderId = Get-RequiredProcessValue "FIREBASE_MESSAGING_SENDER_ID"
$firebaseProjectId = Get-RequiredProcessValue "FIREBASE_PROJECT_ID"
$backendProjectId = Get-RequiredProcessValue "FLEET_FIREBASE_PROJECT_ID"

if ($firebaseProjectId -ne $backendProjectId) {
    throw "FIREBASE_PROJECT_ID and FLEET_FIREBASE_PROJECT_ID must identify the same staging project."
}
$parsedApiUrl = $null
if (-not [Uri]::TryCreate($apiBaseUrl, [UriKind]::Absolute, [ref]$parsedApiUrl) -or
    $parsedApiUrl.Scheme -ne "https" -or
    [string]::IsNullOrWhiteSpace($parsedApiUrl.Host) -or
    -not [string]::IsNullOrWhiteSpace($parsedApiUrl.Query) -or
    -not [string]::IsNullOrWhiteSpace($parsedApiUrl.Fragment)) {
    throw "FLEET_API_BASE_URL must be an absolute staging HTTPS URL without query or fragment."
}
if ($firebaseSenderId -notmatch "^[0-9]+$") {
    throw "FIREBASE_MESSAGING_SENDER_ID must contain digits only."
}
if ($firebaseProjectId -notmatch "^[a-z0-9][a-z0-9-]{4,28}[a-z0-9]$") {
    throw "FIREBASE_PROJECT_ID does not have a valid Firebase project-id shape."
}

$credentialValue = [Environment]::GetEnvironmentVariable(
    "GOOGLE_APPLICATION_CREDENTIALS",
    "Process"
)
if (-not [string]::IsNullOrWhiteSpace($credentialValue)) {
    $credentialPath = [IO.Path]::GetFullPath($credentialValue)
    if (-not (Test-Path -LiteralPath $credentialPath -PathType Leaf)) {
        throw "GOOGLE_APPLICATION_CREDENTIALS does not point to an existing external file."
    }
    $repoPrefix = $repoRoot.TrimEnd("\") + "\"
    if ($credentialPath.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "GOOGLE_APPLICATION_CREDENTIALS must remain outside the repository."
    }
}

$flutter = Join-Path $flutterRoot "bin\flutter.bat"
$buildArguments = @(
    "build",
    "apk",
    "--flavor",
    "pilot",
    "--release",
    "--build-name=$versionName",
    "--build-number=$versionCode",
    "--dart-define=FLEET_PILOT=true",
    "--dart-define=FLEET_AUTH_MODE=firebase",
    "--dart-define=FLEET_BUILD_PROFILE=firebase-staging",
    "--dart-define=FLEET_API_BASE_URL=$apiBaseUrl",
    "--dart-define=FIREBASE_ANDROID_API_KEY=$firebaseApiKey",
    "--dart-define=FIREBASE_ANDROID_APP_ID=$firebaseAppId",
    "--dart-define=FIREBASE_MESSAGING_SENDER_ID=$firebaseSenderId",
    "--dart-define=FIREBASE_PROJECT_ID=$firebaseProjectId"
)

$previousPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
Push-Location $mobileRoot
try {
    & $flutter pub get
    if ($LASTEXITCODE -ne 0) {
        throw "Flutter dependency setup failed with exit code $LASTEXITCODE."
    }
    & $flutter @buildArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Flutter Firebase staging APK build failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
    $ErrorActionPreference = $previousPreference
}

$builtApk = Join-Path $mobileRoot "build\app\outputs\flutter-apk\app-pilot-release.apk"
if (-not (Test-Path -LiteralPath $builtApk -PathType Leaf)) {
    throw "Flutter completed without producing the expected staging APK."
}

$verificationScript = Join-Path $PSScriptRoot "firebase_staging_apk.py"
$verificationOutput = @(
    & $python.Source $verificationScript $builtApk `
        --version-name $versionName `
        --version-code $versionCode `
        --api-base-url $apiBaseUrl `
        --api-key $firebaseApiKey `
        --app-id $firebaseAppId `
        --sender-id $firebaseSenderId `
        --project-id $firebaseProjectId 2>&1
)
if ($LASTEXITCODE -ne 0) {
    throw "APK staging verification failed: $($verificationOutput -join ' ')"
}
$identity = ($verificationOutput -join "`n") | ConvertFrom-Json

$releaseDirectory = Join-Path $mobileRoot "build\release"
New-Item -ItemType Directory -Force -Path $releaseDirectory | Out-Null
$namedApk = Join-Path $releaseDirectory "FleetAI-Systems-Firebase-Staging-$versionName-pilot-$versionCode.apk"
if (Test-Path -LiteralPath $namedApk) {
    throw "Refusing to overwrite an existing versioned staging APK."
}
Copy-Item -LiteralPath $builtApk -Destination $namedApk

$provenance = [ordered]@{
    schemaVersion = 1
    package = $identity.package
    versionName = $identity.versionName
    versionCode = [int]$identity.versionCode
    signerSha256 = $identity.signerSha256
    apkSha256 = $identity.apkSha256
    authMode = $identity.authMode
    buildProfile = $identity.buildProfile
    sourceGitCommit = $commit
    sourceTreeClean = $true
    apiBaseUrl = $apiBaseUrl
    firebaseProjectId = $firebaseProjectId
    builtAtUtc = [DateTime]::UtcNow.ToString("o")
}
$provenanceJson = ($provenance | ConvertTo-Json -Depth 4) + "`n"
[System.IO.File]::WriteAllText(
    "$namedApk.build.json",
    $provenanceJson,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Output "PACKAGE=$($identity.package)"
Write-Output "VERSION=$($identity.versionName)"
Write-Output "VERSION_CODE=$($identity.versionCode)"
Write-Output "AUTH_MODE=$($identity.authMode)"
Write-Output "BUILD_PROFILE=$($identity.buildProfile)"
Write-Output "SIGNING_CERTIFICATE_SHA256=$($identity.signerSha256)"
Write-Output "APK_SHA256=$($identity.apkSha256)"
Write-Output "APK_PATH=$namedApk"
Write-Output "SOURCE_GIT_COMMIT=$commit"
