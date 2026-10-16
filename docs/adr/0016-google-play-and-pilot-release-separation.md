# ADR 0016: Google Play and private Pilot release separation

- Status: Accepted for production preparation
- Date: 2026-10-16

## Context

Existing Pilot installations use package
`com.fleetmanager.fleet_manager_mobile.pilot`, the permanent Pilot signing
certificate, private HTTPS manifests, and Android's package installer. Google
Play production updates must not enable that sideload path or replace the Pilot
identity.

## Decision

The Play application keeps the already-declared production package
`com.fleetmanager.fleet_manager_mobile`. It is a different Android application
from the Pilot package and therefore cannot update a Pilot installation in
place. Migration is controlled and side-by-side: every Pilot queue is synced,
active duty is ended, the Play app is installed, the Driver enters a fresh
owner-issued activation code, configures the existing PIN/device
authentication, and the new installation registers against the same existing
Fleet User. The Pilot app is removed only after server records and the new app
are verified.

Pilot releases continue to use the protected `fleetPilot*` Gradle properties,
the Pilot package, and private update channel. Play bundles use separate
`fleetPlay*` upload-signing properties. A production release build cannot fall
back to a debug signer. Bundle validation checks package, version, signer, and
the absence of `REQUEST_INSTALL_PACKAGES` before upload.

The Play workflow is manual, targets a protected GitHub environment, requires
an exact package confirmation, checks `main` ancestry and CI success, and uses
the Google Play Developer API only after building and validating the AAB. The
production app uses `https://api.fleetaisystems.com` and mandatory
`FLEET_AUTH_MODE=company_pin`. Firebase compatibility code is not initialised
or required in this mode. Play App Signing owns the distribution signing key; the
separate upload key is supplied externally and is never generated in CI or
committed.

## Consequences

- Pilot local SQLite data, secure tokens, photographs, and installation ID
  cannot be transferred automatically to the different Play package. Pending
  work must be synced from the Pilot app before migration.
- Backend Driver, Assignment, Event UUID, evidence, and historical records stay
  in the same production database and are not recreated.
- The Pilot signer remains unchanged and can continue private Pilot upgrades.
- Play Console application creation, Play App Signing enrollment, upload-key
  registration, and service-account access are
  external blockers until the owner completes them.
