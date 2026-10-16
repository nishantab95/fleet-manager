# Public marketing website agent guide

Read [PROJECT_RULES.md](../../PROJECT_RULES.md) first; it is the primary contract.
Use [change workflows](../../docs/development/change-workflows.md) and
[Ubuntu cloud deployment](../../docs/production-deployment.md); the
[Windows public-site runbook](../../docs/public-website-deployment.md) is a preserved alternative.
Check Git status and inspect the existing route, component and tests before editing.

- Public routes: [app/](app/). Shared UI: [components/](components/).
  Lead handling: [lib/leads.ts](lib/leads.ts). Browser regressions: [e2e/](e2e/).
- This is a separate public application, not an owner dashboard or driver-authentication surface.
  Do not import `apps/web`, add Fleet API proxy routes, or expose private administration/evidence services.
- Product copy must describe owner-issued activation with `company_pin`, not required SMS/Firebase login.
  Do not claim live deployment, guaranteed emergency response, or Google Play publication without evidence.
- Preserve mobile offline records/event UUIDs, device registrations and Pilot package/signing identity;
  this scope must not mutate them or add authentication/release features.
- From this directory use `npm run dev` (port 3001); run `npm run lint`, `npm run typecheck`,
  `npm test -- <affected-test>` and relevant `npm run test:e2e -- <spec>` checks.
  Run `npm run build` for runtime/configuration changes; report checks not executed.
- Building/testing is local verification, not authority to deploy, change DNS or publish applications.

Keep the framework-maintained block below intact and consult its installed-version guidance.

<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
