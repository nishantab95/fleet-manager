# Operations documentation

[Documentation home](../index.md)

Cloud deployment is prepared and locally tested, not live. These runbooks
require explicit approval before any VPS, DNS, production data, or release
change. Read the [readiness gates](../production-readiness-report.md) first.
The [latest repository audit report](repository-readiness-report.md) consolidates
the subsequent disk, documentation, agent, packaging and regression verification.

## Prepared Ubuntu deployment

- [Production deployment](../production-deployment.md): Docker topology,
  private routing, external configuration, and approved release entry point.
- [Migration, backups, and rollback](../production-migration-and-rollback.md):
  preserved records, independent database/evidence backups, restore verification,
  and application rollback without destructive schema reversal.
- [Production operations](../production-operations.md): host hardening, health,
  logging, capacity, incident handling, and provider migration.
- [Cloud packaging and capacity](cloud-packaging.md): operations-only VPS bundle,
  image sizes, evidence/backup disk growth and conditional 40 GB envelope.
- [Build-context inventory](build-context-inventory.md): exact native Docker
  input paths/bytes and exclusion verification, separate from runtime image size.
- [Data handling](../production-data-handling.md): access, retention, evidence,
  marketing leads, and outstanding owner/privacy decisions.

## Local workstation and preserved Pilot

- [Windows development](../development.md): independent laptop services.
- [Local disk audit](local-disk-audit.md): before/after measurements, protected
  material, cleanup evidence, and Docker storage kept separate from checkout size.
- [Manual maintenance](local-maintenance.md): report-only inventory, separately
  approved cache cleanup and protected backup/image retention; never an automatic janitor.
- [Pilot runbook](../pilot-runbook.md) and
  [Pilot checklist](../pilot-checklist.md): existing Pilot operations and acceptance.
- [Mobile Pilot runbook](../mobile-pilot-runbook.md): private APK distribution
  and device procedures, separate from Google Play.
- [Windows website runbook](../public-website-deployment.md): preserved alternative
  topology, not the Ubuntu VPS procedure.

Do not reset Pilot data, delete Docker volumes, or regenerate signing keys as
maintenance. Android package migration belongs to the
[Google Play release guide](../google-play-release.md), not routine server cleanup.
