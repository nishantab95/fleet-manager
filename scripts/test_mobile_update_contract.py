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
