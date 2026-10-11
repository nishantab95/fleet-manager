[CmdletBinding()]
param([string]$DeployRoot = 'C:\FleetAISystems\Website')

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this website stop helper from an elevated PowerShell window.'
}
. (Join-Path $PSScriptRoot 'public-website-cloudflare-common.ps1')
$state = Get-CloudflareWebsiteState -DeployRoot $DeployRoot
Stop-CloudflareManagedProcess -State $state
Write-Host 'Stopped only the recorded Cloudflare marketing website process. The Cloudflare connector and private Fleet services were not changed.'
