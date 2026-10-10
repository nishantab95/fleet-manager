# Firebase phone authentication setup

This guide describes the Firebase authentication architecture and base setup.
For the controlled staging build, exact configuration placement, real-device
test matrix, and rollback procedure, use
[Firebase staging and real-device OTP runbook](firebase-staging-runbook.md).
Neither document authorizes a production deployment. Use separate Firebase
projects for staging and production, and never reuse a staging service account
in production.

## 1. Create and harden Firebase projects

1. Create distinct Firebase projects, for example `fleet-manager-dev` and `fleet-manager-prod`.
2. In **Authentication → Sign-in method**, enable **Phone**.
3. Add fictional test phone numbers and fixed codes only to the development project. Do not use real customer numbers in automated tests.
4. Review Authentication usage limits, authorized domains, abuse controls, billing/quotas, and project IAM. Grant the backend identity only the minimum Firebase Auth permissions it needs.

## 2. Register Android applications

Register only the Android package IDs that will actually use Firebase:

- Controlled staging/Pilot flavor: `com.fleetmanager.fleet_manager_mobile.pilot`
- Future production flavor, not part of staging: `com.fleetmanager.fleet_manager_mobile`

Add SHA-1 and SHA-256 fingerprints for every signing certificate used by Firebase builds: local debug, CI/staging, and the protected release keystore. Obtain fingerprints with Gradle's `signingReport` or `keytool`. Phone sign-in can fail on a real device when the installed build's package name or certificate fingerprint is missing.

The current client receives Firebase values through build-time Dart defines; do not commit `google-services.json`, `GoogleService-Info.plist`, or service-account JSON.

## 3. Configure the mobile build

For staging, use `scripts/build-firebase-staging-apk.ps1`; it forces Firebase
mode, the staging build profile, the `.pilot` package, the protected Pilot
signer, and an explicit HTTPS API URL. Supply the selected project's public
Android app values at build time:

```powershell
flutter run --flavor pilot `
  --dart-define=FLEET_PILOT=true `
  --dart-define=FLEET_AUTH_MODE=firebase `
  --dart-define=FLEET_BUILD_PROFILE=firebase-staging `
  --dart-define=FLEET_API_BASE_URL=https://<staging-api-host> `
  --dart-define=FIREBASE_ANDROID_API_KEY=<android-api-key> `
  --dart-define=FIREBASE_ANDROID_APP_ID=<android-app-id> `
  --dart-define=FIREBASE_MESSAGING_SENDER_ID=<sender-id> `
  --dart-define=FIREBASE_PROJECT_ID=<firebase-project-id>
```

These client identifiers are not backend credentials, but project-specific files and values should still be supplied by the build environment. Restrict the Android API key to the registered package and signing certificates where supported.

Pilot mode remains explicit and does not initialize Firebase:

```powershell
flutter run --flavor pilot --dart-define=FLEET_AUTH_MODE=pilot
```

## 4. Configure the API

Use Application Default Credentials in the deployed runtime (recommended), or mount a narrowly scoped service-account file outside the repository and point `GOOGLE_APPLICATION_CREDENTIALS` to that mounted path.

```text
FLEET_ENVIRONMENT=staging
FLEET_AUTH_MODE=firebase
FLEET_FIREBASE_PROJECT_ID=<firebase-project-id>
FLEET_FIREBASE_CHECK_REVOKED_TOKENS=true
FLEET_JWT_SIGNING_KEY=<independent-random-secret-at-least-32-characters>
```

The API and mobile build must reference the same environment-specific Firebase project. Do not put Firebase private keys in `FLEET_JWT_SIGNING_KEY`; Fleet JWT signing and Firebase credentials are independent trust domains.

For local testing from `main`, keep backend settings in the gitignored root `.env` and start the API normally. Set `FLEET_AUTH_MODE=firebase`, `FLEET_FIREBASE_PROJECT_ID`, and either Application Default Credentials or `GOOGLE_APPLICATION_CREDENTIALS`; keep the existing independent Fleet JWT signing key. Do not switch the file to Firebase mode until all of those values are available, because an incomplete Firebase configuration intentionally fails closed.

The Owner launcher remains independent of Flutter Firebase configuration. `Start Fleet Manager Owner.bat` only starts the Next.js application and reads `FLEET_API_UPSTREAM_URL` from `apps/web/.env.local`; it does not read Android API keys, app IDs, sender IDs, or `google-services.json`. Point it at the intended healthy API without copying mobile or backend credentials into the web directory.

For local pilot development, use only the established controlled settings:

```text
FLEET_ENVIRONMENT=development
FLEET_AUTH_MODE=pilot
FLEET_OTP_PROVIDER=development
FLEET_ENABLE_DEVELOPMENT_OTP=true
```

Staging and production profiles reject Pilot mode and development OTP
configuration. A controlled Pilot fallback uses a separate
`FLEET_ENVIRONMENT=pilot` runtime and separately built Pilot-auth APK; it is not
a hidden fallback inside Firebase mode.

## 5. Apply the database migration

Back up the database, then upgrade the existing database in place:

```powershell
cd services/api
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
```

Migration `0023_user_auth_identity` is additive. Do not reset the Pilot database or recreate People. Existing People must have a unique, accurate phone number and an active membership before their first Firebase login.

## 6. Pre-production verification

1. Use Firebase console test numbers in the development project to exercise Driver, Supervisor, and Owner/Admin login without sending SMS.
2. Confirm unknown, duplicate, inactive, and disabled People are denied.
3. Confirm the first successful login creates one identity link and later logins reuse it.
4. Confirm only server-returned memberships can be selected and cross-tenant choices are rejected.
5. Confirm logout signs out both Fleet and Firebase, while a different Driver cannot see the previous Driver's offline queue or assignment.
6. Test real-device Android delivery in a controlled non-production environment, including resend, wrong/expired code, quota/rate limiting, no network, app restart, and the release signing certificate.
7. Review audit logs for `AUTH_IDENTITY_LINKED`, `LOGIN_SUCCESS`, `LOGIN_DENIED`, `MEMBERSHIP_ACCESS_DENIED`, `AUTH_IDENTITY_DISABLED`, `AUTH_SESSIONS_REVOKED`, `PHONE_CHANGE_REQUESTED`, and `LOGOUT`; verify no token, OTP, credential, or full phone is recorded.

Do not switch the production deployment to Firebase mode until credentials, signing fingerprints, quotas, monitoring, rollback procedure, and the production migration have been reviewed and approved.

