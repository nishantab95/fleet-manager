from __future__ import annotations

from collections.abc import Iterator
from typing import cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_object_storage, get_otp_provider
from fleet_api.auth.providers import FakeOtpProvider
from fleet_api.auth.service import AuthService
from fleet_api.core.config import Settings
from fleet_api.db.models import (
    AssetDocumentRevision,
    CompanyMembership,
    FleetAsset,
    MaintenanceRecord,
    User,
)
from fleet_api.db.session import get_db as session_get_db
from fleet_api.domain.enums import (
    AssetOwnershipType,
    FleetAssetStatus,
    FleetAssetType,
)
from fleet_api.main import create_app

pytestmark = pytest.mark.postgres


class MemoryObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put_private(self, *, object_key: str, content: bytes, content_type: str) -> str:
        self.objects[object_key] = (content, content_type)
        return object_key

    def delete_private(self, *, object_key: str) -> None:
        self.objects.pop(object_key, None)

    def read_private(self, *, object_key: str) -> tuple[bytes, str]:
        return self.objects[object_key]

    def check_ready(self) -> None:
        return None


def value[T](records: dict[str, object], key: str, expected_type: type[T]) -> T:
    item = records[key]
    assert isinstance(item, expected_type)
    return item


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "phone_default_region": "IN",
        "jwt_signing_key": "test-signing-key-that-is-longer-than-32-characters",
        "otp_resend_cooldown_seconds": 0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type,call-arg]


def access_token(
    db_session: Session,
    membership: CompanyMembership,
    app_settings: Settings,
) -> str:
    user = db_session.get(User, membership.user_id)
    assert user is not None
    user.phone_number = f"+919{uuid4().int % 1_000_000_000:09d}"
    db_session.flush()
    provider = FakeOtpProvider()
    auth = AuthService(db_session, app_settings, provider)
    challenge_id = auth.request_otp(phone=user.phone_number)
    pre_session, _ = auth.verify_otp(
        challenge_id=challenge_id,
        otp=provider.deliveries[challenge_id],
    )
    tokens = auth.create_session(
        pre_session_token=pre_session,
        membership_id=membership.id,
    )
    db_session.commit()
    return tokens.access_token


def authenticated_client(
    db_session: Session,
    membership: CompanyMembership,
    app_settings: Settings,
    storage: MemoryObjectStorage | None = None,
) -> TestClient:
    app = create_app(app_settings)

    def override_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[session_get_db] = override_db
    app.dependency_overrides[get_otp_provider] = lambda: FakeOtpProvider()
    if storage is not None:
        app.dependency_overrides[get_object_storage] = lambda: storage
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {access_token(db_session, membership, app_settings)}"
    return client


