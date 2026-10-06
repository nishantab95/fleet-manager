# Fleet Manager

## Owner web workstation

On an Owner laptop connected to the private Tailscale network, set the server-side-only upstream in `apps/web/.env.local`:

```dotenv
FLEET_API_UPSTREAM_URL=https://your-private-fleet-api-host
```

Then double-click `Start Fleet Manager Owner.bat`. The launcher checks the remote `/health` and `/ready` gates, starts only the local Next.js web app, waits for its same-origin API proxy, and opens the Owner workspace. It does not start a local API or database.

Production foundation for a construction company's fleet operations.

The active Pilot supports three roles (`DRIVER`, `SUPERVISOR`, and
`OWNER_ADMIN`) and one canonical `FleetAsset` model. Assets may be owned or
rented and may be Tippers, Excavators, Backhoe Loaders, Rollers, or Graders.
Tippers use odometer/KM capabilities; machinery uses hour-meter/HMR
capabilities. Effective-dated Site deployments and Driver/Operator assignments
preserve history while the existing Driver, Supervisor, Owner, reporting,
backup, authentication, and Pilot-update workflows remain active.

## Current active Pilot features

- Tenant-scoped People, Sites, Supervisor access, Fleet Assets, deployments,
  and Driver/Operator assignments.
- Tipper trips, KM, diesel, emergency, and duty workflows.
- Machinery HMR, diesel, emergency, and duty workflows.
- Offline Drift queue, private evidence, idempotent sync, Supervisor
  verification, Owner reporting, Excel, templates, and backup/restore.

## Locally gated operations modules

Maintenance, asset compliance, in-app notifications, telematics simulation,
fuel reconciliation, multi-meter assets, workforce/payroll, and attendance
location corroboration have persisted backend modules and compact Owner web
surfaces. They are all disabled by default and appear only when their
server-authoritative `FLEET_*_ENABLED` flag is explicitly enabled. No real
telematics, messaging, fuel, toll, payment, or payroll provider is connected.

Toll/expense remains a contract-only foundation. The Driver mobile Pilot is
unchanged: it has no phone-location permission and does not expose the new
multi-meter/location capture flow. See
`docs/overnight-working-modules-2026-10-06.md` for the acceptance matrix,
limitations, APIs, and local morning procedure.

## Repository layout

```text
apps/mobile/       Flutter / Dart Android-first shell
apps/web/          React / Next.js TypeScript shell
services/api/      FastAPI modular-monolith backend
infra/             Local infrastructure notes and configuration
docs/              Architecture, domain, development, security, and ADRs
scripts/           Windows PowerShell development helpers
.github/workflows/ CI skeleton
```

## Prerequisites

Required for backend work:

- Git
- Python 3.12+ (3.13 recommended once selected for the local machine)
- uv
- Docker Desktop with Compose

Required for the checked-in shell verification:

- Node.js 24+ and npm for the web shell
- Flutter 3.47.5, Android SDK 36, and JDK 17 for the mobile shell

The verified workstation uses the official Python Launcher-backed CPython 3.12, Node.js 24.19.0/npm 11.17.0, Flutter 3.47.5/Dart 3.13.4, Temurin JDK 17.0.20.1, and Android SDK 36. See `docs/development.md` for the exact checks and user-local setup guidance.

## Quick start on Windows

For normal daily use, copy `.env.example` to `.env` once during setup, then
double-click `Start Fleet Manager.bat` in the repository root. It verifies the
trusted Python 3.12 environment (using uv only to create the locked environment
when needed), starts Docker Desktop when needed, waits for the local services,
reuses healthy Fleet Manager API/Web processes, and opens
`http://localhost:3000/lab`. Double-click `Stop Fleet Manager.bat` to stop only
Fleet Manager-owned API/Web processes; Docker services and volumes are left
running.

Developer/bootstrap commands remain available:

```powershell
Copy-Item .env.example .env
.\scripts\bootstrap.ps1
services\api\.venv\Scripts\python.exe launch.py --status
```

The API is then available at `http://localhost:8000`, with `GET /health` and `GET /ready`. Local PostgreSQL and MinIO are started by Docker Compose. MinIO uses host ports `19000` (S3 API) and `19001` (console) by default so it does not collide with TallyPrime on port `9000`; change `MINIO_API_PORT`, `MINIO_CONSOLE_PORT`, and `FLEET_S3_ENDPOINT_URL` together when selecting other free host ports.

Run checks with:

```powershell
.\scripts\test.ps1
```

## Scope guardrails

Do not activate dormant modules, add continuous phone GPS, external messaging,
payment/accounting, customer billing, predictive automation, AI/LLM features,
or asynchronous infrastructure without an explicit reviewed phase. Feature
flags and UI hiding never replace backend RBAC or tenant isolation.

## Current status

Phase 4 contains the Android-first driver client with secure session storage,
assignment-scoped four-button event capture, camera evidence for KM and DIESEL,
an on-device Drift queue, bounded retry/refresh sync, and tenant-safe backend
event/evidence APIs. Phase 5 adds the authenticated supervisor web workflow:
explicit `SupervisorSiteAccess` site scope, trip/KM/diesel/emergency review,
reasoned individual or batch decisions, append-only verification history, private
evidence access, emergency acknowledgement, stale-decision conflicts, and daily
per-tipper completeness flags. The backend remains authoritative for assignment,
role, device, event idempotency, evidence ownership, and verification state.

Phase 3 contains owner/admin management for sites, owned tippers, people,
supervisor site grants, and effective-dated assignments, plus the authenticated
web administration shell. Phase 6 adds the owner operations dashboard,
timezone-aware operational-day reporting, site/tipper drill-downs, explicit
exceptions, daily site closure/history, and a reconciled Excel export.

Phase 2 contains the authentication boundary, OTP challenge persistence,
membership selection, access/refresh session rotation, authenticated identity
routes, and reusable tenant/RBAC dependencies. The default OTP provider is
unavailable and fails closed; development OTP requires explicit development
configuration. Reporting covers current generic Fleet Assets while retaining
compatibility labels where required. Fuel-efficiency claims and
external-provider data remain deferred.

Phase 7 adds release-candidate hardening for a controlled one-tipper pilot:
production-profile validation, API/web security headers, browser refresh
cookies, durable mobile sync diagnostics, cold-restart/retry tests, evidence
content validation, backup/restore tooling, and pilot documentation. It does
not add new equipment or change the driver's four-button contract. See
`docs/phase7-e2e-matrix.md`, `docs/pilot-runbook.md`, and
`docs/pilot-checklist.md`.
