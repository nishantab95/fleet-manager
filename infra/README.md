# Local infrastructure

`docker-compose.yml` starts only the Phase 0 dependencies:

- PostgreSQL for transactional application data.
- MinIO as a local S3-compatible object-storage target.

No message broker, cache, worker pool, or continuous tracking service is part of the foundation. Production credentials, endpoints, bucket policies, TLS, and backups must be supplied by deployment configuration rather than committed files.

