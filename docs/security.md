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
secrets, tokens, credentials, uploaded content, and unnecessary PII. Phase 4
validates evidence MIME type and size, uses server-generated provider-neutral
private keys, scopes metadata by company/membership/event, and removes an
object on metadata-flush failure when the provider supports deletion. Malware
scanning, content inspection, and production secret management remain deferred
controls.

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

## Phase 3 management controls

- All management routes require the backend `OWNER_ADMIN` dependency. Hiding
  a web tab is only convenience; supervisor and driver sessions receive a
  backend `403`.
- Admin queries scope by the authenticated company and return a generic
  `NOT_FOUND` for foreign resource identifiers, reducing cross-tenant
  existence leakage. Foreign memberships, sites, tippers, and assignment
  resources are rejected by the service/domain layer before writes.
- Onboarding may create or associate a global User, but can create only
  DRIVER or SUPERVISOR memberships. It cannot self-escalate to
  `OWNER_ADMIN`. Deactivation is a membership status change and immediately
  invalidates that identity on subsequent authenticated requests.
- Site grants require a same-company SUPERVISOR membership and Site. Assignment
  creation reuses role, tenant, active-resource, and PostgreSQL overlap rules.
- The web shell stores tokens in React runtime state only. It does not use
  localStorage and clears the session on logout; backend authorization remains
  authoritative.

## Phase 4 driver controls

- Driver routes require a live authenticated `DRIVER` membership. The current
  assignment response contains only the driver's active tipper, site, and
  supervisor context; no company-wide data is exposed.
- Device registration is company- and membership-scoped. Duplicate client UUID
  retries must match the original driver and device, preventing a second driver
  from replaying another driver's event.
- Evidence uploads allow only configured image MIME types and a bounded byte
  size. Object storage is private; the API returns an opaque server key rather
  than a public URL.
- The mobile queue writes event data before attempting network sync, never logs
  access or refresh tokens, and refreshes an expired access token at most once
  before retaining the event for a later retry.

## Phase 5 supervisor controls

- Supervisor routes require an active `SUPERVISOR` membership and verify an
  explicit same-company `SupervisorSiteAccess` row for every site-scoped read,
  decision, acknowledgement, and evidence request. Owners and drivers receive
  `403` from this boundary; cross-company data is not returned.
- Individual verification uses an expected status with a row lock. A stale
  decision returns `409` and cannot silently overwrite another supervisor's
  result. Rejection and dispute require a non-empty reason.
- Verification history is append-only and records the supervisor membership,
  status, reason, and timestamp. Batch approval calls the same individual
  decision path, preserving per-event records. Emergency acknowledgement is an
  audited lifecycle change.
- Evidence remains private. Supervisors receive bytes only after event and site
  authorization succeeds; no public object URL is exposed. Daily completeness
  is scoped to assigned tippers and reports missing readings, pending decisions,
  and unresolved emergencies without introducing financial or operational totals.

## Phase 6 reporting and closure controls

- Owner report routes require `OWNER_ADMIN`; closure reads/actions additionally
  authorize a permitted supervisor site. Every report derives company scope
  from the authenticated membership and returns no foreign site, tipper, event,
  or evidence data.
- Reporting ranges are calculated from the company IANA timezone and converted
  to UTC for queries. The closure stores the timezone and day-start snapshot so
  a later settings change cannot reinterpret a historical close.
- Official totals use approved event status only. Pending, disputed, rejected,
  ambiguous KM, and unresolved emergency states stay visible as separate
  exceptions. Diesel is labelled issued/recorded and no consumption or
  efficiency metric is derived.
- Close/reopen transitions append both a closure-history row and an audit log.
  Structured blockers prevent a close; only an owner can reopen a closed day,
  and the reason is mandatory. A supervisor cannot bypass blockers or use a
  foreign site's route.
- Excel output is generated from the same tenant-scoped report object as the
  JSON API. The workbook contains no macros, tokens, object-store keys, or
  session data. Text values beginning with `=`, `+`, `-`, or `@` are prefixed
  before cell creation to prevent formula injection.

## PC Role Lab controls

- Browser access tokens remain in React runtime memory only; no access or
  refresh token is written to localStorage or sessionStorage.
- Browser refresh uses the existing HttpOnly `fleet_web_refresh` cookie and
  `/api/v1/auth/web-refresh`, then resolves identity through `/api/v1/auth/me`.
- `/driver-test` is disabled unless `NEXT_PUBLIC_ENABLE_DRIVER_QA=true` is
  explicitly configured. A disabled route is not an authentication bypass.
- Driver QA uses the authenticated `DRIVER` role, the real current assignment,
  `WEB` device platform, private evidence upload, and the existing event API.
- Pilot reset accepts only the named `Pilot Construction` fixture, refuses
  production, requires explicit confirmation, and never deletes arbitrary
  company data.

## Deferred controls

Phase 7 adds a hashed source-address OTP cooldown in addition to the
per-phone cooldown, magic-byte checks for configured image types, explicit
security headers, and production profile validation. The PC Role Lab already
uses the browser HttpOnly refresh-cookie adapter described above. A real SMS
provider is still an integration boundary and must be configured explicitly;
the unavailable provider fails closed.

Malware scanning/content inspection, automated key rotation, and a full BFF
that removes the browser access token from JavaScript remain follow-up work.
The current browser access token is short-lived, runtime-only, protected by
backend authorization, and never written to localStorage; the longer-lived
refresh credential is now HttpOnly/SameSite. The Phase 1 domain services and
Phase 2 dependencies are not a substitute for endpoint-specific validation.

## Controlled internal pilot policy

The one-tipper internal pilot may use an explicitly enabled development/test
OTP provider and controlled local connectivity. This is not an Internet or
production deployment: public exposure and plaintext authentication traffic are
forbidden, and HTTPS/TLS plus a real OTP provider are required before broader
rollout. Evidence MIME/signature, size, private-key, storage, and authorization
controls are the pilot baseline; malware scanning/content inspection remains a
required pre-production follow-up.
