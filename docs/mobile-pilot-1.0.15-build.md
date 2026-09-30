# Fleet Manager Pilot 1.0.15 Build Record

- Phase: `Fast Machinery MVP`
- Version name: `1.0.15-pilot`
- Version code: `16`
- Application ID: `com.fleetmanager.fleet_manager_mobile.pilot`
- Artifact: `dist/FleetManager-Pilot-1.0.15-code16.apk`
- Size: `61,674,582` bytes
- SHA-256: `94A5029C9581ED3509B6BCC0C79DA2CA71A727F5F700F8B4EE72408B75452427`
- Build command: `flutter build apk --flavor pilot --release --build-name=1.0.15 --build-number=16 --dart-define=FLEET_PILOT=true`
- Device installation: not performed; physical acceptance is still pending.

Automated validation for this build:

- `git diff --check`: pass (line-ending notices only)
- Dart formatting: pass (`25` files checked, `0` changed)
- Flutter analyze: pass (`No issues found`)
- Flutter tests: `90 passed`
- Backend pytest: `123 passed`, `12` dependency/configuration warnings
- Ruff: pass
- strict mypy: pass across `78` source files
- Alembic check: pass (`No new upgrade operations detected`)
- Migration validation: clean database to head and existing `0014` Pilot database
  to `0015_machinery_hmr` pass
- APK metadata: `1.0.15-pilot` / code `16`
- APK signature: APK Signature Scheme v2 verified

Short physical machinery acceptance checklist:

1. Upgrade in place with `adb install -r`; do not clear app or Pilot data.
2. As Owner, create one machinery Asset without a registration, deploy it to a
   Site, and assign an Operator.
3. As Operator, confirm the header identifies Asset/Site and shows exactly
   `HMR READING`, `DIESEL`, and `EMERGENCY` actions.
4. Capture START HMR with a photo, capture Diesel/Emergency, force-stop/reopen,
   then capture a greater END HMR with a photo.
5. Confirm pending work, active/closed duty, and assignment survive cold restart
   and sync without leaking across accounts.
6. As Supervisor, confirm START HMR, END HMR, machine hours, Diesel, evidence,
   Review, and Timeline are readable and no fake Trip/KM metrics appear.
7. As Owner, confirm the duty and daily reports show HMR/machine hours, leave
   trip/distance metrics blank for machinery, and the Excel download opens.
8. Recheck a Tipper still has exactly four actions and its KM/trip behavior is
   unchanged.
