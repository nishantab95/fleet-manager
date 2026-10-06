# Architecture

## Decision

Fleet Manager is a modular monolith in a monorepo. The backend is one FastAPI
deployment with explicit domain services, SQLAlchemy models, and one
PostgreSQL database. Mobile and web clients remain separate shells and do not
contain Phase 1 business workflows.

## Feature-gated operations boundary (2026-10-06)

Nine future modules share one typed, server-authoritative feature registry.
Every flag defaults to false; no environment profile enables a module
implicitly. Disabled endpoints fail closed, and enabling a feature does not
replace authentication, role authorization, or company scoping.

Migration `0018_future_foundations` introduces maintenance schedules/records
and stable asset-document revision identities. Forward migration
`0019_working_future_modules` adds work orders and attachments, document
policies, durable in-app notifications, normalized telematics/geofences,
external fuel imports, and reconciliation. Forward migration
`0020_multi_meter_workforce` adds per-asset meter capabilities, grouped meter
captures, maintenance criteria, telemetry meter discrepancies, compensation,
payroll, and attendance-location evidence. Existing single-meter records and
schedule columns remain intact and are backfilled into the additive model.

The Owner web exposes compact table-first modules only for enabled flags.
Telematics and fuel use local simulation/CSV ingestion and never call an
external provider. Attendance location is event-snapshot corroboration, not
proof of driving and not a payroll deduction input. Toll/expense remains a
contract-only domain adapter. The Flutter Pilot is unchanged and has no new
location permission or background tracking.

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

## Phase 1A fleet-asset foundation

`FleetAsset` is the single canonical persistence record for company fleet.
The `fleet_assets` table replaces the former `tippers` table in place, keeping
every UUID while `assignments.asset_id` and `duty_sessions.asset_id` replace
their former tipper-named foreign keys. Operational events, verification
history, evidence, and closures remain connected through their existing
assignment, duty, event, and site relationships; no parallel vehicle table or
copied history exists.

The model declares `TIPPER`, `EXCAVATOR`, `BACKHOE_LOADER`, `ROLLER`, and
`GRADER`, with `OWNED` and `RENTED` ownership. Registration is nullable for
non-road machinery, while company-scoped `asset_code` is the stable required
identifier. Status-based deactivation preserves assignment and event history.
Composite `(company_id, asset_id)` foreign keys retain the database tenant
boundary.

`AssetCapabilities` is the single workflow capability map. Phase 1A enables
the existing trip, odometer, diesel, emergency, and duty capabilities only for
`TIPPER`; future machinery types are declared but have no Driver workflow.
Ownership is descriptive and does not change tipper operations.

The public 1.0.4 contract remains intentionally tipper-shaped. Existing
`/tippers` routes, report routes, workbook layout, and fields such as
`tipper_id`, `tipper_registration_number`, and `tipper_short_name` are adapters
over `FleetAsset`. Generic management endpoints and UI are deferred to the
next phase.

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
fleet assets, and memberships. People creation associates an existing global User
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
envelope second, and keeps retryable failures in the queue with bounded delay.
The shared mobile API client handles Driver, Supervisor, and Owner authentication:
one access-token `401` starts one single-flight refresh, persists rotated tokens
to secure storage, and retries the original request once. A failed refresh or a
second `401` clears local authentication and returns the nested UI to login;
requests never loop. Secure storage holds mobile session tokens and the
installation identifier; event payloads do not contain company IDs supplied by
the user.

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
date-scoped, groups operational rows by tipper into Trips, KM Readings, and
Diesel sections, and keeps emergencies in a separate prominent alert area with
driver/tipper identity, contact action, lifecycle controls, and append-only
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
Supervisor and Owner web workspaces render those bytes in a modal, while the stable
`/evidence/{event_id}` route authenticates the current session and chooses the
role-scoped evidence endpoint. Report workbooks link to that application route
with `FLEET_WEB_PUBLIC_BASE_URL`; they never embed images or object-storage keys.

