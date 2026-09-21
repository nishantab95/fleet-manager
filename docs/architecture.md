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

The API exposes the Phase 0 `/health` and `/ready` endpoints, authentication
under `/api/v1/auth`, Phase 3 administration under `/api/v1/admin`, and the
Phase 4 driver boundary under `/api/v1/driver`. Supervisor verification remains
later-phase work.

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
Phase 3 adds `/api/v1/admin` management routes for sites, owned tippers,
people/memberships, supervisor site access, and assignments. Every admin route
requires an authenticated `OWNER_ADMIN` membership and derives the company
from that context. The default OTP provider is unavailable; no fake provider
is selectable through production configuration.

## Phase 3 management boundary

`fleet_api.domain.admin.AdminService` is the application service for the web
administration surface. Routes remain transport adapters: they validate
schemas, translate domain failures to stable HTTP errors, commit transactions,
and delegate business rules to the service or the existing asset/assignment
domain services.

Management uses status changes instead of destructive deletion for sites,
tippers, and memberships. People creation associates an existing global User
by normalized phone or creates one, then creates only DRIVER or SUPERVISOR
memberships; owner/admin privilege is not granted through this onboarding
flow. Assignment creation reuses the existing effective-dated overlap
constraints and rejects inactive or cross-company resources before creation.

The web shell performs phone OTP, membership selection, owner-role gating, and
real API calls for each administration area. Access and refresh tokens are
held only in runtime memory; a reload requires authentication again, and the
browser never writes a refresh token to localStorage.

## Phase 4 driver and sync boundary

The driver client captures exactly four event types. It stores an immutable
assignment snapshot and client event UUID in a local Drift queue before any
network call. Sync uploads required private evidence first, submits the event
envelope second, refreshes an access token at most once per attempt, and keeps
retryable failures in the queue with bounded delay. Secure storage holds mobile
session tokens and the installation identifier; event payloads do not contain
company IDs supplied by the user.

The backend derives the assignment from the authenticated driver and event
timestamp. It registers an installation-scoped device, enforces the
company/client UUID idempotency boundary, checks duplicate ownership by driver
and device, and persists private evidence metadata only after object storage
accepts the object. `EvidenceObject` keys are server-generated and contain no
user-provided path segments.

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
