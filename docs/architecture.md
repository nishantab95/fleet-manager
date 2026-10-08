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
identifier. Optional chassis and engine identifiers apply to every Asset type;
they are technical detail fields rather than primary list columns. Status-based
deactivation preserves assignment and event history.
Composite `(company_id, asset_id)` foreign keys retain the database tenant
boundary.

`AssetCapabilities` is the single workflow capability map. `TIPPER` uses trip
and odometer capture; `EXCAVATOR`, `BACKHOE_LOADER`, `ROLLER`, and `GRADER` use
hour-meter capture. All current Pilot types support duty, diesel, and emergency
operations. Ownership is descriptive and does not change operations.

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

## Maintenance V2 and meter-capability boundary

Maintenance is an Owner/Admin module built on the canonical `FleetAsset` and
its operational history. `fleet_api.domain.maintenance` owns template matching,
plan materialization, due-state calculation, work-order transitions, service
completion, and immutable maintenance history. The `/api/v1/owner/maintenance`
routes are transport adapters and derive tenant scope from the authenticated
Owner membership.

Maintenance triggers are configured per plan item. Wheeled assets may use any
non-empty combination of calendar date, odometer kilometres, and hour-meter
hours. Non-wheeled/tracked assets may use date and hours, but never kilometres.
Operational meter capabilities remain separate from those task triggers:
`is_wheeled` classifies the asset, while `supports_odometer_km` and
`supports_hour_meter` determine which readings the Driver must capture. A
wheeled asset configured for both meters requires KM and HMR together at duty
start and duty end; a tracked hour-meter asset requires HMR only. Drivers never
enter maintenance calendar dates.

Driver dual-meter capture is one logical, idempotent operation. The mobile
client persists one compound queue record before network work, uploads each
meter's evidence, and submits both readings to `/api/v1/driver/meter-captures`.
The backend validates the exact asset capability set and stores the meter events
under one `capture_group_uuid` in one transaction. Supervisor review and alert
counts group those rows as one capture card, while reporting and maintenance
retain the individual typed readings.

Maintenance templates are versioned setup data. Applying a template copies
compatible task definitions into an asset-owned plan; later template changes do
not rewrite that plan. Specific manufacturer/model/year matches are preferred
deterministically, a generic template may provide descriptive starter tasks,
and no invented OEM interval is supplied. Copying another asset's plan copies
only compatible task definitions and resets all service baselines; it never
copies maintenance history. Work-order completion records decimal costs,
optional notes and references, supplied meter baselines, and the calendar
completion date in an immutable history row.

Migrations `0019_asset_meters` and `0020_maintenance_v2` add the independent
asset capabilities, grouped meter captures, templates, plans, criteria, work
orders, history, and attachment metadata. Historical Pilot tippers are safely
backfilled as wheeled KM assets and historical machinery as HMR assets, so an
upgrade does not suddenly demand a second reading from existing assignments.

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

The configurable Excel route calls the same dashboard report object as the JSON
routes and creates the selected private, macro-free management, tipper,
machinery, trip, meter, diesel, duty, and exception sheets. User-controlled text
beginning with `=`, `+`, `-`, or `@` is prefixed before writing cells, and no
object-store key or session/token value is exported.

The built-in `Simple Site Workbook` is a separate Owner-only presentation over
the same reporting service; it does not replace or modify the configurable
daily export. Its input is exactly one tenant-scoped Site and an inclusive date
range of at most 366 operational days. Effective-dated deployment history
determines which assets receive a sheet, including deployments with no Driver
assignment, while each operational day delegates trip, meter, diesel, and base
status calculations to the existing daily report path. An unassigned deployment
therefore receives a summary/asset sheet but no fabricated work rows.

Multiple duty sessions under one assignment remain one authoritative
assignment/day row using the existing reporting service's first/last meter
aggregate. Displayed duty bounds span the sessions and Duty End remains blank if
any session is active. Pending, disputed, rejected, and amended session events
remain visible in daily status; the Simple workbook does not reinterpret the
authoritative aggregate. A same-day Driver reassignment remains separate rows
but counts as one distinct asset working day. A working day requires a persisted
duty session or a non-emergency operational event, rather than deployment or an
emergency-only record alone.

