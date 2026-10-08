# Fleet Pilot signing key backup

The single permanent Fleet Pilot signing keystore is:

`%USERPROFILE%\.fleet-manager\signing\fleet-pilot-release.jks`

Key alias: `fleet-pilot`

Signing certificate SHA-256: `9f613076ce4c0dcaf4b0e713aa021e0f9b4f08eb86e3467f651e4e51d47b6520`

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
