from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fleet_api.api.dependencies import get_phone_identity_provider
from fleet_api.auth.firebase import PhoneIdentityAuthProvider, VerifiedPhoneIdentity
from fleet_api.auth.providers import FakeOtpProvider, UnavailableOtpProvider
from fleet_api.auth.service import AuthService
from fleet_api.core.config import Settings
from fleet_api.db.models import (
    Assignment,
    AuditLog,
    AuthSession,
    Company,
    CompanyMembership,
    FleetAsset,
    Site,
    User,
    UserAuthIdentity,
)
from fleet_api.db.session import get_db as session_get_db
from fleet_api.domain.assignments import create_assignment
from fleet_api.domain.enums import (
    AuthIdentityProvider,
    MembershipRole,
    MembershipStatus,
    UserStatus,
)
from fleet_api.domain.errors import (
    AmbiguousPhoneIdentityError,
    AuthConfigurationError,
    FirebaseTokenError,
    FleetIdentityAccessDeniedError,
    IdentityLinkConflictError,
    MembershipSelectionError,
)
from fleet_api.domain.owner_people_sites import OwnerPeopleSiteService
from fleet_api.main import create_app

pytestmark = pytest.mark.postgres


@dataclass
class FakeFirebasePhoneAuthProvider:
    identity: VerifiedPhoneIdentity | None = None
    error: Exception | None = None

    def verify(self, id_token: str) -> VerifiedPhoneIdentity:
        assert id_token
        if self.error is not None:
            raise self.error
        assert self.identity is not None
        return self.identity


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "auth_mode": "firebase",
        "firebase_project_id": "fleet-auth-test",
        "phone_default_region": "IN",
        "jwt_signing_key": "test-signing-key-that-is-longer-than-32-characters",
    }
    values.update(overrides)
    return Settings.model_validate(values)


def _identity(subject: str, phone: str) -> VerifiedPhoneIdentity:
    return VerifiedPhoneIdentity(
        provider=AuthIdentityProvider.FIREBASE_PHONE,
        subject=subject,
        normalized_phone=phone,
        verified_at=datetime.now(UTC),
    )


def _user(db: Session, name: str) -> User:
    user = db.scalar(select(User).where(User.display_name == name))
    assert user is not None
    return user


def _membership(db: Session, user: User, role: MembershipRole | None = None) -> CompanyMembership:
    statement = select(CompanyMembership).where(CompanyMembership.user_id == user.id)
    if role is not None:
        statement = statement.where(CompanyMembership.role == role)
    membership = db.scalar(statement)
    assert membership is not None
    return membership


def _service(
    db: Session,
    provider: PhoneIdentityAuthProvider,
    settings: Settings | None = None,
) -> AuthService:
    return AuthService(
        db,
        settings or _settings(),
        UnavailableOtpProvider(),
        phone_identity_provider=provider,
    )


@pytest.mark.parametrize(
    ("display_name", "role", "phone", "subject"),
    [
        ("Driver A", MembershipRole.DRIVER, "+919876540001", "firebase-driver"),
        ("Supervisor A", MembershipRole.SUPERVISOR, "+919876540002", "firebase-supervisor"),
        ("Owner A", MembershipRole.OWNER_ADMIN, "+919876540003", "firebase-owner"),
    ],
)
def test_valid_firebase_identity_uses_server_membership_role(
    db_session: Session,
    tenant_records: dict[str, object],
    display_name: str,
    role: MembershipRole,
    phone: str,
    subject: str,
) -> None:
    del tenant_records
    user = _user(db_session, display_name)
    user.phone_number = phone
    db_session.flush()
    provider = FakeFirebasePhoneAuthProvider(_identity(subject, phone))
    service = _service(db_session, provider)

    pre_session, _ = service.verify_firebase_identity(id_token="valid-token")
    options = service.list_memberships(pre_session_token=pre_session)

    assert [option[3] for option in options] == [role]
    tokens = service.create_session(
        pre_session_token=pre_session,
        membership_id=options[0][0],
    )
    assert tokens.context.membership.role == role
    assert (
        db_session.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "LOGIN_SUCCESS"))
        == 1
    )


