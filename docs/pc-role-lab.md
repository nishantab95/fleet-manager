# PC Role Lab

This is the controlled local acceptance workflow for the owned-tipper system.
It uses one Next.js web application with four routes:

- `/login` — shared phone/OTP and membership selection.
- `/owner` — production-intended Owner/Admin PC workspace.
- `/supervisor` — `INTERNAL / QA REFERENCE` for supervisor verification.
- `/driver-test` — `QA DRIVER SIMULATOR / NON-PRODUCTION WEB TEST CLIENT`.

The Driver QA route is disabled unless `NEXT_PUBLIC_ENABLE_DRIVER_QA=true` is
present in the web process environment. It is disabled by default and does not
change backend authorization.

## Start the local role lab

Normal daily use is one double-click. From Windows:

1. Double-click the root-level file:

   ```text
   Start Fleet Manager.bat
   ```

   The wrapper finds `uv` without requiring Python on PATH, starts Docker
   Desktop when needed, waits for the Docker engine, starts or reuses
   PostgreSQL, MinIO, API, and Web, and opens exactly one normal Edge
   `http://localhost:3000/lab` app window. No PowerShell command or menu choice
   is required.
2. Choose Driver, Supervisor, or Owner in the Lab. Each role route still
   requires its real backend authentication and authorization. If Edge is not
   available, open `http://localhost:3000/lab` manually.

To stop only Fleet Manager-owned API/Web processes, double-click:

```text
Stop Fleet Manager.bat
```

Docker services and their volumes are left running and untouched.

Advanced launcher operations are available without changing the normal flow:

```text
uv run --project services/api launch.py --fresh    # type RESET PILOT when prompted
uv run --project services/api launch.py --status
uv run --project services/api launch.py --stop
uv run --project services/api launch.py --menu
uv run --project services/api launch.py --help
```

The launcher validates the local non-production configuration, starts and
health-checks PostgreSQL and MinIO, applies migrations, reuses the existing
idempotent pilot bootstrap, starts the API and web app on ports 8000 and 3000,
and enables Driver QA only in the managed web process. It never resets data on
normal start or status checks.

The normal launcher uses the regular Edge profile and does not open three
visible role windows. The Lab cards are navigation only: they do not
impersonate a role or grant access. The existing isolated role-profile routine
remains available for advanced/manual use under
`%LOCALAPPDATA%\FleetManagerRoleLab\profiles\owner`, `supervisor`, and
`driver-qa`; those profiles keep separate browser sessions. The launcher
suppresses Edge first-run tabs and does not open a duplicate control window
when one is active. Before
authentication, each role route carries its existing cosmetic login hint;
backend membership authorization remains unchanged.

The Lab `START FRESH TEST` button never resets data from the browser. It
explains that you must run the advanced `--fresh` command and type `RESET PILOT`
at the launcher prompt. System status checks API and database readiness
directly; Object Store is marked `LAUNCHER` because MinIO readiness continues
to be checked by the advanced `--status` command rather than by a new backend
endpoint.

## Troubleshooting / Manual startup

The detailed commands below are fallback diagnostics when the launcher reports
an actionable failure. Keep OTP values and the pilot driver number in `.env`
only.

Create and edit the ignored local environment file:

```powershell
Copy-Item .env.example .env
# Set FLEET_PILOT_DRIVER_PHONE to the local pilot driver's real number.
# Set FLEET_OTP_PROVIDER=pilot, FLEET_PILOT_OTP=<six digits>, and a local JWT key.
```

Start PostgreSQL and MinIO, then the API:

```powershell
docker compose up -d postgres minio
.\scripts\dev.ps1 -SkipInfrastructure
```

In a second terminal, verify `http://localhost:8000/health` and
`http://localhost:8000/ready`. Apply migrations from the API working directory:

```powershell
Push-Location services\api
uv --cache-dir "..\..\.uv-cache" run alembic upgrade head
Pop-Location
.\scripts\bootstrap-pilot.ps1
```

Start the one web server with Driver QA explicitly enabled in that local
process:

```powershell
$env:NEXT_PUBLIC_ENABLE_DRIVER_QA="true"
Push-Location apps\web
npm ci
npm run dev
Pop-Location
```

All workspaces use `http://localhost:3000`; the normal entry point is
`http://localhost:3000/lab`.

## Isolated manual browser profiles

