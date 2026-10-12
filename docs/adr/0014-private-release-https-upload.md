# ADR 0014: Private HTTPS transport for Pilot releases

## Status

Accepted.

## Context

Pilot APK publication already validates the Android package, permanent signer,
version, checksum, and release metadata before an atomic activation under
`D:\FleetManagerData\releases\pilot`. The original laptop transport used
Taildrop only. Its preflight treated a Tailscale DERP relay as unavailable even
though the private HTTPS server remained reachable.

## Decision

The Fleet API exposes `POST /api/v1/admin/pilot-releases` through the existing
private Tailscale HTTPS origin. It requires a dedicated bearer credential read
from `C:\ProgramData\FleetAISystems\pilot-publisher.token` by default. This
credential is independent of Fleet JWT, Firebase, user PIN, and database
credentials.

The API streams a bounded multipart APK into the existing release incoming
area, verifies the declared checksum, replaces all client filenames with a
server-generated release identifier, and hands the pair to
`pilot_release_inbox.py`. The inbox performs the existing APK identity and
profile checks and calls `server_manager.publish_pilot_apk()`. That function
remains the only activation transaction and verifies both published download
hashes before committing. Any activation or verification error restores the
previous release.

The laptop sender prefers HTTPS and verifies `release.json`, source commit, and
the downloaded APK hash before reporting `PUBLISHED SUCCESSFULLY`. Taildrop is
retained as a fallback when the HTTPS upload route is unavailable; a direct
peer connection is not required for either the HTTPS attempt or fallback.

## Consequences

- A one-time deployment and external credential installation are required on
  the server.
- Ordinary future releases require no interactive server inbox processing.
- The upload route remains private and credential-protected; it is not a public
  APK distribution service.
- The manual inbox processor remains available for recovery.
