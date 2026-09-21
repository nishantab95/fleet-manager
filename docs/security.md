# Security Baseline

## Phase 1 protections

- No secrets, passwords, hardcoded production users, or hardcoded tenant IDs
  are added.
- Settings and database connection configuration remain environment-driven.
- Company-owned rows use non-null `company_id` and composite foreign keys to
  prevent cross-tenant relationships at the database boundary.
- Role checks for assignment creation and supervisor site grants remain in
  domain services; Phase 2 adds authenticated HTTP authorization around them.
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

## Phase 2 authentication controls

- Phone numbers are normalized to E.164 using the configured default region
  only when needed. Invalid input is rejected before a challenge is created.
- OTPs are generated with a cryptographically secure source, stored only as a
  salted PBKDF2-HMAC-SHA256 result, expire quickly, have bounded attempts, and
  are protected by a resend cooldown. OTP values are not returned or logged.
- Unknown phone numbers receive the same successful verification shape but no
  usable memberships, limiting account enumeration. Membership selection is
  checked against the user from the pre-session token.
- Access JWTs require signature, issuer, audience, expiry, and typed identity
  claims. The database session, user, membership, company, and role are
  revalidated on every request, so revocation or deactivation takes effect
  immediately.
- Refresh tokens are opaque and stored only as hashes. Rotation preserves the
  previous hash solely for replay detection; presenting it again revokes the
  complete family and records a generic audit event without token material.
- Development OTP is available only with explicit non-production settings.
  The default and production-safe provider is unavailable until a real
  provider is configured, so authentication fails closed rather than silently
  using a fake delivery path.
- HTTP responses use generic authentication failures and do not expose OTPs,
  token values, or raw provider/configuration details.

## Deferred controls

Rate limiting beyond the OTP cooldown/attempt bound, upload scanning, key
rotation, production SMS provider integration, and production secret
management remain follow-up work. The Phase 1 domain services and Phase 2
dependencies are not a substitute for endpoint-specific business validation.
