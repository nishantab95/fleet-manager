# Security Baseline

## Current protections

- No secret values are committed; `.env.example` contains local-development placeholders only.
- Settings are environment-backed and production configuration must come from a secret manager or deployment environment.
- CORS is explicit and defaults to the local web origin rather than `*`.
- The API emits a request ID and JSON structured logs. Request bodies and credentials are not serialized by the foundation formatter.
- Unhandled API errors return a generic message. Stack traces are logged server-side only.
- SQLAlchemy is configured for parameterized database access; no raw user input is interpolated into SQL.
- Uploaded objects are not implemented yet. Phase 1+ upload work must enforce MIME allowlists, byte-size limits, filename sanitization, and provider-independent object keys.

## Threat assumptions

The API is deployed behind a TLS-terminating edge in production. Client devices may be lost, offline, retried, or tampered with; client timestamps and company IDs are untrusted. The server remains authoritative for tenant, role, assignment, event UUID uniqueness, and server receive time.

The system handles operational and potentially personal data. Logs must avoid phone numbers, tokens, uploaded content, precise personal location, and request bodies. Access to event history is role- and company-scoped.

## Deferred controls

Authentication, phone/OTP support, access/refresh tokens, password hashing if passwords are introduced, backend RBAC, tenant-scoped query dependencies, rate limiting, upload scanning, key rotation, and production secret management are intentionally deferred to the phases that implement those capabilities. They must be implemented before production workflows are exposed.

