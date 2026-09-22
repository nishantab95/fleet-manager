# Fleet Manager

Production foundation for a construction company's company-owned tipper operations.

V1 is intentionally limited to owned tippers and three roles: `DRIVER`, `SUPERVISOR`, and `OWNER_ADMIN`. Phase 0 established the modular-monolith workspace and runtime foundation; Phase 1 adds the tenant-safe core domain schema and database invariants; Phase 2 adds phone OTP authentication, server-side sessions, and tenant-scoped RBAC; Phase 3 adds tenant-safe owner/admin management APIs and an authenticated web administration shell; Phase 4 adds the offline-first driver event client and reliable event/evidence sync; Phase 5 adds supervisor site-scoped verification and operational completeness review.

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

The verified workstation uses uv-managed CPython 3.12.14, Node.js 24.19.0/npm 11.17.0, Flutter 3.47.5/Dart 3.13.4, Temurin JDK 17.0.20.1, and Android SDK 36. See `docs/development.md` for the exact checks and user-local setup guidance.

## Quick start on Windows

```powershell
Copy-Item .env.example .env
.\scripts\bootstrap.ps1
.\scripts\dev.ps1
```

The API is then available at `http://localhost:8000`, with `GET /health` and `GET /ready`. Local PostgreSQL and MinIO are started by Docker Compose. MinIO uses host ports `19000` (S3 API) and `19001` (console) by default so it does not collide with TallyPrime on port `9000`; change `MINIO_API_PORT`, `MINIO_CONSOLE_PORT`, and `FLEET_S3_ENDPOINT_URL` together when selecting other free host ports.

Run checks with:

```powershell
.\scripts\test.ps1
```

## Scope guardrails

Do not add rented equipment, non-tipper machinery, payroll, accounting, customer billing, continuous GPS, predictive maintenance, WhatsApp, AI/LLM features, or asynchronous infrastructure until the owned-tipper workflow is reliable in production.

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
configuration. Reporting is limited to company-owned tippers; rented
equipment, machinery, fuel-efficiency calculations, and later business
expansion remain deferred.

Phase 7 adds release-candidate hardening for a controlled one-tipper pilot:
production-profile validation, API/web security headers, browser refresh
cookies, durable mobile sync diagnostics, cold-restart/retry tests, evidence
content validation, backup/restore tooling, and pilot documentation. It does
not add new equipment or change the driver's four-button contract. See
`docs/phase7-e2e-matrix.md`, `docs/pilot-runbook.md`, and
`docs/pilot-checklist.md`.
