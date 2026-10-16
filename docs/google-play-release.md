# Google Play production release and Pilot migration

## Audited Android identities

The current private Pilot identity was inspected locally on 2026-10-16 before
the Play process was added:

- package: `com.fleetmanager.fleet_manager_mobile.pilot`;
- certificate SHA-1:
  `11:D4:B4:DC:04:F0:D3:06:89:03:E1:C3:33:C1:89:4E:7A:E4:7A:74`;
- certificate SHA-256:
  `FD:25:11:5E:20:AC:18:A8:A7:CD:A9:1B:9F:4D:5F:61:53:F5:4B:4D:79:C7:51:B5:00:5A:3A:C7:34:CC:3C:29`.

The configured signer matched the hard-coded Pilot APK validator. No key,
alias, password, package, or certificate was generated, replaced, or copied.
Private Pilot builds still use `fleetPilot*` Gradle properties and the existing
private update workflow.

The existing production flavor is
`com.fleetmanager.fleet_manager_mobile`. This package has not been verified as
created or available in Play Console. It is deliberately not changed in this
phase. Because it differs from the `.pilot` package, Google Play cannot upgrade
an installed Pilot APK in place. Android treats the two packages as separate
apps even if their visible names match.

## Release identities

Google Play uses two certificates:

- the Play App Signing certificate, held by Google and used on APKs delivered
  to users;
- a separate upload certificate used to authenticate submitted AABs.

Create/enroll these only in the owner-controlled Play Console process. Do not
reuse, export, rotate, or regenerate the Pilot key. Put the upload keystore and
passwords in an owner-controlled secret store. The repository and CI never
generate signing material.

Local Gradle properties use only these names:

```properties
fleetPlayStoreFile=C:\secure\fleet-play-upload.jks
fleetPlayStorePassword=<secret>
fleetPlayKeyAlias=<alias>
fleetPlayKeyPassword=<secret>
```

The expected upload certificate SHA-256 is independently recorded as
`FLEET_PLAY_UPLOAD_CERT_SHA256`. The build refuses the Pilot SHA-256 and refuses
debug signing.

## Production authentication and Play Console prerequisites

1. Keep the server and AAB at `FLEET_AUTH_MODE=company_pin`. Google Play
   distribution does not change authentication: an Owner creates a time-limited,
   single-use code, the authorised person enters it once, and the installation
   then uses the existing PIN/device authentication. No SMS OTP service or
   Firebase Phone Authentication is required.
2. In Play Console, create the app with the exact existing production package,
   enroll in Play App Signing, and register the separate upload certificate.
3. Complete store listing, privacy policy, Data safety, content rating, target
   audience, app access/reviewer instructions, account deletion disclosures,
   and testing requirements applicable to the account.
4. Give a dedicated service account only the release permissions needed for
   this app. Do not use a personal owner credential.

Firebase packages remain in the source solely for compatibility with explicit
legacy/test builds. `main.dart` initialises Firebase only when the explicit auth
mode is `firebase`; the production mode is `company_pin`. Do not remove these
dependencies until the legacy paths and their tests are retired separately.

## Local signed AAB build

Create `%USERPROFILE%\.fleetaisystems\google-play-mobile.ps1` outside Git:

```powershell
$env:FLEET_API_BASE_URL='https://api.fleetaisystems.com'
$env:FLEET_PLAY_UPLOAD_CERT_SHA256='<colon-separated upload certificate SHA-256>'
```

Validate identity/configuration without building:

```powershell
.\scripts\build-play-aab.ps1 -BuildNumber 30 -BuildName 1.1.0 -ValidateOnly
```

Build and validate a signed AAB without uploading:

```powershell
.\scripts\build-play-aab.ps1 -BuildNumber 30 -BuildName 1.1.0
```

The validator checks the production package and approved version, requires
target SDK 36, verifies the JAR signature against the separate upload
certificate, and rejects `REQUEST_INSTALL_PACKAGES`. The production app defaults to
`https://api.fleetaisystems.com`; the workflow also supplies that URL
explicitly with `FLEET_AUTH_MODE=company_pin`. It has no Pilot update controller,
Pilot update manifest, FileProvider, or unknown-app installation permission.

## Approved Google Play workflow

Create a protected GitHub Environment named `google-play-production` with
required owner review and these secrets:

- `PLAY_UPLOAD_KEYSTORE_BASE64`
- `PLAY_UPLOAD_STORE_PASSWORD`
- `PLAY_UPLOAD_KEY_ALIAS`
- `PLAY_UPLOAD_KEY_PASSWORD`
- `PLAY_UPLOAD_CERT_SHA256`
- `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON`

