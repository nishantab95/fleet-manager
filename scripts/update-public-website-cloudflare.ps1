[CmdletBinding()]
param([string]$DeployRoot = 'C:\FleetAISystems\Website')

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this website update helper from an elevated PowerShell window.'
}
. (Join-Path $PSScriptRoot 'public-website-cloudflare-common.ps1')

$config = Get-CloudflareWebsiteConfig -DeployRoot $DeployRoot
$sourceRoot = [IO.Path]::GetFullPath([string]$config.sourceRoot)
$gitExe = (Get-Command git.exe -ErrorAction Stop).Source
$branch = (& $gitExe -C $sourceRoot branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne 'main') { throw 'Website updates are allowed only from the existing main branch.' }
$dirty = (& $gitExe -C $sourceRoot status --porcelain) -join "`n"
if ($LASTEXITCODE -ne 0 -or -not [string]::IsNullOrWhiteSpace($dirty)) { throw "Review and commit or discard repository changes before creating a production website release: $dirty" }

$marketingRoot = Join-Path $sourceRoot 'apps\marketing'
$nodeDirectory = [IO.Path]::GetDirectoryName([string]$config.nodePath)
$env:Path = "$nodeDirectory;$env:SystemRoot\System32;$env:SystemRoot"
$env:npm_config_cache = Join-Path $env:TEMP 'FleetAIWebsiteNpmCache'
$env:npm_config_logs_max = '0'
Push-Location $marketingRoot
try {
    npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'npm.cmd ci failed; no active release was changed.' }
    npm.cmd audit --omit=dev
    if ($LASTEXITCODE -ne 0) { throw 'npm production audit failed; no active release was changed.' }
    npm.cmd run lint
    if ($LASTEXITCODE -ne 0) { throw 'Marketing lint failed; no active release was changed.' }
    npm.cmd run typecheck
    if ($LASTEXITCODE -ne 0) { throw 'Marketing typecheck failed; no active release was changed.' }
    npm.cmd test
    if ($LASTEXITCODE -ne 0) { throw 'Marketing tests failed; no active release was changed.' }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Marketing build failed; no active release was changed.' }
} finally {
    Pop-Location
}

$dirtyAfterBuild = (& $gitExe -C $sourceRoot status --porcelain) -join "`n"
if ($LASTEXITCODE -ne 0 -or -not [string]::IsNullOrWhiteSpace($dirtyAfterBuild)) {
    throw "The build changed tracked or untracked repository files; review before release creation: $dirtyAfterBuild"
}
$gitCommit = (& $gitExe -C $sourceRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $gitCommit -notmatch '^[0-9a-f]{40}$') { throw 'Unable to resolve the full production source commit.' }
$releaseId = "$(Get-Date -Format 'yyyyMMdd-HHmmss')-$gitCommit"
$releasesRoot = Join-Path $config.deployRoot 'releases'
$stagePath = Join-Path $releasesRoot ".staging-$releaseId"
$releasePath = Join-Path $releasesRoot $releaseId
if (Test-Path -LiteralPath $releasePath) { throw "Release path already exists: $releasePath" }
New-Item -ItemType Directory -Path $stagePath -Force | Out-Null
try {
    $standalone = Join-Path $marketingRoot '.next\standalone'
    $static = Join-Path $marketingRoot '.next\static'
    $public = Join-Path $marketingRoot 'public'
    if (-not (Test-Path -LiteralPath (Join-Path $standalone 'server.js') -PathType Leaf) -or
        -not (Test-Path -LiteralPath $static -PathType Container) -or
        -not (Test-Path -LiteralPath $public -PathType Container)) {
        throw 'The Next.js standalone server, static assets, or public assets are missing.'
    }
    Get-ChildItem -LiteralPath $standalone -Force | Copy-Item -Destination $stagePath -Recurse -Force
    New-Item -ItemType Directory -Path (Join-Path $stagePath '.next\static') -Force | Out-Null
    Get-ChildItem -LiteralPath $static -Force | Copy-Item -Destination (Join-Path $stagePath '.next\static') -Recurse -Force
    Copy-Item -LiteralPath $public -Destination (Join-Path $stagePath 'public') -Recurse -Force
    & icacls.exe $stagePath /inheritance:r /grant:r '*S-1-5-18:RX' '*S-1-5-32-544:F' /T /C | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Unable to restrict the immutable release ACL.' }
    Move-Item -LiteralPath $stagePath -Destination $releasePath
} catch {
    if (Test-Path -LiteralPath $stagePath) { Remove-Item -LiteralPath $stagePath -Recurse -Force }
    throw
}

