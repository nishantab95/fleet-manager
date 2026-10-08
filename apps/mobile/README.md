# Fleet Manager mobile

Android-first driver client for Phase 4. The operational surface follows duty
state: off-duty Drivers see only `START DUTY` and `EMERGENCY`; on-duty Drivers
see the work actions supported by the assigned asset and `END DUTY` at the
bottom. Normal START/END KM or HMR capture is part of duty start/end instead of
a separate primary meter tile. `MAINTENANCE · Coming later` is a disabled
placeholder only.

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

The Pilot flavor defaults to `http://127.0.0.1:8000`, which works with
`adb reverse tcp:8000 tcp:8000`. For a physical device without ADB reverse,
use the host machine's LAN address through the visible Pilot server settings.

Driver duty state and the causal event queue are stored locally in Drift. A
START KM/HMR with its required evidence makes the duty operational immediately;
the queue preserves START before trips, diesel, and END across app restarts.
