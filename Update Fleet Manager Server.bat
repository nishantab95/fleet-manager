@echo off
setlocal EnableExtensions
set "FLEET_UPDATE_SCRIPT=%~f0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$source = [IO.File]::ReadAllText($env:FLEET_UPDATE_SCRIPT); $index = $source.LastIndexOf('# POWERSHELL-BEGIN'); if ($index -lt 0) { throw 'Embedded Fleet updater is missing.' }; & ([ScriptBlock]::Create($source.Substring($index)))"
set "FLEET_EXIT_CODE=%ERRORLEVEL%"
if not defined FLEET_SERVER_NO_PAUSE pause
endlocal & exit /b %FLEET_EXIT_CODE%
# POWERSHELL-BEGIN
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$devRepo = 'D:\NAB\GIT\fleet-manager'
$liveRepo = 'D:\NAB\SERVER-DRYRUN\fleet-manager'
$serverRoot = 'D:\NAB\SERVER-DRYRUN'
$batchName = 'Update Fleet Manager Server.bat'
$liveBatch = Join-Path $liveRepo $batchName
$configFile = Join-Path $serverRoot 'config\.env'
$venvPython = Join-Path $liveRepo 'services\api\.venv\Scripts\python.exe'
$psql = 'D:\NAB\SERVER-STAGING\postgresql-native\server\bin\psql.exe'
$stopScript = Join-Path $serverRoot 'stop-dryrun.ps1'
$startScript = Join-Path $serverRoot 'start-dryrun.ps1'
$powerShell = Join-Path $PSHOME 'powershell.exe'
$previousCommit = $null
$checkoutAttempted = $false
$dependencySyncAttempted = $false
$dependenciesChanged = $false
$batchHash = $null

function Invoke-Git {
    param([string]$Repository, [string[]]$GitArgs)
    # Windows PowerShell promotes native stderr to error records when the
    # global preference is Stop. Git writes normal fetch information there.
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $captured = @(& git -C $Repository @GitArgs 2>&1)
        $gitExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    $stdout = @($captured | Where-Object { $_ -isnot [Management.Automation.ErrorRecord] } | ForEach-Object { [string]$_ })
    $stderr = @($captured | Where-Object { $_ -is [Management.Automation.ErrorRecord] } | ForEach-Object { $_.ToString() })
    if ($gitExitCode -ne 0) {
        $detail = (($stderr + $stdout) -join [Environment]::NewLine).Trim()
        if ([string]::IsNullOrWhiteSpace($detail)) { $detail = 'Git provided no diagnostic output.' }
        throw "GIT_FAILED=$($GitArgs[0]); EXIT_CODE=$gitExitCode; DETAIL=$detail"
    }
    return $stdout
}

function Get-Commit {
    param([string]$Repository)
    $result = @(Invoke-Git $Repository @('rev-parse', '--verify', 'HEAD^{commit}'))
    if ($result.Count -ne 1 -or $result[0] -notmatch '^[0-9a-f]{40}$') { throw 'COMMIT_CHECK=FAIL' }
    return $result[0]
}

function Get-ListenerPids {
    $lines = @(& netstat -ano -p tcp 2>$null)
    if ($LASTEXITCODE -ne 0) { throw 'PORT_8000_CHECK=FAIL' }
    $ids = @(
        foreach ($line in $lines) {
            if ($line -match '^\s*TCP\s+127\.0\.0\.1:8000\s+\S+\s+LISTENING\s+(\d+)\s*$') {
                [int]$Matches[1]
            }
        }
    )
    return @($ids | Sort-Object -Unique)
}

