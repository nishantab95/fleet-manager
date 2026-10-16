<#
Manual, one-time cleanup of four independently audited generated artifacts.
Default is report-only. No startup/CI/release command invokes this script.
Run while development/build clients are closed; this is not a concurrent janitor.
Independently verify any remaining Gradle daemon is idle before applying; this
tool detects clients and exclusive file access, not a daemon's internal job state.
Unknown content, links, locked files, Git failures and process-query errors refuse cleanup.
#>
[CmdletBinding()]
param([switch]$Apply)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-FleetCleanupAllowlist {
    @(
        '.tmp/fleet-api-ci.tar'
        'apps/web/.next/dev/cache'
        'apps/marketing/.next/dev/cache'
        'apps/mobile/build/app/intermediates/merged_native_libs/productionDebug'
    )
}

function Assert-FleetNoReparseAncestor([string]$Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Reparse point refused: $current"
            }
        }
        $parent = [IO.Directory]::GetParent($current)
        $current = if ($parent) { $parent.FullName } else { $null }
    }
}

function Get-FleetCleanupRoot {
    $root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
    Assert-FleetNoReparseAncestor $root
    $gitRoot = & git -C $root rev-parse --show-toplevel
    if ($LASTEXITCODE -ne 0 -or @($gitRoot).Count -ne 1) { throw 'Cannot verify Git checkout' }
    if (-not [string]::Equals($root, [IO.Path]::GetFullPath($gitRoot), 'OrdinalIgnoreCase')) {
        throw 'Script location is not the verified Git root'
    }
    return $root
}

function Resolve-FleetCleanupTarget([string]$Root, [string]$Relative) {
    if ($Relative -cnotin (Get-FleetCleanupAllowlist)) { throw 'Target is not allowlisted' }
    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    $target = [IO.Path]::GetFullPath((Join-Path $rootFull $Relative))
    if (-not $target.StartsWith($rootFull + [IO.Path]::DirectorySeparatorChar, 'OrdinalIgnoreCase')) {
        throw 'Target escapes checkout'
    }
    Assert-FleetNoReparseAncestor $target
    return $target
}

