@echo off
setlocal EnableExtensions

set "REPO_ROOT=%~dp0"
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"
set "POWERSHELL_EXE=pwsh.exe"
where pwsh.exe >nul 2>&1
if errorlevel 1 set "POWERSHELL_EXE=powershell.exe"

pushd "%REPO_ROOT%" >nul 2>&1
if errorlevel 1 goto :missing

"%POWERSHELL_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\build-publish-company-mobile.ps1" %*
set "FLEET_EXIT_CODE=%ERRORLEVEL%"
popd
goto :done

:missing
echo Fleet AI Systems could not open its repository folder.
set "FLEET_EXIT_CODE=1"

:done
pause
endlocal & exit /b %FLEET_EXIT_CODE%
