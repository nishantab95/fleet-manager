@echo off
setlocal EnableExtensions

set "REPO_ROOT=%~dp0"
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"

pushd "%REPO_ROOT%" >nul 2>&1
if errorlevel 1 (
    echo.
    echo Fleet Manager could not open its repository folder:
    echo %REPO_ROOT%
    pause
    exit /b 1
)

echo Preparing the trusted Python 3.12 environment...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\ensure-trusted-python.ps1"
if errorlevel 1 (
    echo.
    echo Fleet Manager could not prepare its trusted Python environment.
    popd
    pause
    endlocal & exit /b 1
)

set "PYTHON_EXE=%REPO_ROOT%\services\api\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo.
    echo Fleet Manager could not find its trusted project Python executable.
    popd
    pause
    endlocal & exit /b 1
)

echo Starting Fleet Manager...
"%PYTHON_EXE%" "%REPO_ROOT%\launch.py"
set "FLEET_EXIT_CODE=%ERRORLEVEL%"
popd

if not "%FLEET_EXIT_CODE%"=="0" (
    echo.
    echo Fleet Manager did not reach READY. Review the message above.
    pause
)

endlocal & exit /b %FLEET_EXIT_CODE%
