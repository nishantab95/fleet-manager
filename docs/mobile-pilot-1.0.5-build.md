# Fleet Manager Pilot 1.0.5 Build Record

- Phase: `1B.1 — Owner Fleet Management`
- Version name: `1.0.5-pilot`
- Version code: `6`
- Application ID: `com.fleetmanager.fleet_manager_mobile.pilot`
- Artifact: `dist/FleetManager-Pilot-1.0.5-code6.apk`
- Size: `60,451,603` bytes
- SHA-256: `5FB4CFC68C0B68B2C633964487974A8AA83D53F677EF9D7B3AB23201A6D1C583`
- Build command: `flutter build apk --flavor pilot --release --build-name=1.0.5 --build-number=6 --dart-define=FLEET_PILOT=true`
- Device installation: performed on Samsung SM-S918B. Phase 1B.1 passed except
  the expired-session duplicate-registration test, which exposed the shared
  mobile refresh defect corrected in Pilot 1.0.6/code7.

The known-good `FleetManager-Pilot-1.0.4-code5.apk` was not overwritten.
