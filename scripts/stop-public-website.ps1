[CmdletBinding()]
param([string]$DeployRoot = 'C:\FleetAISystems\Website')

. (Join-Path $PSScriptRoot 'public-website-common.ps1')
$state = Get-WebsiteState -DeployRoot $DeployRoot
if ($null -ne $state) { Stop-RecordedWebsiteProcess -State $state }
$service = Get-Service -Name caddy -ErrorAction SilentlyContinue
if ($null -ne $service -and $service.Status -ne 'Stopped') { Stop-Service -Name caddy }
Write-Host 'Stopped only the public website process and its Caddy service.'
