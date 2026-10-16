# Architecture documentation

[Documentation home](../index.md)

The product remains a modular monolith. These guides describe existing
boundaries and decisions, not permission to add business modules or rewrite
working workflows.

- [Architecture](../architecture.md): backend, mobile, browser, marketing,
  authentication, offline sync, and deployment boundaries.
- [Domain model](../domain-model.md): tenant ownership, effective-dated
  assignments, event identity, evidence, and operational history.
- [ADR inventory](../adr/README.md): the canonical list of decisions, including
  supersession and repaired historical identifiers.
- [Maintenance reference sources](../maintenance-template-sources.md):
  provenance and limitations of existing starter/template data.
- [Engineering audit](../production-engineering-audit.md): current coupling,
  verification limits, and incremental maintenance recommendations.

Current production authentication is owner-issued activation plus the existing
`company_pin` device/session mechanism. Firebase is optional compatibility,
not a Play prerequisite. Start with ADRs
[0012](../adr/0012-company-managed-activation-pin.md) and
[0013](../adr/0013-device-auth-and-workspaces.md).

For operational changes use the [operations index](../operations/index.md);
for deployment and Android distribution use the [release index](../releases/index.md).
