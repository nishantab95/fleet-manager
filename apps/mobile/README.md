# Fleet Manager mobile

Android-first driver client for Phase 4. The operational surface is deliberately
limited to `TRIP COMPLETE`, `KM READING`, `DIESEL`, and `EMERGENCY`.

Events are written to a local Drift SQLite queue before network sync. Session
tokens and the installation identifier use secure storage. KM and DIESEL require
camera evidence; evidence uploads complete before the event envelope is sent.
The server remains authoritative for the active assignment, role, device, and
event idempotency boundary.

## Checks

```powershell
flutter pub get
dart run build_runner build
flutter analyze
flutter test
```

Use `--dart-define=FLEET_API_BASE_URL=http://10.0.2.2:8000` for an Android
emulator pointing at the local API.
