@echo off
setlocal EnableExtensions

set "REPO_ROOT=%~dp0"
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"
set "PYTHON_EXE=%REPO_ROOT%\services\api\.venv\Scripts\python.exe"

pushd "%REPO_ROOT%" >nul 2>&1
if errorlevel 1 goto :missing
if not exist "%PYTHON_EXE%" goto :missing_python
if "%~1"=="" goto :usage

if /I "%~2"=="--mandatory" (
    if not "%~3"=="" goto :usage
    "%PYTHON_EXE%" "%REPO_ROOT%\scripts\server_manager.py" publish-apk "%~1" --mandatory
) else if "%~2"=="" (
    "%PYTHON_EXE%" "%REPO_ROOT%\scripts\server_manager.py" publish-apk "%~1"
) else if /I "%~3"=="--mandatory" (
    "%PYTHON_EXE%" "%REPO_ROOT%\scripts\server_manager.py" publish-apk "%~1" --version-file "%~2" --mandatory
) else if "%~3"=="" (
    "%PYTHON_EXE%" "%REPO_ROOT%\scripts\server_manager.py" publish-apk "%~1" --version-file "%~2"
) else (
    goto :usage
)
set "FLEET_EXIT_CODE=%ERRORLEVEL%"
popd
goto :done

:usage
echo Usage: Publish Pilot APK.bat ^<verified-apk^> [version.txt] [--mandatory]
popd
set "FLEET_EXIT_CODE=2"
goto :done

:missing
echo Fleet Manager could not open its repository folder.
set "FLEET_EXIT_CODE=1"
goto :done

:missing_python
echo Fleet Manager Server is not configured: backend Python is missing.
popd
set "FLEET_EXIT_CODE=1"

:done
if not defined FLEET_SERVER_NO_PAUSE pause
endlocal & exit /b %FLEET_EXIT_CODE%
