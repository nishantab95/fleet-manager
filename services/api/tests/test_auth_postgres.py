from __future__ import annotations

import logging
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from fleet_api.auth.phone import normalize_phone
from fleet_api.auth.providers import FakeOtpProvider, build_otp_provider
from fleet_api.auth.service import (
    AuthService,
    SessionTokens,
    ensure_company,
    ensure_role,
    ensure_supervisor_site_access,
)
from fleet_api.auth.tokens import decode_access_token, issue_access_token
from fleet_api.core.config import Settings
from fleet_api.db.models import (
    AuditLog,
    AuthSession,
    Company,
    CompanyMembership,
    OtpChallenge,
    Site,
    User,
)
from fleet_api.db.models.common import utc_now
from fleet_api.domain.assignments import grant_supervisor_site_access
from fleet_api.domain.enums import (
    CompanyStatus,
    MembershipRole,
    MembershipStatus,
    OtpChallengeStatus,
    UserStatus,
)
from fleet_api.domain.errors import (
    AuthConfigurationError,
    AuthenticationError,
    InvalidOtpError,
    InvalidTokenError,
    MembershipSelectionError,
    RefreshTokenReuseError,
    RoleViolationError,
    TenantConsistencyError,
)

pytestmark = pytest.mark.postgres


def value[T](records: dict[str, object], key: str, expected_type: type[T]) -> T:
    item = records[key]
    assert isinstance(item, expected_type)
    return item


def user_by_name(db_session: Session, display_name: str) -> User:
    user = db_session.scalar(select(User).where(User.display_name == display_name))
    assert user is not None
    return user


def auth_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "phone_default_region": "IN",
        "jwt_signing_key": "test-signing-key-that-is-longer-than-32-characters",
        "otp_ttl_seconds": 300,
        "otp_max_attempts": 3,
        "otp_resend_cooldown_seconds": 60,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def prepare_user(user: User, db_session: Session, phone: str = "+919876543210") -> None:
    user.phone_number = phone
    db_session.flush()


def new_service(
    db_session: Session,
    settings: Settings | None = None,
) -> tuple[AuthService, FakeOtpProvider]:
    provider = FakeOtpProvider()
    return AuthService(db_session, settings or auth_settings(), provider), provider


def create_owner_session(
    db_session: Session,
    records: dict[str, object],
    *,
    settings: Settings | None = None,
) -> tuple[AuthService, FakeOtpProvider, SessionTokens]:
    owner = user_by_name(db_session, "Owner A")
    membership = value(records, "owner_a", CompanyMembership)
    prepare_user(owner, db_session)
    service, provider = new_service(db_session, settings)
    challenge_id = service.request_otp(phone=owner.phone_number)
    pre_session, _ = service.verify_otp(
        challenge_id=challenge_id,
        otp=provider.deliveries[challenge_id],
    )
    tokens = service.create_session(pre_session_token=pre_session, membership_id=membership.id)
    return service, provider, tokens


def test_phone_normalization_uses_canonical_e164_without_country_hardcoding() -> None:
    assert normalize_phone("+91 98765 43210") == "+919876543210"
    assert normalize_phone("09876543210", default_region="IN") == "+919876543210"
    assert normalize_phone("+1 (202) 555-0123") == "+12025550123"


def test_otp_challenge_hashes_code_and_enforces_cooldown(
    db_session: Session,
) -> None:
    service, provider = new_service(db_session)
    challenge_id = service.request_otp(
        phone="+91 98765 43210",
        request_ip="192.0.2.1",
        user_agent="test-agent",
    )
    challenge = db_session.get(OtpChallenge, challenge_id)
    assert challenge is not None
    code = provider.deliveries[challenge_id]
    assert challenge.otp_hash != code
    assert code not in challenge.otp_hash
    assert challenge.phone_number == "+919876543210"
    assert challenge.request_ip_hash != "192.0.2.1"
    assert challenge.request_user_agent_hash != "test-agent"

    assert service.request_otp(phone="+919876543210") == challenge_id
    assert len(provider.deliveries) == 1


