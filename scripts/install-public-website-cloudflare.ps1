[CmdletBinding()]
param(
    [string]$DeployRoot = 'C:\FleetAISystems\Website',
    [string]$LeadDirectory = 'C:\ProgramData\FleetAISystems\MarketingLeads'
)

$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this Cloudflare website installer from an elevated PowerShell window.'
}

$sourceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$deployFull = [IO.Path]::GetFullPath($DeployRoot)
$leadFull = [IO.Path]::GetFullPath($LeadDirectory)
$sourcePrefix = $sourceRoot.TrimEnd('\') + '\'
if ($deployFull.StartsWith($sourcePrefix, [StringComparison]::OrdinalIgnoreCase) -or
    $leadFull.StartsWith($sourcePrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Website deployment and lead storage must stay outside the repository.'
}
if ($leadFull.StartsWith($deployFull.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Lead storage must remain separate from website releases.'
}

$paths = [pscustomobject]@{
    Root = $deployFull
    Runtime = Join-Path $deployFull 'runtime\cloudflare'
    Logs = Join-Path $deployFull 'logs\cloudflare'
    Releases = Join-Path $deployFull 'releases'
}
foreach ($directory in @($paths.Root, $paths.Runtime, $paths.Logs, $paths.Releases, $leadFull)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}
foreach ($restrictedDirectory in @($paths.Runtime, $paths.Logs)) {
    & icacls.exe $restrictedDirectory /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Unable to restrict directory ACL: $restrictedDirectory" }
}
& icacls.exe $leadFull /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' /T | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Unable to restrict the marketing lead directory ACL.' }

$nodePath = Join-Path $env:ProgramFiles 'nodejs\node.exe'
if (-not (Test-Path -LiteralPath $nodePath -PathType Leaf)) { $nodePath = (Get-Command node.exe -ErrorAction Stop).Source }
$config = [ordered]@{
    sourceRoot = $sourceRoot
    deployRoot = $deployFull
    leadDirectory = $leadFull
    nodePath = [IO.Path]::GetFullPath($nodePath)
    port = 3001
    domain = 'fleetaisystems.com'
    taskName = 'Fleet AI Systems Website (Cloudflare)'
}
$configPath = Join-Path $paths.Runtime 'config.json'
$config | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding utf8

$powerShellPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$startScript = Join-Path $sourceRoot 'scripts\start-public-website-cloudflare.ps1'
$arguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File `"$startScript`" -DeployRoot `"$deployFull`" -AsTask"
$action = New-ScheduledTaskAction -Execute $powerShellPath -Argument $arguments
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
$taskPrincipal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $config.taskName -Action $action -Trigger $trigger -Settings $settings `
    -Principal $taskPrincipal -Description 'Starts only the loopback Fleet AI Systems marketing website.' -Force | Out-Null

$updateScript = Join-Path $sourceRoot 'scripts\update-public-website-cloudflare.ps1'
& $updateScript -DeployRoot $deployFull
if ($LASTEXITCODE -ne 0) { throw 'Initial Cloudflare website release failed.' }
Write-Host "Cloudflare website startup task installed. Origin is 127.0.0.1:3001; no public inbound rule was created."
