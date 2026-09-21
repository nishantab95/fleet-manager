[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$sdkRoot = Join-Path $env:LOCALAPPDATA "Android\Sdk"
$toolsRoot = Join-Path $env:USERPROFILE "Tools"
$archivePath = Join-Path $toolsRoot "commandlinetools-win-15859902_latest.zip"
$extractRoot = Join-Path $toolsRoot "android-commandline-extract"
$cmdlineRoot = Join-Path $sdkRoot "cmdline-tools\latest"
$sdkManager = Join-Path $cmdlineRoot "bin\sdkmanager.bat"
$downloadUrl = "https://dl.google.com/android/repository/commandlinetools-win-15859902_latest.zip"
$expectedHash = "90AE805D20434428BFFCB699C290860F19BB5F66A67E6B330067E3DE801FB04A"

New-Item -ItemType Directory -Force -Path $toolsRoot, $sdkRoot | Out-Null

$configuredJavaHome = [Environment]::GetEnvironmentVariable("JAVA_HOME", "User")
if (-not [string]::IsNullOrWhiteSpace($configuredJavaHome) -and (Test-Path -LiteralPath (Join-Path $configuredJavaHome "bin\java.exe"))) {
    $env:JAVA_HOME = $configuredJavaHome
    $env:Path = (Join-Path $configuredJavaHome "bin") + ";" + $env:Path
}

if (-not (Test-Path -LiteralPath $sdkManager)) {
    if (-not (Test-Path -LiteralPath $archivePath)) {
        Invoke-WebRequest -Uri $downloadUrl -OutFile $archivePath
    }
    $actualHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
    if ($actualHash -ne $expectedHash) {
        throw "Android command-line tools checksum mismatch. Expected $expectedHash, got $actualHash."
    }
    if (Test-Path -LiteralPath $extractRoot) {
        Remove-Item -LiteralPath $extractRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $extractRoot | Out-Null
    Expand-Archive -LiteralPath $archivePath -DestinationPath $extractRoot -Force
    $sourceRoot = Join-Path $extractRoot "cmdline-tools"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $cmdlineRoot) | Out-Null
    Move-Item -LiteralPath $sourceRoot -Destination $cmdlineRoot
}

[Environment]::SetEnvironmentVariable("ANDROID_HOME", $sdkRoot, "User")
[Environment]::SetEnvironmentVariable("ANDROID_SDK_ROOT", $sdkRoot, "User")
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$pathEntries = @($userPath -split ";" | Where-Object { $_ })
foreach ($entry in @(
        (Join-Path $cmdlineRoot "bin"),
        (Join-Path $sdkRoot "platform-tools"),
        (Join-Path $sdkRoot "emulator")
    )) {
    if ($pathEntries -notcontains $entry) {
        $pathEntries += $entry
    }
}
[Environment]::SetEnvironmentVariable("Path", ($pathEntries -join ";"), "User")

$licenseAnswers = @("y") * 20
$licenseAnswers | & $sdkManager --sdk_root=$sdkRoot --licenses
if ($LASTEXITCODE -ne 0) {
    throw "sdkmanager license acceptance failed with exit code $LASTEXITCODE."
}
& $sdkManager --sdk_root=$sdkRoot "platform-tools" "platforms;android-36" "build-tools;36.0.0"
if ($LASTEXITCODE -ne 0) {
    throw "sdkmanager package installation failed with exit code $LASTEXITCODE."
}