def test_first_login_links_exact_phone_without_creating_a_user(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    del tenant_records
    user = _user(db_session, "Driver A")
    user.phone_number = "+919876540010"
    original_user_count = db_session.scalar(select(func.count(User.id)))
    service = _service(
        db_session,
        FakeFirebasePhoneAuthProvider(_identity("firebase-first-login", user.phone_number)),
    )

    service.verify_firebase_identity(id_token="valid-token")

    link = db_session.scalar(
        select(UserAuthIdentity).where(UserAuthIdentity.provider_subject == "firebase-first-login")
    )
    assert link is not None
    assert link.user_id == user.id
    assert db_session.scalar(select(func.count(User.id))) == original_user_count
    assert (
        db_session.scalar(
            select(func.count(AuditLog.id)).where(AuditLog.action == "AUTH_IDENTITY_LINKED")
        )
        == 1
    )


def test_unknown_verified_phone_is_denied_without_creating_business_data(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    del tenant_records
    original_user_count = db_session.scalar(select(func.count(User.id)))
    service = _service(
        db_session,
        FakeFirebasePhoneAuthProvider(_identity("firebase-unknown", "+919876549999")),
    )

    with pytest.raises(FleetIdentityAccessDeniedError, match="not registered"):
        service.verify_firebase_identity(id_token="valid-token")

    assert db_session.scalar(select(func.count(User.id))) == original_user_count
    assert db_session.scalar(select(func.count(UserAuthIdentity.id))) == 0


@pytest.mark.parametrize("case", ["invalid", "expired", "wrong-project"])
def test_invalid_expired_or_wrong_project_token_is_denied(
    db_session: Session,
    tenant_records: dict[str, object],
    case: str,
) -> None:
    del tenant_records
    provider = FakeFirebasePhoneAuthProvider(error=FirebaseTokenError(case))
    with pytest.raises(FirebaseTokenError, match=case):
        _service(db_session, provider).verify_firebase_identity(id_token=f"{case}-token")
    assert db_session.scalar(select(func.count(UserAuthIdentity.id))) == 0


@pytest.mark.parametrize("disable_user", [True, False])
def test_disabled_user_or_membership_is_denied(
    db_session: Session,
    tenant_records: dict[str, object],
    disable_user: bool,
) -> None:
    del tenant_records
    user = _user(db_session, "Driver A")
    user.phone_number = "+919876540020"
    membership = _membership(db_session, user, MembershipRole.DRIVER)
    if disable_user:
        user.status = UserStatus.INACTIVE
    else:
        membership.status = MembershipStatus.INACTIVE
    db_session.flush()
    service = _service(
        db_session,
        FakeFirebasePhoneAuthProvider(_identity("firebase-disabled", user.phone_number)),
    )

    with pytest.raises(FleetIdentityAccessDeniedError):
        service.verify_firebase_identity(id_token="valid-token")
    assert db_session.scalar(select(func.count(UserAuthIdentity.id))) == 0


def test_legacy_duplicate_normalized_phone_is_denied_as_ambiguous(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    company = tenant_records["company_a"]
    assert isinstance(company, Company)
    first = _user(db_session, "Driver A")
    first.phone_number = "+919876540030"
    duplicate = User(
        phone_number="09876540030",
        display_name="Legacy Duplicate",
        status=UserStatus.ACTIVE,
    )
    db_session.add(duplicate)
    db_session.flush()
    db_session.add(
        CompanyMembership(
            company_id=company.id,
            user_id=duplicate.id,
            role=MembershipRole.DRIVER,
            status=MembershipStatus.ACTIVE,
        )
    )
    db_session.flush()
    service = _service(
        db_session,
        FakeFirebasePhoneAuthProvider(_identity("firebase-ambiguous", first.phone_number)),
    )

    with pytest.raises(FleetIdentityAccessDeniedError, match="multiple Fleet accounts"):
        service.verify_firebase_identity(id_token="valid-token")
    assert db_session.scalar(select(func.count(UserAuthIdentity.id))) == 0


def test_inactive_legacy_duplicate_still_blocks_automatic_identity_link(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    del tenant_records
    first = _user(db_session, "Driver A")
    first.phone_number = "+919876540031"
    db_session.add(
        User(
            phone_number="09876540031",
            display_name="Inactive Legacy Duplicate",
            status=UserStatus.INACTIVE,
        )
    )
    db_session.flush()

    service = _service(
        db_session,
        FakeFirebasePhoneAuthProvider(_identity("firebase-ambiguous-inactive", first.phone_number)),
    )

    with pytest.raises(AmbiguousPhoneIdentityError):
        service.verify_firebase_identity(id_token="valid-token")
    assert db_session.scalar(select(func.count(UserAuthIdentity.id))) == 0


def test_firebase_subject_cannot_relink_or_replace_an_active_link(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    del tenant_records
    user = _user(db_session, "Driver A")
    user.phone_number = "+919876540040"
    first_provider = FakeFirebasePhoneAuthProvider(
        _identity("firebase-original", user.phone_number)
    )
    _service(db_session, first_provider).verify_firebase_identity(id_token="first-token")

    second_provider = FakeFirebasePhoneAuthProvider(
        _identity("firebase-attacker", user.phone_number)
    )
    with pytest.raises(IdentityLinkConflictError):
        _service(db_session, second_provider).verify_firebase_identity(id_token="second-token")
    assert db_session.scalar(select(func.count(UserAuthIdentity.id))) == 1
    assert (
        db_session.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "LOGIN_DENIED"))
        == 1
    )


def test_owner_phone_change_revokes_sessions_and_requires_new_firebase_verification(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    owner = _user(db_session, "Owner A")
    owner.phone_number = "+919876540041"
    auth_service = _service(
        db_session,
        FakeFirebasePhoneAuthProvider(_identity("firebase-owner", owner.phone_number)),
    )
    pre_session, _ = auth_service.verify_firebase_identity(id_token="owner-token")
    owner_membership = _membership(db_session, owner, MembershipRole.OWNER_ADMIN)
    owner_tokens = auth_service.create_session(
        pre_session_token=pre_session,
        membership_id=owner_membership.id,
    )

    driver = _user(db_session, "Driver A")
    driver.phone_number = "+919876540042"
    driver_membership = _membership(db_session, driver, MembershipRole.DRIVER)
    old_identity = UserAuthIdentity(
        user_id=driver.id,
        provider=AuthIdentityProvider.FIREBASE_PHONE,
        provider_subject="firebase-old-driver",
        normalized_phone=driver.phone_number,
        verified_at=datetime.now(UTC),
    )
    db_session.add(old_identity)
    db_session.flush()
    driver_auth = _service(
        db_session,
        FakeFirebasePhoneAuthProvider(_identity("firebase-old-driver", driver.phone_number)),
    )
    driver_pre_session, _ = driver_auth.verify_firebase_identity(id_token="old-driver-token")
    driver_auth.create_session(
        pre_session_token=driver_pre_session,
        membership_id=driver_membership.id,
    )
    driver_session = db_session.scalar(
        select(AuthSession).where(AuthSession.membership_id == driver_membership.id)
    )
    assert driver_session is not None

    supervisor_membership = tenant_records["supervisor_a"]
    asset = tenant_records["tipper_a"]
    site = tenant_records["site_a"]
    assert isinstance(supervisor_membership, CompanyMembership)
    assert isinstance(asset, FleetAsset)
    assert isinstance(site, Site)
    assignment = create_assignment(
        db_session,
        company_id=driver_membership.company_id,
        driver_membership_id=driver_membership.id,
        supervisor_membership_id=supervisor_membership.id,
        asset_id=asset.id,
        site_id=site.id,
        starts_at=datetime.now(UTC) - timedelta(minutes=1),
        ends_at=None,
        regular_duty_minutes=600,
    )
    membership_ids_before = set(
        db_session.scalars(
            select(CompanyMembership.id).where(CompanyMembership.user_id == driver.id)
        ).all()
    )

    people = OwnerPeopleSiteService(
        db_session,
        owner_tokens.context,
        phone_default_region="IN",
        auth_mode="firebase",
    )
    people.update_person(
        driver_membership.id,
        phone="+919876540043",
        fields_set={"phone"},
    )

    assert driver.phone_number == "+919876540043"
    assert old_identity.disabled_at is not None
    assert old_identity.disabled_reason == "phone_change_requested"
    assert driver_session.revoked_at is not None
    assert driver_session.revocation_reason == "phone_change_requested"
    preserved_assignment = db_session.get(Assignment, assignment.id)
    assert preserved_assignment is not None
    assert preserved_assignment.driver_membership_id == driver_membership.id
    assert (
        set(
            db_session.scalars(
                select(CompanyMembership.id).where(CompanyMembership.user_id == driver.id)
            ).all()
        )
        == membership_ids_before
    )
    assert people.get_person(driver_membership.id).phone_auth_linked is False

    with pytest.raises(IdentityLinkConflictError):
        _service(
            db_session,
            FakeFirebasePhoneAuthProvider(_identity("firebase-old-driver", "+919876540042")),
        ).verify_firebase_identity(id_token="old-driver-token-again")

    new_driver_auth = _service(
        db_session,
        FakeFirebasePhoneAuthProvider(_identity("firebase-new-driver", "+919876540043")),
    )
    new_pre_session, _ = new_driver_auth.verify_firebase_identity(id_token="new-driver-token")
    new_tokens = new_driver_auth.create_session(
        pre_session_token=new_pre_session,
        membership_id=driver_membership.id,
    )
    assert new_tokens.context.user.id == driver.id
    assert people.get_person(driver_membership.id).phone_auth_linked is True
    actions = set(
        db_session.scalars(
            select(AuditLog.action).where(
                AuditLog.action.in_(
                    (
                        "AUTH_IDENTITY_DISABLED",
                        "AUTH_SESSIONS_REVOKED",
                        "PHONE_CHANGE_REQUESTED",
                    )
                )
            )
        ).all()
    )
    assert actions == {
        "AUTH_IDENTITY_DISABLED",
        "AUTH_SESSIONS_REVOKED",
        "PHONE_CHANGE_REQUESTED",
    }


def test_firebase_membership_selection_cannot_cross_tenants(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    owner = _user(db_session, "Owner A")
    owner.phone_number = "+919876540050"
    foreign_user = _user(db_session, "Driver B")
    foreign_membership = _membership(db_session, foreign_user, MembershipRole.DRIVER)
    service = _service(
        db_session,
        FakeFirebasePhoneAuthProvider(_identity("firebase-owner-tenant", owner.phone_number)),
    )
    pre_session, _ = service.verify_firebase_identity(id_token="valid-token")

    with pytest.raises(MembershipSelectionError):
        service.create_session(
            pre_session_token=pre_session,
            membership_id=foreign_membership.id,
        )


def test_firebase_cannot_select_or_activate_an_invited_membership(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    del tenant_records
    user = _user(db_session, "Driver A")
    user.phone_number = "+919876540051"
    active_membership = _membership(db_session, user, MembershipRole.DRIVER)
    invited_membership = _membership(db_session, _user(db_session, "Supervisor A"))
    invited_membership.user_id = user.id
    invited_membership.status = MembershipStatus.INVITED
    db_session.flush()
    service = _service(
        db_session,
        FakeFirebasePhoneAuthProvider(_identity("firebase-invited", user.phone_number)),
    )
    pre_session, _ = service.verify_firebase_identity(id_token="valid-token")

    options = service.list_memberships(pre_session_token=pre_session)
    assert [item[0] for item in options] == [active_membership.id]
    with pytest.raises(MembershipSelectionError):
        service.create_session(
            pre_session_token=pre_session,
            membership_id=invited_membership.id,
        )
    assert invited_membership.status == MembershipStatus.INVITED


def test_pilot_otp_is_available_only_in_pilot_mode(db_session: Session) -> None:
    pilot_settings = Settings(
        environment="test",
        auth_mode="pilot",
        otp_provider="pilot",
        pilot_driver_otp="111111",
        pilot_supervisor_otp="222222",
        pilot_owner_otp="333333",
        phone_default_region="IN",
        jwt_signing_key="test-signing-key-that-is-longer-than-32-characters",
    )
    pilot_provider = FakeOtpProvider()
    pilot_service = AuthService(db_session, pilot_settings, pilot_provider)
    assert pilot_service.request_otp(phone="9876540060")

    firebase_service = _service(
        db_session,
        FakeFirebasePhoneAuthProvider(_identity("firebase-mode", "+919876540060")),
    )
    with pytest.raises(AuthConfigurationError, match="disabled"):
        firebase_service.request_otp(phone="9876540060")


def test_production_and_strict_production_reject_pilot_mode() -> None:
    for environment in ("production", "strict-production"):
        with pytest.raises(ValueError, match="Firebase authentication mode"):
            Settings(
                environment=environment,
                auth_mode="pilot",
                jwt_signing_key="production-signing-key-that-is-longer-than-32-characters",
            )


def test_firebase_http_exchange_ignores_client_role_and_company_fields(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    owner = _user(db_session, "Owner A")
    owner.phone_number = "+919876540070"
    foreign_user = _user(db_session, "Driver B")
    foreign_membership = _membership(db_session, foreign_user, MembershipRole.DRIVER)
    provider = FakeFirebasePhoneAuthProvider(_identity("firebase-http-owner", owner.phone_number))
    app = create_app(_settings())

    def override_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[session_get_db] = override_db
    app.dependency_overrides[get_phone_identity_provider] = lambda: provider
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/firebase/verify",
                json={
                    "id_token": "valid-token",
                    "role": "DRIVER",
                    "company_id": str(foreign_membership.company_id),
                },
            )
            assert response.status_code == 200
            pre_session = response.json()["pre_session_token"]
            memberships = client.post(
                "/api/v1/auth/memberships",
                json={"pre_session_token": pre_session},
            ).json()["memberships"]
            assert [item["role"] for item in memberships] == ["OWNER_ADMIN"]
            bypass = client.post(
                "/api/v1/auth/session",
                json={
                    "pre_session_token": pre_session,
                    "membership_id": str(foreign_membership.id),
                },
            )
            assert bypass.status_code == 403
    finally:
        app.dependency_overrides.clear()
