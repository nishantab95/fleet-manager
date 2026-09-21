[CmdletBinding()]
param(
    [string]$MajorVersion = "17"
)

$ErrorActionPreference = "Stop"
$toolsRoot = Join-Path $env:USERPROFILE "Tools"
$javaRoot = Join-Path $toolsRoot "temurin-$MajorVersion"
$downloadRoot = Join-Path $toolsRoot "jdk-download"
$archivePath = Join-Path $toolsRoot "temurin-$MajorVersion.zip"
$downloadUrl = "https://api.adoptium.net/v3/binary/latest/$MajorVersion/ga/windows/x64/jdk/hotspot/normal/eclipse"

New-Item -ItemType Directory -Force -Path $toolsRoot | Out-Null

if (-not (Test-Path -LiteralPath (Join-Path $javaRoot "bin\java.exe"))) {
    Invoke-WebRequest -Uri $downloadUrl -OutFile $archivePath
    if (Test-Path -LiteralPath $downloadRoot) {
        Remove-Item -LiteralPath $downloadRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null
    Expand-Archive -LiteralPath $archivePath -DestinationPath $downloadRoot -Force
    $extractedRoot = Get-ChildItem -LiteralPath $downloadRoot -Directory | Select-Object -First 1
    if ($null -eq $extractedRoot) {
        throw "The JDK archive did not contain a top-level directory."
    }
    Move-Item -LiteralPath $extractedRoot.FullName -Destination $javaRoot
}

[Environment]::SetEnvironmentVariable("JAVA_HOME", $javaRoot, "User")
$env:JAVA_HOME = $javaRoot
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$pathEntries = @($userPath -split ";" | Where-Object { $_ })
$javaBin = Join-Path $javaRoot "bin"
if ($pathEntries -notcontains $javaBin) {
    [Environment]::SetEnvironmentVariable("Path", (($pathEntries + $javaBin) -join ";"), "User")
}
$env:Path = "$javaBin;$env:Path"

& (Join-Path $javaBin "java.exe") -version
