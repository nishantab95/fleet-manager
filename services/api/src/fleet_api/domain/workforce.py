from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from fleet_api.auth.service import AuthContext, ensure_role
from fleet_api.db.models import (
    CompanyMembership,
    CompensationProfile,
    DutySession,
    PayrollAdjustment,
    PayrollLine,
    PayrollPeriod,
    User,
)
from fleet_api.domain.audit import write_audit_log
from fleet_api.domain.enums import (
    AttendanceCalculationState,
    AttendanceConfidence,
    MembershipRole,
    PayBasis,
    PayrollPeriodStatus,
)
from fleet_api.domain.errors import ConflictError, DomainError, NotFoundError

MONEY = Decimal("0.01")


@dataclass(frozen=True)
class AttendanceDay:
    membership_id: UUID
    display_name: str
    operational_date: date
    duty_minutes: int
    overtime_minutes: int
    state: AttendanceCalculationState
    location_confidence: AttendanceConfidence


def _money(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise DomainError("pay amount must be finite")
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def union_interval_minutes(
    intervals: list[tuple[datetime, datetime]],
) -> tuple[int, bool]:
    """Return union minutes and whether any intervals overlap."""

    if not intervals:
        return 0, False
    ordered = sorted(intervals)
    current_start, current_end = ordered[0]
    total_seconds = 0.0
    overlap = False
    for start, end in ordered[1:]:
        if start < current_end:
            overlap = True
            if end > current_end:
                current_end = end
            continue
        total_seconds += (current_end - current_start).total_seconds()
        current_start, current_end = start, end
    total_seconds += (current_end - current_start).total_seconds()
    return max(0, int(total_seconds // 60)), overlap


class WorkforceService:
    """Owner-only compensation, attendance calculation, and frozen payroll service."""

    def __init__(
        self,
        session: Session,
        context: AuthContext,
        *,
        request_id: str | None = None,
    ) -> None:
        ensure_role(context, MembershipRole.OWNER_ADMIN)
        self.session = session
        self.company_id = context.company.id
        self.actor_id = context.membership.id
        self.request_id = request_id

    def _driver(self, membership_id: UUID) -> tuple[CompanyMembership, User]:
        row = self.session.execute(
            select(CompanyMembership, User)
            .join(User, User.id == CompanyMembership.user_id)
            .where(
                CompanyMembership.company_id == self.company_id,
                CompanyMembership.id == membership_id,
                CompanyMembership.role == MembershipRole.DRIVER,
            )
        ).first()
        if row is None:
            raise NotFoundError("driver membership not found")
        return row[0], row[1]

    def create_compensation_profile(
        self,
        *,
        membership_id: UUID,
        pay_basis: PayBasis,
        base_amount: Decimal,
        effective_from: date,
        effective_to: date | None,
        standard_duty_minutes: int,
        overtime_rate_per_hour: Decimal,
        notes: str | None,
    ) -> CompensationProfile:
        self._driver(membership_id)
        if effective_to is not None and effective_to < effective_from:
            raise DomainError("effective_to cannot precede effective_from")
        if standard_duty_minutes < 1 or standard_duty_minutes > 1440:
            raise DomainError("standard_duty_minutes must be between 1 and 1440")
        base_amount = _money(base_amount)
        overtime_rate_per_hour = _money(overtime_rate_per_hour)
        if base_amount < 0 or overtime_rate_per_hour < 0:
            raise DomainError("compensation values cannot be negative")
        overlap = self.session.scalar(
            select(CompensationProfile.id).where(
                CompensationProfile.company_id == self.company_id,
                CompensationProfile.membership_id == membership_id,
                CompensationProfile.effective_from <= (effective_to or date.max),
                or_(
                    CompensationProfile.effective_to.is_(None),
                    CompensationProfile.effective_to >= effective_from,
                ),
            )
        )
        if overlap is not None:
            raise ConflictError("compensation profile dates overlap")
        profile = CompensationProfile(
            company_id=self.company_id,
            membership_id=membership_id,
            pay_basis=pay_basis,
            base_amount=base_amount,
            effective_from=effective_from,
            effective_to=effective_to,
            standard_duty_minutes=standard_duty_minutes,
            overtime_rate_per_hour=overtime_rate_per_hour,
            notes=notes.strip() if notes and notes.strip() else None,
            created_by=self.actor_id,
        )
        self.session.add(profile)
        self.session.flush()
        self._audit(
            "COMPENSATION_PROFILE_CREATED",
            "COMPENSATION_PROFILE",
            profile.id,
            {"membership_id": str(membership_id), "pay_basis": pay_basis.value},
        )
        return profile

    def list_compensation_profiles(
        self, membership_id: UUID | None = None
    ) -> list[CompensationProfile]:
        query = select(CompensationProfile).where(CompensationProfile.company_id == self.company_id)
        if membership_id is not None:
            self._driver(membership_id)
            query = query.where(CompensationProfile.membership_id == membership_id)
        return list(
            self.session.scalars(
                query.order_by(
                    CompensationProfile.membership_id,
                    CompensationProfile.effective_from,
                )
            )
        )

    def _profile_on(self, membership_id: UUID, day: date) -> CompensationProfile | None:
        return self.session.scalar(
            select(CompensationProfile)
            .where(
                CompensationProfile.company_id == self.company_id,
                CompensationProfile.membership_id == membership_id,
                CompensationProfile.effective_from <= day,
                or_(
                    CompensationProfile.effective_to.is_(None),
                    CompensationProfile.effective_to >= day,
                ),
            )
            .order_by(CompensationProfile.effective_from.desc())
            .limit(1)
        )

    def attendance_day(self, membership_id: UUID, day: date) -> AttendanceDay:
        membership, user = self._driver(membership_id)
        sessions = list(
            self.session.scalars(
                select(DutySession).where(
                    DutySession.company_id == self.company_id,
                    DutySession.driver_membership_id == membership_id,
                    DutySession.operational_date == day,
                )
            )
        )
        has_open = any(item.ended_at is None for item in sessions)
        intervals = [
            (item.started_at, item.ended_at)
            for item in sessions
            if item.ended_at is not None and item.ended_at >= item.started_at
        ]
        duty_minutes, overlap = union_interval_minutes(intervals)
        if has_open:
            state = AttendanceCalculationState.OPEN_SESSION
        elif overlap:
            state = AttendanceCalculationState.OVERLAP_EXCEPTION
        elif not sessions:
            state = AttendanceCalculationState.MISSING_DATA
        else:
            state = AttendanceCalculationState.COMPLETE
        profile = self._profile_on(membership_id, day)
        overtime = max(
            0,
            duty_minutes - (profile.standard_duty_minutes if profile is not None else 1440),
        )
        return AttendanceDay(
            membership_id,
            membership.display_name or user.display_name,
            day,
            duty_minutes,
            overtime,
            state,
            AttendanceConfidence.UNKNOWN,
        )

    def attendance(self, starts_on: date, ends_on: date) -> list[AttendanceDay]:
        if ends_on < starts_on or (ends_on - starts_on).days > 366:
            raise DomainError("attendance date range is invalid")
        memberships = self.session.scalars(
            select(CompanyMembership.id).where(
                CompanyMembership.company_id == self.company_id,
                CompanyMembership.role == MembershipRole.DRIVER,
            )
        ).all()
        result: list[AttendanceDay] = []
        current = starts_on
        while current <= ends_on:
            result.extend(self.attendance_day(item, current) for item in memberships)
            current += timedelta(days=1)
        return result

    def _period(self, period_id: UUID, *, lock: bool = False) -> PayrollPeriod:
        query = select(PayrollPeriod).where(
            PayrollPeriod.company_id == self.company_id, PayrollPeriod.id == period_id
        )
        if lock:
            query = query.with_for_update()
        period = self.session.scalar(query)
        if period is None:
            raise NotFoundError("payroll period not found")
        return period

    def create_payroll_period(self, starts_on: date, ends_on: date) -> PayrollPeriod:
        if ends_on < starts_on or (ends_on - starts_on).days > 366:
            raise DomainError("payroll period date range is invalid")
        existing = self.session.scalar(
            select(PayrollPeriod.id).where(
                PayrollPeriod.company_id == self.company_id,
                PayrollPeriod.starts_on == starts_on,
                PayrollPeriod.ends_on == ends_on,
            )
        )
        if existing is not None:
            raise ConflictError("payroll period already exists")
        period = PayrollPeriod(
            company_id=self.company_id,
            starts_on=starts_on,
            ends_on=ends_on,
            status=PayrollPeriodStatus.DRAFT,
            created_by=self.actor_id,
        )
        self.session.add(period)
        self.session.flush()
        self._calculate_lines(period)
        self._audit(
            "PAYROLL_PERIOD_CREATED",
            "PAYROLL_PERIOD",
            period.id,
            {"starts_on": starts_on.isoformat(), "ends_on": ends_on.isoformat()},
        )
        return period

    def _calculate_lines(self, period: PayrollPeriod) -> None:
        membership_ids = list(
            self.session.scalars(
                select(CompensationProfile.membership_id)
                .where(
                    CompensationProfile.company_id == self.company_id,
                    CompensationProfile.effective_from <= period.ends_on,
                    or_(
                        CompensationProfile.effective_to.is_(None),
                        CompensationProfile.effective_to >= period.starts_on,
                    ),
                )
                .distinct()
            )
        )
        for membership_id in membership_ids:
            membership, user = self._driver(membership_id)
            base_pay = Decimal("0")
            overtime_amount = Decimal("0")
            duty_minutes = 0
            overtime_minutes = 0
            states: set[AttendanceCalculationState] = set()
            snapshots: list[dict[str, object]] = []
            bases: set[PayBasis] = set()
            current = period.starts_on
            last_profile: CompensationProfile | None = None
            while current <= period.ends_on:
                profile = self._profile_on(membership_id, current)
                attendance = self.attendance_day(membership_id, current)
                states.add(attendance.state)
                duty_minutes += attendance.duty_minutes
                overtime_minutes += attendance.overtime_minutes
                if profile is not None:
                    last_profile = profile
                    bases.add(profile.pay_basis)
                    if profile.pay_basis == PayBasis.MONTHLY:
                        base_pay += profile.base_amount / Decimal(
                            monthrange(current.year, current.month)[1]
                        )
                    elif profile.pay_basis == PayBasis.DAILY and attendance.duty_minutes > 0:
                        base_pay += profile.base_amount
                    elif profile.pay_basis == PayBasis.HOURLY:
                        base_pay += (
                            profile.base_amount * Decimal(attendance.duty_minutes) / Decimal(60)
                        )
                    overtime_amount += (
                        profile.overtime_rate_per_hour
                        * Decimal(attendance.overtime_minutes)
                        / Decimal(60)
                    )
                snapshots.append(
                    {
                        "date": current.isoformat(),
                        "duty_minutes": attendance.duty_minutes,
                        "overtime_minutes": attendance.overtime_minutes,
                        "state": attendance.state.value,
                        "profile_id": str(profile.id) if profile else None,
                    }
                )
                current += timedelta(days=1)
            assert last_profile is not None
            if AttendanceCalculationState.OPEN_SESSION in states:
                calculation_state = AttendanceCalculationState.OPEN_SESSION
            elif AttendanceCalculationState.OVERLAP_EXCEPTION in states:
                calculation_state = AttendanceCalculationState.OVERLAP_EXCEPTION
            else:
                calculation_state = AttendanceCalculationState.COMPLETE
            line = PayrollLine(
                company_id=self.company_id,
                period_id=period.id,
                membership_id=membership_id,
                display_name_snapshot=membership.display_name or user.display_name,
                pay_basis_snapshot=(
                    next(iter(bases)) if len(bases) == 1 else last_profile.pay_basis
                ),
                base_pay=_money(base_pay),
                duty_minutes=duty_minutes,
                overtime_minutes=overtime_minutes,
                overtime_rate_per_hour=last_profile.overtime_rate_per_hour,
                overtime_amount=_money(overtime_amount),
                adjustment_amount=Decimal("0.00"),
                calculated_gross_pay=_money(base_pay + overtime_amount),
                calculation_state=calculation_state.value,
                calculation_snapshot={"days": snapshots, "profile_basis_count": len(bases)},
            )
            self.session.add(line)
        self.session.flush()

    def list_periods(self) -> list[PayrollPeriod]:
        return list(
            self.session.scalars(
                select(PayrollPeriod)
                .where(PayrollPeriod.company_id == self.company_id)
                .order_by(PayrollPeriod.starts_on.desc(), PayrollPeriod.id)
            )
        )

    def lines(self, period_id: UUID) -> list[PayrollLine]:
        self._period(period_id)
        return list(
            self.session.scalars(
                select(PayrollLine)
                .where(
                    PayrollLine.company_id == self.company_id,
                    PayrollLine.period_id == period_id,
                )
                .order_by(PayrollLine.display_name_snapshot, PayrollLine.id)
            )
        )

    def set_period_status(self, period_id: UUID, status: PayrollPeriodStatus) -> PayrollPeriod:
        period = self._period(period_id, lock=True)
        allowed = {
            PayrollPeriodStatus.DRAFT: PayrollPeriodStatus.REVIEWED,
            PayrollPeriodStatus.REVIEWED: PayrollPeriodStatus.FINALIZED,
        }
        if allowed.get(period.status) != status:
            raise ConflictError("invalid payroll status transition")
        now = datetime.now(UTC)
        if status == PayrollPeriodStatus.REVIEWED:
            period.reviewed_by = self.actor_id
            period.reviewed_at = now
        else:
            period.finalized_by = self.actor_id
            period.finalized_at = now
        period.status = status
        self.session.flush()
        self._audit(
            f"PAYROLL_PERIOD_{status.value}",
            "PAYROLL_PERIOD",
            period.id,
            {"status": status.value},
        )
        return period

    def add_adjustment(
        self, line_id: UUID, *, amount: Decimal, reason: str
    ) -> tuple[PayrollAdjustment, PayrollLine]:
        line = self.session.scalar(
            select(PayrollLine)
            .where(PayrollLine.company_id == self.company_id, PayrollLine.id == line_id)
            .with_for_update()
        )
        if line is None:
            raise NotFoundError("payroll line not found")
        period = self._period(line.period_id, lock=True)
        if period.status == PayrollPeriodStatus.FINALIZED:
            raise ConflictError("finalized payroll is immutable")
        clean_reason = reason.strip()
        amount = _money(amount)
        if amount == 0 or not clean_reason:
            raise DomainError("a non-zero amount and reason are required")
        adjustment = PayrollAdjustment(
            company_id=self.company_id,
            line_id=line.id,
            amount=amount,
            reason=clean_reason,
            created_by=self.actor_id,
        )
        self.session.add(adjustment)
        line.adjustment_amount = _money(line.adjustment_amount + amount)
        line.calculated_gross_pay = _money(
            line.base_pay + line.overtime_amount + line.adjustment_amount
        )
        self.session.flush()
        self._audit(
            "PAYROLL_ADJUSTMENT_CREATED",
            "PAYROLL_LINE",
            line.id,
            {"amount": str(amount), "reason": clean_reason},
        )
        return adjustment, line

    def _audit(
        self, action: str, entity_type: str, entity_id: UUID, values: dict[str, object]
    ) -> None:
        write_audit_log(
            self.session,
            company_id=self.company_id,
            actor_membership_id=self.actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            new_values=values,
            request_id=self.request_id,
        )
