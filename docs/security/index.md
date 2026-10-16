# Security documentation

[Documentation home](../index.md)

- [Security guide](../security.md): backend authorization, tenant isolation,
  sessions, private evidence, safe logging, and fail-closed configuration.
- [Production data handling](../production-data-handling.md): data inventory,
  access, retention, disclosure, and owner review requirements.
- [Production operations](../production-operations.md): host controls,
  monitoring, incident response, and external verification gates.
- [Migration and recovery](../production-migration-and-rollback.md): database
  and evidence protection, verified restore, and rollback boundaries.
- [Readiness report](../production-readiness-report.md): actual scan/test
  evidence and outstanding checks; preparation is not security approval.

## Authentication and distribution boundaries

Production uses [owner-issued activation and PIN](../adr/0012-company-managed-activation-pin.md)
with the existing [device authentication and workspace contract](../adr/0013-device-auth-and-workspaces.md).
Activation expires and is single-use; backend memberships, roles, devices, and
assignments remain authoritative. No SMS or Firebase Phone login is required.

The [Google Play guide](../google-play-release.md) covers approved upload signing,
disabled APK sideload updates, and controlled migration from the distinct Pilot
package. Preserve the [permanent Pilot signing identity](../mobile-pilot-signing-backup.md);
do not generate a replacement or publish private keys.

[Firebase setup](../firebase-auth-setup.md),
[Firebase staging](../firebase-staging-runbook.md), and the
[historical company setup](../firebase-company-setup.md) remain optional
compatibility procedures. Their credentials, billing, and SMS steps are not
requirements of this production release.
