[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$mobileRoot = Join-Path $repoRoot "apps\mobile"
$flutterRoot = Join-Path $env:USERPROFILE "develop\flutter"
$jdkRoot = Join-Path $env:USERPROFILE "Tools\temurin-17"
$sdkRoot = Join-Path $env:LOCALAPPDATA "Android\Sdk"
$gradleHome = Join-Path $env:USERPROFILE ".gradle"
$signingConfig = Join-Path $gradleHome "gradle.properties"
$keystore = Join-Path $env:USERPROFILE ".fleet-manager\signing\fleet-pilot-release.jks"
$apiBaseUrl = "https://staunch-pc-03.tailf0597c.ts.net"
$expectedPackage = "com.fleetmanager.fleet_manager_mobile.pilot"

foreach ($requiredPath in @(
        (Join-Path $flutterRoot "bin\flutter.bat"),
        (Join-Path $flutterRoot "bin\dart.bat"),
        (Join-Path $jdkRoot "bin\java.exe"),
        (Join-Path $sdkRoot "platform-tools\adb.exe"),
        (Join-Path $sdkRoot "build-tools\36.0.0\aapt.exe"),
        (Join-Path $sdkRoot "build-tools\36.0.0\apksigner.bat"),
        (Join-Path $sdkRoot "ndk\28.2.13676358\source.properties"),
        $signingConfig,
        $keystore
    )) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required Pilot build component is missing: $requiredPath"
    }
}

foreach ($propertyName in @(
        "fleetPilotStoreFile",
        "fleetPilotStorePassword",
        "fleetPilotKeyAlias",
        "fleetPilotKeyPassword"
    )) {
    if (-not (Select-String -LiteralPath $signingConfig -Pattern "^$propertyName=" -Quiet)) {
        throw "Required local signing property is missing: $propertyName"
    }
}

$versionLine = Select-String -LiteralPath (Join-Path $mobileRoot "pubspec.yaml") -Pattern "^version:\s*1\.0\.21\+22\s*$"
if (-not $versionLine) {
    throw "Pilot build requires pubspec version 1.0.21+22."
}

$env:JAVA_HOME = $jdkRoot
$env:ANDROID_HOME = $sdkRoot
$env:ANDROID_SDK_ROOT = $sdkRoot
$env:GRADLE_USER_HOME = $gradleHome
$env:FLUTTER_ROOT = $flutterRoot
$env:FLUTTER_SUPPRESS_ANALYTICS = "true"
$env:GIT_CONFIG_COUNT = "1"
$env:GIT_CONFIG_KEY_0 = "safe.directory"
$env:GIT_CONFIG_VALUE_0 = $flutterRoot.Replace("\", "/")
$env:Path = "$(Join-Path $flutterRoot 'bin');$(Join-Path $jdkRoot 'bin');$(Join-Path $sdkRoot 'platform-tools');$(Join-Path $sdkRoot 'build-tools\36.0.0');$env:Path"
$env:PYTHONPATH = "$(Join-Path $repoRoot 'scripts');$env:PYTHONPATH"

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Python is required by the existing APK inspection and release workflow."
}

$commit = (& git -C $repoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $commit -notmatch "^[0-9a-f]{40}$") {
    throw "Unable to identify the source Git commit."
}
$status = @(& git -C $repoRoot status --porcelain --untracked-files=normal)
if ($LASTEXITCODE -ne 0) {
    throw "Unable to inspect source Git status."
}
$sourceTreeClean = [string]::IsNullOrWhiteSpace(($status -join "`n"))

$flutter = Join-Path $flutterRoot "bin\flutter.bat"
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
Push-Location $mobileRoot
try {
    & $flutter pub get
    $pubExit = $LASTEXITCODE
    if ($pubExit -ne 0) {
        throw "Flutter dependency setup failed with exit code $pubExit."
    }

    & $flutter build apk --flavor pilot --release `
        --build-name=1.0.21 `
        --build-number=22 `
        --dart-define=FLEET_PILOT=true `
        --dart-define=FLEET_API_BASE_URL=$apiBaseUrl
    $buildExit = $LASTEXITCODE
    if ($buildExit -ne 0) {
        throw "Flutter Pilot APK build failed with exit code $buildExit."
    }
}
finally {
    Pop-Location
    $ErrorActionPreference = $previousPreference
}

$builtApk = Join-Path $mobileRoot "build\app\outputs\flutter-apk\app-pilot-release.apk"
if (-not (Test-Path -LiteralPath $builtApk)) {
    throw "Flutter completed without producing the expected Pilot APK: $builtApk"
}

$inspectionCode = "import json,sys; from pathlib import Path; import pilot_release_common as c; i=c.inspect_apk(Path(sys.argv[1])); c.validate_expected_identity(i); print(json.dumps({'package':i.package,'versionName':i.version_name,'versionCode':i.version_code,'signerSha256':i.signer_sha256,'apkSha256':i.apk_sha256}))"
$inspectionOutput = @(& $python.Source -c $inspectionCode $builtApk 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "APK metadata or signature verification failed: $($inspectionOutput -join ' ')"
}
$identity = ($inspectionOutput -join "`n") | ConvertFrom-Json
if ($identity.package -ne $expectedPackage -or
    $identity.versionName -ne "1.0.21-pilot" -or
    [int]$identity.versionCode -ne 22) {
    throw "APK package or version does not match the requested Pilot build."
}

$releaseDirectory = Join-Path $mobileRoot "build\release"
New-Item -ItemType Directory -Force -Path $releaseDirectory | Out-Null
$namedApk = Join-Path $releaseDirectory "FleetManager-Pilot-1.0.21-pilot-22.apk"
if (Test-Path -LiteralPath $namedApk) {
    throw "Refusing to overwrite an existing versioned Pilot APK: $namedApk"
}
Copy-Item -LiteralPath $builtApk -Destination $namedApk

$provenance = [ordered]@{
    schemaVersion = 1
    package = $identity.package
    versionName = $identity.versionName
    versionCode = [int]$identity.versionCode
    signerSha256 = $identity.signerSha256
    apkSha256 = $identity.apkSha256
    sourceGitCommit = $commit
    sourceTreeClean = $sourceTreeClean
    apiBaseUrl = $apiBaseUrl
    builtAtUtc = [DateTime]::UtcNow.ToString("o")
}
$provenanceJson = ($provenance | ConvertTo-Json -Depth 4) + "`n"
[System.IO.File]::WriteAllText("$builtApk.build.json", $provenanceJson, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText("$namedApk.build.json", $provenanceJson, [System.Text.UTF8Encoding]::new($false))

Write-Output "PACKAGE=$($identity.package)"
Write-Output "VERSION=$($identity.versionName)"
Write-Output "VERSION_CODE=$($identity.versionCode)"
Write-Output "SIGNING_CERTIFICATE_SHA256=$($identity.signerSha256)"
Write-Output "APK_SHA256=$($identity.apkSha256)"
Write-Output "APK_PATH=$namedApk"
Write-Output "SOURCE_TREE_CLEAN_AT_BUILD=$sourceTreeClean"