`Pending Items` counts non-emergency `PENDING_VERIFICATION` events. `Exceptions`
counts non-pending structured report exceptions, each non-emergency `DISPUTED`
event once. The structured `TRIP_DISPUTED` marker is not counted a second time.
`REJECTED` and `AMENDED` remain visible in daily status but are not unresolved
exception counts.

Effective-dated IDs preserve historical relationship attribution; editable
Site, asset, and person labels are not separately snapshotted and therefore use
their current spelling. Regenerated historical ranges also use the company's
current reporting timezone and operational-day start through the existing daily
report service; daily closure records are the component that snapshots those
settings.

The workbook is macro-free and value-based: `SUMMARY` is first, followed by one
deterministically named sheet per historically relevant asset. Unsupported
capability metrics use `N/A`; applicable incomplete distance/HMR totals and
averages use `MISSING`, while authoritative numeric zero remains zero. Tipper
`Distance per Litre Recorded` is `N/A` when verified recorded diesel is zero or
absent and `MISSING` when diesel is positive but required distance is incomplete.
Machinery `Litres Recorded / Machine Hour` is `N/A` when the HMR denominator is
missing, incomplete, or zero. Both ratios use verified diesel recorded/issued
and never claim actual consumption. Partial valid daily values remain visible
where safe, but an incomplete period aggregate is not presented as a complete
total.
Sheet names are sanitized and de-duplicated within Excel's 31-character limit;
all user-controlled cell text retains the formula-injection guard.

Simple Site Workbook uses its dedicated Site/from/to Owner form and endpoint.
It cannot be duplicated, made the default advanced template, or passed to the
advanced `/reports/daily.xlsx` route; Management Summary remains the advanced
fallback. If rollout finds a case-insensitive custom-template name collision,
the custom template is preserved, renamed with a `(Custom)` suffix, and the
rename is audited before the exact built-in name is created.

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

The mobile Driver surface presents that same state machine directly. Off duty,
START DUTY owns required START KM/HMR capture and Emergency remains available.
On duty, only asset-supported work actions are shown, Emergency stays prominent,
and END DUTY owns required END KM/HMR capture at the bottom of the screen. This
removes the standalone primary meter tile without removing meter events,
evidence, correction, offline queue, or idempotency support.

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
assets require a rental Owner/Supplier name and normalized primary phone; an
alternate phone is optional. Changing an asset to owned clears all rental-only
fields. Edits update the existing UUID so assignments, duty
sessions, events, evidence, verification history, and reports remain linked.

Deactivation is a status transition, never a delete. The direct Fleet lifecycle
route rejects it while the asset has an effective assignment or active duty
session; the relationship orchestrator's documented atomic teardown paths are
the only exceptions. The mobile Owner Fleet tab consumes this API through one
reusable, type-aware card and virtualized scrolling. Assignment identity is
read-only here; assignment mutation remains Phase 1B.2. The PC Fleet CRUD UI is
intentionally deferred to avoid creating a second incomplete management surface
in this phase.

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
Driver and Supervisor selection remain separate. Active duty blocks a move or
removal through the ordinary deployment operations. An off-duty Assignment may
be ended with removal or reconciled during a
move by the Owner relationship orchestrator, and an effective Assignment can be
created only when its Site agrees with the deployment.

Owner Fleet cards and detail views show Site and Driver independently. Owner
Site detail provides the alternate Site-first deployment flow. A direct
deployment mutation remains conservative, while the Owner relationship
orchestrator may reconcile an off-duty Assignment and deployment in one
transaction. Active duty blocks ordinary move and removal; the force-close
composite described below is the sole active-duty teardown exception. Supervisor
Site views read the same relationship, so every active deployed asset is visible
to an authorized Supervisor even when it has no Driver and no events. Event
review and Driver reporting remain Assignment-based and retain their existing
totals and behavior.

