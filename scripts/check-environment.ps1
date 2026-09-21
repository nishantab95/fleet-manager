[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath) {
    $env:Path = "$userPath;$env:Path"
}
$userJavaHome = [Environment]::GetEnvironmentVariable("JAVA_HOME", "User")
if ($userJavaHome) {
    $env:JAVA_HOME = $userJavaHome
}
$userAndroidSdk = [Environment]::GetEnvironmentVariable("ANDROID_SDK_ROOT", "User")
if ($userAndroidSdk) {
    $env:ANDROID_SDK_ROOT = $userAndroidSdk
    $env:ANDROID_HOME = $userAndroidSdk
}

Write-Host "--- Node/npm ---"
node --version
npm --version

Write-Host "--- Java ---"
java -version

Write-Host "--- Flutter/Dart ---"
flutter --version
dart --version

Write-Host "--- Android adb ---"
adb --version

Write-Host "--- Flutter doctor ---"
flutter doctor -v

