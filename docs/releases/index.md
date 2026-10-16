# Release documentation

[Documentation home](../index.md)

The repository is locally prepared; no VPS deployment or Google Play publication
is established by these documents. Review the
[readiness report](../production-readiness-report.md) and its external blockers
before approving any release. A push to `main` is not deployment approval.

## Server and browser releases

- [Production deployment](../production-deployment.md): reviewed full-SHA
  selection, successful CI, protected-environment approval, and one-command dispatch.
- [Migration and rollback](../production-migration-and-rollback.md): pre-change
  backup/restore gates, safe migrations, and prior application images.
- [Operations](../production-operations.md): host and operational acceptance.
- [Production change inventory](../production-change-inventory.md): files in the
  earlier production-preparation implementation, not an automatically updated diff.

## Android channels

- [Google Play release](../google-play-release.md): signed production AAB,
  submission gates, owner-issued activation onboarding, and device acceptance.
- [Play/Pilot separation decision](../adr/0016-google-play-and-pilot-release-separation.md):
  distinct packages and controlled migration; no in-place Pilot-to-Play upgrade.
- [Mobile Pilot runbook](../mobile-pilot-runbook.md): existing private APK channel.
- [Pilot signing backup](../mobile-pilot-signing-backup.md): permanent Pilot
  certificate preservation and recovery.

Play uses the fixed cloud HTTPS API and `company_pin`, without Tailscale, manual
server entry, SMS, or required Firebase login. The private APK updater is disabled
in Play builds. Keep Pilot installed and preserve its offline records/photos
until the migration guide's reconciliation and acceptance checks pass.

## Preserved historical context

- [Pilot acceptance checklist](../pilot-checklist.md).
- [Windows website deployment](../public-website-deployment.md): separate legacy
  hosting procedure; do not apply it to the Ubuntu stack.
- [Historical build and acceptance reports](../archive/README.md): original
  artifacts and recorded results, not approval for a new release.
