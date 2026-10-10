# Firebase staging and real-device OTP runbook

## Scope and stop conditions

This runbook enables controlled Firebase Phone Authentication testing for Fleet
AI Systems. It does not authorize a production rollout, Play Store publishing,
or use of production credentials. Stop if the staging Firebase project, staging
API, protected signing key, or test People records cannot be positively
identified.

The staging Android build deliberately uses the existing Pilot application ID
and Pilot signing identity:

```text
com.fleetmanager.fleet_manager_mobile.pilot
```

That keeps staging isolated from the future production app. The staging build
forces Firebase auth and a fixed HTTPS API URL. It does not load a saved Pilot
server override and does not enable the Pilot self-update path. A Pilot-auth
fallback remains a separate, explicitly built artifact using the same package
and signer.

## 1. Configuration ownership

| Value | Location | Commit? |
| --- | --- | --- |
| `FLEET_AUTH_MODE=firebase` | Staging API runtime and staging APK build process | No local value files |
| `FLEET_FIREBASE_PROJECT_ID` | Staging API runtime and APK build process | No environment values |
| `GOOGLE_APPLICATION_CREDENTIALS` | Optional absolute path on the API host, outside the repository | Never |
| `FLEET_JWT_SIGNING_KEY` | Staging API secret manager/runtime | Never |
| `FIREBASE_ANDROID_API_KEY` | APK build environment; public Firebase client identifier | Never as a local value file |
| `FIREBASE_ANDROID_APP_ID` | APK build environment; public Firebase client identifier | Never as a local value file |
| `FIREBASE_MESSAGING_SENDER_ID` | APK build environment; public Firebase client identifier | Never as a local value file |
| `FIREBASE_PROJECT_ID` | APK build environment | Never as a local value file |
| `FLEET_API_BASE_URL` | APK build environment; exact staging HTTPS API origin | Never as a local value file |
| Pilot keystore/passwords | User profile and user Gradle properties | Never |
| Owner web upstream | `apps/web/.env.local` or process environment | Never |

Firebase Android identifiers are expected to be embedded in the client APK;
they are not service-account credentials. API private keys, Fleet JWT signing
material, OTP values, refresh/access tokens, and service-account JSON must
never be passed as Dart defines or bundled as app assets.

## 2. Firebase staging project

1. Create or select a Firebase project dedicated to staging. Do not select the
   future production project.
2. Link the project to the required billing account before real SMS testing.
   Firebase states that Phone Authentication SMS requires billing.
3. In **Authentication → Sign-in method**, enable **Phone**.
4. In **Authentication → Settings**, configure the SMS region policy for only
   the countries used by this staging test. New projects can deny all regions
   until this is configured.
5. Register an Android app with package
   `com.fleetmanager.fleet_manager_mobile.pilot`.
6. Add the Pilot signing certificate SHA-1 and SHA-256 fingerprints. SHA-256 is
   used by Play Integrity; SHA-1 is required for the reCAPTCHA fallback that is
   common for side-loaded builds.
7. Add fictional Firebase test phone numbers and fixed six-digit codes for the
   first pass. Firebase permits a limited number of configured test numbers;
   keep them fictional, rotate them, and never hardcode them in the app or
   repository.
8. Restrict the Android API key to the registered package/signing certificate
   where supported. Account for Firebase's documented reCAPTCHA fallback when
   applying API-key restrictions.
9. Review Firebase Authentication quotas, per-IP and per-number throttling,
   activity logging, IAM, and budget alerts before sending real SMS.

Official references:

- <https://firebase.google.com/docs/auth/android/phone-auth>
- <https://firebase.google.com/docs/auth/limits>
- <https://firebase.google.com/docs/auth/admin/verify-id-tokens>
- <https://firebase.google.com/docs/auth/admin/manage-sessions>

The current Android sign-in screen accepts an Indian ten-digit mobile number
and sends it to Firebase as `+91...`. The backend normalization layer remains
E.164/region-aware, but non-Indian mobile UI is outside this staging phase.

## 3. Backend staging configuration

Use a staging-only environment or secret manager. A representative key set is:

```text
FLEET_ENVIRONMENT=staging
FLEET_AUTH_MODE=firebase
FLEET_FIREBASE_PROJECT_ID=<staging-project-id>
FLEET_FIREBASE_CHECK_REVOKED_TOKENS=true
GOOGLE_APPLICATION_CREDENTIALS=C:\secure\fleet-staging-service-account.json
FLEET_JWT_SIGNING_KEY=<existing-independent-secret-at-least-32-characters>
FLEET_WEB_PUBLIC_BASE_URL=https://<staging-owner-host>
FLEET_CORS_ALLOWED_ORIGINS=https://<staging-owner-host>
FLEET_ALLOWED_HOSTS=<staging-api-host>
```

