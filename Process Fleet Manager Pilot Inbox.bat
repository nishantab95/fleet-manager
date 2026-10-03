@echo off
setlocal EnableExtensions

set "REPO_ROOT=%~dp0"
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"
set "PYTHON_EXE=%REPO_ROOT%\services\api\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" exit /b 1
pushd "%REPO_ROOT%" >nul 2>&1
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" "%REPO_ROOT%\scripts\pilot_release_inbox.py"
set "FLEET_EXIT_CODE=%ERRORLEVEL%"
popd
endlocal & exit /b %FLEET_EXIT_CODE%
