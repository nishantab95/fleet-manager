# Codex and Claude Code onboarding

[Development index](index.md) · [Shared entry point](../../AGENTS.md)

Open the actual checkout, not `D:\Git\fleet maneger` or a historical `.runtime`
checkout. Begin with `git rev-parse --show-toplevel`, `git status --short --branch`
and `git rev-parse HEAD`. Read [PROJECT_RULES.md](../../PROJECT_RULES.md), then
select the relevant guide through [docs/index.md](../index.md) and inspect the
existing feature, tests and applicable ADRs. Do not ask the agent to reread every
file or infer that a feature is missing from an old phase plan.

## One contract, small entry files

- Root `AGENTS.md` points both agents to the primary contract, task workflow,
  safety boundaries and component map.
- Root `CLAUDE.md` imports `AGENTS.md`; it does not maintain a second policy copy.
- Each of `apps/mobile`, `apps/web`, `apps/marketing` and `services/api` has a
  scoped `AGENTS.md` and a small `CLAUDE.md` import. Scoped files add component
  locations/checks without relaxing project rules.
- Existing Next.js-generated blocks remain intact. Before Next.js code changes,
  read the relevant installed-version guide under that application's
  `node_modules/next/dist/docs`; missing dependencies are a setup issue, not
  permission to guess changed APIs.

Codex discovers project instructions along the path from the repository root
to the working directory; more local instructions refine the scope. Its default
combined instruction-file budget is 32 KiB. Keep entry files concise and start
a new session after changing them. See the
[official Codex AGENTS.md guide](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

Claude supports relative `@path` imports and loads nested instructions when it
works in those subdirectories. Imports add context rather than saving context;
avoid recursive chains and policy duplication. Check loaded memory files in the
session instead of assuming discovery succeeded. See the
[official Claude memory guide](https://code.claude.com/docs/en/memory).

These are behavioral instructions, not an authorization or security boundary.
Protected GitHub environments, credentials, infrastructure permissions and human
release approval remain necessary. No new session is authorized to deploy,
publish, push or clean protected state merely because an instruction file exists.

## A useful task handoff

Give the intended behavior, relevant user role, affected component, compatibility
constraints and verification outcome. Ask the agent to locate existing code first,
make the smallest change, add a regression and report actual checks. The
[change workflows](change-workflows.md) map common requests to source and tests.
For a resumed task supply the current SHA/status and latest report, not instructions
to reset the tree. Separate local preparation from cloud readiness, live verification
and Play publication. Missing access is a blocker to report, not a result to invent.

When changing agent guidance, review root and relevant nested files together,
validate links/imports and source paths, and keep `PROJECT_RULES.md` authoritative.
Do not overwrite useful generated instructions or store credentials, private
driver records or long transient test logs in instruction files.