function Assert-EndpointReady {
    $deadline = (Get-Date).AddSeconds(35)
    do {
        try {
            $health = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 3
            $ready = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/ready' -TimeoutSec 3
            if ([int]$health.StatusCode -eq 200 -and [int]$ready.StatusCode -eq 200) {
                Write-Output 'LOCAL_HEALTH=200'
                Write-Output 'LOCAL_READY=200'
                return
            }
        } catch { }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw 'HEALTH_OR_READY_CHECK=FAIL'
}

function Invoke-StopApi {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $stopOutput = @(& $powerShell -NoProfile -ExecutionPolicy Bypass -File $stopScript 2>&1)
        $stopExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($stopExitCode -ne 0) {
        Write-Output 'STOP_SERVER=FAIL'
        if ($stopOutput.Count -gt 0) { Write-Output "STOP_SCRIPT_DETAIL=$($stopOutput[-1])" }
        throw "STOP_SCRIPT_EXIT_CODE=$stopExitCode; live commit unchanged"
    }
    $deadline = (Get-Date).AddSeconds(60)
    while ($true) {
        if (@(Get-ListenerPids).Count -eq 0) {
            Write-Output 'STOP_SERVER=PASS'
            Write-Output 'PORT_8000_RELEASED=YES'
            return
        }
        if ((Get-Date) -ge $deadline) { break }
        Start-Sleep -Milliseconds 500
    }
    Write-Output 'STOP_SERVER=FAIL'
    throw 'PORT_8000_LISTENER_STILL_PRESENT_AFTER_60_SECONDS; live commit unchanged'
}

function Invoke-StartApi {
    if (@(Get-ListenerPids).Count -ne 0) { throw 'START_REFUSED_PORT_8000_OCCUPIED' }
    & $powerShell -NoProfile -ExecutionPolicy Bypass -File $startScript *> $null
    if ($LASTEXITCODE -ne 0) { throw "START_SCRIPT=FAIL; EXIT_CODE=$LASTEXITCODE" }
    Assert-EndpointReady
}

function Set-LiveCommit {
    param([string]$Commit)
    # Preflight requires the batch file's tracked blob to be unchanged across
    # commits, so Git carries this local operator patch through the checkout.
    [void](Invoke-Git $liveRepo @('checkout', '--detach', $Commit))
    if ((Get-FileHash -LiteralPath $liveBatch -Algorithm SHA256).Hash -ne $batchHash) {
        throw 'OPERATOR_BATCH_CHANGED_DURING_CHECKOUT'
    }
    if ((Get-Commit $liveRepo) -ne $Commit) { throw 'LIVE_COMMIT_MISMATCH' }
}

function Invoke-DependencySync {
    if (-not $dependenciesChanged) { return }
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    $uvExecutable = if ($uvCommand) { $uvCommand.Source } else { 'C:\Users\staun\.local\bin\uv.exe' }
    if (-not (Test-Path -LiteralPath $uvExecutable -PathType Leaf)) { throw 'UV_NOT_FOUND' }
    $previousDownloadSetting = [Environment]::GetEnvironmentVariable('UV_PYTHON_DOWNLOADS', 'Process')
    try {
        $env:UV_PYTHON_DOWNLOADS = 'never'
        & $uvExecutable --cache-dir (Join-Path $liveRepo '.uv-cache') sync --project (Join-Path $liveRepo 'services\api') --python $venvPython --locked --all-groups *> $null
        if ($LASTEXITCODE -ne 0) { throw "DEPENDENCY_SYNC=FAIL; EXIT_CODE=$LASTEXITCODE" }
    } finally {
        [Environment]::SetEnvironmentVariable('UV_PYTHON_DOWNLOADS', $previousDownloadSetting, 'Process')
    }
    Write-Output 'DEPENDENCY_SYNC=PASS'
}

try {
    if ([IO.Path]::GetFullPath($env:FLEET_UPDATE_SCRIPT) -ine $liveBatch) {
        throw 'RUN_ONLY_THE_LIVE_UPDATE_BATCH'
    }
    foreach ($required in @($configFile, $venvPython, $psql, $stopScript, $startScript)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "REQUIRED_FILE_MISSING=$required" }
    }
    $batchHash = (Get-FileHash -LiteralPath $liveBatch -Algorithm SHA256).Hash
    $configHash = (Get-FileHash -LiteralPath $configFile -Algorithm SHA256).Hash
    $devStatus = @(Invoke-Git $devRepo @('status', '--porcelain=v1', '--untracked-files=all', '--ignore-submodules=none'))
    if ($devStatus.Count -ne 0) { throw 'DEVELOPMENT_REPOSITORY_NOT_CLEAN' }
    $sourceCommit = Get-Commit $devRepo
    $previousCommit = Get-Commit $liveRepo
    $liveStatus = @(Invoke-Git $liveRepo @('status', '--porcelain=v1', '--untracked-files=all', '--ignore-submodules=none'))
    foreach ($statusLine in $liveStatus) {
        if ($statusLine -notin @(" M $batchName", (' M "' + $batchName + '"'))) { throw 'LIVE_REPOSITORY_HAS_UNEXPECTED_CHANGES' }
    }
    Write-Output "SOURCE_COMMIT=$sourceCommit"
    Write-Output "PREVIOUS_LIVE_COMMIT=$previousCommit"

    # Read the committed source migration head without running env.py or a migration.
    $devApi = Join-Path $devRepo 'services\api'
    $previousBytecodeSetting = [Environment]::GetEnvironmentVariable('PYTHONDONTWRITEBYTECODE', 'Process')
    try {
        $env:PYTHONDONTWRITEBYTECODE = '1'
        Push-Location $devApi
        try {
            $headsOutput = @(& $venvPython -m alembic -c (Join-Path $devApi 'alembic.ini') heads 2>$null)
            if ($LASTEXITCODE -ne 0) { throw 'SOURCE_ALEMBIC_HEAD_CHECK=FAIL' }
        } finally { Pop-Location }
    } finally {
        [Environment]::SetEnvironmentVariable('PYTHONDONTWRITEBYTECODE', $previousBytecodeSetting, 'Process')
    }
    $heads = @($headsOutput | ForEach-Object { if ($_ -match '^([A-Za-z0-9_]+)\s+\(head\)') { $Matches[1] } })
    if ($heads.Count -ne 1 -or $headsOutput.Count -ne 1) { throw 'SOURCE_ALEMBIC_HEAD_COUNT_INVALID' }
    $sourceRevision = $heads[0]

    $databaseUrlLine = @([IO.File]::ReadAllLines($configFile) | Where-Object { $_ -match '^\s*FLEET_DATABASE_URL=' })
    if ($databaseUrlLine.Count -ne 1) { throw 'DATABASE_URL_CONFIG_INVALID' }
    $databaseUrl = [Uri](($databaseUrlLine[0] -split '=', 2)[1].Trim())
    if ($databaseUrl.Host -ne '127.0.0.1' -or $databaseUrl.Port -ne 5432 -or
        $databaseUrl.AbsolutePath.Trim('/') -ne 'fleet_server_dryrun') {
        throw 'DATABASE_TARGET_NOT_LOCAL_DRYRUN'
    }
    $userInfo = $databaseUrl.UserInfo.Split(':', 2)
    if ($userInfo.Count -ne 2) { throw 'DATABASE_CREDENTIAL_CONFIG_INVALID' }
    $databaseUser = [Uri]::UnescapeDataString($userInfo[0])
    $previousPgPassword = [Environment]::GetEnvironmentVariable('PGPASSWORD', 'Process')
    try {
        $env:PGPASSWORD = [Uri]::UnescapeDataString($userInfo[1])
        $revisionRows = @(& $psql --host 127.0.0.1 --port 5432 --username $databaseUser --dbname fleet_server_dryrun --no-psqlrc --tuples-only --no-align --set ON_ERROR_STOP=1 --command 'SELECT version_num FROM public.alembic_version;' 2>$null)
        if ($LASTEXITCODE -ne 0) { throw 'LIVE_ALEMBIC_QUERY=FAIL' }
    } finally {
        [Environment]::SetEnvironmentVariable('PGPASSWORD', $previousPgPassword, 'Process')
    }
    if ($revisionRows.Count -ne 1 -or [string]::IsNullOrWhiteSpace($revisionRows[0])) {
        throw 'LIVE_ALEMBIC_REVISION_COUNT_INVALID'
    }
    $liveRevision = $revisionRows[0].Trim()
    $migrationFilesChanged = $false
    if ($sourceCommit -ne $previousCommit) {
        [void](Invoke-Git $liveRepo @('fetch', '--no-tags', '--no-recurse-submodules', $devRepo, 'HEAD'))
        $fetched = @(Invoke-Git $liveRepo @('rev-parse', '--verify', 'FETCH_HEAD^{commit}'))
        if ($fetched.Count -ne 1 -or $fetched[0] -ne $sourceCommit) { throw 'FETCHED_COMMIT_MISMATCH' }
        [void](Invoke-Git $liveRepo @('cat-file', '-e', "${sourceCommit}^{commit}"))
        & git -C $liveRepo diff --quiet $previousCommit $sourceCommit -- $batchName 2>$null
        if ($LASTEXITCODE -notin @(0, 1)) { throw 'UPDATE_BATCH_DIFF_CHECK=FAIL' }
        if ($LASTEXITCODE -eq 1) { throw 'UPDATE_BATCH_CHANGED_IN_SOURCE; manual review required' }
        & git -C $liveRepo diff --quiet $previousCommit $sourceCommit -- services/api/migrations 2>$null
        if ($LASTEXITCODE -notin @(0, 1)) { throw 'MIGRATION_DIFF_CHECK=FAIL' }
        $migrationFilesChanged = $LASTEXITCODE -eq 1
        & git -C $liveRepo diff --quiet $previousCommit $sourceCommit -- services/api/pyproject.toml services/api/uv.lock 2>$null
        if ($LASTEXITCODE -notin @(0, 1)) { throw 'DEPENDENCY_DIFF_CHECK=FAIL' }
        $dependenciesChanged = $LASTEXITCODE -eq 1
    }
    if ($sourceRevision -ne $liveRevision -or $migrationFilesChanged) {
        Write-Output 'MIGRATION_REQUIRED=YES'
        throw "MIGRATION_PRECHECK_STOP; SOURCE_REVISION=$sourceRevision; LIVE_REVISION=$liveRevision"
    }
    Write-Output 'MIGRATION_REQUIRED=NO'
    if ((Get-Commit $devRepo) -ne $sourceCommit -or
        @(Invoke-Git $devRepo @('status', '--porcelain=v1', '--untracked-files=all', '--ignore-submodules=none')).Count -ne 0) {
        throw 'DEVELOPMENT_SOURCE_CHANGED_DURING_PREFLIGHT'
    }
    if ($sourceCommit -eq $previousCommit) {
        Assert-EndpointReady
        Write-Output 'ALREADY_DEPLOYED=YES'
        exit 0
    }
    if ($dependenciesChanged -and -not (Get-Command uv -ErrorAction SilentlyContinue) -and
        -not (Test-Path -LiteralPath 'C:\Users\staun\.local\bin\uv.exe' -PathType Leaf)) {
        throw 'UV_REQUIRED_FOR_DEPENDENCY_CHANGE'
    }
    if ((Get-FileHash -LiteralPath $configFile -Algorithm SHA256).Hash -ne $configHash) {
        throw 'SERVER_CONFIG_CHANGED_DURING_PREFLIGHT'
    }
    Assert-EndpointReady
    $rollbackRef = 'refs/fleet-manager/rollback/' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + $previousCommit.Substring(0, 12)
    [void](Invoke-Git $liveRepo @('update-ref', $rollbackRef, $previousCommit))
    Write-Output "ROLLBACK_REF=$rollbackRef"

    Invoke-StopApi
    $checkoutAttempted = $true
    Set-LiveCommit $sourceCommit
    if ($dependenciesChanged) { $dependencySyncAttempted = $true; Invoke-DependencySync }
    if ((Get-FileHash -LiteralPath $configFile -Algorithm SHA256).Hash -ne $configHash) {
        throw 'SERVER_CONFIG_CHANGED_DURING_DEPLOYMENT'
    }
    Invoke-StartApi
    Write-Output "DEPLOYED_COMMIT=$(Get-Commit $liveRepo)"
    Write-Output 'UPDATE_SERVER=PASS'
    exit 0
} catch {
    Write-Output "UPDATE_SERVER=FAIL; REASON=$($_.Exception.Message)"
    if ($previousCommit) {
        try {
            if ($checkoutAttempted) {
                if (@(Get-ListenerPids).Count -ne 0) {
                    Invoke-StopApi
                } else {
                    & $powerShell -NoProfile -ExecutionPolicy Bypass -File $stopScript *> $null
                    if ($LASTEXITCODE -ne 0) { throw "ROLLBACK_STOP_SCRIPT=FAIL; EXIT_CODE=$LASTEXITCODE" }
                }
                Set-LiveCommit $previousCommit
                if ($dependencySyncAttempted) { Invoke-DependencySync }
            }
            if (@(Get-ListenerPids).Count -eq 0) { Invoke-StartApi }
            else { Assert-EndpointReady }
            if ((Get-Commit $liveRepo) -ne $previousCommit) { throw 'ROLLBACK_COMMIT_MISMATCH' }
            if ((Get-FileHash -LiteralPath $configFile -Algorithm SHA256).Hash -ne $configHash) {
                throw 'SERVER_CONFIG_CHANGED_DURING_ROLLBACK'
            }
            Write-Output 'ROLLBACK=PASS'
        } catch {
            Write-Output "ROLLBACK=FAIL; REASON=$($_.Exception.Message)"
        }
    }
    exit 1
}
