# ADR 0010: Editable maintenance starters and exact-model references

## Status

Accepted.

## Context

Owners need a usable maintenance plan before model-specific manuals have been
entered, but a generic interval must never be presented as an OEM requirement.
They also need to preserve local changes after a template is applied.

## Decision

Persist two explicit template classes:

- `COMPANY_STARTER` with `SUGGESTED` confidence; and
- `OEM_VERIFIED` with `VERIFIED` confidence and mandatory manufacturer, model,
  source name, and source reference.

Templates also carry a category, wheeled/non-wheeled applicability, optional
year range, notes, and a version. The six starter categories are heavy
10-wheel tipper, tracked excavator, backhoe loader, road roller/compactor,
wheel loader, and motor grader. Wheel loader is a catalog-only starter until it
becomes a supported operational Fleet asset type, so it cannot be matched to a
different asset category.

Catalog installation is idempotent by tenant, template name, and version. It
adds missing standard versions but never replaces an Owner's edits. Applying a
template copies its tasks and compatible triggers into the Asset plan. Blank
starter intervals are permitted when a generic numeric interval is not
defensible. Later template edits do not update an existing Asset plan.

OEM references match an exact case-insensitive manufacturer and model plus any
specified year range. There is no fuzzy or same-brand auto-application.

## Consequences

- Owners can start from a useful, editable list while the UI clearly labels
  uncertainty.
- The source registry remains auditable without embedding external URLs in
  business records.
- Exact-model references require explicit catalog versions when manufacturer
  publications change.
- Existing Asset plans remain deliberate snapshots and need a future explicit
  compare/apply-updates workflow rather than silent synchronization.
