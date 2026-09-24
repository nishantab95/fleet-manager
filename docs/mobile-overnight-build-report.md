# Fleet Manager Mobile Overnight Build Report

## OVERALL STATUS: READY FOR PHONE TEST

## Morning acceptance checklist

### START PC

Double-click:

`D:\Git\fleet maneger\fleet manager\Start Fleet Manager.bat`

### PHONE

Install:

`D:\Git\fleet maneger\fleet manager\dist\FleetManager-Pilot.apk`

### CONNECT

Open the login settings icon, enter the PC LAN address such as `http://192.168.1.20:8000`, tap `TEST CONNECTION`, and save. For USB, use `Install Fleet Manager Pilot.bat` if available.

### LOGIN DRIVER

`9606743463` / `111111`

Verify the four-button layout, START/END duty gating, photo capture, four trips, 30 L diesel without evidence, app reopen with ACTIVE duty, sequential second session, and one emergency.

### LOGIN SUPERVISOR

`9606743463` / `222222`

Verify assigned-site isolation, emergency-first display, acknowledge/resolve, site → tipper grouping, separate START/END KM review, diesel with and without evidence, evidence viewer, and approve/reject/dispute.

### LOGIN OWNER

`9606743463` / `333333`

Verify dashboard reconciliation, tippers, sites, alerts, two duty sessions, OT visibility, date-based reports, evidence, and XLSX share/open.

## Build evidence

- APK: `D:\Git\fleet maneger\fleet manager\dist\FleetManager-Pilot.apk`
- SHA-256 file: `D:\Git\fleet maneger\fleet manager\dist\FleetManager-Pilot.sha256.txt`
- APK size: `59,828,779` bytes (57.1 MB)
- SHA-256: `48d0472d2af8bc1030fa4af424e4a5a7a68bd699975abe25515d3ff357b34337`
- Android package: `com.fleetmanager.fleet_manager_mobile.pilot`
- App label: `Fleet Manager Pilot`
- Minimum Android API: 24
- Target Android API: 36
- Device install: NOT RUN — no authorized adb device or emulator was available.

## Acceptance status

The repository contains one role-aware Flutter application with backend-authoritative Driver, Supervisor, and Owner sessions. The final Flutter gate passed: analyzer clean and 10 widget/unit tests passed. Flutter integration testing was not run because `adb devices` returned no authorized device and `flutter emulators` reported no emulator. The APK build passed.

Backend gates: Ruff passed; strict mypy passed across 62 files; pytest passed 77/77 (3 dependency deprecation warnings).

Web gates: `npm audit` found 0 vulnerabilities; lint passed; typecheck passed; Vitest passed 22/22 tests; Playwright passed 13 tests with 5 expected skips; production build passed.

Launcher regression: `uv run --project services/api python scripts/test_launch.py` exited successfully.

Local backend health check: `http://127.0.0.1:8000/health` returned `{"status":"ok","service":"fleet-manager-api","version":"0.1.0"}`.

No FCM production credentials are present; foreground polling/in-app attention is implemented and reliable background push remains a production configuration item.
