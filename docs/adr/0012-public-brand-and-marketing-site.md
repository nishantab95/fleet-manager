# ADR 0012: Public brand and marketing-site boundary

## Status

Accepted.

## Context

The operational product already uses one Next.js application for authenticated
Owner, Supervisor, and controlled QA workspaces. The public product brand is now
Fleet AI Systems and its canonical domain is `fleetaisystems.com`. The product
needs a public marketing surface without coupling anonymous visits to an
operations session or introducing a second deployment unnecessarily.

The repository also contains mature compatibility identifiers: Android package
IDs, API route prefixes, PostgreSQL names, environment variables, service names,
launcher filenames, migration history, object paths, and pilot artifact names.
They are operational boundaries rather than customer-facing copy.

## Decision

- Public pages live in an App Router route group inside `apps/web`. The group
  provides the Fleet AI Systems navigation, footer, design system, and public
  routes while preserving the existing operational URLs.
- `/` is the public homepage. Operational access is explicit through `/login`,
  then the existing role-specific workspaces.
- The root provider activates the browser authentication session only for
  operational routes. Anonymous marketing visits do not call session-refresh or
  Fleet API endpoints.
- Public pages are statically renderable. Metadata, Open Graph artwork, the
  favicon, `robots.txt`, and `sitemap.xml` use `fleetaisystems.com`.
- The public contact form does not pretend to persist a lead. Until a reviewed
  first-party capture endpoint or mail provider is configured, it validates the
  fields locally and prepares an email draft for the visitor to review and send.
  The page identifies the channel as a pre-launch dependency.
- The Owner showcase includes a curated capture from the working interface with
  representative test data. Driver and Supervisor device previews are
  constructed from their working interaction patterns. The showcase contains no
  real customer data and does not claim unavailable functionality.
- Visible application branding changes to Fleet AI Systems where safe. Internal
  compatibility identifiers remain unchanged.

## Consequences

The marketing site and operations console share a build, security headers, and
deployment unit, but have separate layouts and runtime behavior. This is the
lowest-risk architecture for the current product size. A separate marketing app
can be reconsidered if independent release cadence, content management, or edge
hosting becomes a concrete requirement.

Before public deployment, the business must confirm that
`hello@fleetaisystems.com` is active, replace the pre-launch legal placeholders,
and decide whether to connect a consent-aware server-side lead store. No backend,
database, authentication, Android package, or infrastructure rename is required
for the public brand launch.

## Alternatives rejected

- A separate marketing application now: it would duplicate tooling and
  deployment work without a current independent-release requirement.
- Reusing `/` as an authenticated redirect: it prevents a canonical public
  homepage and mixes anonymous discovery with operations session restoration.
- Renaming every technical identifier: this would risk application identity,
  migrations, scripts, evidence paths, and existing deployments for no public
  benefit.
- Returning a successful contact response without persistence: this would create
  false lead-delivery behavior.
