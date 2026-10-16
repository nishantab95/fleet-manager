# Local infrastructure

`docker-compose.yml` starts only the Phase 0 dependencies:

- PostgreSQL for transactional application data.
- A dedicated `fleet_test` PostgreSQL database is created on a fresh local
  volume for integration tests.
- MinIO as a local S3-compatible object-storage target.

No message broker, cache, worker pool, or continuous tracking service is part of the foundation. Production credentials, endpoints, bucket policies, TLS, and backups must be supplied by deployment configuration rather than committed files.

`infra/production/` is a separate, prepared single-Ubuntu-VPS topology. It does
not alter the root local Compose stack. Production includes PostgreSQL, private
MinIO, FastAPI, both Next.js runtimes, and Caddy; only Caddy publishes host
ports. Read `docs/production-deployment.md` before using it. The example
environment file contains placeholders only and is not suitable for startup.
Verified database/evidence generations are encrypted to an independent Restic
repository before local rotation; `restic.env.example` is also placeholders
only and must remain outside the runtime repository when populated.
