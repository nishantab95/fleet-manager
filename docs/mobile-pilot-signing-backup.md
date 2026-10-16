# Fleet Pilot signing key backup

The single permanent Fleet Pilot signing keystore is:

`%USERPROFILE%\.fleet-manager\signing\fleet-pilot-release.jks`

Key alias: `fleet-pilot`

Signing certificate SHA-1: `11d4b4dc04f0d3068903e1c333c1894e7ae47a74`

Signing certificate SHA-256: `fd25115e20ac18a8a7cda91b9f4d5f6153f54b4d79c751b5005a3ac734cc3c29`

These fingerprints were re-audited from the configured permanent Pilot
keystore on 2026-10-16 and match the existing APK validator. The previous
SHA-256 printed in this document was stale documentation; no keystore or
certificate was changed.

Preserve this exact keystore for every future Pilot APK. Do not regenerate it,
commit it, send it to GitHub, or copy it to the Fleet server. Keep its password
in a password manager and make an encrypted backup of the keystore in an
owner-controlled secure backup location. The local Gradle configuration is
`%USERPROFILE%\.gradle\gradle.properties`; it is outside Git and contains the
build credentials. Never put its contents in a ticket, log, repository, or
server release folder.

If the keystore or its password is lost, future APKs cannot retain this
signing identity. Stop the release workflow rather than silently creating a
replacement key.
