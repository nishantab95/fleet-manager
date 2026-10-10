[CmdletBinding()]
param(
    [int]$Port = 3000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$webRoot = Join-Path $repoRoot 'apps\web'
$startScript = Join-Path $PSScriptRoot 'start-owner-web.ps1'
$nodeInstallDir = Join-Path $env:ProgramFiles 'nodejs'

if ((-not (Get-Command node.exe -ErrorAction SilentlyContinue)) -and
    (Test-Path -LiteralPath (Join-Path $nodeInstallDir 'node.exe') -PathType Leaf)) {
    $env:Path = "$nodeInstallDir;$env:Path"
}
if (-not (Get-Command node.exe -ErrorAction SilentlyContinue)) {
    throw 'Node.js 22 or newer is required to update the Owner app.'
}
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw 'npm 10 or newer is required to update the Owner app.'
}

function Invoke-RepoGit {
    param([string[]]$GitArguments)
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @(& git -c "safe.directory=$repoRoot" -C $repoRoot @GitArguments 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($exitCode -ne 0) {
        $detail = ($output | ForEach-Object { [string]$_ }) -join ' '
        throw "Git $($GitArguments[0]) failed: $detail"
    }
    return @($output | ForEach-Object { [string]$_ })
}

if ((Invoke-RepoGit @('branch', '--show-current')) -ne 'main') {
    throw 'Owner update requires the main branch.'
}
$sourceStatus = @(Invoke-RepoGit @('status', '--porcelain', '--untracked-files=normal'))
if ($sourceStatus.Count -ne 0) {
    throw 'Owner update requires a clean source checkout.'
}

$currentCommit = Invoke-RepoGit @('rev-parse', 'HEAD') | Select-Object -First 1
[void](Invoke-RepoGit @('fetch', '--no-tags', 'origin', 'main'))
$approvedCommit = Invoke-RepoGit @('rev-parse', 'origin/main') | Select-Object -First 1
if ($currentCommit -ne $approvedCommit) {
    $currentIsAncestor = $false
    & git -c "safe.directory=$repoRoot" -C $repoRoot merge-base --is-ancestor $currentCommit $approvedCommit 2>$null
    if ($LASTEXITCODE -eq 0) {
        [void](Invoke-RepoGit @('merge', '--ff-only', 'origin/main'))
    } else {
        & git -c "safe.directory=$repoRoot" -C $repoRoot merge-base --is-ancestor $approvedCommit $currentCommit 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw 'Owner update refused: local main and origin/main have diverged.'
        }
        Write-Output 'SOURCE=AHEAD_OF_ORIGIN'
    }
}

$lockFile = Join-Path $webRoot 'package-lock.json'
$nextPackage = Join-Path $webRoot 'node_modules\next\package.json'
$runtimeDirectory = Join-Path $repoRoot '.runtime\owner-web'
$lockStamp = Join-Path $runtimeDirectory 'package-lock.sha256'
if (-not (Test-Path -LiteralPath $lockFile -PathType Leaf)) {
    throw 'Owner app package-lock.json is missing.'
}
$lockHash = (Get-FileHash -LiteralPath $lockFile -Algorithm SHA256).Hash
$installedHash = if (Test-Path -LiteralPath $lockStamp -PathType Leaf) {
    (Get-Content -LiteralPath $lockStamp -Raw).Trim()
} else {
    ''
}

function Get-OwnerListenerPids {
    $lines = @(& netstat -ano -p tcp 2>$null)
    if ($LASTEXITCODE -ne 0) { throw 'Owner listener check failed.' }
    $pattern = '^\s*TCP\s+127\.0\.0\.1:' + [regex]::Escape([string]$Port) + '\s+\S+\s+LISTENING\s+(\d+)\s*$'
    return @(
        foreach ($line in $lines) {
            if ($line -match $pattern) { [int]$Matches[1] }
        }
    ) | Sort-Object -Unique
}

function Stop-OwnerForDependencyRefresh {
    $listeners = @(Get-OwnerListenerPids)
    foreach ($processId in $listeners) {
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
        $nextEntry = Join-Path $webRoot 'node_modules\next'
        $commandLine = if ($processInfo) { [string]$processInfo.CommandLine } else { '' }
        if ([string]::IsNullOrWhiteSpace($commandLine) -or
            $commandLine.IndexOf($nextEntry, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
            throw "Port $Port is occupied by an application outside this Owner repo."
        }
        & taskkill.exe /PID $processId /T /F *> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Could not stop the existing Owner app process $processId."
        }
    }
    if ($listeners.Count -gt 0) {
        $deadline = (Get-Date).AddSeconds(20)
        while ((Get-Date) -lt $deadline) {
            $remaining = @(Get-OwnerListenerPids)
            if ($remaining.Count -eq 0) { return }
            Start-Sleep -Milliseconds 500
        }
        throw "Owner port $Port remained occupied after dependency refresh shutdown."
    }
}

if (-not (Test-Path -LiteralPath $nextPackage -PathType Leaf) -or $installedHash -ne $lockHash) {
    Stop-OwnerForDependencyRefresh
    Push-Location $webRoot
    try {
        & npm.cmd ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) {
            throw "Owner dependency installation failed with exit code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }
    New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null
    Set-Content -LiteralPath $lockStamp -Value $lockHash -Encoding ascii
    Write-Output 'OWNER_DEPENDENCIES=UPDATED'
} else {
    Write-Output 'OWNER_DEPENDENCIES=CURRENT'
}

& "$PSHOME\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File $startScript -Port $Port -NoBrowser
if ($LASTEXITCODE -ne 0) {
    throw "Existing Owner launcher failed with exit code $LASTEXITCODE."
}
$ownerHealth = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/api/backend/health" -TimeoutSec 8
if ([int]$ownerHealth.StatusCode -ne 200) {
    throw "Owner app health check returned $([int]$ownerHealth.StatusCode)."
}
$deployedCommit = Invoke-RepoGit @('rev-parse', 'HEAD') | Select-Object -First 1
Write-Output "OWNER_COMMIT=$deployedCommit"
Write-Output "OWNER_HEALTH=$([int]$ownerHealth.StatusCode)"
Write-Output 'OWNER_UPDATE=PASS'
