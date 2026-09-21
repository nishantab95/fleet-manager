# ADR 0001: Foundation architecture and boundaries

- Status: Accepted for Phase 0
- Date: 2026-09-21

## Context

The first release serves one construction company but must be tenant-safe, offline-capable, auditable, and simple enough to operate on weak site connectivity. The product starts with company-owned tippers and must not grow infrastructure before the core workflow is reliable.

## Decision

Use a modular monolith in a monorepo:

- FastAPI + Pydantic + SQLAlchemy 2.x + Alembic for the Python backend.
- PostgreSQL as the transactional system of record.
- Flutter/Dart for an Android-first offline-capable mobile client with SQLite-backed persistence.
- React/Next.js + strict TypeScript for the web client.
- An S3-compatible storage abstraction, with MinIO for local development.
- Effective-dated assignments rather than permanent driver-to-tipper relationships.
- Client-generated event UUIDs and a durable sync state separate from business verification.
- Company-scoped authorization in backend data access, not frontend filtering.

No microservices, Redis, Celery, or message broker are introduced in Phase 0.

## Consequences

The initial deployment has fewer moving parts and can preserve transaction and authorization invariants centrally. The backend modules must remain explicit to prevent a monolith from becoming an untestable route-handler collection. Offline events and audit history require more careful schema design in later phases, but the foundation does not need to be replaced.

## Alternatives rejected

- Microservices: unnecessary operational complexity before domain boundaries are proven.
- Frontend-only tenant filtering: not an authorization boundary.
- Permanent driver/tipper columns: would rewrite or misrepresent history when assignments change.
- Client-only event storage: loses critical actions under weak connectivity and cannot guarantee idempotency.

