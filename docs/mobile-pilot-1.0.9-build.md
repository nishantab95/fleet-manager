# Fleet Manager Pilot 1.0.9 Build Record

- Phase: `1B.2B — Fleet Asset to Site Deployment`
- Version name: `1.0.9-pilot`
- Version code: `10`
- Application ID: `com.fleetmanager.fleet_manager_mobile.pilot`
- Artifact: `dist/FleetManager-Pilot-1.0.9-code10.apk`
- Size: `61,534,087` bytes
- SHA-256: `C52A2AB2B110C221497F7D274BB49D2C7F3468A689C2F92ED9F0C2BC6230CDB0`
- Build command: `flutter build apk --flavor pilot --release --build-name=1.0.9 --build-number=10 --dart-define=FLEET_PILOT=true`
- Device installation: not performed; physical acceptance is pending.

This build adds the effective-dated Fleet Asset-to-Site deployment relationship.
Owners can deploy, move, and remove active assets from Fleet or Site detail
without choosing a Driver or Supervisor. Authorized Supervisors see all active
assets deployed to their Sites, including assets with no Driver and no events.
Driver capture, Assignment history, evidence, and reporting totals remain on
their existing operational relationships.

Validation for this build:

- Dart formatting: pass (`24` files checked)
- Flutter analyze: pass
- Flutter tests: `63 passed`
- Backend pytest: `114 passed`
- Ruff lint: pass
- mypy: pass across `75` source files
- Launcher pytest: `46 passed`
- Migration regression (`0012 -> 0013`): pass with Assignment history preserved
- Existing Pilot database migration: `0012 -> 0013` pass, no reset
- Pilot backfill: `TIPPER-12 / PILOT12 -> Pilot Site` current deployment
- Alembic check: no new upgrade operations
- `git diff --check`: pass (line-ending notices only)

The APK was built only after automated validation passed. Earlier APKs were not
overwritten, and no APK was installed on a device.