## Tenant boundary

`Company` is the tenancy root. Company-owned rows carry a non-null
`company_id`; relationships that could otherwise cross tenants use composite
foreign keys such as `(company_id, site_id)` and `(company_id,
driver_membership_id)`. Fleet relationships use `(company_id, asset_id)`.
Domain services also load records by identity and
validate company scope before flushing a transaction. Client-supplied company
IDs are not authorization. The authenticated membership and its company are
the source of tenant context, and the persistence boundary uses composite
foreign keys to reject cross-tenant relationships.

## Effective-dated assignments

An assignment is the source of operational ownership. It contains the Driver
membership, Fleet Asset, deployment reference, immutable Site snapshot, and a
half-open effective interval. Supervisor authority comes from
`SupervisorSiteAccess`; the nullable supervisor column is legacy history only. The
database enables `btree_gist` and uses PostgreSQL GiST exclusion constraints
over timestamp ranges to protect both driver and asset histories under
concurrent writes. No `current_driver_id` is stored on `FleetAsset`.

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
ownership, bulk-loads subtype/evidence/verification data, and uses generic
asset-domain objects internally. The compatibility API and workbook keep their
current tipper naming and layout; reporting does not use an asset's current
location as history.

`Company.reporting_timezone` and `Company.operational_day_start_minutes`
define the operational day. The service converts the local wall-clock range
to UTC for event queries; timestamps remain timezone-aware UTC values in the
database. Only effective `APPROVED` events contribute to official trip,
diesel-issued, and KM values. Pending, disputed, and rejected records remain
separate and produce explicit exceptions where appropriate. Emergency
lifecycle rows are not normal verification items; only unresolved emergency
status participates in closure blockers.

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

Driver duty, transport sync, and supervisor verification are independent state
machines. A locally valid START makes the duty operationally active before any
network response, so Trip, Diesel, END, and Emergency capture remain available
while START is pending sync or business verification. Normal duty events keep a
local causal chain (`START -> activity -> END`) and are submitted only after the
previous event is accepted. A deterministic START business rejection preserves
the chain as `blockedPendingStartCorrection`; correcting the original START
retains its UUID and releases the chain in order. Emergency has no queue
dependency and is attempted ahead of normal queued work.

Evidence MIME is derived from the file signature and checked against any known
extension before upload. The client sends only `image/jpeg`, `image/png`, or
`image/webp`; the backend remains responsible for its existing MIME, size, and
signature validation.

## Phase 1B.1 Owner Fleet management boundary

Owner Fleet management is a dedicated `/api/v1/owner/assets` surface rather
than unrestricted generic administration. Every route requires an active
`OWNER_ADMIN` membership and derives company scope from that authenticated
membership. Driver and Supervisor sessions receive `403`, while foreign asset
identifiers resolve to the same tenant-scoped `404` used by other management
services.

Creation is intentionally limited to `TIPPER` in this phase. Owned and rented
tippers share the same canonical `FleetAsset` record and operational
capabilities; ownership never selects a different Driver workflow. Rented
assets require a rental party, while changing an asset to owned clears all
rental-only fields. Edits update the existing UUID so assignments, duty
sessions, events, evidence, verification history, and reports remain linked.

Deactivation is a status transition, never a delete. It is rejected while the
asset has an effective assignment or active duty session. The mobile Owner
Fleet tab consumes this API through one reusable, type-aware card and
virtualized scrolling. Assignment identity is read-only here; assignment
mutation remains Phase 1B.2. The PC Fleet CRUD UI is intentionally deferred to
avoid creating a second incomplete management surface in this phase.

## Phase 1B.2A Owner People and Sites boundary

