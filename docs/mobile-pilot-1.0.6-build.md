# Fleet Manager Pilot 1.0.6 Build Record

- Phase: `1B.1 — Owner Fleet Management session-refresh correction`
- Version name: `1.0.6-pilot`
- Version code: `7`
- Application ID: `com.fleetmanager.fleet_manager_mobile.pilot`
- Artifact: `dist/FleetManager-Pilot-1.0.6-code7.apk`
- Size: `60,435,219` bytes
- SHA-256: `AEC06C46021D6F19543C700E0E10A1998092CE9FE3FC978D1E9520F6F4781C7B`
- Build command: `flutter build apk --flavor pilot --release --build-name=1.0.6 --build-number=7 --dart-define=FLEET_PILOT=true`
- Device installation: `adb install -r` succeeded on Samsung SM-S918B; the
  package first-install timestamp and app data were preserved.

The real-device test used the normal configured 600-second access-token TTL.
The Owner session was created at `2026-09-29 13:44:36 UTC`; while the populated
Add Tipper route remained open, the Owner background poll received the expired
access token and the server recorded refresh rotation at
`2026-09-29 13:54:36 UTC`. The nested form remained authenticated.

The exact post-refresh submission used asset code `newcode99`, registration
`testown02`, short name `owned tipper two`, and ownership `OWNED`, with existing
normalized registration `TESTOWN02`. The backend returned
`registration number is already used by this company`; no `NEWCODE99` asset was
created. A subsequent save of the existing `TESTOWN02` edit returned to the
Fleet list and recorded `OWNER_ASSET_UPDATED`, proving the refreshed session
remained usable. A force-stop and relaunch then restored the Owner dashboard
without another login, confirming the rotated access and refresh tokens were
persisted through the existing secure session store.

Validation for this build:

- Dart formatting: pass
- Flutter analyze: pass
- Flutter tests: `48 passed`
- Backend pytest: `97 passed`
- Ruff lint: pass
- mypy: pass across `68` source files
- Alembic check: no new upgrade operations
- `git diff --check`: pass (line-ending notices only)

The prior `FleetManager-Pilot-1.0.5-code6.apk` remains unchanged with SHA-256
`5FB4CFC68C0B68B2C633964487974A8AA83D53F677EF9D7B3AB23201A6D1C583`.
