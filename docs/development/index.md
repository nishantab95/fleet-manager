# Development documentation

[Documentation home](../index.md)

Laptop development is independent of the prepared cloud deployment. Existing
Windows/Pilot configuration, data, signing material, and installed applications
must remain intact. Development stays on the existing `main` branch under the
[project rules](../../PROJECT_RULES.md).

- [Windows development guide](../development.md): toolchain, bootstrap,
  component commands, test databases, and migrations.
- [Safe change workflows](change-workflows.md): source map, nine common change
  paths, targeted verification, release impact, and documentation maintenance.
- [Agent onboarding](agent-onboarding.md): shared Codex/Claude entry files,
  scope discovery and safe task handoffs.
- [Architecture](../architecture.md) and [domain model](../domain-model.md):
  boundaries and invariants to read before changing behavior.
- [Security guide](../security.md): tenant, role, session, evidence, and logging
  requirements that tests must preserve.
- [PC Role Lab](../pc-role-lab.md): explicit local/Pilot QA procedures; its
  historical OTP/reset examples are not production onboarding instructions.
- [Phase 7 E2E matrix](../phase7-e2e-matrix.md) and
  [Pilot acceptance checklist](../pilot-checklist.md): scenario and device checks.
- [Engineering audit](../production-engineering-audit.md): scoped findings and
  safe follow-up priorities, not authorization for broad refactoring.
- [Readiness evidence](../production-readiness-report.md): previously executed
  checks and unresolved external gates, not a fresh test run.
- [Local disk audit](../operations/local-disk-audit.md): measured generated
  output and guarded cleanup; never treat `.runtime` or Git history as a cache.

Production and Play use `company_pin`, without SMS or required Firebase login.
The [optional Firebase staging guide](../firebase-staging-runbook.md) applies
only when that separate mode is explicitly selected. For build/distribution
instructions use the [release index](../releases/index.md).
