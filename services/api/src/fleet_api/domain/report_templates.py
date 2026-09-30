from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fleet_api.auth.service import AuthContext
from fleet_api.db.models import ReportTemplate
from fleet_api.domain.audit import write_audit_log
from fleet_api.domain.errors import ConflictError, DomainError, NotFoundError

MANAGEMENT_DASHBOARD = "management_dashboard"
TIPPER_DAILY = "tipper_daily"
MACHINERY_DAILY = "machinery_daily"
TRIP_REGISTER = "trip_register"
METER_READINGS = "meter_readings"
DIESEL_REGISTER = "diesel_register"
DUTY_REGISTER = "duty_register"
EXCEPTIONS = "exceptions"

SHEET_IDS = (
    MANAGEMENT_DASHBOARD,
    TIPPER_DAILY,
    MACHINERY_DAILY,
    TRIP_REGISTER,
    METER_READINGS,
    DIESEL_REGISTER,
    DUTY_REGISTER,
    EXCEPTIONS,
)

MANAGEMENT_COLUMNS = (
    "asset",
    "asset_type",
    "site",
    "operator",
    "assignment_status",
    "duty_status",
    "trips",
    "distance_km",
    "machine_hours",
    "verified_diesel_l",
    "pending_status",
)
TIPPER_COLUMNS = (
    "asset",
    "site",
    "registration",
    "driver",
    "start_km",
    "end_km",
    "distance_km",
    "approved_trips",
    "diesel_l",
    "duty_start",
    "duty_end",
    "pending",
    "status",
)
MACHINERY_COLUMNS = (
    "asset",
    "asset_type",
    "site",
    "operator",
    "start_hmr",
    "end_hmr",
    "machine_hours",
    "diesel_l",
    "duty_start",
    "duty_end",
    "pending",
    "status",
)

STANDARD_MANAGEMENT_COLUMNS = (
    "asset",
    "asset_type",
    "site",
    "operator",
    "duty_status",
    "trips",
    "distance_km",
    "machine_hours",
    "verified_diesel_l",
    "pending_status",
)
STANDARD_TIPPER_COLUMNS = (
    "asset",
    "site",
    "registration",
    "driver",
    "start_km",
    "end_km",
    "distance_km",
    "approved_trips",
    "diesel_l",
    "status",
)
STANDARD_MACHINERY_COLUMNS = (
    "asset",
    "asset_type",
    "site",
    "operator",
    "start_hmr",
    "end_hmr",
    "machine_hours",
    "diesel_l",
    "status",
)


@dataclass(frozen=True)
class ReportTemplateConfig:
    id: UUID
    name: str
    included_sheets: tuple[str, ...]
    management_dashboard_columns: tuple[str, ...]
    tipper_daily_columns: tuple[str, ...]
    machinery_daily_columns: tuple[str, ...]


@dataclass(frozen=True)
class _BuiltinDefinition:
    key: str
    name: str
    included_sheets: tuple[str, ...]
    management_columns: tuple[str, ...]
    tipper_columns: tuple[str, ...] = STANDARD_TIPPER_COLUMNS
    machinery_columns: tuple[str, ...] = STANDARD_MACHINERY_COLUMNS


BUILTIN_DEFINITIONS = (
    _BuiltinDefinition(
        key="management_summary",
        name="Management Summary",
        included_sheets=(
            MANAGEMENT_DASHBOARD,
            TIPPER_DAILY,
            MACHINERY_DAILY,
            EXCEPTIONS,
        ),
        management_columns=STANDARD_MANAGEMENT_COLUMNS,
    ),
    _BuiltinDefinition(
        key="detailed_operations",
        name="Detailed Operations",
        included_sheets=SHEET_IDS,
        management_columns=STANDARD_MANAGEMENT_COLUMNS,
    ),
    _BuiltinDefinition(
        key="diesel_report",
        name="Diesel Report",
        included_sheets=(MANAGEMENT_DASHBOARD, DIESEL_REGISTER, EXCEPTIONS),
        management_columns=(
            "asset",
            "asset_type",
            "site",
            "operator",
            "verified_diesel_l",
            "pending_status",
        ),
    ),
)


