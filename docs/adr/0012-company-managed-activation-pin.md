# ADR 0012: Company-managed activation and device PIN

## Status

Accepted for Build 28. The role-selection and local-unlock portions are
superseded by ADR 0013; the activation, device binding, fallback PIN, reset,
and backward-compatibility decisions remain in force.

## Context

Firebase phone authentication remains a supported integration, but SMS cost
and external delivery requirements make it unsuitable as a mandatory login
dependency for the current company rollout. The Fleet database, memberships,
roles, sessions, and authorization checks must remain authoritative, and Pilot
fixed OTPs must never become customer credentials.

## Decision

- Add the explicit `company_pin` auth mode while preserving `pilot` and
  `firebase` code paths.
- An authenticated Owner generates a cryptographically random six-digit code
  for an existing active Person. The server stores only a salted challenge
  hash, expires it after 24 hours, limits attempts, consumes it once, and
  cancels older codes when a replacement is generated.
- Successful activation creates one company/User device credential bound to a
  hashed installation identifier. The raw high-entropy credential is returned
  once to Flutter and stored only in platform secure storage.
- The user creates an exactly six-digit PIN. The server stores only a random-
  salt, 600,000-iteration PBKDF2-HMAC-SHA256 hash and enforces failed-attempt
  counting plus a temporary lock. No role or company is accepted from login
  input.
- PIN authentication issues the existing membership-scoped access/refresh
  session. Existing per-request membership, role, tenant, assignment, refresh
  rotation, logout, and session-revocation checks are unchanged.
- Owner reset revokes all sessions and device credentials for the Person in
  that company before generating a replacement code. A reinstall or new phone
  lacks the secure device credential and requires this reactivation flow.
- Android backup is disabled for the company build so secure login material is
  not restored onto a fresh installation.

## Consequences

Migration `0024_company_pin_auth` is additive. Existing Users, memberships,
assignments, sessions, Firebase identities, and operational history are not
deleted or rewritten. The Firebase dependency and implementation remain
available for a future `firebase` deployment, but Firebase Admin credentials
are not loaded or required in `company_pin` mode.

The Owner sees an activation code only in the generation response. Audit logs
contain internal identifiers and safe counts, never activation codes, PINs,
device credentials, or their hashes. Losing the secure device credential is
intentionally unrecoverable without Owner reset.

## Alternatives rejected

- Reusing Pilot fixed OTPs: they are test fixtures and would create shared,
  non-revocable customer credentials.
- Storing PINs locally or in plaintext: this would expose a low-entropy secret
  and bypass server-side lockout and lifecycle checks.
- Replacing Fleet sessions or roles with a new auth store: this would duplicate
  authorization state and violate the existing membership boundary.
