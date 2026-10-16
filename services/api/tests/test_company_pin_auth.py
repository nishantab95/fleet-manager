from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_otp_provider
from fleet_api.auth.providers import UnavailableOtpProvider
from fleet_api.auth.service import AuthContext, AuthService
from fleet_api.core.config import Settings
from fleet_api.db.models import (
    Assignment,
    AuditLog,
    AuthSession,
    Company,
    CompanyMembership,
    CompanyPinCredential,
    FleetAsset,
    OperationalEvent,
    OtpChallenge,
    Site,
    User,
)
from fleet_api.db.models.common import utc_now
from fleet_api.db.session import get_db as session_get_db
from fleet_api.domain.assignments import create_assignment
from fleet_api.domain.enums import (
    AssetOwnershipType,
    FleetAssetStatus,
    FleetAssetType,
    MembershipRole,
    MembershipStatus,
    UserStatus,
)
from fleet_api.domain.errors import (
    ActivationCodeError,
    DeviceCredentialError,
    InvalidTokenError,
    MembershipSelectionError,
    PinAuthenticationError,
    PinLockedError,
)
from fleet_api.domain.owner_people_sites import OwnerPeopleSiteService
from fleet_api.main import create_app

pytestmark = pytest.mark.postgres


def value[T](records: dict[str, object], key: str, expected_type: type[T]) -> T:
    item = records[key]
    assert isinstance(item, expected_type)
    return item


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "auth_mode": "company_pin",
        "phone_default_region": "IN",
        "jwt_signing_key": "test-signing-key-that-is-longer-than-32-characters",
        "otp_max_attempts": 3,
        "activation_code_ttl_seconds": 86_400,
        "activation_setup_ttl_seconds": 900,
        "pin_max_attempts": 3,
        "pin_lock_seconds": 900,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def auth_service(db: Session, config: Settings | None = None) -> AuthService:
    return AuthService(db, config or settings(), UnavailableOtpProvider())


def owner_service(
    db: Session,
    records: dict[str, object],
    config: Settings | None = None,
) -> OwnerPeopleSiteService:
    config = config or settings()
    membership = value(records, "owner_a", CompanyMembership)
    user = db.get(User, membership.user_id)
    company = db.get(Company, membership.company_id)
    assert user is not None and company is not None
    auth_session = AuthSession(
        user_id=user.id,
        company_id=company.id,
        membership_id=membership.id,
        refresh_token_hash=uuid4().hex + uuid4().hex,
        expires_at=utc_now() + timedelta(hours=1),
    )
    db.add(auth_session)
    db.flush()
    return OwnerPeopleSiteService(
        db,
        AuthContext(auth_session, user, membership, company),
        phone_default_region=config.phone_default_region,
        auth_mode=config.auth_mode,
        activation_code_ttl_seconds=config.activation_code_ttl_seconds,
        activation_code_max_attempts=config.otp_max_attempts,
    )


def prepare_driver(
    db: Session,
    records: dict[str, object],
    phone: str = "+919876543210",
) -> tuple[CompanyMembership, User]:
    membership = value(records, "driver_a", CompanyMembership)
    user = db.get(User, membership.user_id)
    assert user is not None
    user.phone_number = phone
    user.status = UserStatus.ACTIVE
    membership.status = MembershipStatus.ACTIVE
    db.flush()
    return membership, user


def generate_code(
    db: Session,
    records: dict[str, object],
    membership: CompanyMembership,
) -> str:
    return owner_service(db, records).generate_person_activation_code(membership.id).activation_code


def activate_and_set_pin(
    db: Session,
    records: dict[str, object],
    *,
    installation: str = "installation-one",
    pin: str = "246810",
) -> tuple[CompanyMembership, User, str, AuthService]:
    membership, user = prepare_driver(db, records)
    code = generate_code(db, records, membership)
    auth = auth_service(db)
    activation = auth.begin_company_activation(
        phone=user.phone_number,
        activation_code=code,
        installation_identifier=installation,
    )
    tokens, credential = auth.complete_company_pin_activation(
        activation_token=activation.device_credential,
        installation_identifier=installation,
        pin=pin,
    )
    assert tokens.context.membership.id == membership.id
    return membership, user, credential, auth


