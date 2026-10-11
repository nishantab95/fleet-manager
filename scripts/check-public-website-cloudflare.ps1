[CmdletBinding()]
param([string]$DeployRoot = 'C:\FleetAISystems\Website')

. (Join-Path $PSScriptRoot 'public-website-cloudflare-common.ps1')
$config = Get-CloudflareWebsiteConfig -DeployRoot $DeployRoot
$active = Get-CloudflareWebsiteActiveRelease -DeployRoot $DeployRoot
$state = Get-CloudflareWebsiteState -DeployRoot $DeployRoot
if ($null -eq $active -or $null -eq $state) { throw 'No active Cloudflare website release is recorded.' }
if (-not (Test-CloudflareWebsiteHealth -Port ([int]$config.port))) { throw 'Marketing /health did not return the expected safe JSON response.' }

function Get-CloudflareWebsiteStatusCode {
    param([Parameter(Mandatory)][string]$Uri)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 5
        return [int]$response.StatusCode
    } catch {
        if ($null -ne $_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
        throw
    }
}

$base = "http://127.0.0.1:$([int]$config.port)"
foreach ($publicPath in @('/', '/features', '/how-it-works', '/solutions', '/pricing', '/contact')) {
    $status = Get-CloudflareWebsiteStatusCode -Uri "$base$publicPath"
    if ($status -ne 200) { throw "Public marketing page $publicPath returned $status, expected 200." }
}
foreach ($privatePath in @('/owner', '/supervisor', '/lab', '/api/v1/auth/me', '/openapi.json', '/docs', '/redoc', '/evidence/private', '/internal', '/admin')) {
    $status = Get-CloudflareWebsiteStatusCode -Uri "$base$privatePath"
    if ($status -ne 404) { throw "Private path $privatePath returned $status, expected 404 from the marketing app." }
}

$listeners = Get-CloudflareWebsiteListeners -Port ([int]$config.port)
if ($listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne '127.0.0.1' -or [int]$listeners[0].OwningProcess -ne [int]$state.pid) {
    throw 'The marketing origin is not bound only to 127.0.0.1 or its recorded process.'
}
$process = Get-CloudflareManagedProcess -State $state
if ($null -eq $process) { throw 'The recorded marketing process is not running.' }
$processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)"
$owner = Invoke-CimMethod -InputObject $processInfo -MethodName GetOwner
if ($owner.ReturnValue -ne 0 -or $owner.User -ne 'SYSTEM') { throw 'The marketing Node process is not running as SYSTEM.' }

$leadAcl = Get-Acl -LiteralPath ([string]$config.leadDirectory)
if (-not $leadAcl.AreAccessRulesProtected) { throw 'Lead directory permissions still inherit parent access.' }
$identities = @($leadAcl.Access | ForEach-Object { $_.IdentityReference.Value })
$unexpectedIdentities = @($identities | Where-Object { $_ -notmatch '(?i)(SYSTEM|Administrators)$' })
if ($unexpectedIdentities.Length -gt 0) {
    throw 'Lead directory ACL contains an identity beyond SYSTEM and Administrators.'
}

$task = Get-ScheduledTask -TaskName ([string]$config.taskName) -ErrorAction SilentlyContinue
if ($null -eq $task) { throw 'The Cloudflare website startup task is missing.' }
$taskInfo = Get-ScheduledTaskInfo -TaskName ([string]$config.taskName)
$cloudflared = Get-Service -Name cloudflared -ErrorAction SilentlyContinue
$cloudflaredStatus = if ($null -eq $cloudflared) { 'not installed' } else { "$($cloudflared.Status); start type $($cloudflared.StartType)" }

Write-Host "Marketing pages: PASS; /health: PASS; private-path isolation: PASS."
Write-Host "Release: $($active.releaseId); source: $($active.gitCommit); PID: $($state.pid); owner: SYSTEM."
Write-Host "Origin: 127.0.0.1:$($config.port); task: $($task.State); last task result: $($taskInfo.LastTaskResult)."
Write-Host "Lead ACL: restricted to SYSTEM and Administrators; path: $($config.leadDirectory)."
Write-Host "cloudflared service: $cloudflaredStatus."
