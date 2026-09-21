# Fleet Manager

Production foundation for a construction company's company-owned tipper operations.

V1 is intentionally limited to owned tippers and three roles: `DRIVER`, `SUPERVISOR`, and `OWNER_ADMIN`. Phase 0 establishes the modular-monolith workspace, backend runtime foundation, local infrastructure, frontend shells, domain specification, security baseline, and verification workflow. Product workflows are deliberately not implemented yet.

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

The API is then available at `http://localhost:8000`, with `GET /health` and `GET /ready`. Local PostgreSQL and MinIO are started by Docker Compose.

Run checks with:

```powershell
.\scripts\test.ps1
```

## Scope guardrails

Do not add rented equipment, non-tipper machinery, payroll, accounting, customer billing, continuous GPS, predictive maintenance, WhatsApp, AI/LLM features, or asynchronous infrastructure until the owned-tipper workflow is reliable in production.

## Current status

Phase 0 is a foundation milestone. It does not contain driver workflows, supervisor workflows, admin screens, domain persistence, authentication, or business APIs. Those are intentionally deferred to Phase 1 and later.
