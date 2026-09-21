# ADR 0003: Phone OTP Authentication and Tenant-Scoped RBAC

## Status

Accepted for Phase 2.

## Context

The Phase 1 domain model has users and company memberships but no authenticated
HTTP identity. Later routes need a reliable way to authenticate a phone owner,
select one of that user's active company memberships, and enforce role and
tenant boundaries without trusting request-body identifiers.

The first production integration does not yet have an SMS provider. The design
must therefore fail closed by default and make any development delivery path
explicit.

## Decision

1. Normalize phone input to E.164 using an optional configured default region.
2. Persist short-lived OTP challenges with a salted PBKDF2-HMAC-SHA256 hash,
   expiry, cooldown, and bounded attempts. Never return or log the code.
3. Verify an OTP into a short-lived pre-session JWT. The client submits that
   token to list active memberships and selects a membership owned by the
   authenticated user.
4. Issue a short-lived HS256 access JWT plus an opaque refresh token. The
   server stores only the refresh hash and validates the access token against
   an active database session on every request.
5. Rotate refresh tokens. A replayed previous token revokes the whole family.
   Logout revokes the server session, and inactive users/memberships/companies
   immediately invalidate access.
6. Put role, tenant, and supervisor-site checks in reusable dependencies and
   domain predicates. The authenticated membership is the only tenant context;
   client-supplied company IDs are consistency checks, not authority.
7. Select the unavailable OTP provider by default. The in-memory development
   provider requires explicit non-production configuration, and production
   settings reject both development and fake providers.

## Consequences

This establishes a narrow authentication API and a secure boundary for the
next business routes. It adds database lookups on authenticated requests so
revocation and membership deactivation take effect immediately. A real SMS
provider, operational rate limiting, key rotation, and admin management APIs
remain follow-up work and are not part of this phase.

## Rejected alternatives

- Trusting a client-supplied `company_id` would allow tenant confusion and was
  rejected in favor of deriving context from the selected membership.
- Storing refresh tokens or OTP codes in plaintext would increase breach impact
  and was rejected in favor of one-way representations.
- A fake provider enabled by an ordinary runtime setting was rejected because
  it can accidentally ship to production; development delivery is explicitly
  gated.
