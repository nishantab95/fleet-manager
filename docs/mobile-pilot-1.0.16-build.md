# Fleet Manager Pilot 1.0.16 Build Record

- Phase: `Fast Machinery MVP — Reporting / Presentation Completion`
- Version name: `1.0.16-pilot`
- Version code: `17`
- Application ID: `com.fleetmanager.fleet_manager_mobile.pilot`
- Artifact: `dist/FleetManager-Pilot-1.0.16-code17.apk`
- Size: `61,740,118` bytes
- SHA-256: `EB7A7D772F57F731B2502F2918B43600D42F86E3B95E4BD6FDEB750750E90EA8`
- Build command: `flutter build apk --flavor pilot --release --build-name=1.0.16 --build-number=17 --dart-define=FLEET_PILOT=true`
- APK signature: APK Signature Scheme v2 verified

Automated validation for this build:

- Dart formatting: pass (`26` files checked, `0` changed)
- Flutter analyze: pass (`No issues found`)
- Flutter tests: `91 passed`
- Backend pytest: `124 passed`, `12` dependency/configuration warnings
- Focused Excel/report tests: `7 passed`
- Ruff: pass
- strict mypy: pass across `78` source files
- Alembic check: pass (`No new upgrade operations detected`)

The reporting workbook now uses eight focused sheets: Management Dashboard,
Tipper Daily, Machinery Daily, Trip Register, Meter Readings, Diesel Register,
Duty Register, and Exceptions. Human-readable timestamps are converted to the
company reporting timezone before export. Tipper distance/trip metrics and
machinery HMR/hour metrics remain capability-specific; non-applicable metrics
are not exported as zero.

The accepted code16 artifact remains unchanged with SHA-256
`94A5029C9581ED3509B6BCC0C79DA2CA71A727F5F700F8B4EE72408B75452427`.

Focused physical acceptance scope:

1. Supervisor EXC-01 card shows `Diesel 10 L`, not event count `1`.
2. Owner EXC-01 duty shows START HMR `1000`, END HMR `1001.5`, and machine
   hours `1.5 h`, without KM labels.
3. Owner workbook shows EXC-01 HMR/hour data and pending `10 L` diesel context,
   no false missing-KM exception, and preserves Tipper trip/KM/diesel values.

Focused Samsung physical acceptance: **PASS** on 2026-09-30.

- Owner EXC-01 duty rendered START HMR `1000`, END HMR `1001.50`, MACHINE
  HOURS `1.50 h`, and `0 L verified · 10 L pending`, with no KM fields.
- Supervisor EXC-01 card rendered START HMR `1000`, END HMR `1001.50`,
  MACHINE HOURS `1.50`, and `Diesel 10 L` with `2 pending`.
- The acceptance was read-only: no review decision, assignment, or operational
  data mutation was performed.
