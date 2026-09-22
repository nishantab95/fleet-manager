# Phase 7 End-to-End and Failure Matrix

Phase 7 hardens the completed owned-tipper workflow without changing the
driver's four primary actions. The matrix below is the acceptance contract for
the one-tipper pilot.

| Area | Scenario | Automated coverage | Pilot verification |
| --- | --- | --- | --- |
| Owner | Create site, owned tipper, driver, supervisor, site grant, assignment | `test_phase7_e2e.py` PostgreSQL flow | Run the owner checklist |
| Driver | Authenticate, restore assignment, capture START, trips, diesel, END | `test_phase7_e2e.py`; mobile widget/unit tests | Sign in on the pilot device |
| Offline | Queue while backend is unavailable, terminate, reopen SQLite, sync | `cold_restart_offline_test.dart` | Kill and relaunch the installed app |
| Retry | Timeout after server commit, 401 refresh, object-store failure | `sync_recovery_test.dart`; event UUID database constraint | Repeat with network toggled |
| Supervisor | Review, approve, reject/dispute, site authorization | Existing supervisor API tests and E2E flow | Verify only the granted site is visible |
| Owner reporting | Dashboard/site/tipper/Excel reconciliation | `test_phase7_e2e.py` and Phase 6 report tests | Compare the pilot workbook |
| Auth | OTP cooldown/attempts/expiry/replay, refresh rotation, revocation | Existing auth PostgreSQL tests plus web cookie route coverage | Use the runbook recovery steps |
| Evidence | MIME allowlist, magic-byte validation, private generated keys | Driver API evidence tests | Try a renamed/non-image file |
| Recovery | API/database/object-storage restart and readiness | Compose/runbook procedure; automated local queue tests | Execute before onboarding |

## Failure-policy invariants

- Local persistence happens before any network call. A failed sync remains in
  the durable queue with a safe category such as `BACKEND_UNAVAILABLE` or
  `AUTH_REQUIRED`.
- A server timeout after commit is retried with the same client UUID. The
  backend unique constraint makes the logical event singular; distinct UUIDs
  are never merged by timestamp heuristics.
- Evidence upload is idempotent by company, driver membership, and client
  event UUID. An event is not reported as synced until its required evidence
  and event submission both succeed.
- Membership or device revocation causes the server to reject later syncs. The
  device retains the unsynced event and exposes `AUTH_REQUIRED` or
  `ACCESS_REVOKED_OR_DENIED` in diagnostics; it is not silently deleted.
- Assignment history is resolved from the event's device-created timestamp.
  Events captured during a valid old assignment cannot be rewritten to a new
  tipper/site.

The PostgreSQL, browser, Android-device, Compose restart, and backup/restore
steps must be run in a pilot environment before declaring field readiness.
