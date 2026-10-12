[CmdletBinding()]
param(
    [string]$Path = (Join-Path $env:USERPROFILE ".fleetaisystems\pilot-publisher.token")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$destination = [IO.Path]::GetFullPath($Path)
if (Test-Path -LiteralPath $destination) {
    throw "Refusing to overwrite an existing publisher credential: $destination"
}
$parent = Split-Path -Parent $destination
New-Item -ItemType Directory -Force -Path $parent | Out-Null

$bytes = [byte[]]::new(48)
[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$token = [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
[IO.File]::WriteAllText($destination, $token + "`n", [Text.UTF8Encoding]::new($false))

if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $acl = [Security.AccessControl.FileSecurity]::new()
    $acl.SetAccessRuleProtection($true, $false)
    $acl.AddAccessRule(
        [Security.AccessControl.FileSystemAccessRule]::new(
            $identity,
            [Security.AccessControl.FileSystemRights]::FullControl,
            [Security.AccessControl.AccessControlType]::Allow
        )
    )
    $acl.AddAccessRule(
        [Security.AccessControl.FileSystemAccessRule]::new(
            "NT AUTHORITY\SYSTEM",
            [Security.AccessControl.FileSystemRights]::FullControl,
            [Security.AccessControl.AccessControlType]::Allow
        )
    )
    try {
        Set-Acl -LiteralPath $destination -AclObject $acl
    }
    catch {
        Remove-Item -LiteralPath $destination -Force -ErrorAction SilentlyContinue
        throw
    }
}

Write-Output "PUBLISHER_CREDENTIAL_CREATED=$destination"
Write-Output "PUBLISHER_CREDENTIAL_SECRET_PRINTED=NO"
