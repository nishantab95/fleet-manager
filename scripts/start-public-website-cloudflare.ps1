[CmdletBinding()]
param(
    [string]$DeployRoot = 'C:\FleetAISystems\Website',
    [switch]$AsTask
)

. (Join-Path $PSScriptRoot 'public-website-cloudflare-common.ps1')
if (-not $AsTask) {
    $config = Get-CloudflareWebsiteConfig -DeployRoot $DeployRoot
    Start-ScheduledTask -TaskName ([string]$config.taskName)
    $healthy = $false
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        if (Test-CloudflareWebsiteHealth -Port ([int]$config.port)) { $healthy = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $healthy) { throw 'The SYSTEM startup task did not start a healthy marketing website.' }
    Write-Host "Marketing website is healthy on 127.0.0.1:$($config.port) under its SYSTEM startup task."
    return
}

$config = Get-CloudflareWebsiteConfig -DeployRoot $DeployRoot
$release = Get-CloudflareWebsiteActiveRelease -DeployRoot $DeployRoot
if ($null -eq $release) { throw 'No active Cloudflare website release is recorded.' }
$state = Start-CloudflareWebsiteRelease -Config $config -Release $release -DeployRoot $DeployRoot
Write-Host "Marketing website is healthy on 127.0.0.1:$($state.port) from $($state.releaseId)."
