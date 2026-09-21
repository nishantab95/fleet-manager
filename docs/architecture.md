# Architecture

## Decision

Fleet Manager is a modular monolith in a monorepo. The backend is one FastAPI
deployment with explicit domain services, SQLAlchemy models, and one
PostgreSQL database. Mobile and web clients remain separate shells and do not
contain Phase 1 business workflows.

## Phase 1 backend boundaries

- `fleet_api.db.models`: persistence models grouped by company, membership,
  assignments, devices, events, and audit concerns.
- `fleet_api.domain`: invariant-protecting services and domain enums. The
  route layer is not used for Phase 1 CRUD.
- `migrations/versions/0002_core_domain.py`: the authoritative PostgreSQL
  schema migration, including composite tenant foreign keys, checks, indexes,
  event idempotency, and assignment exclusion constraints.

The API continues to expose only the Phase 0 `/health` and `/ready` endpoints.
Pydantic/API schemas, authentication, RBAC dependencies, admin CRUD, and sync
endpoints are later-phase work.

## Tenant boundary

`Company` is the tenancy root. Company-owned rows carry a non-null
`company_id`; relationships that could otherwise cross tenants use composite
foreign keys such as `(company_id, site_id)` and `(company_id,
driver_membership_id)`. Domain services also load records by identity and
validate company scope before flushing a transaction. Client-supplied company
IDs are not authorization in this phase because authentication is deferred,
but the persistence boundary is ready for Phase 2 scoped dependencies.

## Effective-dated assignments

An assignment is the source of operational ownership. It contains driver and
supervisor memberships, tipper, site, and a half-open effective interval. The
database enables `btree_gist` and uses PostgreSQL GiST exclusion constraints
over timestamp ranges to protect both driver and tipper histories under
concurrent writes. No `current_driver_id` is stored on `Tipper`.

## Events and verification

`OperationalEvent` is a common envelope for the four event types. It records
server UUID, company, assignment, optional device, client-generated UUID,
device-created time, server-received time, and current verification status.
Subtype tables hold the event-specific payload. The unique company/client UUID
constraint is the database idempotency boundary; verification history is a
separate append-only table and is not sync state.
