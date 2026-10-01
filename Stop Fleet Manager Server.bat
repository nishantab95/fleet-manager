@echo off
setlocal EnableExtensions

set "REPO_ROOT=%~dp0"
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"
set "PYTHON_EXE=%REPO_ROOT%\services\api\.venv\Scripts\python.exe"

pushd "%REPO_ROOT%" >nul 2>&1
if errorlevel 1 goto :missing
if not exist "%PYTHON_EXE%" goto :missing_python

"%PYTHON_EXE%" "%REPO_ROOT%\scripts\server_manager.py" stop
set "FLEET_EXIT_CODE=%ERRORLEVEL%"
popd
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
