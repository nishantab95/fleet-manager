# FastAPI backend agent guide

Read [PROJECT_RULES.md](../../PROJECT_RULES.md) first; it is the primary contract.
Use [change workflows](../../docs/development/change-workflows.md), [security](../../docs/security.md)
and [migration/rollback](../../docs/production-migration-and-rollback.md) for the requested scope.
Check Git status and inspect the route, service, model and existing tests before editing.

- Routes/schemas: [src/fleet_api/api/](src/fleet_api/api/); business rules: [src/fleet_api/domain/](src/fleet_api/domain/).
  Authentication: [src/fleet_api/auth/](src/fleet_api/auth/); persistence: [src/fleet_api/db/](src/fleet_api/db/).
  Migrations: [migrations/versions/](migrations/versions/); regressions: [tests/](tests/).
- Preserve `company_pin`: owner-issued expiring single-use activation, PIN hashing/lockouts, device binding and sessions.
  Firebase/OTP remain optional compatibility modes, never a production SMS requirement; never log credentials/codes.
- Enforce tenant, role, device and assignment permissions server-side. Preserve client UUID idempotency,
  offline compatibility, historical assignments, evidence ownership and existing registrations.
- Keep database, object storage and private administration endpoints private; do not modify Pilot signing/identifiers.
  Schema history is append-only; migration/restore tests require explicitly selected disposable data.
- Run commands here, not from the checkout root: `.\.venv\Scripts\python.exe -m ruff check src tests migrations`,
  `.\.venv\Scripts\python.exe -m ruff format --check src tests migrations`,
  `.\.venv\Scripts\python.exe -m mypy src tests`, and `.\.venv\Scripts\python.exe -m pytest tests/<affected-test>.py`.
  Database tests need the documented dedicated test database; never point them at Pilot/production data.
- Expand checks for schema/security changes and report skipped checks. Local tests/builds never authorize live deployment.
