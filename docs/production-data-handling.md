# Production privacy and data-handling review

## Scope and status

This is an engineering inventory, not legal advice or a claim of compliance.
The final legal entity name/address, controller/processor roles, contracts,
retention schedule, lawful notices, grievance contact, incident reporting, and
cross-border basis require owner and qualified legal review before go-live.

The planned primary VPS region is Singapore. Users and companies may be in
India, so this can be cross-border processing. The Indian
[Digital Personal Data Protection Act, 2023](https://www.meity.gov.in/static/uploads/2024/02/Digital-Personal-Data-Protection-Act-2023-1.pdf)
and the notified
[Digital Personal Data Protection Rules, 2025](https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf)
must be assessed against the actual rollout dates, roles, notices, contracts,
and any restricted destinations. Do not infer compliance from hosting region.

The official
[CERT-In directions of 28 April 2022](https://cert-in.org.in/PDF/CERT-In_Directions_70B_28.04.2022.pdf)
include incident-reporting/time-synchronisation duties and a requirement for
covered entities to retain ICT-system logs for a rolling 180 days within Indian
jurisdiction. Applicability and the necessary Indian log location must be
reviewed before launch: the current size-bounded VPS logs in Singapore do not,
by themselves, prove that requirement. This is a launch blocker if counsel
determines the direction applies and no compliant log archive is configured.

## Data inventory

| Class | Examples | Purpose | Primary location |
| --- | --- | --- | --- |
| Identity/access | Name, phone, company membership, role, activation challenge hash/expiry/use state, PIN hash, device credential hash, installation ID, sessions, lockout state | Authorisation and security | PostgreSQL |
| Fleet operations | Sites, assets, deployments, assignments, duty, trips, diesel, KM/HMR, maintenance, emergency and review records, timestamps and event UUIDs | Deliver the fleet service and audit history | PostgreSQL |
| Evidence | User-captured JPEG/PNG/WebP and associated event/object metadata | Operational proof and review | Private MinIO plus encrypted offsite backup |
| Mobile local data | Offline events, UUIDs, pending photographs, assignment cache, installation/device credential in secure storage | Offline operation and safe retry | Android app sandbox/device secure storage |
| Marketing lead | Name, company, phone, email, fleet size/type, message | Respond to requested contact | VPS lead directory |
| Security/operations | Request ID, IP/access log, image/version, audit reason, backup/deploy state, health/error records | Security, reliability and incident response | Bounded VPS logs/state and approved log archive |

Activation codes and PINs are never stored in plaintext: server records contain
hashes, expiry/attempt/use state, and device-bound credentials. Application code
and documentation must not place codes, PINs, tokens, credentials, database
URLs, evidence bytes, or secret files in logs.

## Access and disclosure

Backend checks remain the source of truth for company membership, role,
membership status, device credential, installation binding, site/assignment,
and record-level permissions. PostgreSQL, MinIO, its console, the Caddy admin
endpoint, OpenAPI/docs, and owner/admin API families are not public. Owner
browser requests use the private same-origin web proxy. Service operators and
backup credentials should receive the least privilege needed and be reviewed
periodically.

The production Android app does not use Firebase Phone Authentication or SMS.
Optional Firebase compatibility code is not initialised under
`FLEET_AUTH_MODE=company_pin`. Google Play distributes the app but does not
replace Fleet authentication. Offsite storage receives Restic-encrypted backup
content; the decryption password is kept separately.

## Retention, requests, and new data uses

Before launch, the Owner must approve retention periods for each class,
including active records, security/audit logs, evidence, marketing leads,
disabled users/devices, and offsite backup snapshots. The current scripts keep
two successfully offsite-backed local backup generations and intentionally do
not prune the remote repository. Deletion requests therefore need a documented
process and a stated backup-expiry delay.

Users should contact their company administrator or
`hello@fleetaisystems.com` for access, correction, export, or deletion. Verify
identity and company authority, preserve legally required records, record the
decision, and avoid disclosing another tenant's data.

The current app has no continuous GPS tracking and no location permission.
Adding GPS/telematics, automated profiling, new document integrations, facial
recognition, new analytics/advertising SDKs, or a new hosting/backup country is
a material scope change. Complete a renewed necessity, privacy, Play Data
safety, permission, retention, contract, security, and user-notice assessment
before implementing or enabling it.