For advanced/manual three-role testing, the preserved role-workspace routine
creates separate Microsoft Edge user-data directories so each role has its own
HttpOnly refresh cookie:

- Browser/Profile A — Owner/Admin, phone `+919876543210`.
- Browser/Profile B — Supervisor, phone `+919876543222`.
- Browser/Profile C — Driver QA, the local value of `$env:FLEET_PILOT_DRIVER_PHONE`.

Enter the configured local pilot OTP when prompted. Never copy a real OTP into
source control or this document.

## Acceptance sequence

1. In Profile A, sign in as Owner/Admin and open `/owner`. Confirm that
   Administration, Operations, Sites, Owned tippers, People, Assignments, and
   Supervisor access are visible.
2. In Profile B, sign in as Supervisor and open `/supervisor`. Confirm that only
   `Pilot Site` is available. Review pending events, evidence, completeness,
   KM, diesel, emergency acknowledgement, individual decisions, batch approval,
   rejection/dispute reasons, and stale-decision behavior.
3. In Profile C, sign in as Driver QA and confirm the current assignment shows
   `Tipper 12`, `Pilot Site`, and the pilot supervisor. Confirm the four primary
   actions are available: `TRIP COMPLETE`, `KM READING`, `DIESEL ISSUED / RECORDED`,
   and `EMERGENCY`.

   The browser must register a generated installation identifier with platform
   `WEB`. It must not use `ANDROID` and must not display operational totals.

4. In Profile C, perform these real API actions:

   - KM `START_READING`, value `10000`, with a local JPEG/PNG/WebP test image.
   - Four separate `TRIP COMPLETE` actions.
   - Diesel `30` litres with a local test image. The label is issued/recorded,
     never consumed, and no km/L is calculated.
   - KM `END_READING`, value `10120`, with a local test image.
   - One one-tap `EMERGENCY` action using the current assignment context. No
     category, description, or evidence is required.

   The QA diagnostics list should show a distinct client UUID for every event,
   the API acknowledgement, and the server verification state.

5. In Profile B, refresh the Pilot Site event review. View evidence, acknowledge
   the emergency according to the existing workflow, and approve the valid
   trip, KM, and diesel events. Resolve any emergency state that blocks closure.

6. In Profile A, open Owner Operations and confirm the same PostgreSQL-backed
   records reconcile:

   - Approved trips: `4`
   - Start KM: `10000`
   - End KM: `10120`
   - Distance: `120 KM`
   - Diesel issued: `30 L`

   Check the dashboard, Pilot Site report, Tipper 12 report, exceptions, and
   closure state. No fuel-efficiency calculation should appear.

7. Download Excel from Owner Operations. Confirm the response is an XLSX file
   and that its Daily Summary, Trip Register, KM Register, Diesel Register, and
   Exceptions sheets reconcile to the same report values. Do not commit the
   downloaded workbook.

## PASS / FAIL

PASS means all three roles authenticate through the backend, each role sees
only its allowed workspace, Driver QA events are visible to Supervisor and
Owner from real PostgreSQL state, the report values above reconcile, Excel
downloads as XLSX, and closure succeeds only after its blockers are resolved.

FAIL means any event was faked, inserted directly into PostgreSQL, assigned to
the wrong role/site, missing required evidence, missing from supervisor review
or owner reporting, or a report calculation disagrees with the backend.

## Reset and repeat

The reset is deliberately narrow. It identifies the exact `Pilot Construction`
company and requires the named `Pilot Site` and `PILOT-12` tipper. It refuses
production and does not accept a company ID. It removes only operational events,
verification history, evidence metadata/objects when storage is configured,
closure records, and related operational audit entries. It retains the company,
users, memberships, site, tipper, supervisor access, and active assignment.

```powershell
.\scripts\reset-pilot.ps1 -ConfirmPilotReset
.\scripts\bootstrap-pilot.ps1
```

The reset never runs automatically. If object storage is unavailable, its
metadata is removed and the local unavailable provider has no object to delete;
use MinIO for a complete evidence-object reset.

## Known mobile follow-up

The Android UI can currently report `Sync complete` while failed events remain
waiting. The local pending query intentionally includes `pending`, `syncing`,
and `syncFailed`; successfully synced events leave that pending count. This is
documented follow-up work and is outside the PC Role Lab. Do not redesign the
mobile sync engine as part of this acceptance stage.
