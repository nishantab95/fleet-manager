Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-CloudflareWebsitePaths {
    param([Parameter(Mandatory)][string]$DeployRoot)
    [pscustomobject]@{
        Root = [IO.Path]::GetFullPath($DeployRoot)
        Config = Join-Path $DeployRoot 'runtime\cloudflare\config.json'
        Active = Join-Path $DeployRoot 'runtime\cloudflare\active-release.json'
        Previous = Join-Path $DeployRoot 'runtime\cloudflare\previous-release.json'
        State = Join-Path $DeployRoot 'runtime\cloudflare\website-state.json'
        Logs = Join-Path $DeployRoot 'logs\cloudflare'
        Temp = Join-Path $DeployRoot 'runtime\cloudflare\temp'
    }
}

function Get-CloudflareWebsiteConfig {
    param([Parameter(Mandatory)][string]$DeployRoot)
    $paths = Get-CloudflareWebsitePaths -DeployRoot $DeployRoot
    if (-not (Test-Path -LiteralPath $paths.Config -PathType Leaf)) {
        throw "Cloudflare website configuration is missing: $($paths.Config). Run install-public-website-cloudflare.ps1 first."
    }
    Get-Content -LiteralPath $paths.Config -Raw | ConvertFrom-Json
}

function Get-CloudflareWebsiteActiveRelease {
    param([Parameter(Mandatory)][string]$DeployRoot)
    $path = (Get-CloudflareWebsitePaths -DeployRoot $DeployRoot).Active
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
    Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
}

function Get-CloudflareWebsiteState {
    param([Parameter(Mandatory)][string]$DeployRoot)
    $path = (Get-CloudflareWebsitePaths -DeployRoot $DeployRoot).State
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
    Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
}

function Get-CloudflareWebsitePreviousRelease {
    param([Parameter(Mandatory)][string]$DeployRoot)
    $path = (Get-CloudflareWebsitePaths -DeployRoot $DeployRoot).Previous
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
    Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
}

function Save-CloudflareWebsiteJson {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][object]$Value
    )
    $directory = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $temporary = "$Path.$([Guid]::NewGuid().ToString('N')).tmp"
    $Value | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $temporary -Encoding utf8
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Test-CloudflareWebsiteHealth {
    param([int]$Port = 3001, [int]$Attempts = 1)
    $expected = '{"status":"ok","service":"fleet-ai-systems-marketing"}'
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3
            if ([int]$response.StatusCode -eq 200 -and $response.Content.Trim() -ceq $expected) { return $true }
        } catch {
            if ($attempt -lt $Attempts) { Start-Sleep -Seconds 1 }
        }
    }
    return $false
}

function Get-CloudflareWebsiteListeners {
    param([int]$Port = 3001)
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    return ,$listeners
}

function Get-CloudflareManagedProcess {
    param([Parameter(Mandatory)][object]$State)
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$State.pid)" -ErrorAction SilentlyContinue
    if ($null -eq $processInfo) { return $null }
    if ($processInfo.Name -ne 'node.exe') { throw "Refusing to act on PID $($State.pid): it is not node.exe." }
    if ([string]$processInfo.CommandLine -notmatch '(?i)\bserver\.js(?:\s|$)') {
        throw "Refusing to act on PID $($State.pid): its command is not the standalone server.js process."
    }
    $process = Get-Process -Id ([int]$State.pid) -ErrorAction SilentlyContinue
    if ($null -eq $process) { return $null }
    $expectedStart = [DateTimeOffset]::Parse([string]$State.startedAt).UtcDateTime
    if ([Math]::Abs(($process.StartTime.ToUniversalTime() - $expectedStart).TotalSeconds) -gt 5) {
        throw "Refusing to act on PID $($State.pid): its start time does not match recorded website state."
    }
    $listeners = @(Get-NetTCPConnection -State Listen -OwningProcess $process.Id -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        if ([int]$listener.LocalPort -ne [int]$State.port -or $listener.LocalAddress -ne '127.0.0.1') {
            throw "Refusing to act on PID $($State.pid): it has an unexpected listening address or port."
        }
    }
    $process
}

function Stop-CloudflareManagedProcess {
    param([AllowNull()][object]$State)
    if ($null -eq $State -or $null -eq $State.pid) { return }
    $process = Get-CloudflareManagedProcess -State $State
    if ($null -eq $process) { return }
    Stop-Process -Id $process.Id -Force
    Wait-Process -Id $process.Id -Timeout 10 -ErrorAction SilentlyContinue
}

