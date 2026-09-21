# ADR 0002: Core domain model and PostgreSQL integrity

- Status: Accepted for Phase 1
- Date: 2026-09-21

## Context

The product needs a tenant-safe owned-tipper core before authentication,
admin APIs, mobile synchronization, or business UI. Historical operational
records must retain the assignment under which they were captured, and retries
from offline clients must not create duplicate logical events.

## Decisions

### Identity and membership

`User` is a global application identity. `CompanyMembership` is the
company-scoped relationship and stores exactly one role from `OWNER_ADMIN`,
`SUPERVISOR`, and `DRIVER`. This preserves the option for one identity to
belong to more than one company without placing tenant role state on a global
user row. OTP and authentication are not implemented yet.

### Assignments and overlap

`Assignment` links driver membership, supervisor membership, company-owned
tipper, company-owned site, and an effective `[starts_at, ends_at)` interval.
The migration enables PostgreSQL `btree_gist` and adds GiST exclusion
constraints for `(company_id, driver_membership_id, time_range)` and
`(company_id, tipper_id, time_range)`. This protects open and historical
intervals under concurrent transactions. The `ends_at > starts_at` check is
also database-enforced and service-validated.

### Tenant scoping

`company_id` is intentionally denormalized on memberships, sites, tippers,
devices, assignments, events, verification history, and audit logs. Composite
foreign keys use that column to make cross-company references impossible at the
database level, while service methods provide clear domain errors before the
flush where possible.

### Event idempotency

`OperationalEvent` is the shared event envelope. Its unique
`(company_id, client_event_uuid)` constraint makes retries idempotent without
confusing close timestamps. The domain service catches a unique-key race in a
savepoint and reloads the committed envelope, while preserving the database
constraint as the authority. Four one-to-one subtype tables hold trip, KM,
diesel, and emergency payloads. Sync state is deliberately absent from the
server business model; local-only/pending-sync state belongs to the future
mobile database.

### Verification history and audit

The event envelope stores current `VerificationStatus`, while every change is
an `EventVerification` row with actor membership, reason, and timestamps.
`AuditLog` is a small explicit append-only model for important changes. It is
not a magical ORM auditing hook and callers must provide safe old/new values.

## Consequences

The Phase 1 schema protects the highest-value invariants before HTTP
authorization exists. PostgreSQL-specific integration tests are required for
the exclusion constraints and tenant foreign keys. Additional authenticated
query dependencies and API schemas must be added in Phase 2 without bypassing
these database boundaries.
