Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-WebsiteConfig {
    param([Parameter(Mandatory)][string]$DeployRoot)
    $configPath = Join-Path $DeployRoot 'website-config.json'
    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
        throw "Website configuration not found: $configPath. Run install-public-website.ps1 first."
    }
    Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
}

function Get-WebsiteState {
    param([Parameter(Mandatory)][string]$DeployRoot)
    $statePath = Join-Path $DeployRoot 'runtime\website-state.json'
    if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) { return $null }
    Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
}

function Save-WebsiteState {
    param(
        [Parameter(Mandatory)][string]$DeployRoot,
        [Parameter(Mandatory)][object]$State
    )
    $runtime = Join-Path $DeployRoot 'runtime'
    New-Item -ItemType Directory -Path $runtime -Force | Out-Null
    $target = Join-Path $runtime 'website-state.json'
    $temporary = "$target.new"
    $State | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $temporary -Encoding utf8
    Move-Item -LiteralPath $temporary -Destination $target -Force
}

function Test-WebsiteHealth {
    param(
        [Parameter(Mandatory)][int]$Port,
        [int]$Attempts = 1
    )
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3
            if ($response.status -eq 'ok' -and $response.service -eq 'fleet-ai-systems-marketing') {
                return $true
            }
        } catch {
            if ($attempt -lt $Attempts) { Start-Sleep -Seconds 1 }
        }
    }
    return $false
}

function Start-WebsiteRelease {
    param(
        [Parameter(Mandatory)][object]$Config,
        [Parameter(Mandatory)][string]$ReleasePath,
        [Parameter(Mandatory)][int]$Port
    )
    if (-not (Test-Path -LiteralPath (Join-Path $ReleasePath 'server.js') -PathType Leaf)) {
        throw "Release is missing server.js: $ReleasePath"
    }
    $logDirectory = Join-Path $Config.deployRoot 'logs'
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $env:NODE_ENV = 'production'
    $env:HOSTNAME = '127.0.0.1'
    $env:PORT = "$Port"
    $env:FLEET_MARKETING_LEAD_DIR = [string]$Config.leadDirectory
    Start-Process -FilePath ([string]$Config.nodePath) `
        -ArgumentList 'server.js' `
        -WorkingDirectory $ReleasePath `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDirectory "website-$stamp.out.log") `
        -RedirectStandardError (Join-Path $logDirectory "website-$stamp.err.log") `
        -PassThru
}

function Write-WebsiteUpstream {
    param(
        [Parameter(Mandatory)][string]$DeployRoot,
        [Parameter(Mandatory)][int]$Port
    )
    $target = Join-Path $DeployRoot 'runtime\upstream.caddy'
    $temporary = "$target.new"
    @"
reverse_proxy 127.0.0.1:$Port {
	header_up X-Real-IP {remote_host}
	health_uri /health
	health_interval 15s
	health_timeout 3s
	health_fails 2
	health_passes 1
	fail_duration 15s
	max_fails 2
}
"@ | Set-Content -LiteralPath $temporary -Encoding utf8
    Move-Item -LiteralPath $temporary -Destination $target -Force
}

function Stop-RecordedWebsiteProcess {
    param([object]$State)
    if ($null -eq $State -or $null -eq $State.pid) { return }
    $process = Get-Process -Id ([int]$State.pid) -ErrorAction SilentlyContinue
    if ($null -eq $process -or $process.ProcessName -ne 'node') { return }
    if ($null -ne $State.startedAt) {
        $expected = [DateTimeOffset]::Parse([string]$State.startedAt).UtcDateTime
        if ([Math]::Abs(($process.StartTime.ToUniversalTime() - $expected).TotalSeconds) -gt 5) {
            throw "Refusing to stop PID $($State.pid): its start time does not match the recorded website process."
        }
    }
    Stop-Process -Id $process.Id -Force
    $process.WaitForExit(10000)
}
