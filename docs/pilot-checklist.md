# One-Tipper Pilot Checklist

Complete and sign this checklist before onboarding a real driver. It covers
the controlled Pilot, not authorization to deploy the cloud stack or publish
to Play; use the [production readiness gates](production-readiness-report.md)
and [Play migration guide](google-play-release.md) for those releases.

## Infrastructure and security

- Internal pilot only: use controlled local connectivity; do not expose the
  API or plaintext authentication traffic to the public Internet.
- Legacy internal OTP testing only: explicitly enabled non-production OTP is
  acceptable on an isolated test network. Current company/production releases
  use `company_pin`; no SMS provider or Firebase login is required.
- Internal pilot only: MIME/signature, size, private-object, and authorization
  checks are required; malware scanning is required before broader rollout.
- [ ] Pilot environment is distinct from development and test.
- [ ] PostgreSQL is healthy and `/ready` returns `200`.
- [ ] Object storage is private, healthy, and tenant-scoped.
- [ ] Explicit CORS origins and allowed hosts are configured.
- [ ] TLS/secure-cookie termination is verified for pilot URLs.
- [ ] Production/pilot JWT signing material is secret-managed and not a local default.
- [ ] Company-PIN activation expiry, single use/replay rejection, PIN lockout,
      device binding and logout/reactivation are verified. Any legacy OTP test
      is explicitly isolated and is not a production fallback.
- [ ] Logs contain request IDs but no activation codes, PINs, device credentials,
      OTPs, JWTs, refresh tokens, passwords, or signed URLs.

## Backup and recovery

- [ ] Timestamped PostgreSQL backup completed.
- [ ] Backup restored into a separate test/restore database.
- [ ] Migration/schema and representative records verified after restore.
- [ ] Evidence-object export completed separately from the database backup.
- [ ] PostgreSQL restart/recovery tested.
- [ ] API restart/readiness recovery tested.
- [ ] Object-storage outage/recovery tested.

## Accounts and domain setup

- [ ] Owner login tested.
- [ ] Supervisor login tested.
- [ ] Driver login tested.
- [ ] Supervisor has access only to the intended site.
- [ ] Owned tipper and effective-dated assignment exist.
- [ ] Driver phone clock is reasonably correct.

## Driver device

- [ ] APK installed from the intended controlled build.
- [ ] App version/build identifier recorded.
- [ ] Camera permission tested.
- [ ] Active assignment appears.
- [ ] While off duty, only START DUTY and EMERGENCY are visible as operational
      actions.
- [ ] While on duty, EMERGENCY is prominent; the tipper shows TRIP COMPLETE and
      DIESEL, and END DUTY is at the bottom. Maintenance visibility follows the
      asset's responsibility/capability; Drivers submit proof, not completion.
- [ ] START/END DUTY capture the asset's required meters and evidence (KM and
      HMR for wheeled Pilot assets); no standalone primary KM tile is shown.
- [ ] Offline trip captured, app terminated, restarted, and event still present.
- [ ] Offline event synced after backend recovery.
- [ ] Duplicate sync produced one logical event.
- [ ] Diagnostics screen was checked without exposing credentials or totals.

## Operational acceptance

- [ ] Eight approved trips reconcile across dashboard/site/tipper/Excel.
- [ ] START 10000 and END 10120 reconcile to 120 KM.
- [ ] Approved diesel is 30 L and is labelled issued/recorded.
- [ ] Simple Site Workbook selects exactly one Site and date range, opens with
      `SUMMARY`, and has exactly one sheet per historically relevant asset.
- [ ] Moving an asset or changing its Driver during the range leaves old rows
      attributed to the old Site/person and new rows to the new Site/person.
- [ ] A same-day Driver reassignment produces two daily rows with the historical
      people but one distinct asset Day Worked.
- [ ] Multiple duty sessions use the authoritative first/last daily aggregate,
      retain each event's review status, and do not drop the day's activity.
- [ ] Summary Pending Items and Exceptions reconcile to pending events,
      structured exceptions, and disputes in daily rows.
- [ ] Machinery/tipper non-applicable cells show `N/A`; recorded-diesel ratios
      carry the consumption disclaimer and remain unavailable when their
      denominator is zero or missing.
- [ ] A pending/disputed/missing-reading failure scenario blocks closure.
- [ ] Emergency contact process is explained; the app is not treated as a guaranteed emergency-response service.
- [ ] Rollback/contact plan is defined.
- [ ] No Phase 8 deployment or real-driver rollout starts automatically from this checklist.
