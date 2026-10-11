# Fleet AI Systems public website: Windows deployment runbook

## Recommended production topology: Cloudflare Tunnel

The recommended public path is:

```text
Internet
  -> Cloudflare HTTPS edge
  -> outbound remotely managed cloudflared tunnel
  -> http://127.0.0.1:3001
  -> apps/marketing standalone Next.js server
```

The Cloudflare path exposes only `apps/marketing`. It does not require router
port forwarding or public inbound Windows Firewall rules. Keep the origin bound
to `127.0.0.1`; do not point a public hostname at another Fleet service.

The older Caddy/public-port procedure below remains an alternative and is not
the recommended production path. Do not enable it alongside Cloudflare Tunnel
unless that change is reviewed separately.

## Cloudflare website install and operation

Run the one-time installer from an elevated PowerShell window in a clean,
reviewed checkout on `main`:

```powershell
.\scripts\install-public-website-cloudflare.ps1
```

The installer creates immutable releases under
`C:\FleetAISystems\Website\releases`, Cloudflare runtime state under
`C:\FleetAISystems\Website\runtime\cloudflare`, and stdout/stderr logs under
`C:\FleetAISystems\Website\logs\cloudflare`. The website process runs as
`SYSTEM` from the active release with `node server.js`, `NODE_ENV=production`,
`HOSTNAME=127.0.0.1`, and `PORT=3001`. Its environment is limited to the values
the marketing app needs, including
`FLEET_MARKETING_LEAD_DIR=C:\ProgramData\FleetAISystems\MarketingLeads`.
Firebase/API credentials are not passed to the marketing process.

Run the start, stop, update, rollback, and check helpers from an elevated
PowerShell window. The start helper triggers the task so the Node process always
runs as `SYSTEM`. The task `Fleet AI Systems Website (Cloudflare)` starts the website at Windows
startup and retries a failed start. Website runtime state tracks PID, process
start time, release, and port. Stop/update/rollback helpers verify the process
identity and recorded start time before stopping it.

```powershell
.\scripts\start-public-website-cloudflare.ps1
.\scripts\stop-public-website-cloudflare.ps1
.\scripts\check-public-website-cloudflare.ps1
.\scripts\update-public-website-cloudflare.ps1
.\scripts\rollback-public-website-cloudflare.ps1
```

For a future update, review or pull source on `main`, commit the reviewed
changes, then run the update helper from an elevated PowerShell window. It
requires a clean working tree and runs `npm ci`, the production-only audit,
lint, typecheck, unit tests, and production build before creating a new release.
It health-checks the new release, switches the startup task to it, and keeps the
previous release available for rollback. It restarts only the marketing Node
process; it does not restart Fleet API, Owner, Supervisor, PostgreSQL, MinIO, or
mobile distribution services.

Check the website task and tunnel service with:

```powershell
Get-ScheduledTask -TaskName 'Fleet AI Systems Website (Cloudflare)'
Get-Service cloudflared
```

The Cloudflare dashboard owns the remotely managed tunnel and public hostname
routes: `fleetaisystems.com` and `www.fleetaisystems.com` should point only to
`http://127.0.0.1:3001`. Never put a tunnel token in this repository, a checked
in environment file, or documentation. Use the official Cloudflare Windows
connector/service flow for any token installation.

Recovery: inspect the website stderr log in `C:\FleetAISystems\Website\logs\cloudflare`,
then run the start helper or `Start-ScheduledTask -TaskName 'Fleet AI Systems Website (Cloudflare)'`.
If the current release is unhealthy, run the rollback helper from an elevated
PowerShell window. Do not manually kill a PID; the helpers verify the recorded
process identity and start time.

The lead directory stays outside Git and website releases at
`C:\ProgramData\FleetAISystems\MarketingLeads`, with access restricted to
`SYSTEM` and local Administrators. Treat lead files as contact PII and follow
the retention and encrypted backup rules below.

## Public/private security boundary

Only the public marketing pages, `/health`, and `POST /public/leads` are
available through the public hostname. The hostname must not route to `apps/web`,
Owner, Supervisor, FastAPI, PostgreSQL, MinIO, Docker, RDP, SMB, SSH, or any
private/admin route. In particular, `/api/v1/*`, `/owner`, `/supervisor`, `/lab`,
`/docs`, `/redoc`, `/openapi.json`, `/evidence/private`, `/internal`, and
`/admin` must remain unavailable from the marketing app. Do not configure router
port forwarding or create inbound firewall rules for ports 80, 443, 3001, 3100,
3101, 8000, 5432, 19000, or 19001.

