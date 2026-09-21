# Security Baseline

## Phase 1 protections

- No secrets, passwords, hardcoded production users, or hardcoded tenant IDs
  are added.
- Settings and database connection configuration remain environment-driven.
- Company-owned rows use non-null `company_id` and composite foreign keys to
  prevent cross-tenant relationships at the database boundary.
- Role checks for assignment creation and supervisor site grants are in domain
  services; Phase 2 will add authenticated HTTP authorization around them.
- PostgreSQL checks and enums constrain statuses, roles, event categories,
  odometer values, diesel litres, and assignment intervals.
- Client event UUID idempotency is a database unique constraint, while server
  receive time is recorded independently of the client timestamp.
- Audit and verification records preserve actor, time, reason, and state
  history without introducing a generic request-body logger.

## Data handling

Audit values are explicit caller-provided JSON fields. Callers must omit
secrets, tokens, credentials, uploaded content, and unnecessary PII. Object
references are placeholders only; upload validation, scanning, MIME allowlists,
size limits, and sanitized provider-independent keys remain future work.

## Deferred controls

Authentication, phone/OTP support, access/refresh tokens, backend RBAC,
tenant-scoped request dependencies, rate limiting, upload scanning, key
rotation, and production secret management are intentionally deferred to Phase
2 or later. The Phase 1 domain services are not a substitute for HTTP
authorization.