function Start-CloudflareWebsiteRelease {
    param(
        [Parameter(Mandatory)][object]$Config,
        [Parameter(Mandatory)][object]$Release,
        [Parameter(Mandatory)][string]$DeployRoot
    )
    $paths = Get-CloudflareWebsitePaths -DeployRoot $DeployRoot
    $releaseRoot = [IO.Path]::GetFullPath((Join-Path $paths.Root 'releases'))
    $releasePath = [IO.Path]::GetFullPath([string]$Release.releasePath)
    if (-not $releasePath.StartsWith($releaseRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Release path is outside the website releases directory: $releasePath"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $releasePath 'server.js') -PathType Leaf)) {
        throw "Standalone release is missing server.js: $releasePath"
    }

    $state = Get-CloudflareWebsiteState -DeployRoot $DeployRoot
    $listeners = Get-CloudflareWebsiteListeners -Port ([int]$Config.port)
    if ($listeners.Count -gt 0) {
        if ($listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne '127.0.0.1' -or
            $null -eq $state -or [int]$state.pid -ne [int]$listeners[0].OwningProcess) {
            throw "Port $($Config.port) is occupied by a process not recorded as this marketing website; refusing to stop it."
        }
        $managed = Get-CloudflareManagedProcess -State $state
        if ($null -ne $managed -and [string]$state.releasePath -eq $releasePath -and
            (Test-CloudflareWebsiteHealth -Port ([int]$Config.port))) { return $state }
        throw "Port $($Config.port) is occupied by a recorded but unhealthy website process."
    }
    if ($null -ne $state) {
        $managed = Get-CloudflareManagedProcess -State $state
        if ($null -ne $managed) { throw 'A recorded website process is alive without its expected listener; refusing to start a duplicate.' }
    }

    New-Item -ItemType Directory -Path $paths.Logs,$paths.Temp -Force | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $logOut = Join-Path $paths.Logs "website-$stamp.out.log"
    $logErr = Join-Path $paths.Logs "website-$stamp.err.log"

    # The website only needs a small runtime environment. This prevents API or Firebase
    # credentials configured for other Windows services from leaking into this process.
    $windowsRoot = [Environment]::GetEnvironmentVariable('SystemRoot', 'Machine')
    if ([string]::IsNullOrWhiteSpace($windowsRoot)) { $windowsRoot = 'C:\Windows' }
    $systemDrive = [IO.Path]::GetPathRoot($windowsRoot).TrimEnd('\')
    $pathValue = "$([IO.Path]::GetDirectoryName([string]$Config.nodePath));$windowsRoot\System32;$windowsRoot"
    $environment = @{
        SystemRoot = $windowsRoot
        WINDIR = $windowsRoot
        SystemDrive = $systemDrive
        PATH = $pathValue
        PATHEXT = '.COM;.EXE;.BAT;.CMD'
        ComSpec = Join-Path $windowsRoot 'System32\cmd.exe'
        TEMP = $paths.Temp
        TMP = $paths.Temp
        NODE_ENV = 'production'
        HOSTNAME = '127.0.0.1'
        PORT = [string]$Config.port
        FLEET_MARKETING_LEAD_DIR = [string]$Config.leadDirectory
    }
    foreach ($entry in [Environment]::GetEnvironmentVariables('Process').GetEnumerator()) {
        [Environment]::SetEnvironmentVariable([string]$entry.Key, $null, 'Process')
    }
    foreach ($entry in $environment.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable([string]$entry.Key, [string]$entry.Value, 'Process')
    }

    $process = Start-Process -FilePath ([string]$Config.nodePath) -ArgumentList 'server.js' `
        -WorkingDirectory $releasePath -WindowStyle Hidden -RedirectStandardOutput $logOut `
        -RedirectStandardError $logErr -PassThru
    $state = [ordered]@{
        releaseId = [string]$Release.releaseId
        releasePath = $releasePath
        gitCommit = [string]$Release.gitCommit
        port = [int]$Config.port
        pid = [int]$process.Id
        startedAt = $process.StartTime.ToUniversalTime().ToString('o')
        deployedAt = [DateTimeOffset]::UtcNow.ToString('o')
    }
    Save-CloudflareWebsiteJson -Path $paths.State -Value $state
    if (-not (Test-CloudflareWebsiteHealth -Port ([int]$Config.port) -Attempts 30)) {
        Stop-CloudflareManagedProcess -State $state
        Remove-Item -LiteralPath $paths.State -Force -ErrorAction SilentlyContinue
        throw "Standalone website failed its health gate on 127.0.0.1:$($Config.port)."
    }
    $state
}
