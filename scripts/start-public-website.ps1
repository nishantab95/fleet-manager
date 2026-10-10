[CmdletBinding()]
param([string]$DeployRoot = 'C:\FleetAISystems\Website')

. (Join-Path $PSScriptRoot 'public-website-common.ps1')
$config = Get-WebsiteConfig -DeployRoot $DeployRoot
$state = Get-WebsiteState -DeployRoot $DeployRoot
if ($null -eq $state) { throw 'No deployed website release exists. Run update-public-website.ps1 first.' }

if (Test-WebsiteHealth -Port ([int]$state.port)) {
    Write-Host "Website is already healthy on port $($state.port)."
} else {
    $process = Start-WebsiteRelease -Config $config -ReleasePath ([string]$state.releasePath) -Port ([int]$state.port)
    $state.pid = $process.Id
    $state.startedAt = $process.StartTime.ToUniversalTime().ToString('o')
    Save-WebsiteState -DeployRoot $DeployRoot -State $state
    if (-not (Test-WebsiteHealth -Port ([int]$state.port) -Attempts 30)) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        throw 'Website process started but did not pass its health gate.'
    }
}

Write-WebsiteUpstream -DeployRoot $DeployRoot -Port ([int]$state.port)
$service = Get-Service -Name caddy -ErrorAction SilentlyContinue
if ($null -ne $service -and $service.Status -ne 'Running') { Start-Service -Name caddy }
Write-Host 'Fleet AI Systems public website is started. Private Fleet services were not touched.'
