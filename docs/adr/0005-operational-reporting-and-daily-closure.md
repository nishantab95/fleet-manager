# ADR 0005: Operational Reporting, Daily Closure, and Excel Export

- Status: Accepted for Phase 6
- Date: 2026-09-22

## Context

Owners need a trustworthy operational-day view over driver events after
supervisor verification. The view must remain tenant-safe, preserve effective
assignment history when a tipper moves sites, make incomplete data visible,
and support a controlled daily close without turning reporting into payroll,
accounting, or fuel-efficiency analytics.

## Decisions

1. **Operational day.** Each Company stores an IANA `reporting_timezone` and a
   local `operational_day_start_minutes` value. A requested local date is
   converted to a half-open UTC range for querying. Database timestamps remain
   timezone-aware UTC values. The closure stores the timezone/start snapshot.

2. **One reporting service.** `ReportingService` is the source of truth for
   dashboard, site/day, tipper/day, exceptions, closure blockers, and Excel.
   Reports follow `OperationalEvent.assignment_id` to `Assignment.site_id`;
   they never infer historical site ownership from current tipper state.

3. **Official totals.** Only current `APPROVED` event records contribute to
   official trip counts, diesel issued, and readings. Pending, disputed, and
   rejected trips/diesel are counted separately. Diesel is issued/recorded,
   not consumed, and no litres/trip or km/litre value is calculated.

4. **KM safety.** Distance is calculated only when exactly one distinct
   approved START and END reading exist and END is not below START. Missing,
   conflicting, or regressing readings produce `null` distance and explicit
   exceptions; the service never chooses MIN/MAX as a hidden correction.

5. **Closure state.** `SiteDailyClosure` persists one row per company/site/
   operational date. `OPEN`/`REOPENED` with no blockers are presented as the
   derived `READY_TO_CLOSE` state. A close is rejected with structured
   blockers for incomplete readings, pending/disputed work, invalid KM, or
   unresolved emergencies. Each transition appends `SiteDailyClosureHistory`
   and an `AuditLog` row.

6. **Authorization.** Owners may view all company reports, close any company
   site, and reopen a closed day only with a reason. A supervisor may view and
   close only an explicitly granted site, and cannot bypass blockers. Drivers
   have no report or closure access.

7. **Excel.** The export calls the already-built dashboard report and writes
   Daily Summary, Trip Register, KM Register, Diesel Register, and Exceptions.
   Headers are bold, panes are frozen, filters and widths are applied, and
   aware datetimes are normalized to naive UTC for Excel compatibility. Values
   beginning with `=`, `+`, `-`, or `@` receive a leading apostrophe.

## Consequences

The owner receives reconciled operational totals and an auditable close
without introducing a second calculation engine or broadening V1 beyond
company-owned tippers. Incomplete or ambiguous records remain operational
exceptions and may require supervisor review. More advanced export formats,
large-scale aggregation, and a browser BFF remain future hardening work.
