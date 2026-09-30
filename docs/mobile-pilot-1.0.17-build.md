# Fleet Manager Pilot 1.0.17 Build Record

- Phase: `Owner Excel Templates + Selectable Columns MVP`
- Version name: `1.0.17-pilot`
- Version code: `18`
- Application ID: `com.fleetmanager.fleet_manager_mobile.pilot`
- Artifact: `dist/FleetManager-Pilot-1.0.17-code18.apk`
- Size: `62,100,730` bytes
- SHA-256: `CD7BA74A21B0CADC7D4ED3FAF5E39CF574EC92B5581DD40F51962ADE9E50A34A`
- Build command: `flutter build apk --flavor pilot --release --build-name=1.0.17 --build-number=18 --dart-define=FLEET_PILOT=true`
- APK signature: APK Signature Scheme v2 verified

Automated validation for this build:

- Dart formatting: pass (`25` files checked)
- Flutter analyze: pass (`No issues found`)
- Flutter tests: `95 passed`
- Backend pytest: `128 passed`, `15` dependency/configuration warnings
- Ruff: pass
- strict mypy: pass across `63` source files
- Alembic check: pass (`No new upgrade operations detected`)
- Migration validation: clean database to head and `0015_machinery_hmr` to
  `0016_report_templates` pass
- Pilot database: migrated in place to `0016_report_templates`; no reset
- Spreadsheet acceptance: all three built-ins and Custom Minimal passed
  programmatic validation; Management Summary and Custom Minimal passed visual
  rendering QA

Generated acceptance workbooks are retained under
`outputs/report-template-samples/` and excluded from Git. They contain the
mixed-fleet fixture: Tipper `6` trips / `100 km` / `20 L`, and Excavator
`1.5 h` / `10 L`.

Focused Samsung physical acceptance scope:

1. Install code18 in place with `adb install -r`; do not clear application data.
2. Confirm Reports shows exactly the three built-in templates.
3. Create `Custom Minimal`, set it as the company default, and export it.
4. Open the workbook and confirm its selected sheets and columns.
5. Force-stop/reopen and confirm the custom/default template persists.

Focused Samsung physical acceptance: **PASS**.

- Installed in place with `adb install -r`; application data was not cleared.
- Installed package reports version name `1.0.17-pilot` and version code `18`.
- API `/health` and `/ready` both returned `200`.
- Reports showed exactly the three built-ins with the expected `4`, `8`, and
  `3` sheet counts.
- Created `Custom Minimal` through the Owner UI with one selected sheet, then
  set it as the company default.
- Exported `FleetManager-2026-09-30-Custom-Minimal.xlsx`; Microsoft Excel
  opened it on the Samsung with exactly the `Management Dashboard` sheet and
  its selected canonical columns.
- After force-stop/reopen, `Custom Minimal · DEFAULT` and the built-in template
  list remained correct.