`GOOGLE_APPLICATION_CREDENTIALS` is optional when the staging runtime already
provides Application Default Credentials through its workload identity. If a
JSON credential is unavoidable, mount it read-only outside the repository and
limit filesystem access. The Firebase Admin credential and Fleet JWT signing
key are separate trust domains.

The `staging` profile fails closed unless Firebase mode, a non-empty Firebase
project ID, a JWT signing key of at least 32 characters, explicit CORS/host
allowlists, an HTTPS public web URL, and secure cookies are in effect. Pilot or
development OTP settings are rejected in this profile.

Full Driver/Supervisor testing also requires configured private evidence
storage. Do not call the environment ready if photo upload is still using the
unavailable provider.

### Database migration

Back up the database, then run from `services/api`:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic check
```

The expected single head is `0023_user_auth_identity`. This migration is
additive. Do not reset the database, recreate People, or rewrite assignments.

### Start the API

Start the API with the staging environment loaded by the process/runtime, then
check `/health` and `/ready`. A missing credential or mismatched Firebase
project must be treated as a failed staging configuration, never worked around
with Pilot OTP endpoints.

## 4. Owner web remains independent

The Owner web app does not need Android Firebase values or service-account
credentials. Point only its server-side upstream at the staging API in the
gitignored `apps/web/.env.local`:

```text
FLEET_API_UPSTREAM_URL=https://<staging-api-host>
```

Then run from `apps/web`:

```powershell
npm run dev
```

The Owner browser can continue using the API's existing web session boundary.
Do not copy `FIREBASE_ANDROID_*`, `GOOGLE_APPLICATION_CREDENTIALS`, or
`FLEET_JWT_SIGNING_KEY` into the web directory.

## 5. People readiness before login

Every person must already exist in Fleet AI Systems. Before enabling a test
number, open Owner → People and resolve the displayed Firebase sign-in state:

- **Linked** — the phone has already completed Firebase verification and is
  durably linked.
- **Ready — verify on first login** — one active Fleet User has the phone and
  can create the link after successful Firebase verification.
- **Phone missing** — enter a valid number and save it.
- **Duplicate phone** — stop; resolve all records that normalize to the same
  E.164 number. Automatic linking intentionally refuses ambiguity.
- **Disabled** — reactivate only after confirming that company access should be
  restored and operational dependencies are safe.

Owner onboarding normalizes new phone numbers and prevents both exact and
legacy-format normalized duplicates. Firebase verification never creates a
User, membership, role, company, assignment, or site.

Changing a linked phone requires Owner confirmation. The API disables the old
Firebase identity link, revokes the person's Fleet sessions, retains the same
User/memberships/assignments/history, and requires verification of the new
number. Cross-company identities require administrator review instead of a
tenant-local phone change.

## 6. Staging APK preflight and build

First validate only local tooling, package identity, version parsing, and the
protected Pilot signer configuration. This reads no Firebase values:

```powershell
.\scripts\build-firebase-staging-apk.ps1 -ToolingOnly
```

Supply real staging values only in the current build process or an approved CI
secret context:

```powershell
$env:FLEET_AUTH_MODE="firebase"
$env:FLEET_API_BASE_URL="https://<staging-api-host>"
$env:FLEET_FIREBASE_PROJECT_ID="<staging-project-id>"
$env:FIREBASE_ANDROID_API_KEY="<staging-android-api-key>"
$env:FIREBASE_ANDROID_APP_ID="<staging-android-app-id>"
$env:FIREBASE_MESSAGING_SENDER_ID="<staging-sender-id>"
$env:FIREBASE_PROJECT_ID="<staging-project-id>"
.\scripts\build-firebase-staging-apk.ps1
```

The script refuses to build unless the branch is `main` and the source tree is
clean. It builds the `pilot` flavor with:

```text
FLEET_AUTH_MODE=firebase
FLEET_BUILD_PROFILE=firebase-staging
```

It then verifies:

- package `com.fleetmanager.fleet_manager_mobile.pilot`;
- version name/code from `pubspec.yaml`;
- the protected Pilot signing certificate;
- the expected staging API URL and Firebase public client values are embedded;
- the Firebase staging build marker is embedded;
- no service-account/private-key marker is present.

The APK and provenance JSON are written only below `apps/mobile/build/release`
and are ignored by Git. The script never copies or publishes them.

Install the resulting APK on a controlled Android device without deleting app
data:

```powershell
adb install -r <absolute-path-to-staging-apk>
```

The sign-in screen must show **FIREBASE STAGING** and the exact staging API URL.
There must be no Server settings action. If any of these checks fail, uninstall
only after confirming there is no active duty or unsynced evidence/event data.

## 7. Real-device verification sequence

Start with Firebase fictional test numbers, then use the smallest approved set
of real phones. Record timestamp, device, package/version, signer fingerprint,
role, expected result, actual result, and the related safe audit action. Never
record the OTP or token.

### Owner

1. Confirm the Owner Person is `Ready — verify on first login`.
2. Request and enter the code; confirm the server returns only the Owner
   membership and the Owner workspace opens.
3. Close/reopen the app and confirm the Fleet session restores.
4. Log out and confirm both Fleet and Firebase sign out.
5. Sign in again and confirm the existing identity link is reused.

### Supervisor

1. Confirm an active Supervisor membership and explicit Site grants.
2. Complete first and repeat login.
3. Confirm only granted Sites are visible and an unauthorized Site remains
   denied by the API.
4. Log out and switch to another approved account.

### Driver

1. Confirm an active Driver membership and existing effective-dated
   assignment.
2. Complete first login and verify the same Asset/Site/Supervisor assignment is
   returned; authentication must not create or rewrite an assignment.
3. Capture an offline-safe event in the approved test workflow, sync it, and
   confirm account-scoped queue behavior.
4. Before account switching, end active duty and sync every queued record. The
   handover guard must block switching if this is not safe.

### Negative and lifecycle cases

- Wrong OTP: safe incorrect-code message; no Fleet session or identity link.
- Expired OTP: safe expiry message; request a new challenge.
- Unknown verified phone: `ACCESS_DENIED`; no User or membership created.
- Ambiguous normalized phone: `ACCOUNT_CONFIGURATION_ERROR`; resolve data
  before retrying. Use automated/disposable staging data for this case rather
  than corrupting a real company record.
- Disabled User or membership: access denied and no session created.
- Changed phone: old Firebase subject denied, old Fleet sessions revoked, new
  number requires verification, and assignment/history remains unchanged.
- Role correctness: every workspace option comes from the server; no client
  role selection can create or elevate access.
- Invalid/wrong-project/revoked Firebase token: rejected by the API.
- Quota/throttling/no network: safe retryable error; do not switch to Pilot
  inside the Firebase staging deployment.

## 8. Monitoring and revocation

During the test window, monitor Firebase Authentication activity/quotas and
Fleet structured logs/audit rows. Expected Fleet audit actions include:

```text
AUTH_IDENTITY_LINKED
LOGIN_SUCCESS
LOGIN_DENIED
MEMBERSHIP_ACCESS_DENIED
AUTH_IDENTITY_DISABLED
AUTH_SESSIONS_REVOKED
PHONE_CHANGE_REQUESTED
LOGOUT
```

Logs must not contain OTPs, Firebase ID tokens, Fleet access/refresh tokens,
credentials, or full phone numbers. Keep
`FLEET_FIREBASE_CHECK_REVOKED_TOKENS=true`; checking revocation adds a Firebase
request and should be included in availability monitoring.

For a compromised/test Firebase account, disable or revoke it in Firebase and
deactivate the relevant Fleet membership/User according to the incident scope.
Firebase revocation alone does not replace Fleet's server-side membership and
session checks.

## 9. Controlled rollback to Pilot authentication

Do not change the running `staging` profile to Pilot mode; startup rejects that
downgrade. If the controlled Firebase test must stop:

1. Stop onboarding and ensure every Driver has ended duty and synced local
   records.
2. Preserve the database and migration `0023`; do not disable or delete linked
   identities merely to roll back transport.
3. Start a separately configured private Pilot API with
   `FLEET_ENVIRONMENT=pilot`, `FLEET_AUTH_MODE=pilot`,
   `FLEET_OTP_PROVIDER=pilot`, and role OTP values supplied outside Git.
4. Build the existing Pilot APK with `scripts/build-pilot-apk.ps1`.
5. Verify the same `.pilot` package and protected signer, then install with
   `adb install -r` so local account-scoped data is retained.
6. Confirm the UI says **PILOT / TEST** and explicitly test the private Pilot
   backend before resuming controlled use.

Pilot fallback is a deliberate environment/artifact replacement, not a hidden
fallback inside a Firebase build.

## 10. Gate before a real company rollout

Do not proceed beyond staging until all of the following are recorded:

- all automated backend/web/mobile tests and static checks pass;
- migration current/head/check passes on a restored staging database;
- package, version, signer, build profile, API URL, and APK hash are recorded;
- Owner, Supervisor, and Driver first/repeat/logout/account-switch flows pass on
  physical devices;
- wrong, expired, unknown, disabled, changed-phone, and role-isolation cases
  pass;
- Driver assignment and offline queue history remain intact;
- Firebase SHA fingerprints, SMS regions, billing, quotas, IAM, audit/activity
  logging, alerting, and revocation procedure are reviewed;
- no credential, `.env`, keystore, APK, token, or Firebase private key appears
  in Git.

Production Firebase project creation/activation, production signing, Play
Store work, and broad company onboarding remain separate approvals.
