# Fleet AI Systems

Fleet AI Systems is the public product brand for this construction fleet
operations platform. The canonical public website is
`https://fleetaisystems.com`.

Start with the [documentation index](docs/index.md) for current production,
development, Pilot, and historical guides, and the
[ADR inventory](docs/adr/README.md) for architectural decisions and supersession.

The public marketing site is the isolated `apps/marketing` deployment at `/`,
`/features`, `/how-it-works`, `/solutions`, `/pricing`, `/contact`, and
`/privacy`.
`apps/web` remains the private Owner/Supervisor operations client and is never
routed through the public marketing hostname. The prepared cloud topology
publishes it separately at `https://app.fleetaisystems.com`, with its
same-origin API proxy. See
[`docs/production-deployment.md`](docs/production-deployment.md) for the Ubuntu
OVHcloud Docker/Caddy topology and
[`docs/public-website-deployment.md`](docs/public-website-deployment.md) for the
preserved Windows/Caddy Pilot website path.

Internal identifiers such as package names, Android application IDs, API route
prefixes, database names, environment variables, service identifiers, launcher
filenames, and historical migration/release records intentionally retain their
existing `fleet-manager` / `Fleet Manager` names. They are compatibility
boundaries, not public brand copy, and renaming them would add deployment risk
without improving the user experience.

## Preserved Pilot Owner web workstation

On an Owner laptop connected to the private Tailscale network, set the server-side-only upstream in `apps/web/.env.local`:

```dotenv
FLEET_API_UPSTREAM_URL=https://your-private-fleet-api-host
```

Then double-click `Start Fleet Manager Owner.bat`. The compatibility launcher
keeps its existing filename, checks the remote `/health` and `/ready` gates,
starts only the local Next.js web app, waits for its same-origin API proxy, and
opens the Fleet AI Systems Owner workspace. It does not start a local API or
database.

## Prepared cloud production

Production is prepared as a separate Linux Docker deployment under
`infra/production`. It runs FastAPI, PostgreSQL, private MinIO evidence storage,
the Owner/Supervisor web application, the marketing site, and Caddy. Only Caddy
publishes host ports. Cloud clients do not require Tailscale; the existing
Tailscale Pilot path remains available during migration.

A push to `main` runs CI and never deploys. Production changes require a manual
`production-deploy.yml` dispatch for a full `main` commit SHA, the exact
confirmation phrase, successful CI, and approval through the protected GitHub
`production` Environment. The VPS command is backup-, restore-verification-,
migration-, health-, and rollback-gated.

The Google Play path is separately manual and protected. It retains production
package `com.fleetmanager.fleet_manager_mobile`, uses a separate externally
supplied Play upload identity, connects to
`https://api.fleetaisystems.com`, uses the existing owner-issued activation and
device PIN flow (`company_pin`), and cannot enable the Pilot APK sideload
updater. Existing `.pilot` installations require the controlled side-by-side
migration in [`docs/google-play-release.md`](docs/google-play-release.md).

No live infrastructure or Play release is created by the checked-in setup.
Current audit results and release gates are consolidated in the
[repository readiness report](docs/operations/repository-readiness-report.md).
The [earlier production report](docs/production-readiness-report.md) retains
its dated implementation and build evidence.
Host hardening, monitoring, scaling, incident response, provider migration, and
data-handling reviews are in [`docs/production-operations.md`](docs/production-operations.md)
and [`docs/production-data-handling.md`](docs/production-data-handling.md).

Production foundation for a civil-construction company's fleet operations.

The core field workflow began with company-owned tippers and three roles:
`DRIVER`, `SUPERVISOR`, and `OWNER_ADMIN`. The current pilot capability catalog
also represents owned or rented tippers, excavators, backhoe loaders, rollers,
and graders for capability-aware duty, meter, diesel, and reporting workflows.
Existing Maintenance V2 is part of the implemented capability model; this does
not authorize unrelated commercial modules or predictive maintenance.

## Repository layout

```text
apps/mobile/       Flutter Android-first driver and role clients, offline queue
apps/web/          Authenticated Next.js Owner/Supervisor operations client
apps/marketing/    Public React / Next.js marketing site
services/api/      FastAPI modular-monolith backend
infra/production/  Independent Linux Docker/Caddy production configuration
docs/              Architecture, domain, development, security, and ADRs
scripts/           Local development, guarded maintenance, and release tooling
.github/workflows/ Verification CI and explicitly approved release workflows
```

## Prerequisites

Required for backend work:

- Git
- Python 3.12 (the verified locked environment; review upgrades separately)
- uv
- Docker Desktop with Compose

Required for client development and verification:

- Node.js 24 and npm for both Next.js applications
- Flutter 3.47.5, Android SDK 36, and JDK 17 for the mobile application

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
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
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

## Implemented workflows and historical phase labels

The phase labels below record implementation history, not a new task sequence.
Current production authentication is `company_pin`; older OTP infrastructure is
optional compatibility, not an onboarding requirement. Start new engineering
work from [PROJECT_RULES.md](PROJECT_RULES.md) and the [documentation index](docs/index.md).

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

The current company deployment selects `company_pin`: an Owner-generated,
one-time activation code enrolls one installation, the user creates a six-digit
PIN, and subsequent mobile access uses the existing Fleet session boundary.
Firebase authentication remains available as an optional mode and is not
required by this deployment. See `docs/adr/0012-company-managed-activation-pin.md`.

Phase 7 adds release-candidate hardening for a controlled one-tipper pilot:
production-profile validation, API/web security headers, browser refresh
cookies, durable mobile sync diagnostics, cold-restart/retry tests, evidence
content validation, backup/restore tooling, and pilot documentation. It does
not add new equipment or change the Driver event/offline contract. See
`docs/phase7-e2e-matrix.md`, `docs/pilot-runbook.md`,
`docs/pilot-checklist.md`, and `docs/firebase-staging-runbook.md`. Cloud
production deliberately uses the existing owner-issued activation and device
PIN flow (`FLEET_AUTH_MODE=company_pin`); the Firebase runbook remains an
optional legacy/staging path and is not a Google Play prerequisite.
