# Architecture decision inventory

ADRs record the decision and its original context. Later decisions can supersede
only part of an earlier record; the retained history must not be mistaken for
current deployment instructions. The current production authentication is
`company_pin` under ADRs 0012 and 0013. Firebase under ADR 0011 remains optional.

"First committed" is the introduction date from local Git history, not an
inferred decision date. Existing decision dates inside documents are retained
even when they differ from the commit date. "This preparation" identifies new
production-preparation ADRs whose introduction commit is this release's commit;
consult Git for its date rather than inferring one from draft creation.

| ID | Decision | First committed | Current scope/status |
| --- | --- | --- | --- |
| [0001](0001-foundation-architecture.md) | Foundation architecture | 2026-09-21 | Accepted modular-monolith boundaries |
| [0002](0002-core-domain-model.md) | Core domain and database integrity | 2026-09-21 | Accepted; later domain additions extend it |
| [0003](0003-authentication-and-rbac.md) | Initial OTP authentication and RBAC | 2026-09-22 | Session/RBAC invariants retained; production provider superseded by 0012/0013 |
| [0004](0004-owner-admin-web-session.md) | Initial browser sessions | 2026-09-22 | Reload behavior superseded by 0006's HttpOnly refresh-cookie adapter |
| [0005](0005-operational-reporting-and-daily-closure.md) | Reporting, closure, and Excel | 2026-09-22 | Accepted; includes the recorded reporting amendment |
| [0006](0006-pc-role-lab-workspaces.md) | PC Role Lab and shared web client | 2026-09-23 | Historical lab scope; shared browser session/workspace boundary retained |
| [0007](0007-pc-supervisor-emergency-alerts.md) | Supervisor grouping and emergency alerts | 2026-09-24 | Accepted within current operational scope |
| [0008](0008-maintenance-v2-meter-capabilities.md) | Maintenance and meter capabilities | 2026-10-09 | Accepted; legacy wheeled defaults corrected by 0009 |
| [0009](0009-rental-operations-maintenance-responsibility.md) | Rental operations and maintenance responsibility | 2026-10-09 | Accepted; intercompany sharing remains disabled |
| [0010](0010-maintenance-starter-catalog.md) | Maintenance starters and model references | 2026-10-09 | Accepted; starter data is not an OEM guarantee |
| [0011](0011-firebase-phone-authentication.md) | Firebase authentication | 2026-10-10 | Optional compatibility/staging; not required by cloud/Play |
| [0012](0012-company-managed-activation-pin.md) | Owner activation and device PIN | 2026-10-11 | Current activation contract; role selection/unlock amended by 0013 |
| [0013](0013-device-auth-and-workspaces.md) | System device authentication and workspaces | 2026-10-12 | Current; preserves Build 28 credentials and backend membership authority |
| [0014](0014-private-release-https-upload.md) | Private Pilot HTTPS publication | 2026-10-12 | Preserved Pilot-only release path |
| [0015](0015-single-vps-production-deployment.md) | Single VPS and approved deployments | This preparation | Accepted for production preparation; external setup gates remain |
| [0016](0016-google-play-and-pilot-release-separation.md) | Play/Pilot distribution separation | This preparation | Accepted for preparation; distinct packages require controlled migration |
| [0017](0017-supervisor-operations-verification.md) | Site-scoped supervisor verification | 2026-09-22 | Accepted; renumbered former duplicate 0005 |
| [0018](0018-public-brand-and-marketing-site.md) | Public brand and marketing isolation | 2026-10-10 | Isolation retained; cloud routing superseded by 0015 |

## Identifier repair on 2026-10-16

Two independently introduced documents reused existing IDs. They were renamed
without rewriting their decisions:

- `0005-supervisor-operations-verification.md` became
  [0017-supervisor-operations-verification.md](0017-supervisor-operations-verification.md).
  ADR 0005 remains the reporting decision.
- `0012-public-brand-and-marketing-site.md` became
  [0018-public-brand-and-marketing-site.md](0018-public-brand-and-marketing-site.md).
  ADR 0012 remains company-managed activation.

Repository references use the canonical paths above. Git history retains the
original documents; use `git log --follow -- <current-path>` to inspect them.
The new numbers describe identifier repair order, not decision chronology.

New ADRs must take the next unused ID, record their date and scope, state any
supersession explicitly, and update this inventory. Do not reuse an existing ID.
