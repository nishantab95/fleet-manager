[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$processor = Join-Path $repositoryRoot "Process Fleet Manager Pilot Inbox.bat"
$taskName = "Fleet Manager Pilot Publisher"

if (-not (Test-Path -LiteralPath $processor -PathType Leaf)) {
    throw "Pilot inbox processor wrapper was not found: $processor"
}

$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$quotedProcessor = '"' + $processor + '"'
$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument ('/d /c "' + $quotedProcessor + '"') `
    -WorkingDirectory $repositoryRoot
$minuteTrigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 1)
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$principal = New-ScheduledTaskPrincipal `
    -UserId $userId `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger @($minuteTrigger, $logonTrigger) `
    -Principal $principal `
    -Settings $settings `
    -Description "Receives private Tailscale Taildrop pilot release pairs and publishes only fully verified APKs." `
    -Force | Out-Null

Write-Host "Fleet Manager Pilot Publisher scheduled task is installed."
Write-Host "User: $userId"
Write-Host "Repository: $repositoryRoot"
