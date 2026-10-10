[CmdletBinding()]
param(
    [string]$DeployRoot = 'C:\FleetAISystems\Website',
    [switch]$SkipProxyReload
)

. (Join-Path $PSScriptRoot 'public-website-common.ps1')

$config = Get-WebsiteConfig -DeployRoot $DeployRoot
$sourceRoot = [IO.Path]::GetFullPath([string]$config.sourceRoot)
$marketingRoot = Join-Path $sourceRoot 'apps\marketing'
if (-not (Test-Path -LiteralPath (Join-Path $marketingRoot 'package-lock.json') -PathType Leaf)) {
    throw "Marketing source or lockfile is missing: $marketingRoot"
}

Push-Location $marketingRoot
try {
    & npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Marketing production build failed.' }
} finally {
    Pop-Location
}

$gitHead = (& git -C $sourceRoot rev-parse --short HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Unable to resolve the source Git revision.' }
$releaseId = "$(Get-Date -Format 'yyyyMMdd-HHmmss')-$gitHead"
$releasesRoot = Join-Path $DeployRoot 'releases'
$stagingPath = Join-Path $releasesRoot ".staging-$releaseId"
$releasePath = Join-Path $releasesRoot $releaseId
New-Item -ItemType Directory -Path $stagingPath -Force | Out-Null

try {
    $standalone = Join-Path $marketingRoot '.next\standalone'
    if (-not (Test-Path -LiteralPath (Join-Path $standalone 'server.js') -PathType Leaf)) {
        throw 'The Next.js standalone output is missing server.js.'
    }
    Copy-Item -Path (Join-Path $standalone '*') -Destination $stagingPath -Recurse -Force
    New-Item -ItemType Directory -Path (Join-Path $stagingPath '.next\static') -Force | Out-Null
    Copy-Item -Path (Join-Path $marketingRoot '.next\static\*') -Destination (Join-Path $stagingPath '.next\static') -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $marketingRoot 'public') -Destination (Join-Path $stagingPath 'public') -Recurse -Force
    Move-Item -LiteralPath $stagingPath -Destination $releasePath
} catch {
    if (Test-Path -LiteralPath $stagingPath) { Remove-Item -LiteralPath $stagingPath -Recurse -Force }
    throw
}

$oldState = Get-WebsiteState -DeployRoot $DeployRoot
$port = if ($null -ne $oldState -and [int]$oldState.port -eq 3100) { 3101 } else { 3100 }
$newProcess = Start-WebsiteRelease -Config $config -ReleasePath $releasePath -Port $port
$startedAt = $newProcess.StartTime.ToUniversalTime().ToString('o')
if (-not (Test-WebsiteHealth -Port $port -Attempts 30)) {
    Stop-Process -Id $newProcess.Id -Force -ErrorAction SilentlyContinue
    throw "New website release failed its health gate on port $port. The existing release was not changed."
}

$upstreamPath = Join-Path $DeployRoot 'runtime\upstream.caddy'
$previousUpstream = if (Test-Path -LiteralPath $upstreamPath) { Get-Content -LiteralPath $upstreamPath -Raw } else { $null }
Write-WebsiteUpstream -DeployRoot $DeployRoot -Port $port
try {
    if (-not $SkipProxyReload) {
        & ([string]$config.caddyPath) reload --config ([string]$config.caddyConfig) --adapter caddyfile
        if ($LASTEXITCODE -ne 0) { throw 'Caddy rejected the new website upstream.' }
    }
} catch {
    if ($null -ne $previousUpstream) {
        $previousUpstream | Set-Content -LiteralPath $upstreamPath -Encoding utf8
        & ([string]$config.caddyPath) reload --config ([string]$config.caddyConfig) --adapter caddyfile | Out-Null
    }
    Stop-Process -Id $newProcess.Id -Force -ErrorAction SilentlyContinue
    throw
}

$newState = [ordered]@{
    releaseId = $releaseId
    releasePath = $releasePath
    gitHead = $gitHead
    port = $port
    pid = $newProcess.Id
    startedAt = $startedAt
    deployedAt = [DateTimeOffset]::UtcNow.ToString('o')
}
Save-WebsiteState -DeployRoot $DeployRoot -State $newState

if ($null -ne $oldState) { Stop-RecordedWebsiteProcess -State $oldState }
Write-Host "Website updated atomically to $releaseId on local port $port."
Write-Host 'The Fleet API, Owner app, database, object storage, and mobile release services were not restarted.'