People and Sites are independent company resources exposed through focused
`/api/v1/owner/people` and `/api/v1/owner/sites` APIs. Both require an active
Owner/Admin session and derive tenant scope exclusively from that session. A
People record reuses the canonical `User` identity and adds a company-scoped
Driver or Supervisor membership; the mobile label for Driver is Operator.

Invitations start as `INVITED`. The existing OTP flow includes invited
memberships in membership selection and changes only the selected membership to
`ACTIVE` when a valid session is created. No password or alternate OTP path is
introduced. Sites keep their UUID and may store an optional description and
coordinates. Supervisor access remains the existing many-to-many
`SupervisorSiteAccess` relationship.

All edits and lifecycle actions are audited. Deactivation changes status and
never deletes identity, assignment, duty, access, event, or reporting history.
Active assignments/duties block People and Site deactivation, and Supervisor
access must be removed before that Supervisor is deactivated. Asset deployment
and Driver-to-Asset assignment mutation remain outside this phase. The PC
People/Sites management UI is explicitly deferred; its existing reporting and
operations surfaces are unchanged.

## Driver device handover

The `Device` row represents one app installation and keeps a stable UUID. Its
`membership_id` is the current Driver binding, not permanent employee identity.
A change of Driver uses the explicit `/api/v1/driver/device` handover flow only;
event submission cannot rebind a device. The server rejects a handover while
the previously bound Driver has an active duty and writes a
`DEVICE_DRIVER_HANDOVER` audit entry when reassignment succeeds. Existing
operational events continue to reference the same device UUID and their
original assignment, so historical Driver attribution is unchanged.

The mobile database scopes queues, duty snapshots, current-duty markers, and
sync diagnostics by normalized server URL, company ID, and membership ID.
Unscoped code-8 data is preserved and claimed by the server-reported previous
binding before a handover. A different Driver never reads or submits another
Driver's scoped records.

## Phase 1B.2B Fleet Asset deployment boundary

`AssetSiteDeployment` is the canonical, effective-dated relationship between a
Fleet Asset and a Site. It is separate from `Assignment`: a Site placement may
exist without a Driver, while Assignment continues to describe the operational
Driver/Supervisor relationship. PostgreSQL enforces non-overlapping deployment
intervals and at most one current deployment for an asset. Migration
`0013_asset_site_deployments` backfills current and historical placement from
existing Assignment history without changing Assignment, event, duty, evidence,
or report rows.

The Owner deployment service exposes current placement, history, deploy/move,
remove, and Site asset-list operations. Company scope comes only from the
authenticated Owner membership. Initial deployment selects only an active Site;
Driver and Supervisor selection remain separate. Moving or removing an asset is
blocked while an effective Assignment or active duty exists, and an effective
Assignment can be created only when its Site agrees with the deployment.

Owner Fleet cards and detail views show Site and Driver independently. Owner
Site detail provides the alternate Site-first deployment flow. Supervisor Site
views read the same relationship, so every active deployed asset is visible to
an authorized Supervisor even when it has no Driver and no events. Event review
and Driver reporting remain Assignment-based and retain their existing totals
and behavior.

## Phase 1B.2C Driver / Operator assignment boundary

The existing `Assignment` aggregate owns the Driver/Operator-to-FleetAsset
lifecycle; no second current-driver relationship exists. New rows reference the
current `AssetSiteDeployment`, so Site is derived from physical placement and
stored on Assignment only as a historical snapshot. Assign, unassign, and
reassign preserve half-open history and are audited.

Owners may manage any same-company deployed supported asset. Supervisors may
manage only assets currently deployed to Sites granted through
`SupervisorSiteAccess`; neither flow asks the user to choose a Site or a
Supervisor. Active duty blocks changes. PostgreSQL driver and asset exclusion
constraints remain the concurrency authority.

Driver current-assignment responses expose every active Site supervisor. Owner
People views expose a Driver's current asset and Site. Reports continue to join
events through their historical Assignment and use a compatibility label for
new rows that have no legacy supervisor value.
