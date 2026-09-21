# PROJECT_RULES.md

## Project Identity

**Project:** Construction Fleet Operations System  
**Repository:** `D:\Git\fleet maneger`  
**Branch policy:** Work on the existing `main` branch only. Do not create feature branches unless the owner explicitly changes this rule.

This file is the persistent engineering contract for the project. Read it before making changes.

---

# 1. Product Scope

This is initially for a real civil construction company.

## V1 scope: company-owned tippers only

Do not implement yet:

- rented tippers
- excavators
- JCBs
- graders
- rollers
- recruitment marketplace
- WhatsApp integration
- payroll
- accounting
- AI/LLM features
- LangChain
- LangGraph
- continuous GPS tracking
- predictive maintenance
- customer billing

Expansion happens only after the owned-tipper workflow is stable in production.

---

# 2. User Roles

The system has three roles:

1. `OWNER_ADMIN`
2. `SUPERVISOR`
3. `DRIVER`

Authorization must be enforced by the backend. UI hiding is not authorization.

---

# 3. Driver App Contract

The driver's main operational screen must contain only four primary actions:

1. `TRIP COMPLETE`
2. `KM READING`
3. `DIESEL`
4. `EMERGENCY`

The driver must not see:

- number of trips completed
- total KM
- diesel totals
- mileage/efficiency
- salary/payment calculations
- other drivers
- other vehicles
- company financial reports
- site productivity reports

The driver app is a simple event-entry interface.

The backend determines the driver's currently active:

`Driver -> Tipper -> Site -> Supervisor -> Assignment`

The driver must not repeatedly choose vehicle/site when a valid active assignment already exists.

---

# 4. Assignment Is a Core Domain Object

Never permanently attach a driver to a tipper.

Use effective-dated `Assignment` records.

An assignment contains:

- company
- driver
- tipper
- site
- supervisor
- start timestamp
- optional end timestamp

Historical events remain attached to the assignment that was valid when the event occurred.

Changing a future/current assignment must not rewrite historical events.

---

# 5. Trip Event Rules

When the driver presses `TRIP COMPLETE`:

- create a client-generated unique event UUID before sync
- capture device-created timestamp
- capture server-received timestamp after sync
- bind to the active assignment
- initial business state is `PENDING_VERIFICATION`

Repeated sync of the same event UUID must create one logical trip only.

Do not deduplicate separate trip events simply because their timestamps are close together.

Near-simultaneous distinct presses may be flagged as `POSSIBLE_DUPLICATE`, but must not be silently deleted.

---

# 6. KM Reading Rules

Driver selects:

- `START_READING`
- `END_READING`

Then:

- enters odometer KM
- captures meter photo
- submits

Backend/reporting logic calculates:

`distance_km = end_reading - start_reading`

Invalid or incomplete conditions must become explicit exceptions, including:

- end reading lower than start reading
- multiple conflicting start readings
- multiple conflicting end readings
- missing start reading
- missing end reading

Never silently correct business data.

---

# 7. Diesel Rules

Driver enters:

- litres
- supporting photo

Backend associates:

- company
- driver
- tipper
- site
- assignment
- event timestamp

For V1 this is `DIESEL_ISSUED` / `DIESEL_RECORDED`.

Do not call this actual fuel consumption unless a valid consumption-measurement method is implemented later.

Do not calculate km/litre from same-day diesel issued by default.

---

# 8. Emergency Rules

Initial emergency categories:

- `BREAKDOWN`
- `ACCIDENT`
- `TYRE_OR_VEHICLE_PROBLEM`
- `CONTACT_SUPERVISOR`

Record timestamps and lifecycle/status.

Do not market or architect this as a guaranteed emergency-response service.

---

# 9. Supervisor Responsibilities

A supervisor may access only permitted sites.

Supervisor functionality will include:

- review pending trip events
- approve/reject/dispute trips
- verify KM readings
- verify diesel entries
- see missing required readings
- see emergencies
- perform daily site closure

Supervisor authorization must be enforced server-side.

---

# 10. Owner/Admin Responsibilities

Owner/admin manages:

- company
- sites
- owned tippers
- drivers
- supervisors
- assignments

Owner reporting will eventually show:

- active tippers
- approved trips
- pending trips
- start/end KM
- total KM
- diesel issued
- missing readings
- emergencies
- daily closure status
- vehicle/day reports
- Excel export

---

# 11. Architecture

Use a monorepo.

Preferred structure:

```text
apps/
  mobile/
  web/
services/
  api/
infra/
docs/
  adr/
scripts/
```

Use a modular monolith.

Do not introduce microservices.

Do not introduce Redis, Celery, Kafka, RabbitMQ, or other infrastructure unless a concrete requirement justifies them.

---

# 12. Technology Direction

## Mobile

- Flutter / Dart
- Android first
- architecture should remain portable to iOS
- offline-first
- SQLite-backed local persistence
- robust sync queue
- clear UI/domain/data separation

## Web