## Phase 1B.2C Driver / Operator assignment boundary

The existing `Assignment` aggregate owns the Driver/Operator-to-FleetAsset
lifecycle; no second current-driver relationship exists. New rows reference the
current `AssetSiteDeployment`, so Site is derived from physical placement and
stored on Assignment only as a historical snapshot. Assign, unassign, and
reassign preserve half-open history and are audited.

Owners may manage any same-company deployed supported asset. Supervisors may
manage only assets currently deployed to Sites granted through
`SupervisorSiteAccess`; neither flow asks the user to choose a Site or a
Supervisor. Active duty blocks ordinary assignment changes. PostgreSQL driver
and asset exclusion constraints remain the concurrency authority.

Driver current-assignment responses expose every active Site supervisor. Owner
People views expose a Driver's current asset and Site. Reports continue to join
events through their historical Assignment and use a compatibility label for
new rows that have no legacy supervisor value.

## Owner relationship orchestration boundary

`OwnerOperationPlanner` is the shared application service for contextual Owner
changes launched from People, Fleet, and Sites. Normal deployment and Driver
assignment work is consolidated into Fleet's Manage Asset surface; the
effective-dated deployment and assignment domains, APIs, and history remain
unchanged. Legacy browser tab identifiers for Deployments and Assignments are
redirected to Fleet. The
browser submits a business intent and explicit resolution choices to
`/api/v1/owner/operations/preview`; the service reloads the company-scoped
membership, asset, deployment, assignment, duty, Site, and Supervisor-access
state and returns business-language dependencies, blockers, and planned changes.
The UI does not provide authoritative relationship state.

Normal Asset and Person management uses contextual forms with human-readable
Driver and Site selectors. The browser keeps preview, state-token, and execute
as an internal safety protocol instead of presenting the planner as a four-step
Current state / Choose changes / Review / Result wizard. A relationship-changing
or destructive action may use one concise confirmation. Complex Site
deactivation retains the dependency-review workflow because it can affect
multiple relationships and requires explicit resolution choices.

Every preview includes a SHA-256 state token over the normalized intent and the
scoped authoritative rows. Execute repeats the preview with row locks and rejects
a changed token with `409 State changed. Review the operation again.` before any
mutation. The route commits once after the complete operation. A failure rolls
back activation, access, deployment, assignment, lifecycle, and audit writes as
one unit.

The planner can activate or deactivate Driver and Supervisor memberships,
reconcile Supervisor Site access, deploy, move, remove, deactivate, or reactivate
assets, assign or change Drivers, end assignments, and deactivate or reactivate
Sites with optional setup. Asset reactivation may remain undeployed, add a Site,
or atomically reactivate, deploy, and assign an eligible Driver; selecting a
Driver requires a deployment Site and activating an inactive Driver role is
always explicit. It ends effective-dated rows and creates replacements when Site
context changes; it never rewrites historical Site or Driver attribution.
Active duty blocks ordinary Driver changes, Site moves/removal, and lifecycle
teardown.

`FORCE_CLOSE_DUTY_AND_DEACTIVATE_ASSET` is the one narrow administrative
exception. It is available only to an authenticated `OWNER_ADMIN`, requires a
non-empty reason, and uses the same preview/state-token/execute boundary. Execute
authoritatively reloads and locks the tenant-scoped asset, active duty,
Assignment, Deployment, Driver, and Site state. In one transaction it closes the
duty without inventing an END KM/HMR event or evidence, ends the current
Assignment and Deployment, deactivates the asset, and appends an audit record
containing the reason and affected relationship context. Any failure rolls back
the complete teardown, and a changed preview token fails before mutation.

Reporting continues through its existing missing-meter path: a forced close with
no legitimate END reading produces the applicable missing END KM or END HMR
exception and never fabricates distance, machine hours, or evidence. Driver
clients reconcile current assignment and active-duty state from the server after
refresh/sync; cached phone relationship state cannot override the completed
server transition.