Enable the IAM Service Account Credentials API in the service account's Google
Cloud project and grant that account `roles/iam.serviceAccountTokenCreator` on
itself only. Keep its Play Console permissions limited to this application.
The workflow derives the account email from the JSON credential and mints a
one-hour access token with only the
`https://www.googleapis.com/auth/androidpublisher` OAuth scope, then passes it
to the uploader as `PLAY_ACCESS_TOKEN`. It does not write a Google credential
file into the checkout. A generic Cloud SDK token is insufficient for the
[Android Publisher API](https://developers.google.com/android-publisher/api-ref/rest/v3/edits/insert);
the token setup follows the
[Google authentication action's access-token instructions](https://github.com/google-github-actions/auth#inputs-generating-oauth-20-access-tokens).

After the selected `main` SHA passes CI, request an Internal-track draft first:

```powershell
$sha = (git rev-parse HEAD).Trim()
gh workflow run google-play-release.yml --ref main `
  -f git_ref=$sha -f version_name=1.1.0 -f version_code=30 `
  -f track=internal -f release_status=draft `
  -f 'confirmation=RELEASE com.fleetmanager.fleet_manager_mobile'
```

The environment review is still mandatory. CI reconstructs the separate
upload keystore in a temporary runner directory, tests the mobile app, builds
the production AAB, validates identity/permissions, retains the AAB for 30
days, and commits the selected Google Play edit. No push triggers this
workflow. A completed production-track release requires separately choosing
`track=production` and `release_status=completed` with the same exact
confirmation and environment approval.

Use Internal testing, then closed testing, then a staged production rollout.
Do not jump to a completed production release before real-device activation,
expiration/replay rejection, PIN/device auth, logout/reactivation,
offline/restart, evidence upload, queue drain, and migration tests pass.

## Store listing and review copy

Use only screenshots captured from the final production candidate with test
data. Do not show real names, phone numbers, registration numbers, faces,
documents, sites, or evidence photographs.

- App name: **Fleet AI Systems**
- Category: **Business**
- Short description: **Offline-ready fleet operations for authorised construction teams.**
- Full description: **Fleet AI Systems connects authorised Owners, Drivers,
  Operators, and Supervisors across daily construction fleet operations. Record
  duty, trips, diesel, meter readings, maintenance, emergencies, and evidence;
  keep working through weak connectivity; and sync records when a connection
  returns. Access is private: your company Owner must register you and provide a
  time-limited, single-use activation code. After activation, the app uses your
  device security or Fleet PIN. Fleet AI Systems does not provide continuous GPS
  tracking.**
- Initial release notes: **Production cloud connection, owner-issued secure
  activation, offline queue preservation, evidence capture, and role-based fleet
  workflows. Private Pilot APK updates are not included in this Play build.**
- Privacy policy URL: `https://fleetaisystems.com/privacy`
- Reviewer access: explain that there is no public registration and provide a
  dedicated, time-limited test company/member and activation code through Play
  Console's protected app-access instructions. Never put a reusable code in the
  listing or release notes.

Required creative assets remain an owner deliverable: 512×512 PNG app icon,
1024×500 feature graphic, and genuine phone screenshots meeting the current
Play Console size/count rules. The repository icon is not approval of final
store artwork. Record evidence that the listing, installed label, screenshots,
and in-app UI all describe the same product.

## Data safety and declarations worksheet

Complete the Play form from the exact release and current Google definitions;
do not copy this worksheet without checking the Console prompts.

| Data or capability | Actual production use | Declaration evidence |
| --- | --- | --- |
| Name, phone, company membership | Account management and authorisation | Owner-created user/membership records |
| Device or installation identifier | Device binding, reactivation, abuse/security controls | Random installation ID and hashed credential record |
| App activity / operational content | Duty, trip, diesel, meters, maintenance, emergency, approval and audit workflows | API/database models |
| Photos | User-selected operational evidence | Camera permission and private S3 object records |
| Diagnostics/security logs | Reliability, security and incident investigation | Request/audit/container logs |
| Location | Not collected by the current app; no location permission | Merged manifest validation |
| SMS / phone authentication | Not used by the Play production app | `company_pin` build gate; no Firebase init in this mode |
| Arbitrary app installation | Not available in the Play flavor | AAB rejects `REQUEST_INSTALL_PACKAGES` |

Data is encrypted in transit; backup data is encrypted before offsite upload.
Access/deletion requests use the public privacy contact and company
administrator because the service has no public self-registration. Confirm the
current Play account-deletion policy against this managed-workforce model in
Console before submission. Camera is core evidence functionality; biometrics
are optional OS-mediated device authentication. Target audience is business
users, not children. Complete the content-rating questionnaire truthfully.

As of 31 August 2026, Google requires new apps and updates to target Android 16
(API 36); the Gradle config and AAB validator enforce 36. For a newly created
personal developer account, Google documents a closed test with at least 12
testers continuously opted in for 14 days before production access. Confirm
the account-specific Console requirement rather than assuming it applies to an
organisation account. See the official [target API requirements](https://developer.android.com/google/play/requirements/target-sdk), [testing requirements](https://support.google.com/googleplay/android-developer/answer/14151465), and [Play App Signing guide](https://support.google.com/googleplay/android-developer/answer/9842756).

## Controlled Pilot-to-Play migration

There is no safe in-place upgrade because the packages differ. For each Pilot
phone:

1. Keep the Pilot app installed. Connect it to the old Pilot/cloud endpoint and
   finish the active duty if one exists.
2. Open sync diagnostics and wait until the event/evidence queue is empty.
   Record the last successful sync and compare the Driver's latest event on the
   server. Never clear Pilot app data with pending work.
3. Install the Play app from the approved test/production track. It can coexist
   with Pilot and gets a new sandbox, secure store, SQLite database,
   installation UUID, and device registration.
4. Have the Owner issue a new single-use activation code for the same existing
   Fleet User. Activate the Play installation, configure PIN/device auth, and
   confirm the server returns the existing company membership, assignment,
   role, and historical records. Do not create a replacement Driver.
5. Perform a controlled duty/evidence/offline/restart/sync acceptance cycle in
   the Play app. Confirm client event UUID idempotency and private evidence read.
6. Remove the Pilot app only after the queue-empty evidence and server checks
   are recorded. Keep the Pilot installer/signing backup available for recovery
   during the migration window.

Existing server records and device registrations are preserved. The new Play
installation adds a new registration; it does not overwrite old events. Local
Pilot photographs and queued events stay inside the Pilot sandbox, which is why
queue drain is a hard migration gate.
