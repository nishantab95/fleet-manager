# ADR 0005: Operational Reporting, Daily Closure, and Excel Export

- Status: Accepted for Phase 6; amended for the 2026-10-08 pilot reporting UX
- Date: 2026-09-22
- Amended: 2026-10-08

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
   official trip counts, diesel issued, and odometer readings; existing HMR
   verification semantics remain unchanged. Pending, disputed, and rejected
   records remain separate. Diesel is issued/recorded, not consumed. The
   Simple Site Workbook may present explicitly named ratios over verified
   recorded diesel, with a consumption disclaimer and safe zero-denominator
   behavior; those ratios are not treated as actual fuel consumption.

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

7. **Excel.** The configurable export calls the already-built dashboard report
   and keeps its existing selectable management, asset, event, duty, and
   exception sheets. Headers are bold, panes are frozen, filters and widths are
   applied, and aware datetimes are normalized for Excel compatibility. Values
   beginning with `=`, `+`, `-`, or `@` receive a leading apostrophe.

8. **Simple Site Workbook.** A separate fixed-layout Owner export accepts one
   tenant-scoped Site and an inclusive range of at most 366 operational days.
   Effective-dated Deployments determine asset-sheet inclusion, including
   assets without a Driver, while `ReportingService.site_daily()` remains
   authoritative for historical Assignment/Driver attribution and metrics.
   `SUMMARY` is first,
   followed by one deterministic, Excel-safe sheet per relevant owned or
   rented asset. Multiple duty sessions use the existing assignment/day
   first/last aggregate and retain event review status; same-day reassignment
   remains multiple rows. The dedicated export cannot become an advanced
   default or be used through the advanced route. The advanced export is neither
   replaced nor reconfigured.

## Consequences

The owner receives reconciled operational totals, a practical Site-range
workbook, and an auditable close without introducing a second calculation
engine. Incomplete or ambiguous records remain operational exceptions and may
require supervisor review. Editable display labels are not historical
snapshots. Multi-Site/ZIP export, ranges beyond the 366-day bound, and a browser
BFF remain future hardening work.
