"""Send a deterministic outside/inside/outside path to the local telematics API.

This utility deliberately accepts only loopback API URLs. It uses the real Owner
ingestion endpoint and can be rerun with the same ``--run-id`` to demonstrate
provider-event idempotency.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _local_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in LOCAL_HOSTS:
        raise argparse.ArgumentTypeError("the simulator only sends to a loopback API URL")
    return value.rstrip("/")


def _post(base_url: str, token: str, path: str, payload: dict[str, Any]) -> Any:
    request = Request(  # noqa: S310 - base URL is restricted to loopback hosts
        f"{base_url}{path}",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:  # noqa: S310 - loopback validated
            return json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise SystemExit(f"API request failed ({exc.code}): {detail}") from exc


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", type=_local_base_url, default="http://127.0.0.1:8000")
    parser.add_argument("--token", default=os.getenv("FLEET_DEMO_OWNER_TOKEN"))
    parser.add_argument("--mapping-id", required=True)
    parser.add_argument("--site-latitude", type=Decimal, default=Decimal("12.971600"))
    parser.add_argument("--site-longitude", type=Decimal, default=Decimal("77.594600"))
    parser.add_argument("--run-id", default="morning-demo")
    parser.add_argument("--odometer-start", type=Decimal, default=Decimal("42150.0"))
    parser.add_argument("--engine-hours-start", type=Decimal, default=Decimal("8421.3"))
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    if not args.token:
        raise SystemExit("provide --token or FLEET_DEMO_OWNER_TOKEN")

    # Roughly 1.1 km per 0.01 latitude degree. The path starts outside a typical
    # 250 m demo geofence, enters it, remains inside, then exits.
    offsets = (
        (Decimal("0.0060"), Decimal("0.0000"), Decimal("18"), True),
        (Decimal("0.0030"), Decimal("0.0000"), Decimal("10"), True),
        (Decimal("0.0008"), Decimal("0.0002"), Decimal("3"), True),
        (Decimal("0.0004"), Decimal("-0.0002"), Decimal("0"), True),
        (Decimal("-0.0030"), Decimal("0.0000"), Decimal("9"), True),
        (Decimal("-0.0060"), Decimal("0.0000"), Decimal("16"), True),
    )
    started_at = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=len(offsets))

    for index, (latitude_delta, longitude_delta, speed, ignition) in enumerate(offsets):
        payload = {
            "provider_event_id": f"{args.run_id}-{index + 1}",
            "recorded_at": (started_at + timedelta(minutes=index)).isoformat(),
            "latitude": str(args.site_latitude + latitude_delta),
            "longitude": str(args.site_longitude + longitude_delta),
            "speed_kph": str(speed),
            "heading": "180" if index >= 3 else "0",
            "ignition_state": ignition,
            "odometer_km": str(args.odometer_start + Decimal(index) * Decimal("0.7")),
            "engine_hours": str(args.engine_hours_start + Decimal(index) * Decimal("0.1")),
            "battery_voltage": "24.6",
        }
        result = _post(
            args.base_url,
            args.token,
            f"/api/v1/owner/telematics/mappings/{args.mapping_id}/positions",
            payload,
        )
        transitions = [item["transition_type"] for item in result["transitions"]]
        print(
            f"point={index + 1} duplicate={result['duplicate']} "
            f"out_of_order={result['out_of_order']} transitions={transitions}"
        )


if __name__ == "__main__":
    main()
