from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from hashlib import pbkdf2_hmac, sha256
from hmac import compare_digest
from secrets import randbelow, token_bytes
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from fleet_api.auth.phone import normalize_phone
from fleet_api.auth.providers import OtpProvider
from fleet_api.auth.tokens import (
    decode_access_token,
    decode_pre_session,
    generate_refresh_token,
    hash_refresh_token,
    issue_access_token,
    issue_pre_session,
)
from fleet_api.core.config import Settings
from fleet_api.db.models import (
    AuthSession,
    Company,
    CompanyMembership,
    OtpChallenge,
    User,
)
from fleet_api.db.models.common import utc_now
from fleet_api.domain.audit import write_audit_log
from fleet_api.domain.enums import (
    CompanyStatus,
    MembershipRole,
    MembershipStatus,
    OtpChallengeStatus,
    UserStatus,
)
from fleet_api.domain.errors import (
    AuthenticationError,
    InvalidOtpError,
    InvalidTokenError,
    MembershipSelectionError,
    RefreshTokenReuseError,
    RoleViolationError,
    TenantConsistencyError,
)


@dataclass(frozen=True)
class AuthContext:
    auth_session: AuthSession
    user: User
    membership: CompanyMembership
    company: Company


@dataclass(frozen=True)
class SessionTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    context: AuthContext


def _hash_metadata(value: str | None) -> str | None:
    if not value:
        return None
    return sha256(value.encode("utf-8")).hexdigest()


def _hash_otp(otp: str, salt_hex: str) -> str:
    return pbkdf2_hmac(
        "sha256",
        otp.encode("utf-8"),
        bytes.fromhex(salt_hex),
        120_000,
    ).hex()


def _new_otp() -> str:
    return f"{randbelow(1_000_000):06d}"


def _active_context_for_membership(
    session: Session,
    *,
    user_id: UUID,
    membership_id: UUID,
    company_id: UUID,
) -> tuple[User, CompanyMembership, Company] | None:
    statement = (
        select(User, CompanyMembership, Company)
        .join(CompanyMembership, CompanyMembership.user_id == User.id)
        .join(Company, Company.id == CompanyMembership.company_id)
        .where(
            User.id == user_id,
            User.status == UserStatus.ACTIVE,
            CompanyMembership.id == membership_id,
            CompanyMembership.company_id == company_id,
            CompanyMembership.status == MembershipStatus.ACTIVE,
            Company.status == CompanyStatus.ACTIVE,
        )
    )
    row = session.execute(statement).first()
    return row._tuple() if row is not None else None