## Legacy alternative: public Caddy ports

The Caddy steps below describe a separate alternative using public ports 80/443.
They are not the recommended Cloudflare production path. Do not run these steps
for a Cloudflare-only deployment.

### Alternative deployment scope

```text
Internet :80/:443
        -> Caddy automatic HTTPS
        -> 127.0.0.1:3100 or :3101
        -> apps/marketing standalone Next.js process

Private only: apps/web, Fleet API, PostgreSQL, MinIO/evidence,
Firebase credentials, release tooling, /login, /owner, /supervisor, /lab,
/api, /docs, /redoc, /openapi.json, /admin, /evidence, /internal
```

The public lead route is `POST /public/leads` in the marketing process. It is
not a route in the Fleet API. There is no public lead-list/read route.

## Prerequisites

- A Windows host that can stay powered on and has a reserved private LAN IP.
- Administrator access for the one-time service, task, ACL, and firewall setup.
- Node.js 24.x and npm 11.x available to the administrator and `SYSTEM` account.
- The official Caddy Windows executable at `C:\Caddy\caddy.exe`.
- Control of the `fleetaisystems.com` DNS zone.
- A working mailbox for `hello@fleetaisystems.com` and a monitored TLS contact
  email.
- Reviewed privacy notice, terms, lead-retention period, and consent wording.

Caddy uses the domain in its site address to enable automatic HTTPS. Ports 80
and 443 must be externally reachable for the normal certificate flow. The
checked-in configuration follows Caddy's documented Windows-service and reverse
proxy patterns.

## 1. Build and application checks before touching the network

From the repository root:

```powershell
Push-Location apps\marketing
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npm run e2e
Pop-Location
```

Confirm `http://127.0.0.1:3001/health` returns only:

```json
{"status":"ok","service":"fleet-ai-systems-marketing"}
```

Confirm the legal/footer copy and email address are approved. Do not proceed if
either is still marked as pre-launch.

## 2. Check public-IP and CGNAT conditions

1. Record the router's WAN IPv4 address.
2. From the host, check the public IPv4 shown by the ISP or a reputable IP
   lookup service.
3. If the addresses differ, or the router WAN address is in `100.64.0.0/10`,
   `10.0.0.0/8`, `172.16.0.0/12`, or `192.168.0.0/16`, assume CGNAT/double NAT.
4. For CGNAT, request a public/static IPv4 from the ISP or choose a separately
   reviewed tunnel/VPS design. Port forwarding alone will not solve CGNAT.
5. If IPv6 is used, publish an `AAAA` record only after inbound IPv6 80/443 and
   host firewall behavior are verified. Otherwise omit `AAAA`.

Do not expose ports 3000, 3100, 3101, 8000, 5432, 19000, 19001, 2019, Docker,
SMB, RDP, or SSH to the public Internet.

## 3. Configure DNS

At the authoritative DNS provider:

1. Create an `A` record for `@` pointing to the host's public IPv4.
2. Create a `CNAME` for `www` pointing to `fleetaisystems.com`.
3. Use a short TTL such as 300 seconds for initial launch; raise it after the
   address is stable.
4. If the ISP address changes, configure a reputable dynamic-DNS updater or buy
   a static address before launch.
5. Wait until public resolvers return the intended records before expecting
   certificate issuance.

## 4. Configure the router and Windows Firewall

On the router, reserve the host's LAN address and forward **TCP 80 and TCP 443
only** to that address. If another modem/router sits upstream, configure both or
bridge the upstream device.

In an elevated PowerShell window, create narrowly scoped inbound rules:

```powershell
New-NetFirewallRule -DisplayName 'Fleet AI Systems Website HTTP' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 80 -Profile Any
New-NetFirewallRule -DisplayName 'Fleet AI Systems Website HTTPS' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 443 -Profile Any
```

Do not add rules for the loopback marketing ports or private Fleet services.

## 5. Install the local runtime

First review `infra/caddy/Caddyfile.marketing.example` and the scripts. Then run
the checked-in helper from an elevated PowerShell window:

```powershell
.\scripts\install-public-website.ps1 `
  -TlsEmail 'ops@fleetaisystems.com' `
  -CaddyPath 'C:\Caddy\caddy.exe'
```

The helper:

