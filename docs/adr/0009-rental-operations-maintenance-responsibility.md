# ADR 0009: Rental operations and maintenance responsibility

- Status: Accepted
- Date: 2026-10-09

## Context

Ownership was being used as a proxy for two unrelated concerns: whether an
asset participates in operations and which company maintains it. That would
incorrectly remove KM/HMR capture and reporting from rented equipment, while
also allowing a renter to configure or complete work that remains the rental
Owner's responsibility. Migration 0019 also conservatively left legacy
wheeled assets without HMR, contrary to the corrected Pilot rule.

## Decision

Keep ownership, operational responsibility, and maintenance responsibility
separate. Every assigned asset remains operational according to physical meter
capabilities. Every `is_wheeled=true` Pilot asset requires both KM and HMR;
tracked assets require HMR only. Migration 0021 applies that rule to legacy
wheeled rows because no capability-provenance field exists.

Add `maintenance_responsibility` with `OWNER_COMPANY`, `RENTER_COMPANY`, and
`SHARED`. The current Pilot enables current-tenant plan/work-order/due/proof
behavior only for owned assets with owner/shared responsibility. Rented assets
default to external Owner maintenance: their current tenant continues duty,
meter, diesel, emergency, and reporting workflows, can read preserved history,
but cannot configure or complete periodic maintenance.

A Driver may submit private service-photo proof only for a due/overdue item on
the current assignment. Proof is idempotent and pending; it is not completion.
Only a Supervisor explicitly authorized for the submission Site may reject it
with a reason or confirm service. Confirmation creates immutable maintenance
history and resets supported baselines from the current authoritative meters
and confirmation date.

Persist a dormant `InterCompanyAssetRental` agreement skeleton with effective
dates, responsibility, paired tenant assets, and individually opt-in sharing
fields. The feature flag and every sharing field default off. No API or sync
path is enabled, and the model creates no cross-tenant permission.

## Consequences

- Rented assets stay visible and complete in operational reports.
- Maintenance alerts and mutations no longer imply ownership or silently cross
  company responsibility boundaries.
- Driver evidence cannot self-complete maintenance; Supervisor Site authority
  and an auditable review are mandatory.
- Legacy wheeled assets begin requiring dual KM/HMR after migration 0021.
- Future intercompany sharing requires a separate explicit authorization and
  synchronization decision before the dormant model can be activated.
