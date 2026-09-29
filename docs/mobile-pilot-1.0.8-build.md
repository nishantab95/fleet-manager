# Mobile Pilot 1.0.8 build

- Flutter version: `1.0.8+9`
- Android versionName: `1.0.8-pilot`
- Android versionCode: `9`
- Output: `dist/FleetManager-Pilot-1.0.8-code9.apk`

This build adds guarded company-phone handover between Driver memberships.
Code-8 local records are migrated in place: previously unscoped queue and duty
rows are assigned to the server-reported existing Driver binding, retained on
disk, and excluded from every other account scope. Handover is blocked when
that prior scope has unsynced records, evidence awaiting delivery, or an active
local duty. The backend separately blocks an active server duty and records
successful reassignment in the audit log.

Install as an update with `adb install -r`; do not uninstall or clear app data.
