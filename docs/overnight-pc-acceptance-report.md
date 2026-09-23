# Overnight PC Acceptance Report

Date: 2026-09-24  
Repository: `D:\Git\fleet maneger\fleet manager`  
Starting HEAD: `6cc7076c6513df91cd75b6c9f64a1c020dd0f1e2`  
Final acceptance commit: reported in the handoff below.

## Result

PASS. The controlled PC Role Lab happy path, fresh-pilot negative checks,
launcher checks, backend checks, web checks, Flutter checks, and repository
hygiene checks completed successfully.

The only product defect found was browser-session restoration after reload. In
the Next development build, React StrictMode could start two refresh requests
with the same rotating HttpOnly refresh token. The second request was correctly
treated by the API as refresh-token reuse, which revoked the session family and
returned the user to login. The web `AuthProvider` now deduplicates concurrent
refresh calls, with a regression test.

## Environment

- Windows PowerShell; uv-managed Python 3.12.14
- Node.js 22.23.2; npm 10.9.8
- Playwright 1.63.0 with Chromium
- Flutter 3.47.5; Dart 3.13.4
- Docker 29.8.0; Docker Compose v5.5.1
- PostgreSQL and MinIO were launcher-managed and ready during browser acceptance

No credentials, OTP values, access tokens, or private evidence contents were
written to this report.

## Happy path

Fresh pilot reset was performed through the launcher using the exact
`RESET PILOT` confirmation. The real browser flow then passed:

1. Owner authenticated and confirmed Pilot Site, PILOT12 / Tipper 12, Pilot
   Driver, Pilot Supervisor, supervisor access, and the active assignment.
2. Driver QA submitted exactly eight events: START 10000, four TRIP COMPLETE
   events, DIESEL 30, END 10120, and one
   `TYRE_OR_VEHICLE_PROBLEM` emergency with the required description.
3. All eight events had distinct client UUIDs. KM and diesel evidence was
   uploaded and each evidence control was opened from Supervisor review.
4. Supervisor saw one permitted site, approved the seven non-emergency events,
   acknowledged and resolved the emergency, and reached zero unresolved review
   exceptions.
5. Owner reporting reconciled to four approved trips, 120.00 km, 30.000 L,
   zero missing readings, and zero unresolved emergencies. The emergency remains
   one pending verification event because it was resolved, not approved; this is
   the existing verification model.
6. Owner downloaded the XLSX report, closed the site day, reloaded the browser,
   and confirmed `CLOSED` with the Reopen action available.

The exported workbook was structurally inspected and contained these sheets:
`Daily Summary`, `Trip Register`, `KM Register`, `Diesel Register`, and
`Exceptions`. The export was taken before closure and therefore correctly showed
`READY_TO_CLOSE`; the subsequent UI closure reached `CLOSED`.

Evidence screenshots and the workbook are retained in the ignored local QA
directory `.runtime/overnight-qa/`.

## Negative tests

PASS on a separate fresh pilot reset:

- KM submission without an image was blocked by the required evidence field and
  created no event.
- Diesel value `0` failed the browser numeric constraint.
- A DRIVER session opening `/owner` received the explicit OWNER_ADMIN access
  denial.
- Supervisor saw only the permitted Pilot Site, no event-review articles, and
  missing START/END completeness on the empty day.
- Backend coverage passed role boundaries, tenant isolation, evidence
  authorization, missing/invalid KM closure blockers, rejection/dispute reason
  requirements, emergency lifecycle, idempotency, and closure policy.

## Bugs found and fixed

### Fixed: duplicate browser refresh rotation

`apps/web/features/auth/AuthProvider.tsx` now shares one in-flight refresh
promise between StrictMode/reload callers. This preserves the existing
runtime-only access token model and HttpOnly refresh-cookie security without
changing backend or domain behavior.

Regression coverage is in
`apps/web/features/auth/AuthProvider.test.tsx`.

### Test-harness-only corrections

The temporary acceptance harness required several locator and formatting
corrections while observing the real UI (combined assignment text, option
placeholder, decimal display formatting, and exception-row collision). These
were not product defects. The temporary harness and generated artifacts were
removed after the run.

## UX observations

- The PC Test Lab role cards were understandable at 1366x768 and did not
  horizontally overflow.
- Driver QA presents exactly four primary actions and no operational totals.
- Supervisor summary metrics are assignment/completeness counts, while the
  event review separately shows all eight events; this distinction was clear in
  the rendered page after using the labels and detail rows.
- Owner totals use two decimal places for KM and three for litres, matching the
  API/report contract.
- Closure blockers were visible before closure and disappeared from the active
  closed-day workflow.

## Automated quality gates

Backend:

- Ruff format check: PASS; 68 files already formatted.
- Ruff lint: PASS.
- mypy strict check: PASS; 60 source files.
- PostgreSQL pytest: PASS; 57 passed, 3 warnings.
- Alembic check: PASS; no new upgrade operations.
- Alembic offline upgrade generation: PASS.

Web:

- npm audit: PASS; 0 vulnerabilities.
- ESLint: PASS.
- TypeScript typecheck: PASS.
- Vitest: PASS; 6 files, 15 tests.
- Production build: PASS.
- Existing Playwright suite: PASS; 13 passed, 3 existing OTP-environment
  skips.
- Real browser acceptance: PASS; 2 happy-path/layout tests and 1 fresh-pilot
  negative test.

Launcher:

- Launcher pytest: PASS; 32 passed.
- `git diff --check`: PASS.
- CLI help, status, legacy menu dispatch, fresh-reset confirmation, and safe
  launcher-owned stop paths were exercised.

Flutter:

- Dart format check: PASS; 12 files, 0 changes.
- Flutter analyze: PASS; no issues.
- Flutter tests: PASS; all 7 tests passed.
- Debug APK build: PASS.

## Security and repository state

- Known local port conflicts remain interactive and opt-in; unrelated PIDs are
  never killed automatically.
- Evidence was accessed only through authorized Supervisor/Owner flows during
  acceptance.
- No secrets or tokens were added to tracked files or the report.
- No mobile feature work was introduced.
- The pre-existing generated change in `apps/web/next-env.d.ts` was preserved
  and intentionally left unstaged.

## Remaining blockers

No acceptance blocker remains. The three skipped existing Playwright tests are
the repository's optional real-OTP tests and were superseded for this run by
the controlled pilot OTP acceptance flow.

## Recommendation

Use `python launch.py` for the normal PC Role Lab workflow. Use
`python launch.py --fresh` only when a new pilot day is required, and type the
exact `RESET PILOT` confirmation.