def builtin_template_id(company_id: UUID, key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"fleet-manager:{company_id}:report-template:{key}")


def _clean_name(name: str) -> str:
    cleaned = " ".join(name.strip().split())
    if not cleaned:
        raise DomainError("Template name is required.")
    if len(cleaned) > 120:
        raise DomainError("Template name must be 120 characters or fewer.")
    return cleaned


def _canonical_selection(
    values: Iterable[str], catalog: tuple[str, ...], *, label: str
) -> list[str]:
    selected = list(values)
    if len(selected) != len(set(selected)):
        raise DomainError(f"{label} contains duplicate field IDs.")
    invalid = sorted(set(selected) - set(catalog))
    if invalid:
        raise DomainError(f"{label} contains invalid field IDs: {', '.join(invalid)}")
    if "asset" not in selected:
        raise DomainError(f"{label} must include the mandatory asset field.")
    return [field_id for field_id in catalog if field_id in selected]


def _canonical_sheets(values: Iterable[str]) -> list[str]:
    selected = list(values)
    if not selected:
        raise DomainError("At least one report sheet is required.")
    if len(selected) != len(set(selected)):
        raise DomainError("Included sheets contain duplicate IDs.")
    invalid = sorted(set(selected) - set(SHEET_IDS))
    if invalid:
        raise DomainError(f"Included sheets contain invalid IDs: {', '.join(invalid)}")
    return [sheet_id for sheet_id in SHEET_IDS if sheet_id in selected]


