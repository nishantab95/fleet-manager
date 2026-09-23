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
under `/api/v1/auth`, Phase 3 administration under `/api/v1/admin`, the Phase 4
driver boundary under `/api/v1/driver`, and Phase 5 supervisor operations under
`/api/v1/supervisor`.

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

The initial web shell performed phone OTP, membership selection, owner-role
gating, and real API calls for each administration area. Stage A keeps the
access token in runtime memory and uses the HttpOnly refresh-cookie adapter
described below for reload restoration; the browser never writes a refresh
token to localStorage.

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

## PC Role Lab web boundary

The web client remains one Next.js application with route-specific workspaces:
`/login`, `/owner`, `/supervisor`, and `/driver-test`. Shared browser
authentication keeps the short-lived access token in React runtime state and
uses the existing `/api/v1/auth/web-refresh` HttpOnly cookie on reload. The
backend remains the authorization authority; route guards are convenience
only. Owner reporting calls the existing report APIs, Supervisor is an
`INTERNAL / QA REFERENCE`, and Driver QA is a development/pilot-only client
behind `NEXT_PUBLIC_ENABLE_DRIVER_QA=true`.

The Driver QA client registers `DevicePlatform.WEB`, obtains the current
assignment from `/api/v1/driver/assignment/current`, uploads evidence through
`/api/v1/driver/evidence`, and submits `/api/v1/driver/events`. It does not
write PostgreSQL, synthesize acknowledgements, or calculate driver totals.

## Phase 5 supervisor verification boundary

The supervisor web shell uses the existing authenticated web application. A
`SUPERVISOR` membership can list and review only sites granted through its
company-scoped `SupervisorSiteAccess` rows; owners and drivers are denied by the
backend role dependency even if they call the routes directly. Site review is
date-scoped and shows each captured trip, KM, diesel, and emergency event with
driver/tipper identity, evidence availability, current decision, and append-only
history.

Individual decisions use an expected current verification status and a row lock.
If another supervisor has changed the event, the stale decision returns a
conflict instead of overwriting it. Reject and dispute decisions require a
reason and append an `EventVerification` row; batch approval loops through the
same individual decision path so each event retains its own history. Emergency
acknowledgement is a separate audited lifecycle action. Completeness is derived
per assigned tipper and UTC review date, reporting missing start/end readings,
pending trip/diesel decisions, and unresolved emergencies. Private evidence is
read through an authorization-checked API response rather than a public URL.

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

## Phase 6 reporting and closure boundary

`fleet_api.domain.reporting.ReportingService` is the single calculation path
for the owner dashboard, site/day report, tipper/day report, exception list,
closure blockers, and Excel export. It scopes assignments and events to the
authenticated company, follows `event -> assignment -> site` for historical
ownership, bulk-loads subtype/evidence/verification data, and does not use a
tipper's current location as history.

`Company.reporting_timezone` and `Company.operational_day_start_minutes`
define the operational day. The service converts the local wall-clock range
to UTC for event queries; timestamps remain timezone-aware UTC values in the
database. Only effective `APPROVED` events contribute to official trip,
diesel-issued, and KM values. Pending, disputed, and rejected records remain
separate and produce explicit exceptions where appropriate.

`SiteDailyClosure` stores the company/site/operational-date closure snapshot;
`SiteDailyClosureHistory` and `AuditLog` preserve every close and reopen
action. `OPEN` and `REOPENED` with no blockers are presented as derived
`READY_TO_CLOSE`; close is rejected with structured blockers until the day is
complete. Supervisors may close only permitted sites, while only an owner may
reopen a closed day with a reason.

The Excel route calls the same dashboard report object as the JSON routes and
creates five private, macro-free sheets: Daily Summary, Trip Register, KM
Register, Diesel Register, and Exceptions. User-controlled text beginning
with `=`, `+`, `-`, or `@` is prefixed before writing cells, and no object-store
key or session/token value is exported.

## Phase 7 pilot-hardening boundary

Phase 7 does not introduce a new business service. It hardens boundaries that
already exist: production configuration validation, explicit API and Next.js
security headers, trusted-host checks when configured, and a browser-only
refresh-cookie adapter that keeps refresh credentials out of JavaScript. The
web access token remains runtime-only and is refreshed through the HttpOnly
cookie; mobile refresh tokens remain in secure device storage.

The mobile queue is a durable Drift/SQLite state machine. A row is marked
`syncing` before network work and remains retryable after a process kill. Event
submission and evidence upload use the existing client UUID idempotency
boundary. Diagnostics persist only safe support categories and timestamps;
they never expose payloads or credentials.
