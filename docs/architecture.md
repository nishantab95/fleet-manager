# Architecture

## Decision

Fleet Manager is a modular monolith in a monorepo. The backend is one FastAPI
deployment with explicit domain services, SQLAlchemy models, and one
PostgreSQL database. Mobile and web clients remain separate shells and do not
contain Phase 1 business workflows.

## Phase 1 and Phase 2 backend boundaries

- `fleet_api.db.models`: persistence models grouped by company, membership,
  assignments, devices, events, and audit concerns.
- `fleet_api.domain`: invariant-protecting services and domain enums. The
  route layer is not used for Phase 1 CRUD.
- `migrations/versions/0002_core_domain.py`: the authoritative PostgreSQL
  schema migration, including composite tenant foreign keys, checks, indexes,
  event idempotency, and assignment exclusion constraints.
- `fleet_api.auth`: phone normalization, OTP challenges, pre-session tokens,
  server-side sessions, refresh rotation, and authorization predicates.
- `fleet_api.api.dependencies`: authenticated request context, role checks,
  tenant consistency, and supervisor site-access dependencies.
- `migrations/versions/0003_authentication.py`: OTP challenge and
  authentication-session persistence.

The API exposes the Phase 0 `/health` and `/ready` endpoints plus the Phase 2
authentication routes under `/api/v1/auth`. Admin CRUD, operational business
routes, and sync endpoints remain later-phase work.

## Phase 2 authentication boundary

- `fleet_api.auth.phone` normalizes input to canonical E.164 values. A default
  region is configuration, not a hardcoded country assumption.
- `fleet_api.auth.service` owns OTP challenge state, membership selection,
  server-side session state, refresh rotation, logout, and authorization
  predicates.
- `fleet_api.auth.tokens` issues short-lived JWT pre-session and access tokens.
  Access tokens carry user, membership, company, role, and session identity;
  every authenticated request revalidates the session and active membership in
  PostgreSQL.
- Refresh tokens are opaque high-entropy values. Only their hashes are stored,
  and rotation uses a previous hash only to detect replay and revoke the
  entire session family.
- `fleet_api.api.dependencies` is the HTTP authorization boundary. Routes use
  the authenticated membership/company context rather than trusting a client
  supplied company ID. Supervisor site access is checked against the explicit
  company-scoped grant table.

The Phase 2 API surface is intentionally small: request/verify OTP, list
memberships, create a selected-membership session, refresh, logout, and `me`.
The default provider is unavailable; no fake provider is selectable through
production configuration.

## Tenant boundary

`Company` is the tenancy root. Company-owned rows carry a non-null
`company_id`; relationships that could otherwise cross tenants use composite
foreign keys such as `(company_id, site_id)` and `(company_id,
driver_membership_id)`. Domain services also load records by identity and
validate company scope before flushing a transaction. Client-supplied company
IDs are not authorization. The authenticated membership and its company are
the source of tenant context, and the persistence boundary uses composite
foreign keys to reject cross-tenant relationships.

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
constraint is the database idempotency boundary. The domain service handles a
unique-key race inside a savepoint and reloads the committed envelope, so
retries resolve to the same logical event without poisoning the caller
transaction. Verification history is a separate append-only table and is not
sync state.
