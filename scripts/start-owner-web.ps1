[CmdletBinding()]
param(
    [int]$Port = 3000,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$webRoot = Join-Path $repoRoot 'apps\web'
$envFile = Join-Path $webRoot '.env.local'
$logRoot = Join-Path $repoRoot '.runtime\owner-web'
$logFile = Join-Path $logRoot 'owner-web.log'
$localUrl = "http://127.0.0.1:$Port"

function Stop-WithMessage([string]$Message) {
    Write-Host "Fleet Manager Owner could not start: $Message" -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}

if (-not (Get-Command node.exe -ErrorAction SilentlyContinue)) { Stop-WithMessage 'Node.js is not installed or is not on PATH.' }
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { Stop-WithMessage 'npm is not installed or is not on PATH.' }
if (-not (Test-Path -LiteralPath (Join-Path $webRoot 'node_modules\next\package.json'))) { Stop-WithMessage 'Web dependencies are missing. Run npm install in apps\web.' }

$upstream = [Environment]::GetEnvironmentVariable('FLEET_API_UPSTREAM_URL', 'Process')
if ([string]::IsNullOrWhiteSpace($upstream) -and (Test-Path -LiteralPath $envFile)) {
    $line = Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^\s*FLEET_API_UPSTREAM_URL\s*=' } | Select-Object -Last 1
    if ($line) { $upstream = ($line -split '=', 2)[1].Trim().Trim('"').Trim("'") }
}
if ([string]::IsNullOrWhiteSpace($upstream)) { Stop-WithMessage 'Set FLEET_API_UPSTREAM_URL in apps\web\.env.local to the private server URL.' }

try {
    $health = Invoke-RestMethod -Uri "$($upstream.TrimEnd('/'))/health" -TimeoutSec 12
    $ready = Invoke-RestMethod -Uri "$($upstream.TrimEnd('/'))/ready" -TimeoutSec 12
    if ($health.status -ne 'ok' -or $ready.status -ne 'ready') { throw 'The server did not report healthy and ready.' }
} catch {
    Stop-WithMessage 'The private Fleet API is unreachable. Confirm Tailscale is connected and try again.'
}

$alreadyRunning = $false
try {
    $probe = Invoke-WebRequest -Uri "$localUrl/api/backend/health" -UseBasicParsing -TimeoutSec 3
    $alreadyRunning = $probe.StatusCode -eq 200
} catch {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) { Stop-WithMessage "Port $Port is already used by another application." }
}

if (-not $alreadyRunning) {
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $command = "npm run dev -- --hostname 127.0.0.1 --port $Port > `"$logFile`" 2>&1"
    Start-Process -FilePath 'cmd.exe' -ArgumentList '/d', '/s', '/c', $command -WorkingDirectory $webRoot -WindowStyle Hidden
    $deadline = (Get-Date).AddSeconds(75)
    do {
        Start-Sleep -Milliseconds 750
        try {
            $probe = Invoke-WebRequest -Uri "$localUrl/api/backend/health" -UseBasicParsing -TimeoutSec 3
            if ($probe.StatusCode -eq 200) { $alreadyRunning = $true; break }
        } catch { }
    } while ((Get-Date) -lt $deadline)
    if (-not $alreadyRunning) { Stop-WithMessage "The web app did not become ready. See $logFile" }
}

Write-Host "Fleet Manager Owner is ready at $localUrl/owner" -ForegroundColor Green
if (-not $NoBrowser) { Start-Process "$localUrl/owner" }
