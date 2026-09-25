[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$apiProject = Join-Path $repoRoot "services\api"
$projectPython = Join-Path $apiProject ".venv\Scripts\python.exe"
$cacheDir = Join-Path $repoRoot ".uv-cache"

function Get-TrustedPythonLauncher {
    $candidates = [System.Collections.Generic.List[string]]::new()

    foreach ($name in @("py.exe", "py")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command -and $command.Source) {
            $candidates.Add($command.Source)
        }
    }

    if ($env:LOCALAPPDATA) {
        $candidates.Add(
            (Join-Path $env:LOCALAPPDATA "Programs\Python\Launcher\py.exe")
        )
    }

    $existing = [System.Collections.Generic.List[string]]::new()
    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $existing.Add($candidate)
        }
    }
    return $existing.ToArray()
}

function Get-UvExecutable {
    $command = Get-Command uv.exe, uv -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command -and $command.Source) {
        return $command.Source
    }

    $candidates = @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:LOCALAPPDATA "uv\uv.exe"),
        (Join-Path $env:USERPROFILE ".cargo\bin\uv.exe"),
        (Join-Path $env:USERPROFILE "scoop\shims\uv.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }
    return $null
}

$pyLaunchers = @(Get-TrustedPythonLauncher)
if ($pyLaunchers.Count -eq 0) {
    throw "Trusted Python Launcher was not found. Install Python 3.12 with the standard py launcher."
}

$trustedPython = $null
foreach ($pyLauncher in $pyLaunchers) {
    try {
        $candidate = (& $pyLauncher -3.12 -c "import sys; print(sys.executable)").Trim()
        if ($LASTEXITCODE -eq 0 -and $candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            $trustedPython = $candidate
            break
        }
    } catch {
        # Try the next standard launcher candidate without bypassing policy.
    }
}
if (-not $trustedPython) {
    throw "The Python Launcher could not resolve a trusted Python 3.12 interpreter."
}

$trustedBase = (& $trustedPython -c "import sys; print(sys.prefix)").Trim()
if ($LASTEXITCODE -ne 0 -or -not $trustedBase) {
    throw "The trusted Python 3.12 interpreter could not be executed."
}

$needsSync = -not (Test-Path -LiteralPath $projectPython -PathType Leaf)
if (-not $needsSync) {
    $projectBase = (& $projectPython -c "import sys; print(sys.base_prefix)").Trim()
    if ($LASTEXITCODE -ne 0 -or $projectBase -ne $trustedBase) {
        $needsSync = $true
    }
}

if ($needsSync) {
    $uv = Get-UvExecutable
    if (-not $uv) {
        throw "uv is required to create the locked Fleet Manager environment with trusted Python 3.12."
    }

    # The explicit interpreter prevents uv from selecting or downloading its
    # own CPython. This does not bypass Windows Application Control.
    $env:UV_PYTHON_DOWNLOADS = "never"
    & $uv --cache-dir $cacheDir sync --project $apiProject --python $trustedPython --locked --all-groups
    if ($LASTEXITCODE -ne 0) {
        throw "Trusted Python environment synchronization failed (exit $LASTEXITCODE)."
    }
}

# This is the security gate: the exact project interpreter that services use
# must execute successfully before the wrapper reports readiness.
& $projectPython -c "import sys; print(sys.executable); print(sys.base_prefix)"
if ($LASTEXITCODE -ne 0) {
    throw "The project Python interpreter is blocked or unusable by Windows Application Control."
}

Write-Output "Trusted Python: $trustedPython"
Write-Output "Project Python: $projectPython"
