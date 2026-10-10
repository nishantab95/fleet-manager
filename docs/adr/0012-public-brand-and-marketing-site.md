# ADR 0012: Public brand and marketing-site boundary

## Status

Accepted.

## Context

The operational product uses one Next.js application for authenticated Owner,
Supervisor, and controlled QA workspaces. The public product brand is Fleet AI
Systems and its canonical domain is `fleetaisystems.com`. Public Internet
traffic must not share an application process, route tree, runtime credentials,
or deployment lifecycle with those private operations surfaces.

The repository also contains mature compatibility identifiers: Android package
IDs, API route prefixes, PostgreSQL names, environment variables, service names,
launcher filenames, migration history, object paths, and pilot artifact names.
They are operational boundaries rather than customer-facing copy.

## Decision

- Public pages live in the independent `apps/marketing` Next.js application.
  Its deployment contains no Owner, Supervisor, Driver QA, authentication, API
  proxy, evidence, administration, or OpenAPI routes.
- `apps/web` remains private. Its `/` redirects to the private login workspace,
  and its root metadata disallows indexing.
- Caddy exposes only the marketing process on ports 80/443. The Fleet API,
  operations web app, PostgreSQL, object storage, evidence, and internal tooling
  are not upstreams in the public Caddyfile.
- Public pages are statically renderable. Metadata, Open Graph artwork, the
  favicon, `robots.txt`, and `sitemap.xml` use `fleetaisystems.com`.
- The contact form posts only to `POST /public/leads` in the marketing process.
  It has strict field/enum/length validation, JSON size and origin checks, a
  honeypot, bounded in-memory source throttling, no read route, PII-free
  application logging, and fail-closed storage. Each accepted lead is written
  once to an administrator-protected directory outside the repository. It does
  not call the authenticated Fleet API or store data in the Fleet database.
- Product imagery is generated from the working Owner and Flutter role screens
  with deterministic representative fixtures. The capture command is explicit,
  is not part of normal tests, and never uses customer records.
- Visible application branding changes to Fleet AI Systems where safe. Internal
  compatibility identifiers remain unchanged.

## Consequences

The marketing site and operations console have independent builds, processes,
ports, routing boundaries, and update lifecycles. A website release can switch
between loopback ports after a health gate and reload Caddy without restarting
the Fleet API, database, private web app, object storage, or mobile publication.

Before public deployment, the business must confirm that
`hello@fleetaisystems.com` is active, approve privacy/terms copy and lead
retention, configure DNS/router/firewall/public-IP prerequisites, and execute the
go-live checks. No backend, database, authentication, Android package, or
infrastructure rename is required for the public brand launch.

## Alternatives rejected

- Integrating marketing routes into `apps/web`: rejected because it expands the
  Internet-facing artifact and couples public updates to the private operations
  client.
- Publishing the private app and relying only on route middleware: rejected
  because deployment isolation is a stronger and more auditable boundary.
- Renaming every technical identifier: this would risk application identity,
  migrations, scripts, evidence paths, and existing deployments for no public
  benefit.
- Returning a successful contact response without durable persistence: this
  would create false lead-delivery behavior.
