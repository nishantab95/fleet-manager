# ADR 0013: System device authentication and membership workspaces

## Status

Accepted for Build 29.

## Context

Build 28 bound a company device credential to the membership used as
activation provenance. PIN login immediately opened that membership. A person
with multiple active roles could therefore be pinned to one role, and the
normal return flow always required a Fleet-specific PIN.

Fleet must not receive Android lock-screen secrets or biometric data. Existing
Build 28 installations also need to keep working while Build 29 is installed.

## Decision

- Android return unlock uses the maintained Flutter `local_auth` integration.
  It permits the system-supported biometric or device credential and returns
  only an authentication result to Flutter. Fleet never receives the Android
  PIN, pattern, password, face data, or fingerprint data.
- The random Fleet device credential remains in platform secure storage and
  remains bound to the hashed installation identifier on the server. The
  exactly six-digit Fleet PIN remains a server-verified fallback only when
  system authentication is unavailable or unconfigured.
- Company authentication produces a short-lived, company-scoped pre-session
  for the User. It does not select a role. The server returns only current
  active memberships for that User and company.
- Multiple memberships always produce a workspace chooser. Selecting or
  switching a workspace creates a session for the exact selected membership.
  The previous session is revoked on a switch, and foreign, inactive, or
  unassigned memberships are rejected.
- Owner activation is person/company scoped. The membership ID retained in the
  Build 28 table and challenge row is activation provenance only and is not a
  Build 29 authorization decision.
- Existing Build 28 activation and PIN-login endpoints stay available. Build
  29 can exchange an existing, active Build 28 credential through the new
  role-neutral endpoints without reactivation.

## Consequences

No database migration is required after `0024_company_pin_auth`; existing
credential rows are reused. Removing one role revokes sessions for that
membership but preserves the person-level device credential while another
active membership remains. Owner device reset still revokes every session,
credential, and pending activation for the person in that company.

Server authorization remains membership scoped after workspace selection.
Client labels and navigation do not grant roles.