class AuthService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        otp_provider: OtpProvider,
        *,
        request_id: str | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.otp_provider = otp_provider
        self.request_id = request_id

    def request_otp(
        self,
        *,
        phone: str,
        request_ip: str | None = None,
        user_agent: str | None = None,
    ) -> UUID:
        normalized_phone = normalize_phone(
            phone,
            default_region=self.settings.phone_default_region,
        )
        now = utc_now()
        latest = self.session.scalar(
            select(OtpChallenge)
            .where(
                OtpChallenge.phone_number == normalized_phone,
                OtpChallenge.status == OtpChallengeStatus.ACTIVE,
            )
            .order_by(OtpChallenge.created_at.desc())
            .limit(1)
        )
        if latest is not None:
            if latest.expires_at <= now:
                latest.status = OtpChallengeStatus.EXPIRED
            elif latest.next_allowed_at > now:
                return latest.id
            else:
                latest.status = OtpChallengeStatus.CANCELLED

        otp = _new_otp()
        salt = token_bytes(16).hex()
        challenge = OtpChallenge(
            phone_number=normalized_phone,
            otp_hash=_hash_otp(otp, salt),
            otp_salt=salt,
            status=OtpChallengeStatus.ACTIVE,
            expires_at=now + timedelta(seconds=self.settings.otp_ttl_seconds),
            attempt_count=0,
            max_attempts=self.settings.otp_max_attempts,
            next_allowed_at=now + timedelta(seconds=self.settings.otp_resend_cooldown_seconds),
            request_ip_hash=_hash_metadata(request_ip),
            request_user_agent_hash=_hash_metadata(user_agent),
            provider_name=type(self.otp_provider).__name__,
        )
        self.session.add(challenge)
        self.session.flush()
        self.otp_provider.deliver(
            phone_number=normalized_phone,
            otp=otp,
            challenge_id=challenge.id,
        )
        return challenge.id

    def verify_otp(self, *, challenge_id: UUID, otp: str) -> tuple[str, int]:
        challenge = self.session.scalar(
            select(OtpChallenge).where(OtpChallenge.id == challenge_id).with_for_update()
        )
        if challenge is None:
            raise InvalidOtpError("OTP is invalid")

        now = utc_now()
        if challenge.status != OtpChallengeStatus.ACTIVE:
            raise InvalidOtpError("OTP is invalid")
        if challenge.expires_at <= now:
            challenge.status = OtpChallengeStatus.EXPIRED
            self.session.flush()
            raise InvalidOtpError("OTP is invalid")
        if challenge.attempt_count >= challenge.max_attempts:
            challenge.status = OtpChallengeStatus.EXHAUSTED
            self.session.flush()
            raise InvalidOtpError("OTP is invalid")

        challenge.attempt_count += 1
        expected_hash = _hash_otp(otp, challenge.otp_salt)
        if not compare_digest(expected_hash, challenge.otp_hash):
            if challenge.attempt_count >= challenge.max_attempts:
                challenge.status = OtpChallengeStatus.EXHAUSTED
            self.session.flush()
            raise InvalidOtpError("OTP is invalid")

        challenge.status = OtpChallengeStatus.CONSUMED
        challenge.consumed_at = now
        self.session.flush()
        user = self.session.scalar(select(User).where(User.phone_number == challenge.phone_number))
        pre_session = issue_pre_session(
            self.settings,
            user_id=user.id if user is not None else None,
            now=now,
        )
        return pre_session, self.settings.pre_session_ttl_seconds

    def list_memberships(
        self, *, pre_session_token: str
    ) -> list[tuple[UUID, UUID, str, MembershipRole]]:
        claims = decode_pre_session(pre_session_token, self.settings)
        if claims.user_id is None:
            return []
        statement = (
            select(CompanyMembership.id, Company.id, Company.name, CompanyMembership.role)
            .join(Company, Company.id == CompanyMembership.company_id)
            .where(
                CompanyMembership.user_id == claims.user_id,
                CompanyMembership.status == MembershipStatus.ACTIVE,
                Company.status == CompanyStatus.ACTIVE,
            )
            .order_by(Company.name, CompanyMembership.id)
        )
        return [row._tuple() for row in self.session.execute(statement).all()]

    def create_session(self, *, pre_session_token: str, membership_id: UUID) -> SessionTokens:
        claims = decode_pre_session(pre_session_token, self.settings)
        if claims.user_id is None:
            raise MembershipSelectionError("membership selection is not available")
        membership_row = self.session.scalar(
            select(CompanyMembership).where(CompanyMembership.id == membership_id)
        )
        if membership_row is None:
            raise MembershipSelectionError("membership selection is invalid")
        context_row = _active_context_for_membership(
            self.session,
            user_id=claims.user_id,
            membership_id=membership_id,
            company_id=membership_row.company_id,
        )
        if context_row is None:
            raise MembershipSelectionError("membership selection is invalid")
        user, membership, company = context_row
        now = utc_now()
        refresh_token = generate_refresh_token()
        auth_session = AuthSession(
            user_id=user.id,
            company_id=company.id,
            membership_id=membership.id,
            refresh_token_hash=hash_refresh_token(refresh_token),
            expires_at=now + timedelta(seconds=self.settings.refresh_token_ttl_seconds),
            last_used_at=now,
        )
        self.session.add(auth_session)
        self.session.flush()
        write_audit_log(
            self.session,
            company_id=company.id,
            actor_membership_id=membership.id,
            action="AUTH_SESSION_CREATED",
            entity_type="AUTH_SESSION",
            entity_id=auth_session.id,
            new_values={"membership_id": str(membership.id), "role": membership.role.value},
            request_id=self.request_id,
        )
        access_token = issue_access_token(
            self.settings,
            user_id=user.id,
            membership_id=membership.id,
            company_id=company.id,
            session_id=auth_session.id,
            role=membership.role.value,
            now=now,
        )
        context = AuthContext(auth_session, user, membership, company)
        return SessionTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.settings.access_token_ttl_seconds,
            context=context,
        )

    def authenticate_access_token(self, *, access_token: str) -> AuthContext:
        claims = decode_access_token(access_token, self.settings)
        auth_session = self.session.scalar(
            select(AuthSession).where(AuthSession.id == claims.session_id)
        )
        if auth_session is None or auth_session.revoked_at is not None:
            raise InvalidTokenError("session is not active")
        if auth_session.expires_at <= utc_now():
            raise InvalidTokenError("session is expired")
        context_row = _active_context_for_membership(
            self.session,
            user_id=claims.user_id,
            membership_id=claims.membership_id,
            company_id=claims.company_id,
        )
        if context_row is None:
            raise InvalidTokenError("identity is no longer active")
        user, membership, company = context_row
        if (
            auth_session.user_id != user.id
            or auth_session.membership_id != membership.id
            or auth_session.company_id != company.id
            or claims.role != membership.role.value
        ):
            raise InvalidTokenError("token context is stale")
        return AuthContext(auth_session, user, membership, company)

    def refresh(self, *, refresh_token: str) -> SessionTokens:
        token_hash = hash_refresh_token(refresh_token)
        auth_session = self.session.scalar(
            select(AuthSession)
            .where(
                or_(
                    AuthSession.refresh_token_hash == token_hash,
                    AuthSession.previous_refresh_token_hash == token_hash,
                )
            )
            .with_for_update()
        )
        if auth_session is None:
            raise AuthenticationError("refresh token is invalid")
        if auth_session.previous_refresh_token_hash == token_hash:
            now = utc_now()
            family_sessions = self.session.scalars(
                select(AuthSession).where(AuthSession.family_id == auth_session.family_id)
            ).all()
            for family_session in family_sessions:
                family_session.revoked_at = now
                family_session.revocation_reason = "refresh_token_reuse_detected"
            write_audit_log(
                self.session,
                company_id=auth_session.company_id,
                actor_membership_id=auth_session.membership_id,
                action="AUTH_REFRESH_REUSE_DETECTED",
                entity_type="AUTH_SESSION",
                entity_id=auth_session.id,
                reason="rotated refresh token was presented again",
                request_id=self.request_id,
            )
            self.session.flush()
            raise RefreshTokenReuseError("refresh token reuse detected")
        if auth_session.revoked_at is not None or auth_session.expires_at <= utc_now():
            raise AuthenticationError("refresh token is invalid")

        context_row = _active_context_for_membership(
            self.session,
            user_id=auth_session.user_id,
            membership_id=auth_session.membership_id,
            company_id=auth_session.company_id,
        )
        if context_row is None:
            raise AuthenticationError("session identity is no longer active")
        user, membership, company = context_row
        now = utc_now()
        new_refresh_token = generate_refresh_token()
        auth_session.previous_refresh_token_hash = auth_session.refresh_token_hash
        auth_session.refresh_token_hash = hash_refresh_token(new_refresh_token)
        auth_session.last_rotated_at = now
        auth_session.last_used_at = now
        self.session.flush()
        access_token = issue_access_token(
            self.settings,
            user_id=user.id,
            membership_id=membership.id,
            company_id=company.id,
            session_id=auth_session.id,
            role=membership.role.value,
            now=now,
        )
        return SessionTokens(
            access_token=access_token,
            refresh_token=new_refresh_token,
            expires_in=self.settings.access_token_ttl_seconds,
            context=AuthContext(auth_session, user, membership, company),
        )

    def logout(self, context: AuthContext) -> None:
        if context.auth_session.revoked_at is None:
            context.auth_session.revoked_at = utc_now()
            context.auth_session.revocation_reason = "logout"
            write_audit_log(
                self.session,
                company_id=context.company.id,
                actor_membership_id=context.membership.id,
                action="AUTH_SESSION_LOGOUT",
                entity_type="AUTH_SESSION",
                entity_id=context.auth_session.id,
                request_id=self.request_id,
            )
            self.session.flush()


def ensure_role(context: AuthContext, *allowed_roles: MembershipRole) -> AuthContext:
    if context.membership.role not in allowed_roles:
        raise RoleViolationError("membership role is not allowed")
    return context


def ensure_company(context: AuthContext, company_id: UUID) -> AuthContext:
    if context.company.id != company_id:
        raise TenantConsistencyError("requested company is outside the authenticated tenant")
    return context


def ensure_supervisor_site_access(
    session: Session,
    context: AuthContext,
    *,
    site_id: UUID,
) -> AuthContext:
    ensure_role(context, MembershipRole.SUPERVISOR)
    from fleet_api.db.models import SupervisorSiteAccess

    access = session.scalar(
        select(SupervisorSiteAccess).where(
            SupervisorSiteAccess.company_id == context.company.id,
            SupervisorSiteAccess.supervisor_membership_id == context.membership.id,
            SupervisorSiteAccess.site_id == site_id,
        )
    )
    if access is None:
        raise TenantConsistencyError("supervisor is not authorized for this site")
    return context