- creates `C:\FleetAISystems\Website` for releases/runtime/logs;
- creates `C:\ProgramData\FleetAISystems\MarketingLeads` outside the repo;
- removes inherited lead-directory permissions and grants only Administrators
  and `SYSTEM` full control;
- builds a standalone release and starts it on loopback;
- validates the Caddyfile and installs Caddy as an automatic Windows service;
- creates a `SYSTEM` startup task for the marketing Node process.

It does not edit DNS, the router, the Windows Firewall, the Fleet API, the Owner
app, PostgreSQL, MinIO, or mobile distribution.

## 6. Validate before and after public cutover

Run:

```powershell
.\scripts\check-public-website.ps1
```

The helper verifies the local health payload, Caddy config, and representative
private-path 404 responses. Also check from a device outside the LAN:

```powershell
curl.exe -I https://fleetaisystems.com/
curl.exe https://fleetaisystems.com/health
curl.exe -I https://fleetaisystems.com/owner
curl.exe -I https://fleetaisystems.com/api/v1/auth/me
curl.exe -I https://fleetaisystems.com/openapi.json
```

Expected results: public pages are HTTPS; `/health` is safe and minimal; every
private route returns 404; `www` redirects to the canonical apex domain. Inspect
the certificate hostname/chain and test from both mobile data and a second
external network.

Submit one representative contact request and confirm exactly one JSON record
appears in the protected lead directory. Confirm invalid, oversized, honeypot,
and repeated requests are rejected, and that no request appears in PostgreSQL.

## Website-only start, stop, check, and update

PowerShell helpers and matching root `.cmd` launchers are provided:

```powershell
.\scripts\start-public-website.ps1
.\scripts\stop-public-website.ps1
.\scripts\check-public-website.ps1
.\scripts\update-public-website.ps1
```

The update helper performs `npm ci` and a production build, creates an immutable
timestamped release, starts it on the inactive loopback port, waits for `/health`,
atomically replaces the Caddy upstream include, reloads Caddy, writes runtime
state, and only then stops the old marketing Node PID. If health or Caddy reload
fails, it keeps/restores the old upstream and leaves private services alone.

No update helper invokes Docker, Alembic, the API launcher, the Owner web
launcher, PostgreSQL, MinIO, APK publication, or mobile update services.
Releases are retained for manual rollback. To roll back, point a new website
release at reviewed source; do not copy a mutable `.next` directory over the
running release.

## Lead data, logs, backup, and retention

- Lead JSON files contain contact PII. Keep the directory outside source control,
  do not sync it to consumer cloud drives, and do not serve it through Caddy.
- Application logs record receipt IDs and event names, not form fields, email,
  phone, IP, or user agent. Caddy access logs do contain network metadata and are
  configured for rolling retention of approximately 30 days.
- Choose and document a business retention period before launch (90 days is a
  reasonable starting policy only after legal approval). Delete expired lead
  files through an approved, auditable process.
- Back up leads only to encrypted, access-controlled storage. Test restoring a
  copy to a non-public directory. The Fleet PostgreSQL/Object Storage backup
  scripts do not include this independent lead store.
- Restrict the host, patch Windows/Node/Caddy, monitor disk space and certificate
  renewal, review rejected/429 trends, and alert on website or Caddy service
  failure.

## Controlled screenshot regeneration

The committed screenshots contain deterministic representative data. They are
generated from working product widgets, not customer environments. On the
approved Windows development machine:

```powershell
Push-Location apps\mobile
flutter test --update-goldens tool\marketing_screenshots_test.dart
Pop-Location
```

Review every changed PNG under `apps/marketing/public/product` before commit.
Normal `flutter test` does not run this `tool/` capture harness or rewrite the
marketing assets.

## Final go-live gates

- [ ] Legal/privacy/terms and lead retention approved.
- [ ] `hello@fleetaisystems.com` and TLS contact mailbox tested.
- [ ] Public/static IP or approved CGNAT solution confirmed.
- [ ] DNS apex and `www` records resolve correctly.
- [ ] Only TCP 80/443 forwarded and allowed.
- [ ] Caddy automatic HTTPS succeeds and renewals are monitored.
- [ ] Local and external health/private-route checks pass.
- [ ] Contact persistence, ACL, backup, retention, and failure fallback tested.
- [ ] Owner/API/database/object storage remain unreachable from the Internet.
- [ ] Recovery owner and website rollback procedure identified.
