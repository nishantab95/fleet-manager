# ADR 0004: Initial Owner/Admin Web Session Handling

## Status

Accepted for Phase 3.

## Context

Phase 3 needs a functional owner/admin web surface that uses the Phase 2
authentication flow. The current web app is a static Next.js shell, and there
is not yet a server-side web session or BFF layer. Storing a refresh token in
browser persistent storage would make a later XSS compromise more durable.

## Decision

The initial shell calls the versioned FastAPI auth and admin APIs directly.
After phone verification and membership selection, it keeps access and
refresh tokens in React runtime state only. It clears that state on logout and
does not write either token to localStorage, sessionStorage, cookies, or the
URL. A reload therefore requires a new authentication flow.

The backend remains the authorization authority: the web checks the selected
role for navigation, while every management endpoint requires the authenticated
`OWNER_ADMIN` membership and derives tenant context from the access token and
database session.

## Consequences

This keeps the first administration shell simple and avoids persistent browser
refresh-token exposure. It is intentionally not a final production browser
session architecture: a later web hardening phase may add a BFF with
HttpOnly/Secure/SameSite cookies, CSRF protection, and server-side session
rotation. Until then, loss of state on reload is an explicit trade-off.
