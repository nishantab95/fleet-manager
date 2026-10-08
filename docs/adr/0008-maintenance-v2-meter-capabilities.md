# ADR 0008: Maintenance V2 and independent meter capabilities

- Status: Accepted
- Date: 2026-10-08

## Context

Fleet assets differ in both physical classification and the readings required
for operations. Maintenance tasks also differ: a task may become due by date,
kilometres, hours, or the first of several triggers. Treating asset type as a
single implied meter capability would make dual-meter wheeled equipment and
tracked hour-meter equipment ambiguous, and would couple Driver capture to
Owner maintenance setup.

## Decision

Store `is_wheeled`, `supports_odometer_km`, and `supports_hour_meter` as
separate asset properties. Operational capabilities determine the readings and
evidence required at duty start/end. Maintenance criteria are configured per
plan item and are constrained by classification and available operational
meters. Wheeled assets may use date, KM, and/or hours; non-wheeled assets may
use date and/or hours and cannot use KM. Drivers capture only operational meter
values and never maintenance calendar inputs.

For an asset that supports both meters, the Driver client persists and submits
KM and HMR as one compound capture. The API validates and commits both events
atomically under a shared capture-group UUID. Supervisors review the group as
one card; reporting and due calculations consume its typed member readings.

Maintenance templates are versioned sources for copied task definitions.
Asset plans are independent after application. Copying a plan copies compatible
definitions only and resets baselines. Completing a work order appends an
immutable history record and updates only the relevant asset plan baselines.

## Consequences

- Dual-meter capture cannot leave a half-written start or end reading.
- A missing meter yields an explicit `UNKNOWN` criterion without masking a
  usable overdue trigger.
- Existing assets can be migrated conservatively without changing their Driver
  workflow; Owners can opt into additional capabilities later.
- Physical classification, operational capture, and maintenance scheduling can
  evolve independently while retaining one canonical asset and event history.
- Template updates do not silently alter active asset plans or past records.