function Assert-FleetGeneratedEntry([string]$Relative, [string]$Within, [bool]$Directory) {
    $parts = $Within -split '[/\\]'
    foreach ($part in $parts) {
        if ($part -match '^(\.git|\.runtime|node_modules|\.venv|evidence|backups|uploads|postgres|minio)$' -or
            $part -match '^\.env' -or $part -match '^(key|local)\.properties$' -or
            $part -match '\.(jks|keystore|pem|p12|pfx|crt|cer|key|apk|aab|db|sqlite3?|sql|dump|bak)$') {
            throw "Protected name refused: $Within"
        }
    }
    if ($Relative -eq '.tmp/fleet-api-ci.tar') {
        if ($Directory -or $Within) { throw 'Expected the audited tar file only' }
        return
    }
    if (-not $Within) {
        if (-not $Directory) { throw 'Expected generated directory' }
        return
    }
    $name = $Within.Replace('\', '/')
    if ($Relative -like 'apps/*/.next/dev/cache') {
        $valid = if ($Directory) {
            $name -match '^(images(/[A-Za-z0-9_-]+)?|turbopack(/v[0-9.]+-[a-f0-9]+)?)$'
        } else {
            $name -match '^(\.rscinfo|next-devtools-config\.json)$' -or
            $name -match '^turbopack/v[0-9.]+-[a-f0-9]+/(\d+\.(sst|meta|del)|CURRENT|LOG)$' -or
            $name -match '^images/[A-Za-z0-9_-]+/\d+\.\d+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.webp$'
        }
    } else {
        $valid = if ($Directory) {
            $name -match '^mergeProductionDebugNativeLibs(/out(/lib(/(arm64-v8a|armeabi-v7a|x86|x86_64))?)?)?$'
        } else {
            $name -match '^mergeProductionDebugNativeLibs/out/lib/(arm64-v8a|armeabi-v7a|x86|x86_64)/lib[A-Za-z0-9_]+\.so$'
        }
    }
    if (-not $valid) { throw "Unrecognised generated content: $Within" }
}

function Get-FleetTargetInventory([string]$Root, [string]$Relative) {
    $target = Resolve-FleetCleanupTarget $Root $Relative
    $files = [Collections.Generic.List[object]]::new()
    $directories = [Collections.Generic.List[string]]::new()
    if (-not (Test-Path -LiteralPath $target)) {
        return [pscustomobject]@{ Path = $target; Relative = $Relative; Files = @(); Directories = @(); Bytes = [long]0; Missing = $true }
    }
    $pending = [Collections.Generic.Stack[string]]::new()
    $pending.Push($target)
    while ($pending.Count) {
        $path = $pending.Pop()
        $item = Get-Item -LiteralPath $path -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse point refused: $path" }
        $within = if ($path -eq $target) { '' } else { $path.Substring($target.Length + 1) }
        Assert-FleetGeneratedEntry $Relative $within $item.PSIsContainer
        if ($item.PSIsContainer) {
            $directories.Add($path)
            foreach ($child in Get-ChildItem -LiteralPath $path -Force) { $pending.Push($child.FullName) }
        } else {
            $files.Add([pscustomobject]@{ Path = $path; Bytes = [long]$item.Length; Ticks = $item.LastWriteTimeUtc.Ticks })
        }
    }
    $bytes = [long]0
    foreach ($file in $files) { $bytes += $file.Bytes }
    return [pscustomobject]@{ Path = $target; Relative = $Relative; Files = $files.ToArray(); Directories = $directories.ToArray(); Bytes = $bytes; Missing = $false }
}

function Assert-FleetNoTrackedTarget([string]$Root, [string]$Relative) {
    $tracked = & git -C $Root ls-files -- $Relative
    if ($LASTEXITCODE -ne 0) { throw 'Git tracked-file verification failed' }
    if ($tracked) { throw "Tracked files exist under allowlisted target: $Relative" }
}

function Test-FleetBuildClient([object]$Process) {
    if ($Process.ProcessId -eq $PID -or $Process.Name -notmatch '^(node|dart|flutter|java|gradle)(\.exe)?$') { return $false }
    if (-not $Process.CommandLine) { return $true }
    # A Gradle daemon process is not itself a client; its idle state must be
    # independently verified. Clients/workers and locked target files are refused.
    if ($Process.CommandLine -match 'org\.gradle\.launcher\.daemon\.bootstrap\.GradleDaemon') { return $false }
    return $Process.CommandLine -match '(next[\\/]|next-server|next dev|next build|flutter_tools|gradle)'
}

function Assert-FleetNoBuildClients {
    $clients = @(Get-CimInstance Win32_Process | Where-Object { Test-FleetBuildClient $_ })
    if ($clients.Count) {
        $ids = ($clients | ForEach-Object { "$($_.Name):$($_.ProcessId)" }) -join ', '
        throw "Close build/development clients before cleanup (no processes were stopped): $ids"
    }
}

function Initialize-FleetHandleCheck {
    if ('FleetCleanupHandle' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class FleetCleanupHandle {
    [StructLayout(LayoutKind.Sequential)] private struct Info {
        public uint Attributes;
        public System.Runtime.InteropServices.ComTypes.FILETIME Creation, Access, Write;
        public uint Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow;
    }
    [DllImport("kernel32.dll", SetLastError=true)]
    private static extern bool GetFileInformationByHandle(SafeFileHandle handle, out Info info);
    public static uint Links(SafeFileHandle handle) {
        Info info;
        if (!GetFileInformationByHandle(handle, out info)) throw new Win32Exception();
        return info.Links;
    }
}
'@
}

function Assert-FleetExclusiveFiles([object[]]$Inventories) {
    Initialize-FleetHandleCheck
    $handles = [Collections.Generic.List[IO.FileStream]]::new()
    try {
        foreach ($inventory in $Inventories) {
            foreach ($file in $inventory.Files) {
                Assert-FleetNoReparseAncestor $file.Path
                $stream = [IO.File]::Open($file.Path, 'Open', 'Read', 'None')
                $handles.Add($stream)
                if ($stream.Length -ne $file.Bytes -or (Get-Item -LiteralPath $file.Path -Force).LastWriteTimeUtc.Ticks -ne $file.Ticks) {
                    throw "File changed during inspection: $($file.Path)"
                }
                if ([FleetCleanupHandle]::Links($stream.SafeFileHandle) -ne 1) { throw "Hardlinked file refused: $($file.Path)" }
                if ($inventory.Relative -eq '.tmp/fleet-api-ci.tar') {
                    $sha = [Security.Cryptography.SHA256]::Create()
                    try { $hash = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
                    finally { $sha.Dispose() }
                    if ($stream.Length -ne 202826240 -or $hash -ne '807adb24f88192e944e3eabd9560a391f23b81ef8cebce254058946a35bcba3b') {
                        throw 'Tar differs from the independently audited disposable export'
                    }
                }
            }
        }
    } finally {
        foreach ($handle in $handles) { $handle.Dispose() }
    }
}

function Remove-FleetVerifiedInventory([object]$Inventory) {
    # Never recursively remove: unexpected newly created content must survive.
    foreach ($file in $Inventory.Files) {
        Assert-FleetNoReparseAncestor $file.Path
        $current = Get-Item -LiteralPath $file.Path -Force
        if ($current.PSIsContainer -or $current.Length -ne $file.Bytes -or $current.LastWriteTimeUtc.Ticks -ne $file.Ticks) {
            throw "File changed after inspection: $($file.Path)"
        }
        Remove-Item -LiteralPath $file.Path -Force -ErrorAction Stop
        Write-Output "REMOVED_FILE logical_bytes=$($file.Bytes) path=$($file.Path)"
    }
    foreach ($directory in ($Inventory.Directories | Sort-Object Length -Descending)) {
        Assert-FleetNoReparseAncestor $directory
        if (@(Get-ChildItem -LiteralPath $directory -Force).Count) { throw "Directory changed after inspection: $directory" }
        # Remove-Item can prompt to recurse if a child races the empty check.
        # Directory.Delete(false) guarantees refusal instead of recursion.
        [IO.Directory]::Delete($directory, $false)
    }
}

function Invoke-FleetGeneratedCleanup([switch]$Apply) {
    $root = Get-FleetCleanupRoot
    $inventories = @(foreach ($relative in Get-FleetCleanupAllowlist) {
        Assert-FleetNoTrackedTarget $root $relative
        Get-FleetTargetInventory $root $relative
    })
    foreach ($inventory in $inventories) {
        Write-Output "CANDIDATE path=$($inventory.Path) files=$($inventory.Files.Count) logical_bytes=$($inventory.Bytes) missing=$($inventory.Missing)"
    }
    Assert-FleetNoBuildClients
    Assert-FleetExclusiveFiles $inventories
    if (-not $Apply) { Write-Output 'REPORT_ONLY: nothing removed. Explicit -Apply is required.'; return }
    # Re-inventory the whole allowlist immediately before any removal.
    foreach ($inventory in $inventories) {
        $fresh = Get-FleetTargetInventory $root $inventory.Relative
        if (($fresh | ConvertTo-Json -Depth 5 -Compress) -ne ($inventory | ConvertTo-Json -Depth 5 -Compress)) {
            throw "Target changed after inspection: $($inventory.Path)"
        }
        Assert-FleetNoTrackedTarget $root $inventory.Relative
    }
    Assert-FleetNoBuildClients
    Assert-FleetExclusiveFiles $inventories
    $removed = [long]0
    foreach ($inventory in $inventories) {
        Remove-FleetVerifiedInventory $inventory
        $removed += $inventory.Bytes
    }
    Write-Output "COMPLETE removed_logical_bytes=$removed; allocated/reclaimable bytes require the independent before/after disk audit."
}

if ($MyInvocation.InvocationName -ne '.') { Invoke-FleetGeneratedCleanup -Apply:$Apply }
