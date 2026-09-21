# Architecture

## Decision

Fleet Manager is a modular monolith in a monorepo. The backend is one FastAPI deployment with explicit modules and one PostgreSQL database. Mobile and web clients are separate applications that communicate with the versioned API.

This keeps deployment, transactions, tenant boundaries, and audit behavior understandable while the owned-tipper workflow is validated in production. New modules must earn additional infrastructure; Redis, workers, brokers, and microservices are not part of the foundation.

## Repository boundaries

- `services/api`: HTTP, application services, domain rules, persistence, migrations, authentication, authorization, and storage adapters.
- `apps/mobile`: Android-first Flutter client with UI/domain/data separation and a local event queue.
- `apps/web`: Next.js TypeScript client for owner/admin workflows and later supervisor workflows.
- `infra`: local infrastructure configuration only; production services remain replaceable.
- `docs`: contracts and architectural decisions.

The backend route layer will remain thin. Business rules belong in domain/application services, and SQLAlchemy models remain separate from Pydantic API schemas.

## Runtime foundation

The API currently provides `/health` and `/ready`, environment-backed settings, SQLAlchemy engine/session configuration, an Alembic migration boundary, JSON logs, and request IDs. Business tables and authenticated routes are intentionally deferred to Phase 1 and Phase 2.

PostgreSQL is the system of record. Object storage is represented by an S3-compatible configuration boundary; MinIO is used only for local development. The storage adapter must not leak provider-specific behavior into domain services.

## Tenant and authorization boundary

Every future business row will carry a non-null `company_id`, with foreign keys and indexes. The authenticated principal determines the authorized company; a client-provided company ID is never sufficient authorization. Query/service methods will require a company scope, and supervisor site permissions and driver active-assignment permissions will be enforced server-side.

The foundation does not yet implement authentication or business authorization. Adding those in a later phase must include negative tests before routes are considered usable.

## Operational event flow

The mobile app will create an event UUID and durable local record before attempting network transmission. Sync status (`LOCAL_ONLY`, `PENDING_SYNC`, `SYNCED`, `SYNC_FAILED`) is separate from business verification (`PENDING_VERIFICATION`, `APPROVED`, `REJECTED`, `DISPUTED`, `AMENDED`). Server receive time is recorded independently from the device timestamp. Event UUID uniqueness is a database constraint, not only an application check.

Assignments are effective-dated. Events reference the assignment that was valid at capture/sync time so future assignment changes cannot rewrite history.

