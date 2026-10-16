# ADR 0015: Single-VPS production deployment and explicit releases

- Status: Accepted for production preparation
- Date: 2026-10-16

Delivery mechanics are extended by [ADR 0019](0019-operations-only-deployment-bundles.md):
approved application images plus a small operations bundle, not a VPS Git checkout.

## Context

The controlled Windows/Tailscale Pilot must remain usable while Fleet AI
Systems gains a cloud production path for two browser users and approximately
30 Android phones. A code push must never be sufficient authorization to
change production. PostgreSQL, evidence storage, and administrative surfaces
must not become public during the migration.

## Decision

Production is one Ubuntu VPS running the existing modular monolith as Docker
Compose services: FastAPI, PostgreSQL, private MinIO S3-compatible storage, the
combined Owner/Supervisor Next.js client, the marketing Next.js site, and
Caddy. Only Caddy publishes host ports. PostgreSQL, MinIO, its console, FastAPI,
and both Next.js processes have no host port mapping.

Caddy routes the marketing site at `fleetaisystems.com`, the authenticated web
client at `app.fleetaisystems.com`, and the mobile API at
`api.fleetaisystems.com`. The API host refuses OpenAPI/docs, legacy admin,
Owner, and report route families. Browser access to authenticated Owner and
report routes goes through the app's same-origin server proxy over the Docker
network. Driver and Supervisor mobile routes remain protected by the existing
backend authentication and authorization.

Production images use immutable full-Git-SHA tags in GHCR. The production
workflow is `workflow_dispatch` only, requires an exact confirmation phrase,
requires the selected SHA to be on `main`, requires CI success for that SHA,
and is attached to the protected GitHub `production` environment. The VPS
deploy command takes a verified backup, performs a disposable restore test,
runs Alembic once, starts the new containers, and gates completion on internal
and public health/private-route checks.

Application rollback selects a prior immutable image tag. It never performs an
automatic Alembic downgrade. Migrations released through this process must be
backward-compatible with the immediately previous application image. A data
restore is a separate, explicit incident operation.

The root Compose file and Windows server scripts remain the local/Pilot path.
Tailscale is optional for that path and is not a dependency of cloud clients.

## Consequences

- A single VPS is an intentional availability boundary. Verified off-host,
  encrypted backup copies are required before production cutover.
- Deployments have a short container replacement window; the mobile offline
  queue covers transient unavailability.
- GitHub environment protection, VPS credentials, DNS, an independent encrypted
  Restic repository, and GHCR pull access are external setup gates.
- Database rollback means restoring a verified backup during an approved
  maintenance incident, never an automatic migration downgrade.
