[CmdletBinding()]
param(
    [string]$FlutterRoot = ""
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($FlutterRoot)) {
    $FlutterRoot = Join-Path $env:USERPROFILE "develop\flutter"
}

$flutterParent = Split-Path -Parent $FlutterRoot
New-Item -ItemType Directory -Force -Path $flutterParent | Out-Null

if (-not (Test-Path -LiteralPath (Join-Path $FlutterRoot "bin\flutter.bat"))) {
    git clone --depth 1 --branch stable https://github.com/flutter/flutter.git $FlutterRoot
}

$flutterBin = Join-Path $FlutterRoot "bin"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$pathEntries = @($userPath -split ";" | Where-Object { $_ })
if ($pathEntries -notcontains $flutterBin) {
    [Environment]::SetEnvironmentVariable("Path", (($pathEntries + $flutterBin) -join ";"), "User")
}

& (Join-Path $flutterBin "flutter.bat") --version
& (Join-Path $flutterBin "dart.bat") --version

