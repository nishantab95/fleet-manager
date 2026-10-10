"""Print the protected Android signer fingerprints without exposing passwords."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from pilot_release_common import EXPECTED_SIGNER_SHA256


class FingerprintError(RuntimeError):
    """A safe local signing configuration error."""


def _properties(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise FingerprintError(
            f"Signing configuration is unavailable: {path}"
        ) from error
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "!")) or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _keytool() -> str:
    java_home = os.environ.get("JAVA_HOME", "").strip()
    candidates = []
    if java_home:
        candidates.append(Path(java_home) / "bin" / "keytool.exe")
    user_profile = Path(os.environ.get("USERPROFILE", ""))
    candidates.append(user_profile / "Tools" / "temurin-17" / "bin" / "keytool.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("keytool")
    if found:
        return found
    raise FingerprintError("Java keytool is unavailable.")


def signer_fingerprints(properties_file: Path) -> dict[str, str]:
    values = _properties(properties_file)
    required = (
        "fleetPilotStoreFile",
        "fleetPilotStorePassword",
        "fleetPilotKeyAlias",
        "fleetPilotKeyPassword",
    )
    missing = [name for name in required if not values.get(name)]
    if missing:
        raise FingerprintError(
            "Signing configuration is incomplete: " + ", ".join(missing)
        )
    store = Path(values["fleetPilotStoreFile"])
    if not store.is_absolute():
        store = (
            Path(__file__).resolve().parents[1]
            / "apps"
            / "mobile"
            / "android"
            / "app"
            / store
        )
    if not store.is_file():
        raise FingerprintError(f"Protected Pilot keystore is unavailable: {store}")

    environment = dict(os.environ)
    environment["FLEET_SIGNER_STORE_PASSWORD"] = values["fleetPilotStorePassword"]
    result = subprocess.run(
        [
            _keytool(),
            "-list",
            "-v",
            "-keystore",
            str(store),
            "-alias",
            values["fleetPilotKeyAlias"],
            "-storepass:env",
            "FLEET_SIGNER_STORE_PASSWORD",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise FingerprintError("Java keytool could not inspect the configured signer.")
    output = f"{result.stdout}\n{result.stderr}"
    found: dict[str, str] = {}
    for algorithm in ("SHA1", "SHA256"):
        match = re.search(rf"{algorithm}:\s*([0-9A-Fa-f:]+)", output)
        if not match:
            raise FingerprintError(f"Java keytool did not report {algorithm}.")
        found[algorithm] = match.group(1).upper()
    normalized_sha256 = found["SHA256"].replace(":", "").casefold()
    if normalized_sha256 != EXPECTED_SIGNER_SHA256:
        raise FingerprintError(
            "Configured signer does not match the permanent Fleet Pilot identity."
        )
    return {
        "sha1": found["SHA1"],
        "sha256": found["SHA256"],
        "expectedSignerPreserved": "true",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--properties",
        type=Path,
        default=Path.home() / ".gradle" / "gradle.properties",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        fingerprints = signer_fingerprints(args.properties)
    except (FingerprintError, OSError, subprocess.TimeoutExpired) as error:
        print(f"[FAILED] {error}")
        return 1
    if args.json:
        print(json.dumps(fingerprints))
    else:
        print("Fleet AI Systems Android signer")
        print(f"SHA-1:   {fingerprints['sha1']}")
        print(f"SHA-256: {fingerprints['sha256']}")
        print("Permanent signer: VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
