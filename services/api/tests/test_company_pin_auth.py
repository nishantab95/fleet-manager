from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

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
    OtpChallenge,
    User,
)
from fleet_api.db.models.common import utc_now
from fleet_api.domain.enums import MembershipRole, MembershipStatus, UserStatus
from fleet_api.domain.errors import (
    ActivationCodeError,
    DeviceCredentialError,
    InvalidTokenError,
    PinAuthenticationError,
    PinLockedError,
)
from fleet_api.domain.owner_people_sites import OwnerPeopleSiteService

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
