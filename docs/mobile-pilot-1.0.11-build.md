# Fleet Manager Pilot 1.0.11 Build Record

- Phase: `1B.2C — Driver Assignment Reconciliation Fix`
- Version name: `1.0.11-pilot`
- Version code: `12`
- Application ID: `com.fleetmanager.fleet_manager_mobile.pilot`
- Artifact: `dist/FleetManager-Pilot-1.0.11-code12.apk`
- Size: `61,625,218` bytes
- SHA-256: `381555C2E7B153FF487E318702ABDEABE142878107D1926BC73E710F4E10B61F`
- Requested build command: `flutter build apk --flavor pilot --release --build-name=1.0.11 --build-number=12 --dart-define=FLEET_PILOT=true`
- Device installation: in-place upgrade with `adb install -r`; no uninstall or app-data clear.
- Physical device: Samsung SM-S918B (`RZCW12B4GPX`).

This build makes the server response authoritative for the Driver's current
assignment. A reachable `204 No Content` clears the account-scoped current
assignment cache without deleting duty or event history. A genuine connectivity
failure can still use the scoped last-known assignment. Manual Sync, automatic
queue Sync, app resume, and cold session restoration now share the same
assignment/duty reconciliation path.

Validation for this build:

- Dart formatting: pass (`25` files checked, `0` changed)
- Flutter analyze: pass (`No issues found`)
- Flutter tests: `79 passed`
- New assignment reconciliation tests: server-none clearing, offline fallback,
  OWN-to-RENT-to-OWN changes, cold restart, and protected local work all pass
- Driver widget regression: manual Sync updates assignment and keeps exactly
  four operational actions with correct no-assignment gating
- Device handover regression: offline session restoration activates the scoped
  account before using its cached assignment
- Backend pytest: not rerun; this fix changed no backend source, migration, or test
- Alembic check: pass (`No new upgrade operations detected`)
- `git diff --check`: pass (line-ending notices only)

Windows Application Control blocked Flutter SDK `impellerc.exe` while compiling
the unchanged stock Material shaders. Security policy was not changed. Flutter
had already produced the code12 release kernel and all three AOT libraries; the
identical compiled stock shaders were restored from the validated code11 APK in
ignored build output, and Gradle packaged the verified code12 outputs while
skipping only the blocked shader task. APK verification confirmed version
`1.0.11-pilot` / code `12`, APK Signature Scheme v2, all three `libapp.so` ABIs,
and both stock shader assets.

Real Samsung acceptance passed without Driver logout/login during assignment
changes:

1. Test Driver Two opened on OWN-T02.
2. Supervisor unassigned OWN-T02 through the authenticated API.
3. Driver Sync showed `NO ACTIVE ASSIGNMENT`; all four event buttons were disabled.
4. Force-stop/reopen remained signed in and still showed no assignment.
5. Supervisor assigned RENT-T03 to Test Driver Two.
6. Driver Sync changed immediately to RENT-T03.
7. Force-stop/reopen remained signed in and reopened on RENT-T03.
8. Supervisor restored OWN-T02 and unassigned RENT-T03.
9. Driver Sync changed immediately back to OWN-T02.

Final preserved fixture verification: `TIPPER-12 -> Pilot Driver`, `OWN-T02 ->
Test Driver Two`, `RENT-T03 -> unassigned`, with zero duplicate active Asset
assignments. The Pilot database and phone app data were never reset.
