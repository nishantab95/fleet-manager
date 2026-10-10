from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from firebase_staging_apk import scan_apk_strings


def _archive(path: Path, payload: bytes) -> Path:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("lib/arm64-v8a/libapp.so", payload)
    return path


def _test_apk(name: str) -> Path:
    return Path(__file__).with_name(f".{name}-{uuid4().hex}.apk")


def test_scan_apk_strings_finds_required_public_values() -> None:
    apk = _archive(
        _test_apk("staging"), b"api.example firebase-staging project-staging"
    )
    try:
        found, forbidden = scan_apk_strings(
            apk,
            required={
                "profile": b"firebase-staging",
                "project": b"project-staging",
            },
        )

        assert found == {"profile", "project"}
        assert forbidden == set()
    finally:
        apk.unlink(missing_ok=True)


def test_scan_apk_strings_detects_service_account_material() -> None:
    apk = _archive(
        _test_apk("unsafe"),
        b'{"private_key":"-----BEGIN PRIVATE KEY-----","client_email":"x"}',
    )
    try:
        _found, forbidden = scan_apk_strings(apk, required={})

        assert "service-account private key" in forbidden
        assert "service-account private_key field" in forbidden
    finally:
        apk.unlink(missing_ok=True)
