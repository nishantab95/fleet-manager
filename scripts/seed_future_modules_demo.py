"""Seed realistic future-module data through a running local Fleet Manager API.

The script is intentionally local/development-only. It creates three sites,
ten tippers, six machinery assets, deployments, maintenance schedules,
compliance policies/documents, telematics mappings/geofences, and an external
fuel import. Existing objects with the demo names are reused.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import uuid
from datetime import date, datetime, timedelta
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class LocalApi:
    def __init__(self, base_url: str, token: str) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in LOCAL_HOSTS:
            raise SystemExit("refusing to seed a non-loopback API URL")
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"}

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        content_type: str = "application/json",
        raw: bytes | None = None,
    ) -> Any:
        data = raw if raw is not None else (json.dumps(payload).encode() if payload else None)
        headers = dict(self.headers)
        if data is not None:
            headers["Content-Type"] = content_type
        request = Request(  # noqa: S310 - base URL is restricted to loopback hosts
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        try:
            with urlopen(request, timeout=20) as response:  # noqa: S310 - loopback validated
                body = response.read()
                return json.loads(body) if body else None
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise RuntimeError(f"{method} {path} failed ({exc.code}): {detail}") from exc

    def multipart(
        self,
        path: str,
        *,
        fields: dict[str, str],
        filename: str,
        content_type: str,
        content: bytes,
    ) -> Any:
        boundary = f"fleet-demo-{uuid.uuid4().hex}"
        pieces: list[bytes] = []
        for name, value in fields.items():
            pieces.extend(
                [
                    f"--{boundary}\r\n".encode(),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                    value.encode(),
                    b"\r\n",
                ]
            )
        pieces.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                ).encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                content,
                b"\r\n",
                f"--{boundary}--\r\n".encode(),
            ]
        )
        return self.request(
            "POST",
            path,
            content_type=f"multipart/form-data; boundary={boundary}",
            raw=b"".join(pieces),
        )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", default=os.getenv("FLEET_DEMO_OWNER_TOKEN"))
    parser.add_argument("--environment", default=os.getenv("FLEET_ENVIRONMENT", "development"))
    return parser.parse_args()


def _ensure_sites(api: LocalApi) -> list[dict[str, Any]]:
    wanted = (
        ("Future Demo Quarry", "Demo Quarry", "12.971600", "77.594600"),
        ("Future Demo Highway", "Demo Highway", "12.935200", "77.624500"),
        ("Future Demo Yard", "Demo Yard", "12.998100", "77.552900"),
    )
    existing = {item["short_name"]: item for item in api.request("GET", "/api/v1/owner/sites")}
    result = []
    for name, short_name, latitude, longitude in wanted:
        item = existing.get(short_name)
        if item is None:
            item = api.request(
                "POST",
                "/api/v1/owner/sites",
                {
                    "name": name,
                    "short_name": short_name,
                    "location_description": "Local future-module demonstration site",
                    "latitude": latitude,
                    "longitude": longitude,
                },
            )
        result.append(item)
    return result


def _ensure_assets(api: LocalApi, sites: list[dict[str, Any]]) -> list[dict[str, Any]]:
    specs = [
        *(("TIPPER", f"Demo Tipper {index:02d}", True, index in {1, 2}) for index in range(1, 11)),
        ("EXCAVATOR", "Demo Excavator 01", False, True),
        ("BACKHOE_LOADER", "Demo Backhoe 01", True, True),
        ("ROLLER", "Demo Roller 01", False, True),
        ("GRADER", "Demo Grader 01", True, True),
        ("EXCAVATOR", "Demo Excavator 02", True, True),
        ("BACKHOE_LOADER", "Demo Backhoe 02", False, True),
    ]
    existing = {item["short_name"]: item for item in api.request("GET", "/api/v1/owner/assets")}
    result = []
    for index, (asset_type, short_name, odometer, hours) in enumerate(specs):
        item = existing.get(short_name)
        if item is None:
            item = api.request(
                "POST",
                "/api/v1/owner/assets",
                {
                    "asset_type": asset_type,
                    "ownership_type": "OWNED",
                    "registration_number": (
                        f"KA51DM{index + 1:04d}" if asset_type == "TIPPER" else None
                    ),
                    "short_name": short_name,
                    "manufacturer": "Fleet Demo",
                    "model": f"{asset_type}-LOCAL",
                    "supports_odometer_km": odometer,
                    "supports_hour_meter": hours,
                },
            )
        if item.get("current_deployment") is None:
            deployment = api.request(
                "POST",
                f"/api/v1/owner/assets/{item['id']}/deployment",
                {"site_id": sites[index % len(sites)]["id"]},
            )
            item = {**item, "current_deployment": deployment}
        result.append(item)
    return result


def _ensure_assignments(api: LocalApi, assets: list[dict[str, Any]]) -> int:
    drivers = [
        item
        for item in api.request("GET", "/api/v1/owner/people")
        if item["role"] == "DRIVER"
        and item["status"] != "INACTIVE"
        and not item["has_active_assignment"]
    ]
    assigned = 0
    for asset, driver in zip(
        (item for item in assets if not item["has_active_assignment"]),
        drivers,
        strict=False,
    ):
        api.request(
            "POST",
            f"/api/v1/owner/assets/{asset['id']}/assignment",
            {
                "driver_membership_id": driver["membership_id"],
                "regular_duty_minutes": 480,
            },
        )
        assigned += 1
    return assigned


def _ensure_maintenance(api: LocalApi, assets: list[dict[str, Any]]) -> None:
    existing = api.request("GET", "/api/v1/owner/maintenance/schedules")
    existing_keys = {(item["asset_id"], item["maintenance_type"]) for item in existing}
    today = date.today()
    for index, asset in enumerate(assets[:8]):
        key = (asset["id"], "ENGINE_OIL")
        if key in existing_keys:
            continue
        if index < 2:
            last_service = today - timedelta(days=220)
        elif index < 4:
            last_service = today - timedelta(days=165)
        else:
            last_service = today - timedelta(days=30)
        schedule = api.request(
            "POST",
            "/api/v1/owner/maintenance/schedules",
            {
                "asset_id": asset["id"],
                "maintenance_type": "ENGINE_OIL",
                "description": "Demo 180-day engine-oil interval",
                "interval_basis": "DATE",
                "interval_value": "180",
                "warning_threshold": "30",
                "last_service_date": last_service.isoformat(),
                "notes": "Created by seed_future_modules_demo.py",
            },
        )
        if index == 0 and asset["supports_odometer_km"]:
            api.request(
                "POST",
                f"/api/v1/owner/maintenance/schedules/{schedule['id']}/criteria",
                {
                    "basis": "ODOMETER_KM",
                    "interval_value": "10000",
                    "warning_threshold": "1000",
                    "last_baseline_value": "40000",
                },
            )


def _ensure_compliance(api: LocalApi, assets: list[dict[str, Any]]) -> None:
    for asset_type, document_type in (
        ("TIPPER", "INSURANCE"),
        ("EXCAVATOR", "EQUIPMENT_INSPECTION"),
        ("BACKHOE_LOADER", "EQUIPMENT_INSPECTION"),
    ):
        api.request(
            "PUT",
            "/api/v1/owner/asset-documents/policies",
            {
                "asset_type": asset_type,
                "ownership_type": "OWNED",
                "document_type": document_type,
                "required": True,
                "expiry_warning_days": 30,
            },
        )

    existing = api.request("GET", "/api/v1/owner/asset-documents")
    documented = {(item["asset_id"], item["document_type"]) for item in existing}
    expiries = (
        date.today() + timedelta(days=180),
        date.today() + timedelta(days=15),
        date.today() - timedelta(days=5),
    )
    for index, expiry in enumerate(expiries):
        asset = assets[index]
        key = (asset["id"], "INSURANCE")
        if key in documented:
            continue
        upload_id = str(uuid.uuid4())
        evidence = api.multipart(
            f"/api/v1/owner/asset-documents/evidence?{urlencode({'upload_id': upload_id})}",
            fields={},
            filename=f"demo-insurance-{index + 1}.png",
            content_type="image/png",
            content=PNG_1X1,
        )
        api.request(
            "POST",
            "/api/v1/owner/asset-documents",
            {
                "asset_id": asset["id"],
                "document_type": "INSURANCE",
                "evidence_object_id": evidence["evidence_object_id"],
                "document_number": f"DEMO-INS-{index + 1:03d}",
                "issue_date": (date.today() - timedelta(days=365)).isoformat(),
                "expiry_date": expiry.isoformat(),
                "issuer": "Local Demo Insurer",
                "notes": "Synthetic local demonstration document",
                "expiry_warning_days": 30,
            },
        )


def _ensure_telematics(
    api: LocalApi, assets: list[dict[str, Any]], sites: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    existing = api.request("GET", "/api/v1/owner/telematics/mappings")
    by_asset = {item["asset_id"]: item for item in existing}
    type_sample: dict[str, dict[str, Any]] = {}
    for asset in assets:
        type_sample.setdefault(asset["asset_type"], asset)
    mappings = []
    for asset in type_sample.values():
        mapping = by_asset.get(asset["id"])
        if mapping is None:
            mapping = api.request(
                "POST",
                "/api/v1/owner/telematics/mappings",
                {
                    "asset_id": asset["id"],
                    "provider": "LOCAL_SIMULATOR",
                    "provider_vehicle_id": f"demo-{asset['id']}",
                },
            )
        mappings.append(mapping)
    for site in sites:
        api.request(
            "PUT",
            "/api/v1/owner/telematics/geofences",
            {"site_id": site["id"], "radius_m": "250"},
        )
    return mappings


def _seed_fuel(api: LocalApi, assets: list[dict[str, Any]]) -> None:
    now = datetime.now().astimezone().replace(microsecond=0)
    rows = ["external_transaction_id,occurred_at,litres,asset_identifier,source_type"]
    for index, asset in enumerate(assets[:4], start=1):
        identifier = asset["registration_number"] or asset["asset_code"]
        rows.append(
            f"DEMO-FUEL-{date.today().isoformat()}-{index},"
            f"{(now - timedelta(hours=index)).isoformat()},{100 + index}.250,"
            f"{identifier},FUEL_CARD"
        )
    imported = api.multipart(
        "/api/v1/owner/fuel/imports",
        fields={"source_name": "LOCAL_DEMO_CSV"},
        filename="demo-fuel.csv",
        content_type="text/csv",
        content=("\n".join(rows) + "\n").encode(),
    )
    api.request(
        "POST",
        f"/api/v1/owner/fuel/imports/{imported['batch']['id']}/reconcile",
        {"tolerance_litres": "1.000", "time_window_minutes": 720},
    )


def _ensure_workforce(api: LocalApi) -> tuple[int, str | None]:
    drivers = [
        item
        for item in api.request("GET", "/api/v1/owner/people")
        if item["role"] == "DRIVER" and item["status"] != "INACTIVE"
    ]
    profiles = api.request("GET", "/api/v1/owner/workforce/compensation")
    profiled = {item["membership_id"] for item in profiles}
    month_start = date.today().replace(day=1)
    for index, driver in enumerate(drivers):
        if driver["membership_id"] in profiled:
            continue
        api.request(
            "POST",
            "/api/v1/owner/workforce/compensation",
            {
                "membership_id": driver["membership_id"],
                "pay_basis": "MONTHLY",
                "base_amount": str(25000 + index * 1500),
                "effective_from": month_start.isoformat(),
                "standard_duty_minutes": 480,
                "overtime_rate_per_hour": "150.00",
                "notes": "Synthetic local demo compensation; not statutory payroll",
            },
        )
    periods = api.request("GET", "/api/v1/owner/workforce/payroll-periods")
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_end = next_month - timedelta(days=1)
    existing = next(
        (
            item
            for item in periods
            if item["starts_on"] == month_start.isoformat()
            and item["ends_on"] == month_end.isoformat()
        ),
        None,
    )
    if existing is None and drivers:
        existing = api.request(
            "POST",
            "/api/v1/owner/workforce/payroll-periods",
            {"starts_on": month_start.isoformat(), "ends_on": month_end.isoformat()},
        )
    api.request(
        "PUT",
        "/api/v1/owner/attendance-location/settings",
        {
            "site_match_required": True,
            "asset_proximity_threshold_m": "100",
            "gps_freshness_seconds": 900,
            "max_accuracy_m": "100",
            "retention_days": 30,
        },
    )
    return len(drivers), existing["id"] if existing is not None else None


def main() -> None:
    args = _arguments()
    if args.environment.lower() == "production":
        raise SystemExit("refusing to seed while FLEET_ENVIRONMENT=production")
    if not args.token:
        raise SystemExit("provide --token or FLEET_DEMO_OWNER_TOKEN")
    api = LocalApi(args.base_url, args.token)

    flags = api.request("GET", "/api/v1/owner/future-features")
    needed = (
        "maintenance",
        "asset_documents",
        "notifications",
        "telematics",
        "fuel_integrations",
        "multi_meter",
        "payroll",
        "attendance_location",
    )
    disabled = [name for name in needed if not flags.get(name, False)]
    if disabled:
        raise SystemExit(f"enable these local-only feature flags first: {', '.join(disabled)}")

    sites = _ensure_sites(api)
    assets = _ensure_assets(api, sites)
    assignment_count = _ensure_assignments(api, assets)
    _ensure_maintenance(api, assets)
    _ensure_compliance(api, assets)
    mappings = _ensure_telematics(api, assets, sites)
    _seed_fuel(api, assets)
    driver_count, payroll_period_id = _ensure_workforce(api)
    api.request("GET", "/api/v1/owner/notifications")

    print(
        f"sites={len(sites)} assets={len(assets)} assignments_created={assignment_count} "
        f"mappings={len(mappings)} drivers={driver_count} payroll_period={payroll_period_id}"
    )
    print("Run a deterministic ENTER/EXIT path with:")
    print(
        "python scripts/telematics_simulator.py "
        f"--mapping-id {mappings[0]['id']} "
        f"--site-latitude {sites[0]['latitude']} "
        f"--site-longitude {sites[0]['longitude']}"
    )
    print("Demo data is synthetic, local-only, and safe to recreate after resetting the local DB.")


if __name__ == "__main__":
    main()
