# Fleet Manager Pilot 1.0.7 Build Record

- Phase: `1B.2A — Owner People and Site Management`
- Version name: `1.0.7-pilot`
- Version code: `8`
- Application ID: `com.fleetmanager.fleet_manager_mobile.pilot`
- Artifact: `dist/FleetManager-Pilot-1.0.7-code8.apk`
- Size: `61,419,231` bytes
- SHA-256: `8CBE3562366A1A765B5F3CF3726B3364462E01ED3171F28A18C3914BB31908AD`
- Build command: `flutter build apk --flavor pilot --release --build-name=1.0.7 --build-number=8 --dart-define=FLEET_PILOT=true`
- Device installation: not performed; automated acceptance must complete before
  Samsung installation.

The build adds Owner People and Sites management with invitation lifecycle,
search and filters, status-aware cards, optional Site coordinates, and
Supervisor-to-Site access management. Driver remains labelled Operator in the
Owner UI. Asset deployment and Driver-to-Asset assignment mutation are not
included. The Driver four-button capture flow is unchanged.

Validation for this build:

- Dart formatting: pass
- Flutter analyze: pass
- Flutter tests: `51 passed`
- Backend pytest: `103 passed`
- Ruff lint: pass
- mypy: pass across `71` source files
- Launcher pytest: `46 passed`
- Clean database migration `base -> head`: pass
- Previous-head migration `0011 -> 0012`: pass with UUID/data preservation
- Alembic check: no new upgrade operations
- `git diff --check`: pass (line-ending notices only)

The Pilot database was not reset or migrated during validation. Earlier APKs
were not overwritten, and no APK was installed on a device.
