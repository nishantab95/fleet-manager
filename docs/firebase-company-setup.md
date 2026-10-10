# Firebase company release setup

These steps switch authentication and publish a company-facing APK without changing the installed Pilot package ID or its permanent signing certificate. Secrets stay outside Git.

1. In Firebase Console, open the company project and enable **Authentication > Sign-in method > Phone**.
2. Register Android app package `com.fleetmanager.fleet_manager_mobile.pilot`. Do not create a different package for this update path.
3. On the build PC, restore the existing permanent signer at `%USERPROFILE%\.fleet-manager\signing\fleet-pilot-release.jks` and its four user Gradle properties (`fleetPilotStoreFile`, `fleetPilotStorePassword`, `fleetPilotKeyAlias`, `fleetPilotKeyPassword`) in `%USERPROFILE%\.gradle\gradle.properties`; never generate a replacement identity. Run `services\api\.venv\Scripts\python.exe scripts\android_signer_fingerprints.py`, then add both reported SHA-1 and SHA-256 fingerprints to the Android app in Firebase Console.
4. Copy the Firebase Android app ID, Web API key, messaging sender ID, and project ID. These Android client values are identifiers, not a service-account credential.
5. Create `%USERPROFILE%\.fleetaisystems\firebase-mobile.ps1` outside the repository with exactly these lines, replacing every placeholder:

   ```powershell
   $env:FLEET_AUTH_MODE='firebase'
   $env:FLEET_API_BASE_URL='https://<private-server-host>'
   $env:FIREBASE_ANDROID_API_KEY='<android-web-api-key>'
   $env:FIREBASE_ANDROID_APP_ID='<android-app-id>'
   $env:FIREBASE_MESSAGING_SENDER_ID='<numeric-sender-id>'
   $env:FIREBASE_PROJECT_ID='<firebase-project-id>'
   ```

6. In Firebase Console, create a service-account JSON credential for the server only. Store it outside the repository, for example under `C:\ProgramData\FleetAISystems\secrets\`.
7. On the server, create `C:\ProgramData\FleetAISystems\firebase-server.env` with `FLEET_AUTH_MODE=firebase`, `FLEET_FIREBASE_PROJECT_ID=<firebase-project-id>`, `GOOGLE_APPLICATION_CREDENTIALS=<absolute-json-path>`, `FLEET_JWT_SIGNING_KEY=<existing-strong-signing-key>`, and optionally `FLEET_FIREBASE_CHECK_REVOKED_TOKENS=true`. Remove all `FLEET_PILOT_*_OTP` values when Firebase mode is active.
8. In Firebase Console, confirm the authorized phone accounts correspond to active Fleet AI Systems memberships. The server—not the APK—continues to decide company and role access.
9. Run `Check Fleet AI Systems Server.bat`. It should show `Firebase: FIREBASE`, plus healthy Git, database, API, and Owner states before a company release.
10. Optionally run `Build & Publish Fleet AI Systems Mobile.bat -ValidateOnly`. This checks local config, build tools, version, and both signing fingerprints without building, sending, or publishing.
11. Run `Build & Publish Fleet AI Systems Mobile.bat` only when ready to release. It builds the Firebase company profile, verifies package/version/signature/hash, sends it over the existing private channel, waits for server validation, and reports publication success.

The company build remains package `com.fleetmanager.fleet_manager_mobile.pilot`, uses the permanent Pilot signer, hides Pilot/test presentation, and retains private APK update checks. It does not contain the Firebase service-account JSON or signing passwords.
