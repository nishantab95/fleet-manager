[CmdletBinding()]
param([string]$DeployRoot = 'C:\FleetAISystems\Website')

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this website rollback helper from an elevated PowerShell window.'
}
. (Join-Path $PSScriptRoot 'public-website-cloudflare-common.ps1')

$config = Get-CloudflareWebsiteConfig -DeployRoot $DeployRoot
$paths = Get-CloudflareWebsitePaths -DeployRoot $DeployRoot
$current = Get-CloudflareWebsiteActiveRelease -DeployRoot $DeployRoot
$previous = Get-CloudflareWebsitePreviousRelease -DeployRoot $DeployRoot
if ($null -eq $current -or $null -eq $previous) { throw 'There is no previous healthy release to roll back to.' }
if (-not (Test-Path -LiteralPath (Join-Path ([string]$previous.releasePath) 'server.js') -PathType Leaf)) {
    throw "Previous release is missing: $($previous.releasePath)"
}
$state = Get-CloudflareWebsiteState -DeployRoot $DeployRoot
$listeners = Get-CloudflareWebsiteListeners -Port ([int]$config.port)
if ($listeners.Count -gt 0) {
    if ($listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne '127.0.0.1' -or
        $null -eq $state -or [int]$listeners[0].OwningProcess -ne [int]$state.pid) {
        throw 'The website port is held by an unverified process; refusing rollback.'
    }
    $null = Get-CloudflareManagedProcess -State $state
}
if ($null -ne $state) { Stop-CloudflareManagedProcess -State $state }
Save-CloudflareWebsiteJson -Path $paths.Previous -Value $current
Save-CloudflareWebsiteJson -Path $paths.Active -Value $previous

Start-ScheduledTask -TaskName ([string]$config.taskName)
$healthy = $false
for ($attempt = 1; $attempt -le 30; $attempt++) {
    if (Test-CloudflareWebsiteHealth -Port ([int]$config.port)) { $healthy = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $healthy) {
    $failedState = Get-CloudflareWebsiteState -DeployRoot $DeployRoot
    if ($null -ne $failedState -and [string]$failedState.releasePath -eq [string]$previous.releasePath) {
        Stop-CloudflareManagedProcess -State $failedState
        Remove-Item -LiteralPath $paths.State -Force -ErrorAction SilentlyContinue
    }
    Save-CloudflareWebsiteJson -Path $paths.Active -Value $current
    Save-CloudflareWebsiteJson -Path $paths.Previous -Value $previous
    Start-ScheduledTask -TaskName ([string]$config.taskName)
    $currentHealthy = $false
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        if (Test-CloudflareWebsiteHealth -Port ([int]$config.port)) { $currentHealthy = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $currentHealthy) { throw 'The previous release failed and the current release did not recover.' }
    throw 'The previous release failed its health check; the current release was restored and verified.'
}
Write-Host "Rolled back to healthy website release $($previous.releaseId) on 127.0.0.1:$($config.port)."
