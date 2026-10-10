[CmdletBinding()]
param(
    [string]$DeployRoot = 'C:\FleetAISystems\Website',
    [string]$Domain = 'fleetaisystems.com',
    [Parameter(Mandatory)][string]$TlsEmail,
    [string]$CaddyPath = 'C:\Caddy\caddy.exe',
    [string]$LeadDirectory = 'C:\ProgramData\FleetAISystems\MarketingLeads'
)

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this install helper from an elevated PowerShell window.'
}
if ($Domain -notmatch '^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$') {
    throw 'Domain must be a lowercase DNS hostname.'
}
if ($TlsEmail -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') {
    throw 'TlsEmail must be a single valid email address.'
}
if (-not (Test-Path -LiteralPath $CaddyPath -PathType Leaf)) { throw "Caddy was not found at $CaddyPath" }
$sourceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$deployFull = [IO.Path]::GetFullPath($DeployRoot)
$leadFull = [IO.Path]::GetFullPath($LeadDirectory)
$sourcePrefix = $sourceRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$deployPrefix = $deployFull.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if ($deployFull.Equals($sourceRoot, [StringComparison]::OrdinalIgnoreCase) -or $deployFull.StartsWith($sourcePrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'The deployment root must be outside the repository.'
}
if ($leadFull.Equals($sourceRoot, [StringComparison]::OrdinalIgnoreCase) -or $leadFull.StartsWith($sourcePrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Lead storage must be outside the repository.'
}
if ($leadFull.Equals($deployFull, [StringComparison]::OrdinalIgnoreCase) -or $leadFull.StartsWith($deployPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Lead storage must be separate from the website release directory.'
}

foreach ($directory in @($deployFull, (Join-Path $deployFull 'releases'), (Join-Path $deployFull 'runtime'), (Join-Path $deployFull 'logs'), $leadFull)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}
& icacls.exe $leadFull /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F'
if ($LASTEXITCODE -ne 0) { throw 'Unable to restrict the lead-directory ACL.' }

$nodePath = (Get-Command node.exe -ErrorAction Stop).Source
$caddyConfig = Join-Path $deployFull 'Caddyfile'
$upstream = (Join-Path $deployFull 'runtime\upstream.caddy').Replace('\', '/')
$accessLog = (Join-Path $deployFull 'logs\access.json').Replace('\', '/')
$template = Get-Content -LiteralPath (Join-Path $sourceRoot 'infra\caddy\Caddyfile.marketing.example') -Raw
$template.Replace('__TLS_EMAIL__', $TlsEmail).Replace('__DOMAIN__', $Domain).Replace('__UPSTREAM_INCLUDE__', $upstream).Replace('__ACCESS_LOG__', $accessLog) | Set-Content -LiteralPath $caddyConfig -Encoding utf8

$config = [ordered]@{
    sourceRoot = $sourceRoot
    deployRoot = $deployFull
    domain = $Domain
    leadDirectory = $leadFull
    nodePath = $nodePath
    caddyPath = [IO.Path]::GetFullPath($CaddyPath)
    caddyConfig = $caddyConfig
}
$config | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $deployFull 'website-config.json') -Encoding utf8

& (Join-Path $PSScriptRoot 'update-public-website.ps1') -DeployRoot $deployFull -SkipProxyReload
if ($LASTEXITCODE -ne 0) { throw 'Initial website release failed.' }
& $CaddyPath validate --config $caddyConfig --adapter caddyfile
if ($LASTEXITCODE -ne 0) { throw 'Caddy configuration validation failed.' }

$service = Get-Service -Name caddy -ErrorAction SilentlyContinue
if ($null -eq $service) {
    & sc.exe create caddy start= auto binPath= "`"$CaddyPath`" run --config `"$caddyConfig`" --adapter caddyfile"
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create the Caddy Windows service.' }
}
& sc.exe failure caddy reset= 86400 actions= restart/5000/restart/15000/restart/30000 | Out-Null

$powerShellPath = (Get-Command powershell.exe -ErrorAction Stop).Source
$taskCommand = "`"$powerShellPath`" -NoLogo -NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $PSScriptRoot 'start-public-website.ps1')`" -DeployRoot `"$deployFull`""
& schtasks.exe /Create /TN 'Fleet AI Systems Website' /SC ONSTART /RU SYSTEM /RL HIGHEST /TR $taskCommand /F
if ($LASTEXITCODE -ne 0) { throw 'Unable to create the website startup task.' }
& (Join-Path $PSScriptRoot 'start-public-website.ps1') -DeployRoot $deployFull
Write-Host 'Local website runtime installed. DNS, router, CGNAT, and firewall configuration remain manual human actions.'
