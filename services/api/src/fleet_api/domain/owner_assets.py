from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from fleet_api.auth.service import AuthContext
from fleet_api.db.models import (
    Assignment,
    CompanyMembership,
    DutySession,
    FleetAsset,
    Site,
    User,
)
from fleet_api.domain.assets import (
    create_fleet_asset,
    normalize_asset_code,
    normalize_registration_number,
)
from fleet_api.domain.audit import write_audit_log
from fleet_api.domain.enums import (
    AssetOwnershipType,
    DutySessionStatus,
    FleetAssetStatus,
    FleetAssetType,
)
from fleet_api.domain.errors import ConflictError, DomainError, NotFoundError


@dataclass(frozen=True)
class ActiveAssetAssignment:
    assignment_id: UUID
    site_id: UUID
    site_name: str
    driver_membership_id: UUID
    driver_name: str


@dataclass(frozen=True)
class OwnerAssetView:
    asset: FleetAsset
    active_assignment: ActiveAssetAssignment | None


def _clean_optional(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


class OwnerAssetService:
    """Owner-only, tenant-scoped lifecycle management for fleet assets."""

    def __init__(
        self,
        session: Session,
        context: AuthContext,
        *,
        request_id: str | None = None,
    ) -> None:
        self.session = session
        self.company_id = context.company.id
        self.actor_membership_id = context.membership.id
        self.request_id = request_id

    def _audit(
        self,
        *,
        action: str,
        asset: FleetAsset,
        old_values: Mapping[str, object] | None = None,
        new_values: Mapping[str, object] | None = None,
    ) -> None:
        write_audit_log(
            self.session,
            company_id=self.company_id,
            actor_membership_id=self.actor_membership_id,
            action=action,
            entity_type="FLEET_ASSET",
            entity_id=asset.id,
            old_values=dict(old_values) if old_values is not None else None,
            new_values=dict(new_values) if new_values is not None else None,
            request_id=self.request_id,
        )

    @staticmethod
    def _values(asset: FleetAsset) -> dict[str, object]:
        return {
            "asset_code": asset.asset_code,
            "asset_type": asset.asset_type.value,
            "ownership_type": asset.ownership_type.value,
            "registration_number": asset.registration_number,
            "short_name": asset.short_name,
            "manufacturer": asset.manufacturer,
            "model": asset.model,
            "status": asset.status.value,
            "rental_party_name": asset.rental_party_name,
            "rental_start_date": (
                asset.rental_start_date.isoformat() if asset.rental_start_date else None
            ),
            "rental_end_date": (
                asset.rental_end_date.isoformat() if asset.rental_end_date else None
            ),
        }

    def _view_query(
        self, *, now: datetime
    ) -> Select[tuple[FleetAsset, Assignment, Site, CompanyMembership, User]]:
        driver_membership = aliased(CompanyMembership)
        driver_user = aliased(User)
        return (
            select(FleetAsset, Assignment, Site, driver_membership, driver_user)
            .outerjoin(
                Assignment,
                and_(
                    Assignment.company_id == FleetAsset.company_id,
                    Assignment.asset_id == FleetAsset.id,
                    Assignment.starts_at <= now,
                    or_(Assignment.ends_at.is_(None), Assignment.ends_at > now),
                ),
            )
            .outerjoin(
                Site,
                and_(
                    Site.company_id == Assignment.company_id,
                    Site.id == Assignment.site_id,
                ),
            )
            .outerjoin(
                driver_membership,
                and_(
                    driver_membership.company_id == Assignment.company_id,
                    driver_membership.id == Assignment.driver_membership_id,
                ),
            )
            .outerjoin(driver_user, driver_user.id == driver_membership.user_id)
        )

    @staticmethod
    def _to_view(row: tuple[object, ...]) -> OwnerAssetView:
        asset, assignment, site, membership, user = row
        assert isinstance(asset, FleetAsset)
        active_assignment = None
        if isinstance(assignment, Assignment):
            assert isinstance(site, Site)
            assert isinstance(membership, CompanyMembership)
            assert isinstance(user, User)
            active_assignment = ActiveAssetAssignment(
                assignment_id=assignment.id,
                site_id=site.id,
                site_name=site.name,
                driver_membership_id=membership.id,
                driver_name=membership.display_name or user.display_name,
            )
        return OwnerAssetView(asset=asset, active_assignment=active_assignment)

    def list_assets(
        self,
        *,
        status: FleetAssetStatus | None = None,
        ownership_type: AssetOwnershipType | None = None,
        asset_type: FleetAssetType | None = None,
    ) -> list[OwnerAssetView]:
        query = self._view_query(now=datetime.now(UTC)).where(
            FleetAsset.company_id == self.company_id
        )
        if status is not None:
            query = query.where(FleetAsset.status == status)
        if ownership_type is not None:
            query = query.where(FleetAsset.ownership_type == ownership_type)
        if asset_type is not None:
            query = query.where(FleetAsset.asset_type == asset_type)
        query = query.order_by(
            FleetAsset.status,
            FleetAsset.asset_code,
            FleetAsset.id,
        )
        return [self._to_view(row._tuple()) for row in self.session.execute(query).all()]

    def get_asset(self, asset_id: UUID) -> OwnerAssetView:
        row = self.session.execute(
            self._view_query(now=datetime.now(UTC)).where(
                FleetAsset.id == asset_id,
                FleetAsset.company_id == self.company_id,
                FleetAsset.asset_type == FleetAssetType.TIPPER,
            )
        ).first()
        if row is None:
            raise NotFoundError("asset was not found")
        return self._to_view(row._tuple())

    def _ensure_unique(
        self,
        *,
        asset_code: str,
        registration_number: str,
        exclude_asset_id: UUID | None = None,
    ) -> None:
        code_query = select(FleetAsset.id).where(
            FleetAsset.company_id == self.company_id,
            FleetAsset.asset_code == asset_code,
        )
        registration_query = select(FleetAsset.id).where(
            FleetAsset.company_id == self.company_id,
            FleetAsset.registration_number == registration_number,
        )
        if exclude_asset_id is not None:
            code_query = code_query.where(FleetAsset.id != exclude_asset_id)
            registration_query = registration_query.where(
                FleetAsset.id != exclude_asset_id
            )
        if self.session.scalar(code_query) is not None:
            raise ConflictError("asset code is already used by this company")
        if self.session.scalar(registration_query) is not None:
            raise ConflictError("registration number is already used by this company")

    @staticmethod
    def _validate_rental(
        *,
        ownership_type: AssetOwnershipType,
        rental_party_name: str | None,
        rental_start_date: date | None,
        rental_end_date: date | None,
    ) -> None:
        if ownership_type == AssetOwnershipType.RENTED and rental_party_name is None:
            raise DomainError("Rental party is required for a rented asset.")
        if ownership_type == AssetOwnershipType.OWNED and any(
            value is not None
            for value in (rental_party_name, rental_start_date, rental_end_date)
        ):
            raise DomainError("Owned assets cannot contain rental details.")
        if (
            rental_start_date is not None
            and rental_end_date is not None
            and rental_end_date < rental_start_date
        ):
            raise DomainError("Rental end date cannot be before rental start date.")

    def create_asset(
        self,
        *,
        asset_type: FleetAssetType,
        ownership_type: AssetOwnershipType,
        asset_code: str,
        registration_number: str,
        short_name: str | None,
        manufacturer: str | None,
        model: str | None,
        rental_party_name: str | None,
        rental_start_date: date | None,
        rental_end_date: date | None,
    ) -> OwnerAssetView:
        if asset_type != FleetAssetType.TIPPER:
            raise DomainError("Only tippers can be created in this phase.")
        normalized_code = normalize_asset_code(asset_code)
        normalized_registration = normalize_registration_number(registration_number)
        clean_rental_party = _clean_optional(rental_party_name)
        self._validate_rental(
            ownership_type=ownership_type,
            rental_party_name=clean_rental_party,
            rental_start_date=rental_start_date,
            rental_end_date=rental_end_date,
        )
        self._ensure_unique(
            asset_code=normalized_code,
            registration_number=normalized_registration,
        )
        try:
            asset = create_fleet_asset(
                self.session,
                company_id=self.company_id,
                asset_type=asset_type,
                ownership_type=ownership_type,
                asset_code=normalized_code,
                registration_number=normalized_registration,
                short_name=short_name,
                manufacturer=manufacturer,
                model=model,
                rental_party_name=clean_rental_party,
                rental_start_date=rental_start_date,
                rental_end_date=rental_end_date,
            )
        except DomainError as exc:
            if "already used" in str(exc):
                raise ConflictError(
                    "asset code or registration number is already used"
                ) from exc
            raise
        self._audit(
            action="OWNER_ASSET_CREATED",
            asset=asset,
            new_values=self._values(asset),
        )
        return OwnerAssetView(asset=asset, active_assignment=None)

    def update_asset(
        self,
        asset_id: UUID,
        *,
        asset_code: str | None,
        registration_number: str | None,
        short_name: str | None,
        manufacturer: str | None,
        model: str | None,
        ownership_type: AssetOwnershipType | None,
        rental_party_name: str | None,
        rental_start_date: date | None,
        rental_end_date: date | None,
        fields_set: set[str],
    ) -> OwnerAssetView:
        view = self.get_asset(asset_id)
        asset = view.asset
        old_values = self._values(asset)

        if "asset_code" in fields_set:
            if asset_code is None:
                raise DomainError("Asset code is required.")
            asset.asset_code = normalize_asset_code(asset_code)
        if "registration_number" in fields_set:
            if registration_number is None:
                raise DomainError("Registration number is required for a tipper.")
            asset.registration_number = normalize_registration_number(
                registration_number
            )
        if "short_name" in fields_set:
            asset.short_name = _clean_optional(short_name)
        if "manufacturer" in fields_set:
            asset.manufacturer = _clean_optional(manufacturer)
        if "model" in fields_set:
            asset.model = _clean_optional(model)
        if "ownership_type" in fields_set:
            if ownership_type is None:
                raise DomainError("Ownership is required.")
            asset.ownership_type = ownership_type

        if asset.ownership_type == AssetOwnershipType.OWNED:
            if "ownership_type" in fields_set:
                asset.rental_party_name = None
                asset.rental_start_date = None
                asset.rental_end_date = None
            elif any(
                field in fields_set and value is not None
                for field, value in (
                    ("rental_party_name", rental_party_name),
                    ("rental_start_date", rental_start_date),
                    ("rental_end_date", rental_end_date),
                )
            ):
                raise DomainError("Owned assets cannot contain rental details.")
        else:
            if "rental_party_name" in fields_set:
                asset.rental_party_name = _clean_optional(rental_party_name)
            if "rental_start_date" in fields_set:
                asset.rental_start_date = rental_start_date
            if "rental_end_date" in fields_set:
                asset.rental_end_date = rental_end_date

        self._validate_rental(
            ownership_type=asset.ownership_type,
            rental_party_name=asset.rental_party_name,
            rental_start_date=asset.rental_start_date,
            rental_end_date=asset.rental_end_date,
        )
        assert asset.registration_number is not None
        self._ensure_unique(
            asset_code=asset.asset_code,
            registration_number=asset.registration_number,
            exclude_asset_id=asset.id,
        )
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise ConflictError("asset code or registration number is already used") from exc
        self._audit(
            action="OWNER_ASSET_UPDATED",
            asset=asset,
            old_values=old_values,
            new_values=self._values(asset),
        )
        return OwnerAssetView(asset=asset, active_assignment=view.active_assignment)

    def deactivate_asset(self, asset_id: UUID) -> OwnerAssetView:
        view = self.get_asset(asset_id)
        asset = view.asset
        if asset.status == FleetAssetStatus.INACTIVE:
            return view
        if view.active_assignment is not None:
            raise ConflictError(
                "Asset cannot be deactivated while it has an active assignment."
            )
        active_duty = self.session.scalar(
            select(DutySession.id).where(
                DutySession.company_id == self.company_id,
                DutySession.asset_id == asset.id,
                DutySession.status == DutySessionStatus.ACTIVE,
            )
        )
        if active_duty is not None:
            raise ConflictError(
                "Asset cannot be deactivated while it has an active duty session."
            )
        old_values = self._values(asset)
        asset.status = FleetAssetStatus.INACTIVE
        self.session.flush()
        self._audit(
            action="OWNER_ASSET_DEACTIVATED",
            asset=asset,
            old_values=old_values,
            new_values=self._values(asset),
        )
        return OwnerAssetView(asset=asset, active_assignment=None)

    def reactivate_asset(self, asset_id: UUID) -> OwnerAssetView:
        view = self.get_asset(asset_id)
        asset = view.asset
        if asset.status == FleetAssetStatus.ACTIVE:
            return view
        old_values = self._values(asset)
        asset.status = FleetAssetStatus.ACTIVE
        self.session.flush()
        self._audit(
            action="OWNER_ASSET_REACTIVATED",
            asset=asset,
            old_values=old_values,
            new_values=self._values(asset),
        )
        return OwnerAssetView(asset=asset, active_assignment=None)
