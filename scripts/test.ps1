[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
$cacheDir = Join-Path $repoRoot ".uv-cache"
$apiProject = Join-Path $repoRoot "services\api"
$failures = [System.Collections.Generic.List[string]]::new()

# A long-lived parent process may not have received user-level PATH changes.
# Load the current user environment explicitly so this script works in a fresh
# PowerShell process without requiring a machine-wide installation.
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

function Invoke-RequiredCheck {
    param([string]$Label, [scriptblock]$Command)
    Write-Host "--- $Label ---"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        $failures.Add($Label)
    }
}

if (Get-Command uv -ErrorAction SilentlyContinue) {
    Push-Location $apiProject
    try {
        Invoke-RequiredCheck "uv lock verification" { uv --cache-dir $cacheDir lock --check }
        Invoke-RequiredCheck "Backend Ruff" { uv --cache-dir $cacheDir run --project . --group dev ruff check src tests migrations }
        Invoke-RequiredCheck "Backend mypy" { uv --cache-dir $cacheDir run --project . --group dev mypy src tests }
        Invoke-RequiredCheck "Backend pytest" { uv --cache-dir $cacheDir run --project . --group dev pytest -p no:cacheprovider }
        Invoke-RequiredCheck "Alembic offline migration check" { uv --cache-dir $cacheDir run --project . alembic upgrade head --sql }
    } finally {
        Pop-Location
    }
} else {
    $failures.Add("Backend checks (uv missing)")
}

$npm = Get-Command npm -ErrorAction SilentlyContinue
if ($npm) {
    Invoke-RequiredCheck "Web lint" { Push-Location (Join-Path $repoRoot "apps\web"); try { npm run lint } finally { Pop-Location } }
    Invoke-RequiredCheck "Web typecheck" { Push-Location (Join-Path $repoRoot "apps\web"); try { npm run typecheck } finally { Pop-Location } }
    Invoke-RequiredCheck "Web build" { Push-Location (Join-Path $repoRoot "apps\web"); try { npm run build } finally { Pop-Location } }
} else {
    Write-Warning "Web checks skipped: Node.js/npm is not installed."
}

$flutter = Get-Command flutter -ErrorAction SilentlyContinue
if ($flutter) {
    Invoke-RequiredCheck "Flutter analyze" { Push-Location (Join-Path $repoRoot "apps\mobile"); try { flutter analyze } finally { Pop-Location } }
    Invoke-RequiredCheck "Flutter tests" { Push-Location (Join-Path $repoRoot "apps\mobile"); try { flutter test } finally { Pop-Location } }
    Invoke-RequiredCheck "Flutter debug APK" { Push-Location (Join-Path $repoRoot "apps\mobile"); try { flutter build apk --debug } finally { Pop-Location } }
} else {
    Write-Warning "Flutter checks skipped: Flutter is not installed."
}

Invoke-RequiredCheck "Docker Compose config" { docker compose config --quiet }

if ($failures.Count -gt 0) {
    throw "Required checks failed: $($failures -join ', ')"
}

Write-Host "All available checks passed; unavailable toolchains were reported above."
