# Flutter/Android agent guide

Read [PROJECT_RULES.md](../../PROJECT_RULES.md) first; it is the primary contract.
Follow [change workflows](../../docs/development/change-workflows.md), the relevant ADRs and
[Google Play release](../../docs/google-play-release.md) before changing a release boundary.
Check Git status and inspect the existing implementation/tests before assuming a feature is absent.

- Entry/role screens: [lib/app.dart](lib/app.dart), [lib/role_screens.dart](lib/role_screens.dart).
  Authentication: [lib/auth/](lib/auth/). API, SQLite and synchronization: [lib/data/](lib/data/).
  Domain rules: [lib/domain/](lib/domain/); regressions: [test/](test/), [integration_test/](integration_test/).
- Production uses `FLEET_AUTH_MODE=company_pin` and `https://api.fleetaisystems.com`:
  owner-issued single-use activation, existing PIN/device/session security, no SMS/Firebase prerequisite.
- Preserve queue/schema compatibility, event UUIDs, timestamps, photographs and secure device registrations.
  Never clear local data to solve an update/sync problem; keep server-side tenant/assignment permissions.
- Preserve Pilot package ID, permanent signer and updater. Play builds must disable private APK installation;
  do not mix distribution channels, expose private API services or alter installed Pilot devices.
- From this directory run `dart format --output=none --set-exit-if-changed lib test integration_test tool`,
  `flutter analyze` and `flutter test <affected-test>`; expand regression/build coverage to match the change.
  Use existing protected release scripts for signing; do not generate keys or substitute debug signing.
- Local checks do not authorize deployment or Play publication. Report actual results and unavailable device/signing checks.
