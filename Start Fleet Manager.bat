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
    echo Install uv for your Windows user, then double-click this file again.
    pause
    exit /b 1
)

pushd "%REPO_ROOT%" >nul 2>&1
if errorlevel 1 (
    echo.
    echo Fleet Manager could not open its repository folder:
    echo %REPO_ROOT%
    pause
    exit /b 1
)

echo Starting Fleet Manager...
"%UV_EXE%" run --project "%REPO_ROOT%\services\api" "%REPO_ROOT%\launch.py"
set "FLEET_EXIT_CODE=%ERRORLEVEL%"
popd

if not "%FLEET_EXIT_CODE%"=="0" (
    echo.
    echo Fleet Manager did not reach READY. Review the message above.
    pause
)

endlocal & exit /b %FLEET_EXIT_CODE%
