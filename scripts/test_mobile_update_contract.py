"""Build-time contracts for the Android-only private Pilot installer bridge."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "apps" / "mobile" / "android" / "app" / "src"


def test_installer_intent_is_content_uri_granted_and_user_confirmed() -> None:
    activity = (
        ANDROID
        / "main"
        / "kotlin"
        / "com"
        / "fleetmanager"
        / "fleet_manager_mobile"
        / "MainActivity.kt"
    ).read_text(encoding="utf-8")

    assert "FileProvider.getUriForFile" in activity
    assert "Intent(Intent.ACTION_VIEW)" in activity
    assert '"application/vnd.android.package-archive"' in activity
    assert "Intent.FLAG_GRANT_READ_URI_PERMISSION" in activity
    assert "intent.resolveActivity(packageManager)" in activity
    assert "startActivity(intent)" in activity
    assert "Uri.fromFile" not in activity
    assert "file://" not in activity


def test_installer_capability_is_declared_only_by_pilot_manifest() -> None:
    pilot = (ANDROID / "pilot" / "AndroidManifest.xml").read_text(encoding="utf-8")
    main = (ANDROID / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")

    assert "android.permission.REQUEST_INSTALL_PACKAGES" in pilot
    assert "androidx.core.content.FileProvider" in pilot
    assert "${applicationId}.fileprovider" in pilot
    assert "android.permission.REQUEST_INSTALL_PACKAGES" not in main
    assert "androidx.core.content.FileProvider" not in main


def test_company_release_keeps_pilot_package_and_signing_identity() -> None:
    gradle = (
        ROOT / "apps" / "mobile" / "android" / "app" / "build.gradle.kts"
    ).read_text(encoding="utf-8")
    build = (ROOT / "scripts" / "build-firebase-staging-apk.ps1").read_text(
        encoding="utf-8"
    )

    assert 'applicationIdSuffix = ".pilot"' in gradle
    assert 'withFlavor("environment" to "pilot")' in gradle
    assert 'getByName("fleetPilotRelease")' in gradle
    assert '"--flavor",\n    "pilot"' in build
    assert "FLEET_BUILD_PROFILE=$buildProfile" in build
    assert '"firebase-company"' in build


def test_company_button_has_safe_config_and_private_publish_preflights() -> None:
    wrapper = (ROOT / "Build & Publish Fleet AI Systems Mobile.bat").read_text(
        encoding="utf-8"
    )
    workflow = (ROOT / "scripts" / "build-publish-company-mobile.ps1").read_text(
        encoding="utf-8"
    )

    assert "build-publish-company-mobile.ps1" in wrapper
    assert ".fleetaisystems\\firebase-mobile.ps1" in workflow
    assert "Read-SafeMobileConfig" in workflow
    assert "android_signer_fingerprints.py" in workflow
    assert "--require-firebase-company" in workflow
    assert "Nothing new was published." in workflow
