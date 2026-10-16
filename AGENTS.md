# Fleet AI Systems — agent entry point

Read [PROJECT_RULES.md](PROJECT_RULES.md) first: it is the primary project
engineering contract. This file and scoped instructions provide navigation,
not competing policies. Explicit owner instructions determine the current task.

## Begin every task

1. Confirm the actual Git root, branch, HEAD and `git status --short --branch`.
   Work on existing `main`; preserve unrelated or unfinished changes.
2. Read the request, [documentation index](docs/index.md), then only the relevant
   architecture, domain/security contracts and ADRs. Inspect existing code/tests
   before assuming a requested feature is missing or adding another implementation.
3. Identify auth, tenant/role, schema, API/client compatibility and offline-data
   impact. State material assumptions; ask before expanding authority.
4. Make the smallest necessary change, add regression coverage, run affected
   checks and update the authoritative docs. Use
   [change workflows](docs/development/change-workflows.md) for source locations,
   tests and release impact; [Windows development](docs/development.md) for setup.
5. Report actual commands/results, unverified checks, risks and Git state. A
   historical report is evidence of that run, not a fresh PASS.

## Boundaries that must survive

- Production is `company_pin`: Owner-issued expiring single-use activation,
  existing PIN/device auth, tenant/role/assignment enforcement. No required SMS
  or Firebase Phone Authentication. Never log credentials or weaken lockouts.
- Preserve offline event UUIDs, queue state, photographs, device registrations,
  memberships and history. Never clear app data to fix an update.
- Preserve the Pilot package and permanent signer. Play is a separate package,
  fixed HTTPS API and no private APK updater; use the controlled migration guide.
- Keep laptop/Pilot configuration independent of `infra/production`. No live
  deployment, push, DNS change, Play publication or signing change without explicit
  authority. A commit/push is not approval to deploy.
- Treat `.git`, `.env`, signing material, `.runtime`, releases, databases,
  evidence and backups as protected. No broad clean/prune/reset or volume deletion.
  Manual maintenance is separate from development, tests, startup and releases.

## Find the right scope

`apps/mobile`: Flutter/offline driver and role clients; `apps/web`: authenticated
Owner/Supervisor client; `apps/marketing`: isolated public website;
`services/api`: FastAPI modular monolith, models and migrations;
`infra/production`, `scripts/production`, `.github/workflows`: approved cloud releases.
Read the scoped `AGENTS.md` before changing a component. Keep generated Next.js
instructions intact. No microservices, decorative layers or broad rewrites.
