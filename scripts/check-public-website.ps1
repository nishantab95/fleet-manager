[CmdletBinding()]
param([string]$DeployRoot = 'C:\FleetAISystems\Website')

. (Join-Path $PSScriptRoot 'public-website-common.ps1')
$config = Get-WebsiteConfig -DeployRoot $DeployRoot
$state = Get-WebsiteState -DeployRoot $DeployRoot
if ($null -eq $state) { throw 'No deployed website release is recorded.' }

$healthy = Test-WebsiteHealth -Port ([int]$state.port)
Write-Host "Marketing health: $(if ($healthy) { 'PASS' } else { 'FAIL' })"
$service = Get-Service -Name caddy -ErrorAction SilentlyContinue
Write-Host "Caddy service: $(if ($null -eq $service) { 'NOT INSTALLED' } else { $service.Status })"
& ([string]$config.caddyPath) validate --config ([string]$config.caddyConfig) --adapter caddyfile
if ($LASTEXITCODE -ne 0) { throw 'Caddy configuration validation failed.' }

function Get-WebsiteStatusCode {
    param([Parameter(Mandatory)][string]$Uri)
    try {
        $response = Invoke-WebRequest -Uri $Uri -TimeoutSec 3 -UseBasicParsing
        return [int]$response.StatusCode
    } catch {
        if ($null -ne $_.Exception.Response) {
            return [int]$_.Exception.Response.StatusCode
        }
        throw
    }
}

foreach ($privatePath in @('/login', '/owner', '/supervisor', '/api/v1/auth/me', '/docs', '/openapi.json', '/evidence/private')) {
    try {
        $statusCode = Get-WebsiteStatusCode -Uri "http://127.0.0.1:$($state.port)$privatePath"
        if ($statusCode -ne 404) { throw "$privatePath returned $statusCode, expected 404." }
    } catch {
        throw "Private-path check failed for ${privatePath}: $($_.Exception.Message)"
    }
}
if (-not $healthy) { throw 'Website health check failed.' }
Write-Host "Release $($state.releaseId) is healthy; private-route probes return 404."
