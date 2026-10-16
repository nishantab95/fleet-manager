# ADR 0019: Operations-only deployment bundles

- Status: Accepted for production preparation; live execution not verified
- Date: 2026-10-16
- Extends: [ADR 0015](0015-single-vps-production-deployment.md)

## Context

The original approved workflow pulled application images but also fetched a
tracked Git checkout on the VPS. It did not upload ignored laptop caches, yet
still required source/history and a repository credential on the server. The
owner requires application delivery through approved images, without transferring
the complete development checkout.

## Decision

Keep the manual full-SHA, main-ancestry, successful-CI and protected-environment
approval gates. Build the three application images on the GitHub runner. Send
only a deterministic, explicit allowlist of Compose/Caddy/MinIO configuration,
systemd units and runtime operations scripts from the approved Git blobs.
Include a release marker and per-file manifest; exclude application source,
Git history, local environment, runtime data and signing material.

Pinned-host SSH and SCP deliver the archive to a new incoming directory. Verify
its expected SHA-256 before extracting into a new full-SHA release directory.
Only successful guarded deployment activates the stable operations symlink.
The receiver and direct deploy/rollback share one lock through activation.
Existing real checkouts, unknown links and existing release directories are
refused rather than overwritten. Retain failed and previous bundles for review.

Keep the Compose project identity and persistent named volumes independent of
the release path. Established PostgreSQL/MinIO configuration hashes must match
before application deployment. Secrets remain external to the bundle/images.

## Consequences and limits

- The VPS no longer needs Git or source-repository credentials. It still needs
  approved image-registry access, SSH and externally provisioned configuration.
- The receiver trusts the reviewed fixed-path builder and authenticated expected
  archive hash; this is not independent artifact signing or a hostile-archive
  sandbox. SHA-tag overwrite refusal depends on registry access policy.
- Image rollback does not automatically revert bundle configuration. Configuration
  recovery must select a compatible retained bundle and reconcile its pointer
  under the same lock after health/state verification.
- Failed or interrupted activation may require operator reconciliation; no
  automatic deletion, same-SHA replacement or production-data adoption is added.
- Exact contents, measurements and commands belong to the
  [packaging review](../operations/cloud-packaging.md),
  [deployment guide](../production-deployment.md) and
  [rollback guide](../production-migration-and-rollback.md).
