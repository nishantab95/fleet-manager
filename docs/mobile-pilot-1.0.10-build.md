# Fleet Manager Pilot 1.0.10 Build Record

- Phase: `1B.2C — Driver / Operator to Fleet Asset Assignment`
- Version name: `1.0.10-pilot`
- Version code: `11`
- Application ID: `com.fleetmanager.fleet_manager_mobile.pilot`
- Artifact: `dist/FleetManager-Pilot-1.0.10-code11.apk`
- Size: `61,616,011` bytes
- SHA-256: `F059E370639BA0B1C095E829EF64534D884722DDB98A5D3F690B9508B78D47A4`
- Build command: `flutter build apk --flavor pilot --release --build-name=1.0.10 --build-number=11 --dart-define=FLEET_PILOT=true`
- Device installation: not performed.

This build evolves the existing effective-dated Assignment relationship into
the canonical Driver/Operator-to-FleetAsset lifecycle. Owners and authorized
Site Supervisors can assign, change, or remove a Driver from an active deployed
tipper. Site is derived from the current deployment, Supervisor authority is
derived from Site access, active duty blocks changes, and all history remains
attached to its original Assignment.

Validation for this build:

- Dart formatting: pass (`24` files checked)
- Flutter analyze: pass
- Flutter tests: `72 passed`
- Backend pytest: `118 passed`
- Ruff lint: pass
- mypy: pass across `78` source files
- Launcher pytest: `46 passed`
- Migration regression (`0013 -> 0014`): pass with Assignment history preserved
- Existing Pilot database migration: `0013 -> 0014` pass, no reset
- Pilot preservation check: memberships `5`, assets `3`, deployment-history rows
  `6`, assignments `1`, operational events `22`, evidence objects `3`, and
  audit records `262`; all counts unchanged
- Legacy Pilot Assignment deployment links: `1/1` linked (`0` null)
- Physical-test fixture prepared without reset: `TIPPER-12 -> Pilot Driver ->
  Pilot Site`; `OWN-T02 -> Test Driver Two -> Test Site B` (Assignment
  `cd7c7715-59bf-4649-9396-c55ad49ffc92`); `RENT-T03 -> Test Site B`
  remains unassigned; `Test Supervisor Two` retains Site access
- Fixture preparation created one Assignment and one audit record only; event
  and evidence counts remain `22` and `3`
- Alembic check: no new upgrade operations
- `git diff --check`: pass (line-ending notices only)

The APK was built only after automated validation passed. Earlier APKs were not
overwritten, and no APK was installed on a device.
