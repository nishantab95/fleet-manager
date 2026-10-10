@echo off
setlocal EnableExtensions

set "REPO_ROOT=%~dp0"
set "POWERSHELL_EXE=pwsh.exe"
where pwsh.exe >nul 2>&1
if errorlevel 1 set "POWERSHELL_EXE=powershell.exe"

"%POWERSHELL_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%scripts\update-owner-web.ps1" %*
exit /b %ERRORLEVEL%