$paths = Get-CloudflareWebsitePaths -DeployRoot $DeployRoot
$oldActive = Get-CloudflareWebsiteActiveRelease -DeployRoot $DeployRoot
$oldPrevious = Get-CloudflareWebsitePreviousRelease -DeployRoot $DeployRoot
$oldState = Get-CloudflareWebsiteState -DeployRoot $DeployRoot
$listeners = Get-CloudflareWebsiteListeners -Port ([int]$config.port)
if ($listeners.Count -gt 0) {
    if ($listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne '127.0.0.1' -or
        $null -eq $oldState -or [int]$listeners[0].OwningProcess -ne [int]$oldState.pid) {
        throw "Port $($config.port) is held by an unverified process; refusing to stop it."
    }
    $null = Get-CloudflareManagedProcess -State $oldState
}
if ($null -ne $oldState) { Stop-CloudflareManagedProcess -State $oldState }

$newRelease = [ordered]@{
    releaseId = $releaseId
    releasePath = $releasePath
    gitCommit = $gitCommit
    createdAt = [DateTimeOffset]::UtcNow.ToString('o')
}
if ($null -ne $oldActive) {
    Save-CloudflareWebsiteJson -Path $paths.Previous -Value $oldActive
}
Save-CloudflareWebsiteJson -Path $paths.Active -Value $newRelease

try {
    Start-ScheduledTask -TaskName ([string]$config.taskName)
    $healthy = $false
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        if (Test-CloudflareWebsiteHealth -Port ([int]$config.port)) { $healthy = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $healthy) { throw 'The new website release did not pass its local health check.' }
    $state = Get-CloudflareWebsiteState -DeployRoot $DeployRoot
    if ($null -eq $state -or [string]$state.releasePath -ne $releasePath) { throw 'The SYSTEM startup task did not start the expected release.' }
    $procInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$state.pid)"
    $owner = Invoke-CimMethod -InputObject $procInfo -MethodName GetOwner
    if ($owner.ReturnValue -ne 0 -or $owner.User -ne 'SYSTEM') { throw 'The marketing website process did not start as SYSTEM.' }
} catch {
    $newState = Get-CloudflareWebsiteState -DeployRoot $DeployRoot
    if ($null -ne $newState -and [string]$newState.releasePath -eq $releasePath) {
        Stop-CloudflareManagedProcess -State $newState
        Remove-Item -LiteralPath $paths.State -Force -ErrorAction SilentlyContinue
    }
    if ($null -ne $oldActive) {
        Save-CloudflareWebsiteJson -Path $paths.Active -Value $oldActive
        Start-ScheduledTask -TaskName ([string]$config.taskName)
        $rolledBack = $false
        for ($attempt = 1; $attempt -le 30; $attempt++) {
            if (Test-CloudflareWebsiteHealth -Port ([int]$config.port)) { $rolledBack = $true; break }
            Start-Sleep -Seconds 1
        }
        if (-not $rolledBack) { throw "New release failed and the previous release did not recover. Original error: $($_.Exception.Message)" }
    } else {
        Remove-Item -LiteralPath $paths.Active -Force -ErrorAction SilentlyContinue
    }
    if ($null -ne $oldPrevious) {
        Save-CloudflareWebsiteJson -Path $paths.Previous -Value $oldPrevious
    } else {
        Remove-Item -LiteralPath $paths.Previous -Force -ErrorAction SilentlyContinue
    }
    throw
}

Write-Host "Website release $releaseId is healthy on 127.0.0.1:$($config.port), running as SYSTEM."
Write-Host 'Only the marketing Node process was restarted; Cloudflare and private Fleet services were not changed.'
