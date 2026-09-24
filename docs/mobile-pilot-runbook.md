# Fleet Manager Mobile Pilot Runbook

## APK

The overnight build is copied to:

`D:\Git\fleet maneger\fleet manager\dist\FleetManager-Pilot.apk`

Final verified artifact: 59,828,779 bytes, SHA-256 `48d0472d2af8bc1030fa4af424e4a5a7a68bd699975abe25515d3ff357b34337`.

Install it with Android Studio/ADB or copy the APK to the phone and open it. The APK is a sideloadable Pilot build and is intentionally debug-signed; it is not a Play Store release.

## Start the PC backend

1. On the PC, double-click `Start Fleet Manager.bat`.
2. Confirm the API is healthy at `http://127.0.0.1:8000/health` on the PC.
3. Put the phone and PC on the same Wi-Fi network, or use USB ADB reverse.

## Connect the phone

The phone must not use `localhost` for the PC. In the Pilot login screen, open the settings icon and enter the PC LAN URL, for example:

`http://192.168.1.20:8000`

Tap `TEST CONNECTION`, confirm `Connected`, then save. The URL is stored on the phone. With a USB-connected device, `Install Fleet Manager Pilot.bat` can configure `adb reverse tcp:8000 tcp:8000`; use `http://127.0.0.1:8000` after that.

## Local Pilot credentials

All roles use phone `9606743463`.

- Driver OTP: `111111`
- Supervisor OTP: `222222`
- Owner OTP: `333333`

These fixed OTPs are local Pilot provider behavior only. Production authentication remains provider/configuration controlled.

## Driver smoke flow

1. Select `DRIVER`, enter the phone, send OTP, and continue with `111111`.
2. Set the server URL if needed.
3. Confirm the four primary actions are visible: `TRIP COMPLETE`, `KM READING`, `DIESEL`, `EMERGENCY`.
4. Tap `KM READING`, enter `10000`, and take/choose the dashboard photo.
5. Record four trips and record `30` litres without a diesel photo.
6. Lock/minimize the app, reopen it, and confirm the duty is still `ACTIVE`.
7. Enter `10120` with an end photo. Confirm the next `KM READING` starts a sequential session.
8. Send one emergency and confirm the success message.

## Supervisor smoke flow

1. Select `SUPERVISOR` and continue with `222222`.
2. Confirm only assigned sites are shown and open emergencies appear first.
3. Acknowledge and resolve the emergency; use `CALL DRIVER` when a phone is supplied.
4. Expand `SITES / TIPPERS`, then `TRIPS`, `KM READINGS`, and `DIESEL`.
5. Verify that START and END KM are labelled distinctly.
6. Review evidence through `VIEW PHOTO`; diesel without a photo remains reviewable.
7. Approve, reject, or dispute pending operational records. Rejection/dispute requires a reason.

## Owner smoke flow

1. Select `OWNER` and continue with `333333`.
2. Review TODAY cards and ATTENTION cards.
3. Inspect TIPPERS, SITES, and ALERTS.
4. Open REPORTS and confirm duty sessions, regular duty end, actual end, and OT are visible only here.
5. Tap `DOWNLOAD / SHARE EXCEL`, choose WhatsApp/email/Sheets or a file handler, and open the generated XLSX.

## Connectivity and notification behavior

- Driver events continue through the existing Drift queue. The UI distinguishes synced, pending, retrying, and needs-attention states.
- Supervisor approval mutations are online-only and are not faked offline.
- Owner data is live when connected; offline/error state is shown rather than presented as live.
- Supervisor and Owner screens poll while open (30 seconds and 60 seconds respectively), with an in-app emergency banner/count. This Pilot repository has no FCM production credentials, so reliable background push is not claimed complete. Configure FCM and platform notification credentials separately for production background delivery.

## Known Pilot limitations

- Camera/gallery flows require Android permission and a real device/emulator image source.
- Local HTTP is enabled only in the `pilot` Android flavor. Use an HTTPS URL for production builds.
- The final APK was built with `flutter build apk --flavor pilot --release --build-name=1.0.0 --build-number=1 --dart-define=FLEET_PILOT=true`.
- The app uses the existing backend authorization and report calculations; it does not calculate OT, distance, verification, or tenant access independently.
