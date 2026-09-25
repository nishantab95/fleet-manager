[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
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

$ensurePython = Join-Path $repoRoot "scripts\ensure-trusted-python.ps1"
& $ensurePython
if ($LASTEXITCODE -eq 0) {
    $projectPython = Join-Path $apiProject ".venv\Scripts\python.exe"
    Push-Location $apiProject
    try {
        if (-not $env:FLEET_TEST_DATABASE_URL) {
            $env:FLEET_TEST_DATABASE_URL = "postgresql+psycopg://fleet:fleet@127.0.0.1:5432/fleet_test"
        }
        if (Get-Command uv -ErrorAction SilentlyContinue) {
            Invoke-RequiredCheck "uv lock verification" { uv --cache-dir (Join-Path $repoRoot ".uv-cache") lock --check }
        }
        Invoke-RequiredCheck "Backend Ruff" { & $projectPython -m ruff check src tests migrations }
        Invoke-RequiredCheck "Backend formatter" { & $projectPython -m ruff format --check src tests migrations }
        Invoke-RequiredCheck "Backend mypy" { & $projectPython -m mypy src tests }
        Invoke-RequiredCheck "Backend pytest" { & $projectPython -m pytest -p no:cacheprovider }
        Invoke-RequiredCheck "Alembic schema check" { & $projectPython -m alembic check }
        Invoke-RequiredCheck "Alembic offline migration check" { & $projectPython -m alembic upgrade head --sql }
    } finally {
        Pop-Location
    }
} else {
    $failures.Add("Trusted Python environment")
}

$npm = Get-Command npm -ErrorAction SilentlyContinue
if ($npm) {
    Invoke-RequiredCheck "Web lint" { Push-Location (Join-Path $repoRoot "apps\web"); try { npm run lint } finally { Pop-Location } }
    Invoke-RequiredCheck "Web typecheck" { Push-Location (Join-Path $repoRoot "apps\web"); try { npm run typecheck } finally { Pop-Location } }
    Invoke-RequiredCheck "Web tests" { Push-Location (Join-Path $repoRoot "apps\web"); try { npm test } finally { Pop-Location } }
    Invoke-RequiredCheck "Web build" { Push-Location (Join-Path $repoRoot "apps\web"); try { npm run build } finally { Pop-Location } }
} else {
    Write-Warning "Web checks skipped: Node.js/npm is not installed."
}

$flutter = Get-Command flutter -ErrorAction SilentlyContinue
if ($flutter) {
    Invoke-RequiredCheck "Flutter format" { Push-Location (Join-Path $repoRoot "apps\mobile"); try { dart format --output=none --set-exit-if-changed lib test integration_test } finally { Pop-Location } }
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
