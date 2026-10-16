# Owner/supervisor dashboard agent guide

Read [PROJECT_RULES.md](../../PROJECT_RULES.md) first; it is the primary contract.
Use [change workflows](../../docs/development/change-workflows.md) and
[security](../../docs/security.md) for the requested task, not a full-repository rewrite.
Check Git status and inspect the existing feature, API contract and tests before editing.

- Routes/proxies: [app/](app/). Workspaces and colocated tests: [features/](features/).
  Shared API types/client: [lib/](lib/). Browser regressions: [e2e/](e2e/).
- Preserve `company_pin` and owner-issued activation; do not introduce SMS/Firebase login requirements.
  Keep browser session handling in the existing auth/proxy flow; backend authorization is authoritative.
- Never expose private administration/storage services or trust UI hiding as permission enforcement.
  API changes must remain compatible with mobile event UUIDs, offline records and existing device registrations.
- Do not change Pilot package/signing identity, deployment targets or live data through a dashboard task.
  Local development uses `npm run dev`; it does not authorize production deployment.
- From this directory run `npm run lint`, `npm run typecheck` and `npm test -- <affected-test>`.
  Run `npm run build` for runtime/configuration changes and relevant `npm run test:e2e -- <spec>` checks.
  Record checks not executed; tests/builds never authorize automatic deployment or publishing.

Keep the framework-maintained block below intact and consult its installed-version guidance.

<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