class ReportTemplateService:
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
        template: ReportTemplate,
        old_values: Mapping[str, object] | None = None,
        new_values: Mapping[str, object] | None = None,
    ) -> None:
        write_audit_log(
            self.session,
            company_id=self.company_id,
            actor_membership_id=self.actor_membership_id,
            action=action,
            entity_type="REPORT_TEMPLATE",
            entity_id=template.id,
            old_values=dict(old_values) if old_values is not None else None,
            new_values=dict(new_values) if new_values is not None else None,
            request_id=self.request_id,
        )

    @staticmethod
    def values(template: ReportTemplate) -> dict[str, object]:
        return {
            "name": template.name,
            "is_builtin": template.is_builtin,
            "is_default": template.is_default,
            "included_sheets": list(template.included_sheets),
            "management_dashboard_columns": list(template.management_dashboard_columns),
            "tipper_daily_columns": list(template.tipper_daily_columns),
            "machinery_daily_columns": list(template.machinery_daily_columns),
        }

    def ensure_builtins(self) -> list[ReportTemplate]:
        existing = {
            item.builtin_key: item
            for item in self.session.scalars(
                select(ReportTemplate).where(
                    ReportTemplate.company_id == self.company_id,
                    ReportTemplate.is_builtin.is_(True),
                )
            )
            if item.builtin_key is not None
        }
        has_default = (
            self.session.scalar(
                select(ReportTemplate.id)
                .where(
                    ReportTemplate.company_id == self.company_id,
                    ReportTemplate.is_default.is_(True),
                )
                .limit(1)
            )
            is not None
        )
        results: list[ReportTemplate] = []
        for definition in BUILTIN_DEFINITIONS:
            template = existing.get(definition.key)
            if template is None:
                template = ReportTemplate(
                    id=builtin_template_id(self.company_id, definition.key),
                    company_id=self.company_id,
                    name=definition.name,
                    builtin_key=definition.key,
                    is_builtin=True,
                    is_default=definition.key == "management_summary" and not has_default,
                    included_sheets=list(definition.included_sheets),
                    management_dashboard_columns=list(definition.management_columns),
                    tipper_daily_columns=list(definition.tipper_columns),
                    machinery_daily_columns=list(definition.machinery_columns),
                )
                self.session.add(template)
                if template.is_default:
                    has_default = True
            results.append(template)
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise ConflictError("Report templates changed; reload and try again.") from exc
        return results

    def list_templates(self) -> list[ReportTemplate]:
        self.ensure_builtins()
        templates = list(
            self.session.scalars(
                select(ReportTemplate).where(ReportTemplate.company_id == self.company_id)
            )
        )
        builtin_order = {
            definition.key: index for index, definition in enumerate(BUILTIN_DEFINITIONS)
        }
        return sorted(
            templates,
            key=lambda item: (
                0 if item.is_builtin else 1,
                builtin_order.get(item.builtin_key or "", 999),
                item.name.casefold(),
            ),
        )

    def get(self, template_id: UUID) -> ReportTemplate:
        self.ensure_builtins()
        template = self.session.scalar(
            select(ReportTemplate).where(
                ReportTemplate.id == template_id,
                ReportTemplate.company_id == self.company_id,
            )
        )
        if template is None:
            raise NotFoundError("Report template was not found.")
        return template

    def _configuration(
        self,
        *,
        included_sheets: Iterable[str],
        management_dashboard_columns: Iterable[str],
        tipper_daily_columns: Iterable[str],
        machinery_daily_columns: Iterable[str],
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        return (
            _canonical_sheets(included_sheets),
            _canonical_selection(
                management_dashboard_columns,
                MANAGEMENT_COLUMNS,
                label="Management Dashboard columns",
            ),
            _canonical_selection(
                tipper_daily_columns,
                TIPPER_COLUMNS,
                label="Tipper Daily columns",
            ),
            _canonical_selection(
                machinery_daily_columns,
                MACHINERY_COLUMNS,
                label="Machinery Daily columns",
            ),
        )

    def create(
        self,
        *,
        name: str,
        included_sheets: Iterable[str],
        management_dashboard_columns: Iterable[str],
        tipper_daily_columns: Iterable[str],
        machinery_daily_columns: Iterable[str],
    ) -> ReportTemplate:
        self.ensure_builtins()
        sheets, management, tipper, machinery = self._configuration(
            included_sheets=included_sheets,
            management_dashboard_columns=management_dashboard_columns,
            tipper_daily_columns=tipper_daily_columns,
            machinery_daily_columns=machinery_daily_columns,
        )
        template = ReportTemplate(
            company_id=self.company_id,
            name=_clean_name(name),
            builtin_key=None,
            is_builtin=False,
            is_default=False,
            included_sheets=sheets,
            management_dashboard_columns=management,
            tipper_daily_columns=tipper,
            machinery_daily_columns=machinery,
        )
        self.session.add(template)
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise ConflictError("A report template with this name already exists.") from exc
        self._audit(
            action="REPORT_TEMPLATE_CREATED",
            template=template,
            new_values=self.values(template),
        )
        return template

    def update(
        self,
        template_id: UUID,
        *,
        name: str | None,
        included_sheets: Iterable[str] | None,
        management_dashboard_columns: Iterable[str] | None,
        tipper_daily_columns: Iterable[str] | None,
        machinery_daily_columns: Iterable[str] | None,
        fields_set: set[str],
    ) -> ReportTemplate:
        template = self.get(template_id)
        if template.is_builtin:
            raise ConflictError("Built-in report templates cannot be edited.")
        nullable_fields = {
            "included_sheets": included_sheets,
            "management_dashboard_columns": management_dashboard_columns,
            "tipper_daily_columns": tipper_daily_columns,
            "machinery_daily_columns": machinery_daily_columns,
        }
        null_fields = sorted(
            field
            for field, value in nullable_fields.items()
            if field in fields_set and value is None
        )
        if null_fields:
            raise DomainError(f"{', '.join(null_fields)} cannot be null.")
        old_values = self.values(template)
        next_sheets = (
            included_sheets
            if "included_sheets" in fields_set and included_sheets is not None
            else template.included_sheets
        )
        next_management = (
            management_dashboard_columns
            if "management_dashboard_columns" in fields_set
            and management_dashboard_columns is not None
            else template.management_dashboard_columns
        )
        next_tipper = (
            tipper_daily_columns
            if "tipper_daily_columns" in fields_set and tipper_daily_columns is not None
            else template.tipper_daily_columns
        )
        next_machinery = (
            machinery_daily_columns
            if "machinery_daily_columns" in fields_set and machinery_daily_columns is not None
            else template.machinery_daily_columns
        )
        sheets, management, tipper, machinery = self._configuration(
            included_sheets=next_sheets,
            management_dashboard_columns=next_management,
            tipper_daily_columns=next_tipper,
            machinery_daily_columns=next_machinery,
        )
        if "name" in fields_set:
            if name is None:
                raise DomainError("Template name cannot be null.")
            template.name = _clean_name(name)
        template.included_sheets = sheets
        template.management_dashboard_columns = management
        template.tipper_daily_columns = tipper
        template.machinery_daily_columns = machinery
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise ConflictError("A report template with this name already exists.") from exc
        self._audit(
            action="REPORT_TEMPLATE_UPDATED",
            template=template,
            old_values=old_values,
            new_values=self.values(template),
        )
        return template

    def duplicate(self, template_id: UUID, *, name: str) -> ReportTemplate:
        source = self.get(template_id)
        return self.create(
            name=name,
            included_sheets=source.included_sheets,
            management_dashboard_columns=source.management_dashboard_columns,
            tipper_daily_columns=source.tipper_daily_columns,
            machinery_daily_columns=source.machinery_daily_columns,
        )

    def delete(self, template_id: UUID) -> None:
        template = self.get(template_id)
        if template.is_builtin:
            raise ConflictError("Built-in report templates cannot be deleted.")
        old_values = self.values(template)
        if template.is_default:
            template.is_default = False
            self.session.flush()
            fallback = next(
                item for item in self.ensure_builtins() if item.builtin_key == "management_summary"
            )
            fallback.is_default = True
        self._audit(
            action="REPORT_TEMPLATE_DELETED",
            template=template,
            old_values=old_values,
        )
        self.session.delete(template)
        self.session.flush()

    def set_default(self, template_id: UUID) -> ReportTemplate:
        template = self.get(template_id)
        previous = self.session.scalar(
            select(ReportTemplate).where(
                ReportTemplate.company_id == self.company_id,
                ReportTemplate.is_default.is_(True),
            )
        )
        self.session.execute(
            update(ReportTemplate)
            .where(ReportTemplate.company_id == self.company_id)
            .values(is_default=False)
        )
        self.session.flush()
        template.is_default = True
        self.session.flush()
        self._audit(
            action="REPORT_TEMPLATE_DEFAULT_SET",
            template=template,
            old_values={"template_id": str(previous.id)} if previous else None,
            new_values={"template_id": str(template.id)},
        )
        return template

    def resolve_for_export(self, template_id: UUID | None) -> ReportTemplate:
        builtins = self.ensure_builtins()
        if template_id is not None:
            return self.get(template_id)
        template = self.session.scalar(
            select(ReportTemplate).where(
                ReportTemplate.company_id == self.company_id,
                ReportTemplate.is_default.is_(True),
            )
        )
        if template is not None:
            return template
        return next(item for item in builtins if item.builtin_key == "management_summary")

    @staticmethod
    def config(template: ReportTemplate) -> ReportTemplateConfig:
        return ReportTemplateConfig(
            id=template.id,
            name=template.name,
            included_sheets=tuple(template.included_sheets),
            management_dashboard_columns=tuple(template.management_dashboard_columns),
            tipper_daily_columns=tuple(template.tipper_daily_columns),
            machinery_daily_columns=tuple(template.machinery_daily_columns),
        )