def test_valid_first_activation_hashes_secrets_and_pin_login_is_membership_bound(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    membership, user = prepare_driver(db_session, tenant_records)
    owner = owner_service(db_session, tenant_records)
    code = owner.generate_person_activation_code(membership.id).activation_code
    challenge = db_session.scalar(
        select(OtpChallenge)
        .where(OtpChallenge.membership_id == membership.id)
        .order_by(OtpChallenge.created_at.desc())
    )
    assert challenge is not None
    assert challenge.otp_hash != code and code not in challenge.otp_hash

    auth = auth_service(db_session)
    activation = auth.begin_company_activation(
        phone=user.phone_number,
        activation_code=code,
        installation_identifier="installation-one",
    )
    tokens, device_credential = auth.complete_company_pin_activation(
        activation_token=activation.device_credential,
        installation_identifier="installation-one",
        pin="246810",
    )
    stored = db_session.scalar(
        select(CompanyPinCredential).where(
            CompanyPinCredential.membership_id == membership.id,
            CompanyPinCredential.revoked_at.is_(None),
        )
    )
    assert stored is not None
    assert stored.credential_hash != device_credential
    assert device_credential not in stored.credential_hash
    assert stored.pin_hash != "246810" and "246810" not in (stored.pin_hash or "")
    assert tokens.context.membership.id == membership.id
    assert tokens.context.membership.role == MembershipRole.DRIVER
    audit_text = "\n".join(
        f"{row.old_values} {row.new_values} {row.reason}"
        for row in db_session.scalars(select(AuditLog)).all()
    )
    assert code not in audit_text
    assert "246810" not in audit_text
    assert device_credential not in audit_text

    logged_in = auth.login_company_pin(
        device_credential=device_credential,
        installation_identifier="installation-one",
        pin="246810",
    )
    assert logged_in.context.membership.id == membership.id
    assert logged_in.context.membership.role == MembershipRole.DRIVER


def test_thirty_company_pin_drivers_sync_unique_events_idempotently(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    """Exercise the initially planned 30-phone production workload locally."""
    config = settings()
    app = create_app(config)

    def override_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[session_get_db] = override_db
    app.dependency_overrides[get_otp_provider] = lambda: UnavailableOtpProvider()
    company = value(tenant_records, "company_a", Company)
    supervisor = value(tenant_records, "supervisor_a", CompanyMembership)
    site = value(tenant_records, "site_a", Site)
    owner = owner_service(db_session, tenant_records, config)
    auth = auth_service(db_session, config)
    event_ids: set[str] = set()

    with TestClient(app) as client:
        for index in range(30):
            phone = f"+91880000{index:04d}"
            user = User(
                phone_number=phone,
                display_name=f"Capacity Driver {index + 1}",
                status=UserStatus.ACTIVE,
            )
            db_session.add(user)
            db_session.flush()
            membership = CompanyMembership(
                company_id=company.id,
                user_id=user.id,
                role=MembershipRole.DRIVER,
                display_name=user.display_name,
                status=MembershipStatus.ACTIVE,
            )
            asset = FleetAsset(
                company_id=company.id,
                asset_type=FleetAssetType.TIPPER,
                ownership_type=AssetOwnershipType.OWNED,
                asset_code=f"CAP-{index + 1:02d}",
                registration_number=f"KA99CP{index + 1:04d}",
                short_name=f"Capacity {index + 1}",
                status=FleetAssetStatus.ACTIVE,
            )
            db_session.add_all([membership, asset])
            db_session.flush()
            create_assignment(
                db_session,
                company_id=company.id,
                driver_membership_id=membership.id,
                supervisor_membership_id=supervisor.id,
                asset_id=asset.id,
                site_id=site.id,
                starts_at=datetime.now(UTC) - timedelta(hours=1),
            )

            activation_code = owner.generate_person_activation_code(membership.id).activation_code
            installation = f"capacity-android-{index + 1:02d}"
            activation = auth.begin_company_activation(
                phone=phone,
                activation_code=activation_code,
                installation_identifier=installation,
            )
            tokens, _device_credential = auth.complete_company_pin_activation(
                activation_token=activation.device_credential,
                installation_identifier=installation,
                pin="246810",
            )
            headers = {"Authorization": f"Bearer {tokens.access_token}"}
            device = client.post(
                "/api/v1/driver/device",
                headers=headers,
                json={
                    "installation_identifier": installation,
                    "platform": "ANDROID",
                },
            )
            assert device.status_code == 200
            assert device.json()["membership_id"] == str(membership.id)

            event_id = str(uuid4())
            event_ids.add(event_id)
            payload = {
                "client_event_uuid": event_id,
                "event_type": "EMERGENCY",
                "device_created_at": datetime.now(UTC).isoformat(),
                "installation_identifier": installation,
                "platform": "ANDROID",
            }
            accepted = client.post("/api/v1/driver/events", headers=headers, json=payload)
            assert accepted.status_code == 200
            assert accepted.json()["status"] == "accepted"
            replay = client.post("/api/v1/driver/events", headers=headers, json=payload)
            assert replay.status_code == 200
            assert replay.json()["status"] == "already_accepted"
            assert replay.json()["event_id"] == accepted.json()["event_id"]

    synchronized = db_session.scalar(
        select(func.count(OperationalEvent.id)).where(
            OperationalEvent.client_event_uuid.in_(event_ids)
        )
    )
    assert synchronized == 30


def test_activation_rejects_wrong_expired_reused_and_regenerated_codes(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    membership, user = prepare_driver(db_session, tenant_records)
    owner = owner_service(db_session, tenant_records)
    old_code = owner.generate_person_activation_code(membership.id).activation_code
    replacement = owner.generate_person_activation_code(membership.id).activation_code
    auth = auth_service(db_session)

    with pytest.raises(ActivationCodeError):
        auth.begin_company_activation(
            phone=user.phone_number,
            activation_code=old_code,
            installation_identifier="installation-one",
        )
    activation = auth.begin_company_activation(
        phone=user.phone_number,
        activation_code=replacement,
        installation_identifier="installation-one",
    )
    assert activation.device_credential
    with pytest.raises(ActivationCodeError):
        auth.begin_company_activation(
            phone=user.phone_number,
            activation_code=replacement,
            installation_identifier="installation-one",
        )

    expiring = owner.generate_person_activation_code(membership.id).activation_code
    challenge = db_session.scalar(
        select(OtpChallenge)
        .where(OtpChallenge.membership_id == membership.id)
        .order_by(OtpChallenge.created_at.desc())
    )
    assert challenge is not None
    challenge.expires_at = utc_now() - timedelta(seconds=1)
    with pytest.raises(ActivationCodeError):
        auth.begin_company_activation(
            phone=user.phone_number,
            activation_code=expiring,
            installation_identifier="installation-two",
        )


def test_activation_denies_unknown_duplicate_and_disabled_identities(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    membership, user = prepare_driver(db_session, tenant_records)
    code = generate_code(db_session, tenant_records, membership)
    auth = auth_service(db_session)
    with pytest.raises(ActivationCodeError):
        auth.begin_company_activation(
            phone="+919999999999",
            activation_code=code,
            installation_identifier="installation-one",
        )

    duplicate = User(
        phone_number="09876543210",
        display_name="Duplicate normalized phone",
        status=UserStatus.ACTIVE,
    )
    db_session.add(duplicate)
    db_session.flush()
    with pytest.raises(ActivationCodeError):
        auth.begin_company_activation(
            phone=user.phone_number,
            activation_code=code,
            installation_identifier="installation-one",
        )
    db_session.delete(duplicate)
    db_session.flush()

    user.status = UserStatus.INACTIVE
    with pytest.raises(ActivationCodeError):
        auth.begin_company_activation(
            phone=user.phone_number,
            activation_code=code,
            installation_identifier="installation-one",
        )
    user.status = UserStatus.ACTIVE
    membership.status = MembershipStatus.INACTIVE
    with pytest.raises(ActivationCodeError):
        auth.begin_company_activation(
            phone=user.phone_number,
            activation_code=code,
            installation_identifier="installation-one",
        )


def test_wrong_pin_locks_device_and_reinstall_requires_reactivation(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    _membership, _user, credential, auth = activate_and_set_pin(
        db_session,
        tenant_records,
    )
    with pytest.raises(DeviceCredentialError):
        auth.login_company_pin(
            device_credential=credential,
            installation_identifier="fresh-installation",
            pin="246810",
        )
    for _ in range(2):
        with pytest.raises(PinAuthenticationError):
            auth.login_company_pin(
                device_credential=credential,
                installation_identifier="installation-one",
                pin="000000",
            )
    with pytest.raises(PinLockedError):
        auth.login_company_pin(
            device_credential=credential,
            installation_identifier="installation-one",
            pin="000000",
        )
    with pytest.raises(PinLockedError):
        auth.login_company_pin(
            device_credential=credential,
            installation_identifier="installation-one",
            pin="246810",
        )


def test_logout_and_owner_reset_revoke_sessions_device_and_preserve_domain_data(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    assignment_count = db_session.scalar(select(func.count(Assignment.id)))
    membership, user, credential, auth = activate_and_set_pin(
        db_session,
        tenant_records,
    )
    tokens = auth.login_company_pin(
        device_credential=credential,
        installation_identifier="installation-one",
        pin="246810",
    )
    auth.logout(tokens.context)
    with pytest.raises(InvalidTokenError):
        auth.authenticate_access_token(access_token=tokens.access_token)

    second_role = CompanyMembership(
        company_id=membership.company_id,
        user_id=user.id,
        role=MembershipRole.SUPERVISOR,
        display_name=user.display_name,
        status=MembershipStatus.ACTIVE,
    )
    db_session.add(second_role)
    db_session.flush()
    second_role_session = AuthSession(
        user_id=user.id,
        company_id=membership.company_id,
        membership_id=second_role.id,
        refresh_token_hash=uuid4().hex + uuid4().hex,
        expires_at=utc_now() + timedelta(hours=1),
    )
    db_session.add(second_role_session)
    db_session.flush()

    replacement = owner_service(db_session, tenant_records).generate_person_activation_code(
        membership.id,
        reset_device=True,
    )
    assert second_role_session.revoked_at is not None
    with pytest.raises(DeviceCredentialError):
        auth.login_company_pin(
            device_credential=credential,
            installation_identifier="installation-one",
            pin="246810",
        )
    activation = auth.begin_company_activation(
        phone=user.phone_number,
        activation_code=replacement.activation_code,
        installation_identifier="installation-two",
    )
    replacement_tokens, _ = auth.complete_company_pin_activation(
        activation_token=activation.device_credential,
        installation_identifier="installation-two",
        pin="135790",
    )
    assert replacement_tokens.context.membership.id == membership.id
    assert db_session.scalar(select(func.count(Assignment.id))) == assignment_count


def _add_role(
    db: Session,
    membership: CompanyMembership,
    user: User,
    role: MembershipRole,
) -> CompanyMembership:
    added = CompanyMembership(
        company_id=membership.company_id,
        user_id=user.id,
        role=role,
        display_name=user.display_name,
        status=MembershipStatus.ACTIVE,
    )
    db.add(added)
    db.flush()
    return added


def activate_role_neutral(
    db: Session,
    records: dict[str, object],
    *,
    installation: str = "build-29-installation",
) -> tuple[CompanyMembership, User, str, str, AuthService]:
    membership, user = prepare_driver(db, records)
    code = (
        owner_service(db, records).generate_person_activation_code_for_user(user.id).activation_code
    )
    auth = auth_service(db)
    activation = auth.begin_company_activation(
        phone=user.phone_number,
        activation_code=code,
        installation_identifier=installation,
    )
    pre_session, _expires_in, credential = auth.complete_company_device_activation(
        activation_token=activation.device_credential,
        installation_identifier=installation,
        pin="246810",
    )
    return membership, user, credential, pre_session, auth


@pytest.mark.parametrize(
    ("role", "expected_role"),
    [
        (MembershipRole.DRIVER, MembershipRole.DRIVER),
        (MembershipRole.SUPERVISOR, MembershipRole.SUPERVISOR),
        (MembershipRole.OWNER_ADMIN, MembershipRole.OWNER_ADMIN),
    ],
)
def test_single_role_device_auth_creates_only_the_authorized_session(
    db_session: Session,
    tenant_records: dict[str, object],
    role: MembershipRole,
    expected_role: MembershipRole,
) -> None:
    membership, user = prepare_driver(db_session, tenant_records)
    membership.role = role
    db_session.flush()
    code = (
        owner_service(db_session, tenant_records)
        .generate_person_activation_code_for_user(user.id)
        .activation_code
    )
    auth = auth_service(db_session)
    activation = auth.begin_company_activation(
        phone=user.phone_number,
        activation_code=code,
        installation_identifier=f"single-{role.value}",
    )
    pre_session, _expires_in, credential = auth.complete_company_device_activation(
        activation_token=activation.device_credential,
        installation_identifier=f"single-{role.value}",
        pin="246810",
    )
    assert [item[3] for item in auth.list_memberships(pre_session_token=pre_session)] == [
        expected_role
    ]
    authenticated, _ = auth.authenticate_company_device(
        device_credential=credential,
        installation_identifier=f"single-{role.value}",
    )
    tokens = auth.create_session(
        pre_session_token=authenticated,
        membership_id=membership.id,
    )
    assert tokens.context.membership.role == expected_role


def test_multi_role_authentication_lists_all_active_roles_and_selects_exact_membership(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    driver, user = prepare_driver(db_session, tenant_records)
    supervisor = _add_role(
        db_session,
        driver,
        user,
        MembershipRole.SUPERVISOR,
    )
    owner = _add_role(
        db_session,
        driver,
        user,
        MembershipRole.OWNER_ADMIN,
    )
    _membership, _user, credential, _activation_context, auth = activate_role_neutral(
        db_session,
        tenant_records,
    )

    pre_session, _ = auth.authenticate_company_device(
        device_credential=credential,
        installation_identifier="build-29-installation",
    )
    options = auth.list_memberships(pre_session_token=pre_session)
    assert {option[3] for option in options} == {
        MembershipRole.DRIVER,
        MembershipRole.SUPERVISOR,
        MembershipRole.OWNER_ADMIN,
    }
    for selected in (driver, supervisor, owner):
        tokens = auth.create_session(
            pre_session_token=pre_session,
            membership_id=selected.id,
        )
        assert tokens.context.membership.id == selected.id
        assert tokens.context.membership.role == selected.role

    foreign_membership = value(tenant_records, "driver_b", CompanyMembership)
    with pytest.raises(MembershipSelectionError):
        auth.create_session(
            pre_session_token=pre_session,
            membership_id=foreign_membership.id,
        )


def test_workspace_switch_is_company_scoped_and_removed_role_disappears(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    driver, user = prepare_driver(db_session, tenant_records)
    supervisor = _add_role(
        db_session,
        driver,
        user,
        MembershipRole.SUPERVISOR,
    )
    _membership, _user, credential, pre_session, auth = activate_role_neutral(
        db_session,
        tenant_records,
    )
    driver_tokens = auth.create_session(
        pre_session_token=pre_session,
        membership_id=driver.id,
    )
    supervisor_tokens = auth.switch_workspace(
        driver_tokens.context,
        membership_id=supervisor.id,
    )
    assert supervisor_tokens.context.membership.role == MembershipRole.SUPERVISOR
    with pytest.raises(InvalidTokenError):
        auth.authenticate_access_token(access_token=driver_tokens.access_token)
    with pytest.raises(MembershipSelectionError):
        auth.switch_workspace(
            supervisor_tokens.context,
            membership_id=value(
                tenant_records,
                "driver_b",
                CompanyMembership,
            ).id,
        )

    supervisor.status = MembershipStatus.INACTIVE
    db_session.flush()
    refreshed_context, _ = auth.authenticate_company_device(
        device_credential=credential,
        installation_identifier="build-29-installation",
    )
    assert [item[3] for item in auth.list_memberships(pre_session_token=refreshed_context)] == [
        MembershipRole.DRIVER
    ]


def test_build_28_credential_is_reused_by_device_auth_and_pin_fallback(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    membership, _user, credential, auth = activate_and_set_pin(
        db_session,
        tenant_records,
    )
    device_context, _ = auth.authenticate_company_device(
        device_credential=credential,
        installation_identifier="installation-one",
    )
    fallback_context, _ = auth.authenticate_company_pin(
        device_credential=credential,
        installation_identifier="installation-one",
        pin="246810",
    )
    assert (
        auth.create_session(
            pre_session_token=device_context,
            membership_id=membership.id,
        ).context.membership.role
        == MembershipRole.DRIVER
    )
    assert (
        auth.create_session(
            pre_session_token=fallback_context,
            membership_id=membership.id,
        ).context.membership.role
        == MembershipRole.DRIVER
    )


def test_role_deactivation_preserves_person_device_until_last_role_and_reset_revokes_it(
    db_session: Session,
    tenant_records: dict[str, object],
) -> None:
    driver, user = prepare_driver(db_session, tenant_records)
    supervisor = _add_role(
        db_session,
        driver,
        user,
        MembershipRole.SUPERVISOR,
    )
    _membership, _user, credential, _pre_session, auth = activate_role_neutral(
        db_session,
        tenant_records,
    )
    owner = owner_service(db_session, tenant_records)
    owner.deactivate_person(supervisor.id)
    still_valid, _ = auth.authenticate_company_device(
        device_credential=credential,
        installation_identifier="build-29-installation",
    )
    assert [item[3] for item in auth.list_memberships(pre_session_token=still_valid)] == [
        MembershipRole.DRIVER
    ]

    replacement = owner.generate_person_activation_code_for_user(
        user.id,
        reset_device=True,
    )
    assert replacement.activation_code
    with pytest.raises(DeviceCredentialError):
        auth.authenticate_company_device(
            device_credential=credential,
            installation_identifier="build-29-installation",
        )
