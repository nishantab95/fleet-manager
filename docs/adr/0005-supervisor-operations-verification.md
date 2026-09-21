# ADR 0005: Site-Scoped Supervisor Verification

## Status

Accepted for Phase 5.

## Context

Supervisors need a small operational review surface for assigned sites after
drivers begin submitting offline events. The workflow must protect company and
site boundaries, preserve the reason and actor for every decision, and avoid a
second client codebase. Two supervisors may also review the same event at the
same time.

## Decision

Extend the existing authenticated Next.js web shell with a `SUPERVISOR` view.
The backend exposes `/api/v1/supervisor` routes and requires both the
`SUPERVISOR` role and an explicit `SupervisorSiteAccess` row for every site,
event, emergency, and evidence operation.

Verification requests include the status the reviewer observed. The service
locks the event row and returns `409 Conflict` when that status is stale.
Rejected and disputed decisions require a reason and append an
`EventVerification` record; batch approval invokes the same per-event path.
Emergency acknowledgement remains a separate audited lifecycle action.

Completeness is a derived, UTC-date view per assigned tipper. It reports
missing start/end KM readings, pending trip/diesel decisions, and unresolved
emergencies. It does not calculate totals or expand the product scope.

## Consequences

The existing web authentication, styling, and deployment remain sufficient for
Phase 5, and the backend remains authoritative even if a client is modified.
Optimistic concurrency gives reviewers a clear reload path without silent data
loss. The supervisor UI is intentionally operational rather than a reporting
or accounting surface; later work may revisit browser session hardening and
broader workflows without changing these authorization and history rules.