- React / Next.js
- TypeScript
- strict TypeScript
- owner/admin dashboard
- supervisor web capability may be added later

## Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy 2.x
- Alembic
- PostgreSQL
- typed code
- async only where useful

## Object Storage

- S3-compatible abstraction
- MinIO acceptable for local development
- production storage must be replaceable by a managed S3-compatible service

---

# 13. Version Policy

Before changing the environment, inspect actual installed versions of:

- Git
- Python
- uv or the selected Python package manager
- Node.js
- npm/pnpm
- Flutter
- Dart
- Java/JDK
- Android SDK
- Docker
- Docker Compose

Use current stable and mutually compatible versions.

Pin project dependencies using lockfiles.

Do not silently install arbitrary global/system software that requires elevated privileges or affects unrelated projects.

If a machine-level dependency is missing:

1. identify it
2. give the exact recommended install command
3. continue with work that does not require it
4. report what could not be verified

---

# 14. Backend Engineering Standards

Use:

- Python type annotations
- Pydantic request/response models
- SQLAlchemy models separate from API schemas
- Alembic migrations
- service/domain layer for business rules
- repositories/data-access abstractions only where they improve testability
- FastAPI dependency injection where appropriate

Version APIs under:

`/api/v1/...`

Prefer UUIDs for domain identifiers.

Use UTC internally.

Preserve:

- device event timestamp
- server receive timestamp

Never trust client timestamps as the only source of truth.

---

# 15. Multi-Tenancy

Even though V1 starts with one real company, tenant isolation must be built from day one.

Every business record must belong to a company.

Company A must never retrieve Company B data.

Do not implement tenancy only through frontend filters.

Add automated tenant-isolation tests.

Do not trust a client-supplied company ID without authorization checks.

---

# 16. Authentication and Authorization

Roles:

- `OWNER_ADMIN`
- `SUPERVISOR`
- `DRIVER`

Design authentication so production phone/OTP authentication can be supported.

A secure local-development auth mechanism may exist, but development shortcuts must not be baked into production execution paths.

If passwords are used:

- never store plaintext
- use a strong password hashing library

If tokens are used:

- short-lived access tokens
- use a refresh strategy if implemented

Secrets:

- environment variables or proper secret management
- never commit secrets
- provide `.env.example` only

---

# 17. Offline-First Contract

This is mandatory.

Driver actions must work with weak or zero network.

Every offline event must receive a client-generated UUID before sync.

Backend must enforce idempotency on that event UUID.

Example sync states:

- `LOCAL_ONLY`
- `PENDING_SYNC`
- `SYNCED`
- `SYNC_FAILED`

Business verification states are separate:

- `PENDING_VERIFICATION`
- `APPROVED`
- `REJECTED`
- `DISPUTED`
- `AMENDED`

Never combine sync state with business approval state.

No important user action may silently disappear because of connectivity loss.

---

# 18. Auditability / Immutability

Operational history must be auditable.

Do not silently overwrite approved historical data.

Corrections must preserve:

- actor
- timestamp
- reason
- old value where applicable
- new value

Use an explicit audit/amendment mechanism.

Design an `AuditLog` from the start.

---

# 19. Database Standards

Use database-level constraints where appropriate for:

- uniqueness
- foreign keys
- required company ownership
- event UUID idempotency
- valid status values
- assignment integrity

Add indexes for real expected queries.

Do not rely only on application-side validation.

Do not prematurely optimize.

---

# 20. Security Requirements

From the beginning:

- no committed secrets
- validate API input
- validate upload MIME/type and file size
- sanitize filenames
- do not trust client-supplied company IDs
- avoid PII in logs
- structured logging
- safe CORS configuration
- secure error handling
- no production stack traces
- request/correlation IDs
- never use `verify=False`
- never globally disable TLS verification
- never suppress security warnings globally
- pin dependency versions
- document threat assumptions

---

# 21. Observability

Provide foundation for:

- structured logs
- request IDs / correlation IDs
- health endpoint
- readiness endpoint
- environment-aware log levels

Do not add a large monitoring stack before it is needed.

---

# 22. Testing Standards

Testing is part of implementation, not cleanup.

## Backend

Use:

- pytest
- unit tests
- API integration tests
- database integration tests where useful

At minimum protect these rules:

1. Driver cannot submit for another driver's assignment.
2. Driver cannot access another company's data.
3. Supervisor cannot access an unauthorized site.
4. Repeated sync of one event UUID creates one logical event.
5. Different event UUIDs remain separate even if timestamps are similar.
6. End KM below start KM is rejected or explicitly flagged.
7. Assignment changes do not rewrite historical events.
8. Approved records cannot be silently overwritten.
9. Tenant isolation works.
10. Invalid role access returns the correct HTTP response.

## Mobile

Use:

- unit tests for domain logic
- repository/sync tests
- widget tests for critical screens

## Web

Use:

- component/unit tests for critical logic
- E2E tests later for key flows

Every phase ends by running relevant tests.

---

# 23. Quality Tooling

