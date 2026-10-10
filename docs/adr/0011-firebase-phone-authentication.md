# ADR 0011: Firebase phone authentication

## Status

Accepted for implementation. Production enablement remains a separate deployment decision.

## Context

Fleet Manager's pilot authentication used server-generated development OTP codes. That flow is useful for controlled local demonstrations, but it is not an Internet-facing phone-verification service. The production path needs a supported SMS verification provider while preserving PostgreSQL as the authority for companies, People, memberships, roles, lifecycle state, and authorization.

Firebase Authentication provides the phone-number verification ceremony and a signed ID token. It does not own Fleet users or roles.

## Decision

- Authentication mode is explicit: `pilot` or `firebase`. Production profiles reject pilot mode at startup.
- Pilot mode retains the controlled test codes and existing local workflow. Firebase endpoints fail closed in pilot mode, and pilot OTP endpoints fail closed in Firebase mode.
- The mobile client signs in with Firebase Phone Authentication and sends the resulting Firebase ID token to the API over TLS.
- The API verifies token signature, issuer, audience/project, expiry, revocation when configured, and that the Firebase sign-in provider is `phone`. It never accepts a client-supplied role, company, or phone as proof.
- PostgreSQL remains the canonical identity and authorization store. A verified phone must resolve to exactly one eligible existing `User` with at least one active membership in an active company. Unknown, ambiguous, inactive, or disabled identities are denied; successful authentication never auto-creates a User or membership.
- `user_auth_identities` durably links a Firebase UID to a Fleet User. A provider subject cannot link to multiple users, and one active Firebase identity cannot silently replace another for a user.
- First successful login links the verified Firebase UID to the single exact normalized phone match. Later logins resolve the durable subject link and recheck User, company, and membership status before Fleet tokens are issued.
- The API issues the existing short-lived Fleet pre-session, membership-scoped access token, opaque rotating refresh token, and server-side session. Firebase tokens are not Fleet authorization tokens.
- If a user has one authorized membership, the client selects it automatically. If there are several, the client displays only memberships returned by the API. A role is never chosen before Firebase verification.
- Owner phone edits are guarded. Collisions are rejected, users shared with another active company cannot be changed by one tenant, and changing a phone disables the prior Firebase link until the new number is verified.
- Mobile logout revokes the Fleet session, signs out of Firebase, clears secure session material, and deactivates the local account scope without deleting offline business records.

## Security and privacy consequences

Authentication audit records contain event type, internal IDs, provider, and safe reason codes. They do not contain OTPs, Firebase ID tokens, refresh/access tokens, credentials, or full phone numbers. Authentication failures return stable messages rather than raw Firebase exceptions.

Firebase service-account JSON and generated platform configuration containing project-specific identifiers must not be committed. Backend credentials use Application Default Credentials or a secret-mounted file outside the repository. Mobile project values are supplied at build time. Development and production use separate Firebase projects.

## Operational consequences

Migration `0023_user_auth_identity` is additive and preserves all existing Users, memberships, sessions, operational data, and offline data. It may be applied directly from `0022`; no database reset is required.

The implementation is merged on `main`. Development and staging use a
dedicated non-production Firebase project and the existing disposable Fleet
test database; they do not create a second permanent business database.
Migration and authentication regression checks must still cover fresh-to-head
and prior-head-to-current-head upgrades. The eventual production migration
adds authentication links to the same canonical database, so People, Assets,
Duties, and history require no re-entry or business-data migration.

Firebase delivery limits, abuse protection, APNs/iOS setup, Android SHA fingerprints, Play Integrity/device behavior, and real-device SMS delivery are external operational concerns. CI and automated tests use provider adapters and Firebase console test numbers; they do not send SMS.

## Alternatives rejected

- Storing roles or tenant claims only in Firebase custom claims: this would duplicate and stale the PostgreSQL authorization model.
- Creating Fleet People automatically after any verified phone login: this would bypass owner-controlled onboarding.
- Treating the Firebase ID token as the Fleet API bearer token: this would bypass membership selection, server-side Fleet sessions, and revocation rules.
- Keeping pilot codes enabled as a production fallback: this would create a downgrade path.

