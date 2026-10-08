# Fleet Manager

## Owner web workstation

On an Owner laptop connected to the private Tailscale network, set the server-side-only upstream in `apps/web/.env.local`:

```dotenv
FLEET_API_UPSTREAM_URL=https://your-private-fleet-api-host
```

Then double-click `Start Fleet Manager Owner.bat`. The launcher checks the remote `/health` and `/ready` gates, starts only the local Next.js web app, waits for its same-origin API proxy, and opens the Owner workspace. It does not start a local API or database.

Production foundation for a civil-construction company's fleet operations.

The core field workflow began with company-owned tippers and three roles:
`DRIVER`, `SUPERVISOR`, and `OWNER_ADMIN`. The current pilot capability catalog
also represents owned or rented tippers, excavators, backhoe loaders, rollers,
and graders for capability-aware duty, meter, diesel, and reporting workflows.
This narrow fleet extension does not bring later commercial or maintenance
modules into scope.

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

Do not add equipment categories beyond the current pilot capability catalog, or
payroll, accounting, customer billing, continuous GPS, predictive maintenance,
WhatsApp, AI/LLM features, or asynchronous infrastructure until the core field
workflow is reliable in production.

## Current status

Phase 4 contains the Android-first driver client with secure session storage,
assignment-scoped duty-state event capture, camera evidence for meter readings
and DIESEL, an on-device Drift queue, bounded retry/refresh sync, and tenant-safe
backend event/evidence APIs. Off-duty Drivers see Start Duty and Emergency;
on-duty actions follow asset capability and keep End Duty at the bottom. Phase 5
adds the authenticated supervisor web workflow:
explicit `SupervisorSiteAccess` site scope, trip/KM/diesel/emergency review,
reasoned individual or batch decisions, append-only verification history, private
evidence access, emergency acknowledgement, stale-decision conflicts, and daily
per-tipper completeness flags. The backend remains authoritative for assignment,
role, device, event idempotency, evidence ownership, and verification state.

Phase 3 contains owner/admin management for sites, pilot fleet assets, people,
supervisor site grants, and effective-dated assignments, plus the authenticated
web administration shell. Phase 6 adds the owner operations dashboard,
timezone-aware operational-day reporting, site/tipper drill-downs, explicit
exceptions, daily site closure/history, and a reconciled Excel export. Owner
report templates also include a Simple Site Workbook: one historical Site and
date range, Summary first, then one capability-aware sheet for every relevant
owned or rented asset. Existing configurable exports remain available. Simple
workbook fuel ratios are explicitly based on verified diesel recorded/issued
and are not represented as actual consumption or true fuel efficiency.

Phase 2 contains the authentication boundary, OTP challenge persistence,
membership selection, access/refresh session rotation, authenticated identity
routes, and reusable tenant/RBAC dependencies. The default OTP provider is
unavailable and fails closed; development OTP requires explicit development
configuration.

Phase 7 adds release-candidate hardening for a controlled one-tipper pilot:
production-profile validation, API/web security headers, browser refresh
cookies, durable mobile sync diagnostics, cold-restart/retry tests, evidence
content validation, backup/restore tooling, and pilot documentation. It does
not add new equipment or change the Driver event/offline contract. See
`docs/phase7-e2e-matrix.md`, `docs/pilot-runbook.md`, and
`docs/pilot-checklist.md`.
