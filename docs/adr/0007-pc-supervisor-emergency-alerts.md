# ADR 0007: PC Supervisor Operations Grouping and Emergency Alerts

## Status

Accepted for the final PC V1 refinement.

## Context

The existing Supervisor view rendered Trip, KM, Diesel, and Emergency events as
one chronological list. That made it difficult to review a tipper's daily work,
distinguish START from END odometer readings, or notice an emergency quickly.
The PC workflow also required emergency category/description input even though
the operational intent is an immediate driver signal.

## Decision

Keep the existing authenticated APIs, evidence flow, verification history, and
report calculations. Refine presentation so a permitted site is rendered as
tipper accordion groups with TRIPS, KM READINGS, and DIESEL sections. Trip
sequence is derived only from captured Trip Complete timestamps; no start time
or duration is invented. KM rows use explicit START KM and END KM labels.

Render Emergency events in a separate prominent alert area with driver, tipper,
site, timestamp, status, CALL DRIVER, and Acknowledge/Resolve lifecycle actions.
Emergency records are not normal verification items and are excluded from
normal pending-verification counts. A driver emergency can be submitted with
one action using the current assignment context; legacy category and description
fields remain optional for compatibility. Server-side rapid-repeat protection
deduplicates a short sequence of open emergency signals while preserving the
normal client UUID idempotency boundary.

Owner Operations shows the same open emergency alerts above the existing
dashboard metrics. Browser notifications remain in-app only; mobile push is
outside this phase.

## Consequences

Supervisor authorization, site scoping, evidence authentication, Excel sheets,
and reporting metric semantics remain unchanged. The API adds only authorized
driver-phone data for emergency contact actions and leaves it empty for normal
report events. A future mobile phase can reuse the one-tap event contract
without changing reporting calculations.
