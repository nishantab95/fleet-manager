# ADR 0006: One web application for the PC Role Lab

- Status: Accepted for Stage A
- Date: 2026-09-23

## Context

The backend already has separate authenticated boundaries for owner
administration, supervisor verification, driver operations, and reporting. The
existing Next.js page had grown into one client component that mixed those
workflows. Manual acceptance needs three browser profiles, but production
architecture must remain one web application and one authoritative backend.

## Decision

Keep one Next.js application and expose four route workspaces:

- `/login` for shared phone/OTP and membership selection.
- `/owner` for the production-intended Owner/Admin PC workspace.
- `/supervisor` for the internal/QA reference supervisor workflow.
- `/driver-test` for a development/pilot-only Driver QA simulator.

Shared auth keeps only the short-lived access token in runtime React state. A
page reload calls the existing `/api/v1/auth/web-refresh` endpoint using its
HttpOnly refresh cookie, then resolves the identity through `/api/v1/auth/me`.
No token is put in localStorage, sessionStorage, a URL, or a JavaScript cookie.

The Driver QA route is compiled as disabled unless
`NEXT_PUBLIC_ENABLE_DRIVER_QA=true` is explicitly set for the web process. It
registers `DevicePlatform.WEB`, uses the current assignment and authenticated
driver APIs, uploads evidence through the existing endpoint, and does not
contain a second persistence or calculation path. Backend role checks remain
authoritative even when the route is enabled.

Owner report calculations remain in the existing backend reporting service;
Supervisor decisions remain in the existing site-scoped service. Components
are split by role and API concern without creating separate Next.js projects,
backend services, or duplicated business rules.

## Consequences

Three local browser profiles can share `http://localhost:3000`. The owner
workspace and report behavior remain available while the supervisor workspace
can be validated before its final Flutter interface exists. Driver QA is useful
for proving real PostgreSQL/evidence/reporting flow but must never be presented
as the final Driver product. A future Supervisor Flutter client can reuse the
same API contracts without changing this web acceptance layer.
