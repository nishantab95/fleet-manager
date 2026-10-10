@echo off
setlocal EnableExtensions
set "FLEET_SERVER_NO_PAUSE=1"
call "%~dp0Update Fleet Manager Server.bat"
set "FLEET_EXIT_CODE=%ERRORLEVEL%"
pause
endlocal & exit /b %FLEET_EXIT_CODE%
