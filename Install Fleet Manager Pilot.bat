@echo off
setlocal
set "ROOT=%~dp0"
set "APK=%ROOT%dist\FleetManager-Pilot.apk"

if not exist "%APK%" (
  echo Pilot APK not found: "%APK%"
  echo Build it with: cd apps\mobile ^&^& flutter build apk --flavor pilot --release
  exit /b 1
)

where adb >nul 2>nul
if errorlevel 1 (
  echo adb was not found on PATH. Install/enable Android platform-tools.
  exit /b 1
)

adb start-server >nul
set "DEVICE="
for /f "tokens=1" %%D in ('adb devices ^| findstr /R /C:"device$"') do set "DEVICE=%%D"
if not defined DEVICE (
  echo No authorized Android device is connected.
  echo Connect a phone or start an emulator, then run this helper again.
  exit /b 1
)

echo Installing Fleet Manager Pilot on %DEVICE%...
adb -s %DEVICE% reverse tcp:8000 tcp:8000
adb -s %DEVICE% install -r "%APK%"
if errorlevel 1 exit /b 1
adb -s %DEVICE% shell monkey -p com.fleetmanager.fleet_manager_mobile.pilot 1 >nul
echo Installed and launched. For USB backend access use http://127.0.0.1:8000 in the app.
endlocal
