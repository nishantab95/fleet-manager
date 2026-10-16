# Fleet AI Systems documentation

This index separates the current production preparation from the preserved
Windows/Tailscale Pilot and earlier acceptance reports. The cloud release uses
`FLEET_AUTH_MODE=company_pin`: Owner-issued, expiring, single-use activation,
followed by the existing PIN/device authentication. Google Play distribution
does not require SMS or Firebase Phone Authentication.

## Current production and release guides

| Guide | Purpose |
| --- | --- |
| [Production readiness report](production-readiness-report.md) | Actual checks, results, and remaining release blockers |
| [Ubuntu VPS deployment](production-deployment.md) | Docker services, domains, private routing, approval process, and deployment command |
| [Migration, backups, and rollback](production-migration-and-rollback.md) | Preserve existing records and evidence; recover through reviewed restore procedures |
| [Production operations](production-operations.md) | Host hardening, health, resource capacity, incidents, and provider portability |
| [Production data handling](production-data-handling.md) | Data classes, privacy, retention, and owner review requirements |
| [Google Play release](google-play-release.md) | Audited identities, signing, submission, activation onboarding, and Pilot migration |

These are preparation instructions. They do not establish that a VPS, DNS,
GitHub protected environment, offsite repository, or Play release exists. The
readiness report is authoritative for what has actually been verified.

## Engineering and local development

- [Project rules](../PROJECT_RULES.md): enduring scope and engineering contract;
  explicit later owner instructions determine the current release scope.
- [Architecture](architecture.md): component boundaries, auth, offline sync,
  and role workflows.
- [Domain model](domain-model.md): records, relationships, and business invariants.
- [Development](development.md): laptop setup, local databases, tools, and tests.
- [Security](security.md): tenant, role, session, evidence, and deployment controls.
- [Production engineering audit](production-engineering-audit.md): scoped source
  findings, corrections, coverage limits and incremental maintenance sequence.
- [Production change inventory](production-change-inventory.md): exact files
  changed by this preparation, including the preserved earlier work.
- [Architecture decision records](adr/README.md): unique IDs, provenance, and
  superseded portions.
- [Maintenance source references](maintenance-template-sources.md): documented
  starter/template provenance.

## Preserved Pilot procedures

- [Pilot runbook](pilot-runbook.md) and [Pilot checklist](pilot-checklist.md).
- [Mobile Pilot runbook](mobile-pilot-runbook.md).
- [Permanent Pilot signing backup](mobile-pilot-signing-backup.md).
- [Windows public website deployment](public-website-deployment.md).
- [PC Role Lab](pc-role-lab.md) and [Phase 7 E2E matrix](phase7-e2e-matrix.md).

These documents retain the installed Pilot's operational context. They are not
instructions to change that installation during cloud preparation. The Play
package differs from the Pilot package, so use the current migration guide
before moving any phone; pending local records and photographs must be synced.

## Optional Firebase compatibility

- [Firebase architecture/setup](firebase-auth-setup.md).
- [Firebase staging tests](firebase-staging-runbook.md).
- [Historical Firebase company release](firebase-company-setup.md).

These guides apply only to explicitly selected Firebase work. Their SMS,
billing, project, and credential steps are not part of this production release.
Existing Firebase code and historical identities remain preserved.

## Historical verification

The [archive index](archive/README.md) catalogs earlier build and acceptance
reports in their original locations. A historical PASS applies to the artifact
and test environment recorded there; it is not proof of the current release.