def test_otp_code_is_not_written_to_application_logs(
    db_session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    service, provider = new_service(db_session)
    with caplog.at_level(logging.INFO, logger="fleet_api"):
        challenge_id = service.request_otp(phone="+919876543210")

    assert provider.deliveries[challenge_id] not in caplog.text


def test_otp_wrong_attempts_are_bounded_and_exhausted(
    db_session: Session,
) -> None:
    service, provider = new_service(db_session)
    challenge_id = service.request_otp(phone="+919876543210")
    correct_code = provider.deliveries[challenge_id]
    wrong_code = "000000" if correct_code != "000000" else "000001"

    for _ in range(3):
        with pytest.raises(InvalidOtpError):
            service.verify_otp(challenge_id=challenge_id, otp=wrong_code)

    challenge = db_session.get(OtpChallenge, challenge_id)
    assert challenge is not None
    assert challenge.status == OtpChallengeStatus.EXHAUSTED
    with pytest.raises(InvalidOtpError):
        service.verify_otp(challenge_id=challenge_id, otp=correct_code)


def test_otp_expiry_and_replay_are_rejected(db_session: Session) -> None:
    service, provider = new_service(db_session)
    expired_id = service.request_otp(phone="+919876543210")
    expired = db_session.get(OtpChallenge, expired_id)
    assert expired is not None
    expired.expires_at = utc_now() - timedelta(seconds=1)
    with pytest.raises(InvalidOtpError):
        service.verify_otp(challenge_id=expired_id, otp=provider.deliveries[expired_id])
    assert expired.status == OtpChallengeStatus.EXPIRED

    active_id = service.request_otp(phone="+12025550123")
    pre_session, _ = service.verify_otp(
        challenge_id=active_id,
        otp=provider.deliveries[active_id],
    )
    assert pre_session
    with pytest.raises(InvalidOtpError):
        service.verify_otp(challenge_id=active_id, otp=provider.deliveries[active_id])


def test_development_provider_and_production_secret_configuration_fail_closed() -> None:
    with pytest.raises(ValueError):
        Settings(environment="production", otp_provider="development", enable_development_otp=True)
    with pytest.raises(ValueError):
        Settings(environment="production", jwt_signing_key="too-short")
    with pytest.raises(AuthConfigurationError):
        build_otp_provider(auth_settings(otp_provider="fake"))
    with pytest.raises(ValueError):
        Settings(
            environment="production",
            otp_provider="sms",
            pilot_driver_otp="111111",
            jwt_signing_key="test-signing-key-that-is-longer-than-32-characters",
        )


def test_local_pilot_otp_and_membership_selection_are_role_bound(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    company = value(tenant_records, "company_a", Company)
    pilot = User(
        phone_number="+919606743463",
        display_name="Pilot Driver",
        status=UserStatus.ACTIVE,
    )
    db_session.add(pilot)
    db_session.flush()
    memberships = [
        CompanyMembership(
            company_id=company.id,
            user_id=pilot.id,
            role=role,
            status=MembershipStatus.ACTIVE,
        )
        for role in MembershipRole
    ]
    db_session.add_all(memberships)
    db_session.flush()

    settings = auth_settings(
        otp_provider="pilot",
        otp_resend_cooldown_seconds=0,
        pilot_driver_otp="111111",
        pilot_supervisor_otp="222222",
        pilot_owner_otp="333333",
    )
    provider = build_otp_provider(settings)
    service = AuthService(db_session, settings, provider)
    expected_codes = {
        MembershipRole.DRIVER: "111111",
        MembershipRole.SUPERVISOR: "222222",
        MembershipRole.OWNER_ADMIN: "333333",
    }

    for role, expected_code in expected_codes.items():
        challenge_id = service.request_otp(
            phone="9606743463",
            requested_role=role,
        )
        assert provider.deliveries[challenge_id] == expected_code  # type: ignore[attr-defined]
        pre_session, _ = service.verify_otp(
            challenge_id=challenge_id,
            otp=expected_code,
        )
        options = service.list_memberships(pre_session_token=pre_session)
        assert [option[3] for option in options] == [role]
        selected = service.create_session(
            pre_session_token=pre_session,
            membership_id=options[0][0],
        )
        assert selected.context.membership.role == role

        other_membership = next(membership for membership in memberships if membership.role != role)
        with pytest.raises(MembershipSelectionError):
            service.create_session(
                pre_session_token=pre_session,
                membership_id=other_membership.id,
            )


def test_membership_selection_is_user_scoped_and_returns_safe_context(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    service, provider, tokens = create_owner_session(db_session, tenant_records)
    owner = user_by_name(db_session, "Owner A")
    owner_membership = value(tenant_records, "owner_a", CompanyMembership)
    foreign_membership = value(tenant_records, "driver_b", CompanyMembership)

    assert (
        service.authenticate_access_token(access_token=tokens.access_token).membership.id
        == owner_membership.id
    )
    challenge_id = service.request_otp(phone=owner.phone_number)
    pre_session, _ = service.verify_otp(
        challenge_id=challenge_id,
        otp=provider.deliveries[challenge_id],
    )
    memberships = service.list_memberships(pre_session_token=pre_session)
    assert [membership[0] for membership in memberships] == [owner_membership.id]
    with pytest.raises(MembershipSelectionError):
        service.create_session(
            pre_session_token=pre_session,
            membership_id=foreign_membership.id,
        )


def test_inactive_membership_and_company_cannot_authenticate(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    service, _, tokens = create_owner_session(db_session, tenant_records)
    membership = value(tenant_records, "owner_a", CompanyMembership)
    company = value(tenant_records, "company_a", Company)
    membership.status = MembershipStatus.INACTIVE
    with pytest.raises(InvalidTokenError):
        service.authenticate_access_token(access_token=tokens.access_token)

    membership.status = MembershipStatus.ACTIVE
    company.status = CompanyStatus.INACTIVE
    with pytest.raises(InvalidTokenError):
        service.authenticate_access_token(access_token=tokens.access_token)


def test_access_token_expiry_and_signature_validation(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    service, _, tokens = create_owner_session(db_session, tenant_records)
    claims = decode_access_token(tokens.access_token, auth_settings())
    assert claims.user_id
    settings = auth_settings(access_token_ttl_seconds=1)
    membership = value(tenant_records, "owner_a", CompanyMembership)
    company = value(tenant_records, "company_a", Company)
    user = user_by_name(db_session, "Owner A")
    expired = issue_access_token(
        settings,
        user_id=user.id,
        membership_id=membership.id,
        company_id=company.id,
        session_id=tokens.context.auth_session.id,
        role=membership.role.value,
        now=utc_now() - timedelta(seconds=10),
    )
    with pytest.raises(InvalidTokenError):
        service.authenticate_access_token(access_token=expired)
    token_parts = tokens.access_token.split(".")
    signature = token_parts[2]
    replacement = "A" if signature[0] != "A" else "B"
    tampered = ".".join((*token_parts[:2], replacement + signature[1:]))
    with pytest.raises(InvalidTokenError):
        service.authenticate_access_token(access_token=tampered)

    wrong_issuer = issue_access_token(
        auth_settings(jwt_issuer="unexpected-issuer"),
        user_id=user.id,
        membership_id=membership.id,
        company_id=company.id,
        session_id=tokens.context.auth_session.id,
        role=membership.role.value,
        now=utc_now(),
    )
    with pytest.raises(InvalidTokenError):
        service.authenticate_access_token(access_token=wrong_issuer)

    wrong_audience = issue_access_token(
        auth_settings(jwt_audience="unexpected-audience"),
        user_id=user.id,
        membership_id=membership.id,
        company_id=company.id,
        session_id=tokens.context.auth_session.id,
        role=membership.role.value,
        now=utc_now(),
    )
    with pytest.raises(InvalidTokenError):
        service.authenticate_access_token(access_token=wrong_audience)


def test_refresh_rotation_reuse_revokes_session_family(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    service, _, tokens = create_owner_session(db_session, tenant_records)
    old_refresh = tokens.refresh_token
    rotated = service.refresh(refresh_token=old_refresh)
    session = db_session.get(AuthSession, tokens.context.auth_session.id)
    assert session is not None
    assert session.previous_refresh_token_hash is not None
    assert old_refresh not in session.refresh_token_hash
    assert rotated.refresh_token != old_refresh

    with pytest.raises(RefreshTokenReuseError):
        service.refresh(refresh_token=old_refresh)
    assert session.revoked_at is not None
    with pytest.raises(AuthenticationError):
        service.refresh(refresh_token=rotated.refresh_token)

    audit_rows = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "AUTH_REFRESH_REUSE_DETECTED")
    ).all()
    assert audit_rows
    assert old_refresh not in str(audit_rows[-1].reason)
    assert old_refresh not in str(audit_rows[-1].new_values)


def test_logout_revokes_access_and_audits_without_tokens(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    service, _, tokens = create_owner_session(db_session, tenant_records)
    service.logout(tokens.context)
    with pytest.raises(InvalidTokenError):
        service.authenticate_access_token(access_token=tokens.access_token)
    audit = db_session.scalar(
        select(AuditLog)
        .where(AuditLog.action == "AUTH_SESSION_LOGOUT")
        .order_by(AuditLog.created_at.desc())
    )
    assert audit is not None
    assert tokens.access_token not in str(audit.new_values)
    assert tokens.refresh_token not in str(audit.new_values)


def test_rbac_roles_tenant_context_and_supervisor_site_access(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    service, _, owner_tokens = create_owner_session(db_session, tenant_records)
    owner_context = owner_tokens.context
    assert ensure_role(owner_context, MembershipRole.OWNER_ADMIN) is owner_context
    with pytest.raises(RoleViolationError):
        ensure_role(owner_context, MembershipRole.SUPERVISOR)

    supervisor = user_by_name(db_session, "Supervisor A")
    supervisor_membership = value(tenant_records, "supervisor_a", CompanyMembership)
    prepare_user(supervisor, db_session, "+919876543211")
    supervisor_service, supervisor_provider = new_service(db_session)
    challenge_id = supervisor_service.request_otp(phone=supervisor.phone_number)
    pre_session, _ = supervisor_service.verify_otp(
        challenge_id=challenge_id,
        otp=supervisor_provider.deliveries[challenge_id],
    )
    supervisor_tokens = supervisor_service.create_session(
        pre_session_token=pre_session,
        membership_id=supervisor_membership.id,
    )
    with pytest.raises(RoleViolationError):
        ensure_role(supervisor_tokens.context, MembershipRole.OWNER_ADMIN)
    site_a = value(tenant_records, "site_a", Site)
    site_b = value(tenant_records, "site_b", Site)
    grant_supervisor_site_access(
        db_session,
        company_id=supervisor_membership.company_id,
        supervisor_membership_id=supervisor_membership.id,
        site_id=site_a.id,
    )
    assert (
        ensure_supervisor_site_access(
            db_session,
            supervisor_tokens.context,
            site_id=site_a.id,
        )
        is supervisor_tokens.context
    )
    with pytest.raises(TenantConsistencyError):
        ensure_supervisor_site_access(db_session, supervisor_tokens.context, site_id=site_b.id)
    with pytest.raises(TenantConsistencyError):
        ensure_company(owner_context, site_b.company_id)

    driver = user_by_name(db_session, "Driver A")
    driver_membership = value(tenant_records, "driver_a", CompanyMembership)
    prepare_user(driver, db_session, "+919876543212")
    driver_service, driver_provider = new_service(db_session)
    driver_challenge_id = driver_service.request_otp(phone=driver.phone_number)
    driver_pre_session, _ = driver_service.verify_otp(
        challenge_id=driver_challenge_id,
        otp=driver_provider.deliveries[driver_challenge_id],
    )
    driver_tokens = driver_service.create_session(
        pre_session_token=driver_pre_session,
        membership_id=driver_membership.id,
    )
    assert ensure_role(driver_tokens.context, MembershipRole.DRIVER) is driver_tokens.context
    with pytest.raises(RoleViolationError):
        ensure_role(driver_tokens.context, MembershipRole.SUPERVISOR)
    with pytest.raises(RoleViolationError):
        ensure_role(driver_tokens.context, MembershipRole.OWNER_ADMIN)


def test_hostile_company_context_cannot_override_authenticated_membership(
    db_session: Session, tenant_records: dict[str, object]
) -> None:
    service, provider, _ = create_owner_session(db_session, tenant_records)
    owner = user_by_name(db_session, "Owner A")
    owner_membership = value(tenant_records, "owner_a", CompanyMembership)
    foreign_membership = value(tenant_records, "supervisor_b", CompanyMembership)
    challenge_id = service.request_otp(phone=owner.phone_number)
    pre_session, _ = service.verify_otp(
        challenge_id=challenge_id,
        otp=provider.deliveries[challenge_id],
    )
    with pytest.raises(MembershipSelectionError):
        service.create_session(pre_session_token=pre_session, membership_id=foreign_membership.id)
    assert owner_membership.company_id != foreign_membership.company_id