## Backend

- Ruff
- mypy or pyright
- pytest

## Web

- ESLint
- strict TypeScript
- formatter

## Flutter

- `flutter analyze`
- Dart formatter
- tests

## Repository

- `.editorconfig`
- `.gitattributes`
- proper `.gitignore`

Do not disable lint/type checks just to make CI pass.

---

# 24. CI

Maintain GitHub Actions capable of running:

## Backend

- lint
- typecheck
- tests

## Web

- lint
- typecheck
- tests/build

## Flutter

- analyze
- tests

Android APK generation can be added later.

---

# 25. Documentation

Maintain:

- `README.md`
- `docs/architecture.md`
- `docs/domain-model.md`
- `docs/development.md`
- `docs/security.md`
- `docs/adr/`

Use ADRs for meaningful architectural decisions.

Important ADR subjects include:

- modular monolith
- Flutter mobile
- FastAPI backend
- PostgreSQL
- offline-first synchronization
- tenant separation

Documentation must explain decisions and invariants, not merely list files.

---

# 26. Windows Development Contract

Primary development environment is Windows.

Repository path:

`D:\Git\fleet maneger`

Because the path contains a space, scripts must quote paths correctly.

Prefer PowerShell support:

- `scripts/bootstrap.ps1`
- `scripts/dev.ps1`
- `scripts/test.ps1`

Do not require Bash as the only local workflow.

Docker may be used for PostgreSQL and local object storage.

---

# 27. No-Vibe-Coding Rules

Do not:

- generate huge unverified code dumps
- create placeholders and call them complete
- hide failures
- leave critical TODOs without reporting them
- fake successful API behaviour
- create UI controls not wired to real functionality
- hardcode production users
- hardcode company/site/tipper IDs
- bypass auth to make demos work
- silently swallow exceptions
- use broad exception handling without justification
- add unnecessary dependencies
- over-engineer the MVP
- create a giant `utils.py`
- put business rules directly in route handlers
- store critical state only in frontend memory
- rely on client-side authorization
- weaken tests to make new code pass
- change architecture without documenting the reason

Every material change must have a concrete reason.

---

# 28. Phase Discipline

Only implement the phase explicitly requested by the user.

Before implementing a phase:

1. inspect current repository state
2. read this file
3. read relevant architecture/domain/security docs and ADRs
4. run or inspect existing tests
5. identify migrations/schema impact
6. identify auth impact
7. identify offline/sync impact

At the end of every phase:

1. run regression tests
2. run new tests
3. run lint
4. run type checks
5. run relevant builds
6. verify migrations
7. verify no secrets were added
8. report failures honestly
9. list intentional technical debt
10. stop

Do not automatically continue to the next phase.

---

# 29. Current Phase Sequence

1. Phase 0 — foundation/bootstrap
2. Phase 1 — core domain + database
3. Phase 2 — authentication + RBAC
4. Phase 3 — admin APIs + owner/admin web setup
5. Phase 4 — driver mobile shell + four-button contract
6. Phase 5 — offline events + idempotent sync
7. Phase 6 — KM + diesel + emergency workflows
8. Phase 7 — supervisor verification
9. Phase 8 — owner reporting + daily closure
10. Phase 9 — Excel export + E2E + hardening
11. Pilot-hardening phases based on real field usage

Do not add rented tippers until owned-tipper V1 is proven.

---

# 30. Phase 0 Scope

Phase 0 is foundation/bootstrap only.

Expected work:

- inspect repository
- inspect actual local tool versions
- establish monorepo structure
- initialize backend
- initialize PostgreSQL configuration
- configure SQLAlchemy + Alembic
- test infrastructure
- lint/typecheck
- health/readiness endpoints
- structured logging/request ID foundation
- local Docker infrastructure
- initialize web shell
- initialize Flutter shell
- create documentation
- create PowerShell scripts
- create CI skeleton
- write initial domain-model specification
- run all applicable validation

Do not implement production business workflows during Phase 0.

---

# 31. Definition of Done for Every Phase

A phase is not complete because code was generated.

It is complete only when:

- requested functionality exists
- persistence is real
- migrations are valid
- authorization is enforced where relevant
- offline/idempotency requirements are respected where relevant
- tests exist
- regression tests pass
- lint passes
- typecheck passes
- relevant build succeeds
- docs are updated
- no secrets are committed
- known blockers are reported

If any required item cannot be verified, phase status is `PARTIAL` or `FAIL`, not `PASS`.

---

# 32. Required Completion Report

Every Codex phase completion response must include:

1. `PHASE STATUS: PASS / PARTIAL / FAIL`
2. What was inspected first
3. Files created
4. Files modified
5. Migrations added/changed
6. Architecture/domain decisions made
7. Commands executed
8. Tests and results
9. Lint/typecheck/build results
10. Security implications
11. Known limitations or technical debt
12. Blockers
13. Recommended next phase
14. Confirmation that no later phase was started

Never claim success without executing the relevant verification commands.
