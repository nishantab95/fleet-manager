# ADR 0004: Initial Owner/Admin Web Session Handling

## Status

Accepted for Phase 3.

## Context

Phase 3 needs a functional owner/admin web surface that uses the Phase 2
authentication flow. The current web app is a static Next.js shell, and there
is not yet a server-side web session or BFF layer. Storing a refresh token in
browser persistent storage would make a later XSS compromise more durable.

## Decision

The initial Phase 3 shell called the versioned FastAPI auth and admin APIs directly.
After phone verification and membership selection, it keeps access and
refresh tokens in React runtime state only. It clears that state on logout and
does not write either token to localStorage, sessionStorage, cookies, or the
URL. A reload therefore requires a new authentication flow.

This is the historical Phase 3 decision. Stage A supersedes its reload
behavior with the shared browser session adapter documented in ADR 0006.

The backend remains the authorization authority: the web checks the selected
role for navigation, while every management endpoint requires the authenticated
`OWNER_ADMIN` membership and derives tenant context from the access token and
database session.

## Consequences

This kept the first administration shell simple and avoided persistent browser
refresh-token exposure. Stage A supersedes the reload behavior: the hardened
browser session adapter now uses the existing HttpOnly/SameSite
`fleet_web_refresh` cookie through `/api/v1/auth/web-refresh`, while the access
token remains runtime-only. A full BFF that removes the access token from
JavaScript and adds CSRF protection remains future hardening work.
