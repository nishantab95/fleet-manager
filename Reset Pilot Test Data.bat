@echo off
setlocal EnableExtensions

set "REPO_ROOT=%~dp0"
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"

set "UV_EXE="
for /f "delims=" %%I in ('where uv 2^>nul') do if not defined UV_EXE set "UV_EXE=%%I"
if not defined UV_EXE if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV_EXE=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV_EXE if exist "%LOCALAPPDATA%\uv\uv.exe" set "UV_EXE=%LOCALAPPDATA%\uv\uv.exe"
if not defined UV_EXE if exist "%USERPROFILE%\.cargo\bin\uv.exe" set "UV_EXE=%USERPROFILE%\.cargo\bin\uv.exe"
if not defined UV_EXE if exist "%USERPROFILE%\scoop\shims\uv.exe" set "UV_EXE=%USERPROFILE%\scoop\shims\uv.exe"

if not defined UV_EXE (
    echo.
    echo Fleet Manager could not find uv.exe.
    echo Install uv for your Windows user, then run this file again.
    pause
    endlocal & exit /b 1
)

set "UV_DIR="
for %%I in ("%UV_EXE%") do set "UV_DIR=%%~dpI"
set "PATH=%UV_DIR%;%PATH%"

pushd "%REPO_ROOT%" >nul 2>&1
if errorlevel 1 (
    echo.
    echo Fleet Manager could not open its repository folder:
    echo %REPO_ROOT%
    pause
    endlocal & exit /b 1
)

echo.
echo This resets only Pilot Construction operational test data.
echo Type RESET PILOT to continue:
set /p "PILOT_CONFIRM=> "
if not "%PILOT_CONFIRM%"=="RESET PILOT" (
    echo.
    echo Reset cancelled. No data was changed.
    popd
    pause
    endlocal & exit /b 1
)

echo.
echo Resetting Pilot test data...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\reset-pilot.ps1" -ConfirmPilotReset
if errorlevel 1 goto :failed

echo Bootstrapping the Pilot fixture...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\bootstrap-pilot.ps1"
if errorlevel 1 goto :failed

echo.
echo Pilot test data reset successfully.
echo Driver can now begin with KM READING -^> START KM.
popd
pause
endlocal & exit /b 0

:failed
echo.
echo Pilot test data reset failed. Review the error above.
popd
pause
endlocal & exit /b 1