def test_disabled_feature_endpoint_fails_closed_before_mutation(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    before = db_session.scalar(select(func.count()).select_from(MaintenanceRecord))
    client = authenticated_client(
        db_session,
        value(tenant_records, "owner_a", CompanyMembership),
        settings(),
    )
    try:
        response = client.post(
            "/api/v1/owner/maintenance/schedules",
            json={
                "asset_id": str(uuid4()),
                "maintenance_type": "ENGINE_OIL",
                "interval_basis": "KM",
                "interval_value": "10000",
                "last_service_meter": "0",
            },
        )
    finally:
        client.close()
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "FEATURE_UNAVAILABLE"
    assert db_session.scalar(select(func.count()).select_from(MaintenanceRecord)) == before


def test_enabled_feature_does_not_bypass_authentication() -> None:
    app = create_app(settings(maintenance_enabled=True))
    with TestClient(app) as client:
        response = client.get("/api/v1/owner/maintenance/schedules")
    assert response.status_code == 401


def test_owner_maintenance_is_tenant_safe_capability_safe_and_append_only(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    client = authenticated_client(
        db_session,
        value(tenant_records, "owner_a", CompanyMembership),
        settings(maintenance_enabled=True),
    )
    tipper = value(tenant_records, "tipper_a", FleetAsset)
    foreign = value(tenant_records, "tipper_b", FleetAsset)
    machine = FleetAsset(
        company_id=tipper.company_id,
        asset_type=FleetAssetType.EXCAVATOR,
        ownership_type=AssetOwnershipType.OWNED,
        asset_code="EXCAVATOR-MAINTENANCE",
        registration_number=None,
        short_name="Maintenance Excavator",
        status=FleetAssetStatus.ACTIVE,
    )
    db_session.add(machine)
    db_session.commit()
    try:
        created = client.post(
            "/api/v1/owner/maintenance/schedules",
            json={
                "asset_id": str(tipper.id),
                "maintenance_type": "engine oil",
                "interval_basis": "KM",
                "interval_value": "10000",
                "last_service_meter": "50000",
                "last_service_date": "2026-10-01",
            },
        )
        assert created.status_code == 201, created.text
        schedule = created.json()
        assert schedule["next_due_meter"] == "60000.00"

        wrong_basis = client.post(
            "/api/v1/owner/maintenance/schedules",
            json={
                "asset_id": str(tipper.id),
                "maintenance_type": "HYDRAULIC_OIL",
                "interval_basis": "HMR",
                "interval_value": "500",
                "last_service_meter": "1000",
            },
        )
        assert wrong_basis.status_code == 422

        hmr_schedule = client.post(
            "/api/v1/owner/maintenance/schedules",
            json={
                "asset_id": str(machine.id),
                "maintenance_type": "HYDRAULIC_OIL",
                "interval_basis": "HMR",
                "interval_value": "500",
                "last_service_meter": "1000",
            },
        )
        assert hmr_schedule.status_code == 201, hmr_schedule.text
        machine_wrong_basis = client.post(
            "/api/v1/owner/maintenance/schedules",
            json={
                "asset_id": str(machine.id),
                "maintenance_type": "GENERAL_SERVICE",
                "interval_basis": "KM",
                "interval_value": "10000",
                "last_service_meter": "0",
            },
        )
        assert machine_wrong_basis.status_code == 422

        foreign_response = client.post(
            "/api/v1/owner/maintenance/schedules",
            json={
                "asset_id": str(foreign.id),
                "maintenance_type": "ENGINE_OIL",
                "interval_basis": "KM",
                "interval_value": "10000",
                "last_service_meter": "0",
            },
        )
        assert foreign_response.status_code == 404

        for performed_on, meter in (("2026-10-02", "51000"), ("2026-10-03", "52000")):
            response = client.post(
                f"/api/v1/owner/maintenance/schedules/{schedule['id']}/records",
                json={"performed_on": performed_on, "meter_value": meter},
            )
            assert response.status_code == 201, response.text
        history = client.get(f"/api/v1/owner/maintenance/schedules/{schedule['id']}/records")
        assert [row["meter_value"] for row in history.json()] == ["51000.00", "52000.00"]
        assert db_session.scalar(select(func.count()).select_from(MaintenanceRecord)) == 2
    finally:
        client.close()


@pytest.mark.parametrize("membership_key", ["driver_a", "supervisor_a"])
def test_maintenance_flag_does_not_bypass_rbac(
    db_session: Session,
    tenant_records: dict[str, object],
    membership_key: str,
) -> None:
    client = authenticated_client(
        db_session,
        value(tenant_records, membership_key, CompanyMembership),
        settings(maintenance_enabled=True, asset_documents_enabled=True),
    )
    try:
        assert client.get("/api/v1/owner/maintenance/schedules").status_code == 403
        assert client.get("/api/v1/owner/asset-documents").status_code == 403
    finally:
        client.close()


def test_asset_documents_preserve_revision_history_and_private_bytes(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    storage = MemoryObjectStorage()
    client = authenticated_client(
        db_session,
        value(tenant_records, "owner_a", CompanyMembership),
        settings(asset_documents_enabled=True),
        storage,
    )
    asset = value(tenant_records, "tipper_a", FleetAsset)
    try:
        first_upload = uuid4()
        uploaded = client.post(
            "/api/v1/owner/asset-documents/evidence",
            params={"upload_id": str(first_upload)},
            files={"file": ("ignored.png", b"\x89PNG\r\n\x1a\ncontent", "image/png")},
        )
        assert uploaded.status_code == 201, uploaded.text
        created = client.post(
            "/api/v1/owner/asset-documents",
            params={"as_of": "2026-10-06"},
            json={
                "asset_id": str(asset.id),
                "document_type": "Registration Certificate",
                "expiry_warning_days": 30,
                "evidence_object_id": uploaded.json()["evidence_object_id"],
                "document_number": "RC-1",
                "issue_date": "2025-10-01",
                "expiry_date": "2026-10-20",
            },
        )
        assert created.status_code == 201, created.text
        document = created.json()
        assert document["document_type"] == "REGISTRATION_CERTIFICATE"
        assert document["expiry_status"] == "EXPIRING_SOON"

        second_upload = uuid4()
        replacement_file = b"%PDF-1.7\nprivate-test"
        uploaded_again = client.post(
            "/api/v1/owner/asset-documents/evidence",
            params={"upload_id": str(second_upload)},
            files={
                "file": (
                    "untrusted-name.pdf",
                    replacement_file,
                    "application/pdf",
                )
            },
        )
        replaced = client.post(
            f"/api/v1/owner/asset-documents/{document['id']}/revisions",
            params={"as_of": "2026-10-06"},
            json={
                "evidence_object_id": uploaded_again.json()["evidence_object_id"],
                "document_number": "RC-2",
                "issue_date": "2026-10-01",
                "expiry_date": "2027-10-01",
            },
        )
        assert replaced.status_code == 201, replaced.text
        assert replaced.json()["revision_number"] == 2
        assert replaced.json()["expiry_status"] == "VALID"

        revisions = client.get(f"/api/v1/owner/asset-documents/{document['id']}/revisions")
        assert [item["document_number"] for item in revisions.json()] == ["RC-1", "RC-2"]
        assert db_session.scalar(select(func.count()).select_from(AssetDocumentRevision)) == 2

        private_file = client.get(f"/api/v1/owner/asset-documents/{document['id']}/file")
        assert private_file.status_code == 200
        assert private_file.content == replacement_file
        assert private_file.headers["cache-control"] == "private, no-store"
        assert "object_key" not in cast(dict[str, object], replaced.json())
    finally:
        client.close()


def test_asset_document_foreign_asset_is_hidden(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    client = authenticated_client(
        db_session,
        value(tenant_records, "owner_a", CompanyMembership),
        settings(asset_documents_enabled=True),
        MemoryObjectStorage(),
    )
    foreign = value(tenant_records, "tipper_b", FleetAsset)
    try:
        uploaded = client.post(
            "/api/v1/owner/asset-documents/evidence",
            params={"upload_id": str(uuid4())},
            files={"file": ("proof.png", b"\x89PNG\r\n\x1a\ncontent", "image/png")},
        )
        response = client.post(
            "/api/v1/owner/asset-documents",
            json={
                "asset_id": str(foreign.id),
                "document_type": "INSURANCE",
                "evidence_object_id": uploaded.json()["evidence_object_id"],
            },
        )
        assert response.status_code == 404
    finally:
        client.close()
