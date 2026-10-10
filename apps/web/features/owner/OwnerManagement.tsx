"use client";

import { useCallback, useMemo, useState, type FormEvent } from "react";

import type {
  AssetOwnershipType,
  AssetSiteDeployment,
  DriverAssetAssignment,
  FleetAssetType,
  OwnerAsset,
  OwnerOperationIntent,
  OwnerPerson,
  OwnerSite,
} from "../../lib/types";
import { assetTypes, title } from "./catalogs";
import type { OwnerRelationshipTarget } from "./OwnerRelationshipManager";
import { OwnerRelationshipWizard } from "./OwnerRelationshipWizard";
import {
  DetailsDialog,
  EmptyTableRow,
  FilterToolbar,
  InlineFeedback,
  OperationsTable,
  PanelHeading,
  SortButton,
  StatusChip,
} from "./OwnerUi";

type WebRequest = <T>(path: string, options?: RequestInit) => Promise<T>;
type Common = {
  apiRequest: WebRequest;
  reload: () => Promise<void>;
  setError: (message: string) => void;
  openRelationshipManager: (target: OwnerRelationshipTarget) => void;
};
type SortDirection = "asc" | "desc";

function useOwnerAction({ reload, setError }: Pick<Common, "reload" | "setError">) {
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState("");
  const [success, setSuccess] = useState("");

  const run = useCallback(
    async (successMessage: string, action: () => Promise<unknown>) => {
      setBusy(true);
      setError("");
      setLocalError("");
      setSuccess("");
      try {
        await action();
        await reload();
        setSuccess(successMessage);
        return true;
      } catch (caught) {
        const message = caught instanceof Error ? caught.message : "The request failed.";
        setLocalError(message);
        setError(message);
        return false;
      } finally {
        setBusy(false);
      }
    },
    [reload, setError],
  );

  return { busy, localError, run, success };
}

function assetLabel(asset: OwnerAsset) {
  return asset.short_name || asset.registration_number || "Unnamed asset";
}

function assetSearchText(asset: OwnerAsset) {
  return [
    asset.short_name,
    asset.registration_number,
    asset.asset_type,
    asset.ownership_type,
    asset.manufacturer,
    asset.model,
    asset.chassis_number,
    asset.engine_number,
    asset.rental_party_name,
    asset.rental_owner_phone_primary,
    asset.rental_owner_phone_secondary,
    asset.current_deployment?.site_name,
    asset.active_assignment?.driver_name,
  ].filter(Boolean).join(" ").toLowerCase();
}

function siteLabel(site: OwnerSite) {
  return site.short_name || site.name;
}

function personForAsset(asset: OwnerAsset, people: OwnerPerson[]) {
  const membershipId = asset.active_assignment?.driver_membership_id;
  return membershipId ? people.find((person) => person.membership_id === membershipId) : undefined;
}

function dateTime(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function phoneDisplay(value: string) {
  const india = value.match(/^\+91(\d{5})(\d{5})$/);
  return india ? `+91 ${india[1]} ${india[2]}` : value;
}

function toggleSort<T extends string>(selected: T, next: T, direction: SortDirection) {
  return { key: next, direction: selected === next && direction === "asc" ? "desc" as const : "asc" as const };
}

function compareText(left: string | null | undefined, right: string | null | undefined) {
  return (left ?? "").localeCompare(right ?? "", undefined, { numeric: true, sensitivity: "base" });
}

export function FleetOverview({ assets, maintenanceAlertCount = 0 }: { assets: OwnerAsset[]; maintenanceAlertCount?: number }) {
  const active = assets.filter((asset) => asset.status === "ACTIVE");
  const assigned = active.filter((asset) => asset.has_active_assignment).length;
  const deployed = active.filter((asset) => asset.current_deployment).length;
  return (
    <section aria-label="Live fleet readiness" className="owner-overview">
      <div className="owner-overview-heading">
        <div>
          <p className="owner-section-eyebrow">Overview</p>
          <h2>Operations overview</h2>
          <p>Live readiness across active assets, deployments, and Driver / Operator assignments.</p>
        </div>
      </div>
      <div className="owner-kpi-grid">
        <div><span>Active assets</span><strong>{active.length}</strong></div>
        <div><span>Assigned</span><strong>{assigned}</strong></div>
        <div><span>Unassigned</span><strong>{active.length - assigned}</strong></div>
        <div><span>Undeployed</span><strong>{active.length - deployed}</strong></div>
        <div><span>Rented</span><strong>{active.filter((asset) => asset.ownership_type === "RENTED").length}</strong></div>
        <div><span>Maintenance alerts</span><strong>{maintenanceAlertCount}</strong></div>
      </div>
    </section>
  );
}

type AssetDraft = {
  asset_type: FleetAssetType;
  ownership_type: AssetOwnershipType;
  registration_number: string;
  short_name: string;
  manufacturer: string;
  model: string;
  model_year: string;
  is_wheeled: boolean;
  supports_odometer_km: boolean;
  supports_hour_meter: boolean;
  chassis_number: string;
  engine_number: string;
  rental_party_name: string;
  rental_owner_phone_primary: string;
  rental_owner_phone_secondary: string;
  rental_start_date: string;
  rental_end_date: string;
};

const blankAsset: AssetDraft = {
  asset_type: "TIPPER", ownership_type: "OWNED", registration_number: "", short_name: "",
  manufacturer: "", model: "", model_year: "", is_wheeled: true, supports_odometer_km: true, supports_hour_meter: true, chassis_number: "", engine_number: "", rental_party_name: "",
  rental_owner_phone_primary: "", rental_owner_phone_secondary: "", rental_start_date: "", rental_end_date: "",
};

function draftForAsset(asset: OwnerAsset): AssetDraft {
  return {
    asset_type: asset.asset_type,
    ownership_type: asset.ownership_type,
    registration_number: asset.registration_number ?? "",
    short_name: asset.short_name ?? "",
    manufacturer: asset.manufacturer ?? "",
    model: asset.model ?? "",
    model_year: asset.model_year?.toString() ?? "",
    is_wheeled: asset.is_wheeled,
    supports_odometer_km: asset.supports_odometer_km,
    supports_hour_meter: asset.supports_hour_meter,
    chassis_number: asset.chassis_number ?? "",
    engine_number: asset.engine_number ?? "",
    rental_party_name: asset.rental_party_name ?? "",
    rental_owner_phone_primary: asset.rental_owner_phone_primary ?? "",
    rental_owner_phone_secondary: asset.rental_owner_phone_secondary ?? "",
    rental_start_date: asset.rental_start_date ?? "",
    rental_end_date: asset.rental_end_date ?? "",
  };
}

function AssetFields({ draft, editing, setDraft }: { draft: AssetDraft; editing: boolean; setDraft: (draft: AssetDraft) => void }) {
  const machinery = draft.asset_type !== "TIPPER";
  return (
    <div className="owner-asset-form-sections">
      <fieldset className="owner-form-section">
        <legend>Basic details</legend>
        <div className="owner-form-grid">
          <label>Short name *<input aria-label="Short name" onChange={(event) => setDraft({ ...draft, short_name: event.target.value })} placeholder={machinery ? "e.g. North excavator" : "e.g. BENZ-1"} required value={draft.short_name} /></label>
          {!machinery && <label>Registration *<input aria-label="Registration" onChange={(event) => setDraft({ ...draft, registration_number: event.target.value })} required value={draft.registration_number} /></label>}
          <label>Asset type *<select aria-label="Asset type" disabled={editing} onChange={(event) => { const assetType = event.target.value as FleetAssetType; const isWheeled = ["TIPPER", "BACKHOE_LOADER", "ROLLER", "GRADER"].includes(assetType); setDraft({ ...draft, asset_type: assetType, is_wheeled: isWheeled, supports_odometer_km: isWheeled, supports_hour_meter: true }); }} value={draft.asset_type}>{assetTypes.map((type) => <option key={type} value={type}>{title(type)}</option>)}</select></label>
          <label>Ownership *<select aria-label="Ownership" onChange={(event) => setDraft({ ...draft, ownership_type: event.target.value as AssetOwnershipType })} value={draft.ownership_type}><option value="OWNED">Owned</option><option value="RENTED">Rented</option></select></label>
          <label>Manufacturer<input aria-label="Manufacturer" onChange={(event) => setDraft({ ...draft, manufacturer: event.target.value })} value={draft.manufacturer} /></label>
          <label>Model<input aria-label="Model" onChange={(event) => setDraft({ ...draft, model: event.target.value })} value={draft.model} /></label>
          <label>Model year <small>Optional</small><input aria-label="Model year" inputMode="numeric" max="2200" min="1900" onChange={(event) => setDraft({ ...draft, model_year: event.target.value })} type="number" value={draft.model_year} /></label>
          <label>Chassis number <small>Optional</small><input aria-label="Chassis number" onChange={(event) => setDraft({ ...draft, chassis_number: event.target.value })} value={draft.chassis_number} /></label>
          <label>Engine number <small>Optional</small><input aria-label="Engine number" onChange={(event) => setDraft({ ...draft, engine_number: event.target.value })} value={draft.engine_number} /></label>
        </div>
      </fieldset>
      <fieldset className="owner-form-section">
        <legend>Meter capabilities</legend>
        <p className="muted">Classify the undercarriage separately from the physical meters. Calendar maintenance is always available.</p>
        <div className="owner-chip-list">
          <label><input checked={draft.is_wheeled} onChange={(event) => setDraft({ ...draft, is_wheeled: event.target.checked, supports_odometer_km: event.target.checked ? draft.supports_odometer_km : false })} type="checkbox" /> Wheeled asset</label>
          <label><input checked={draft.supports_odometer_km} disabled={!draft.is_wheeled} onChange={(event) => setDraft({ ...draft, supports_odometer_km: event.target.checked })} type="checkbox" /> Odometer KM</label>
          <label><input checked={draft.supports_hour_meter} onChange={(event) => setDraft({ ...draft, supports_hour_meter: event.target.checked })} type="checkbox" /> Hour Meter / HMR</label>
        </div>
        {!draft.supports_odometer_km && !draft.supports_hour_meter && <p className="notice error">At least one operational meter is required.</p>}
      </fieldset>
      {draft.ownership_type === "RENTED" && <fieldset className="owner-form-section">
        <legend>Rental Owner / Supplier</legend>
        <div className="owner-form-grid">
          <label>Name *<input aria-label="Rental Owner / Supplier name" onChange={(event) => setDraft({ ...draft, rental_party_name: event.target.value })} required value={draft.rental_party_name} /></label>
          <label>Primary phone *<input aria-label="Primary phone" inputMode="tel" onChange={(event) => setDraft({ ...draft, rental_owner_phone_primary: event.target.value })} required type="tel" value={draft.rental_owner_phone_primary} /></label>
          <label>Alternate phone<input aria-label="Alternate phone" inputMode="tel" onChange={(event) => setDraft({ ...draft, rental_owner_phone_secondary: event.target.value })} type="tel" value={draft.rental_owner_phone_secondary} /></label>
          <label>Rental start<input aria-label="Rental start" onChange={(event) => setDraft({ ...draft, rental_start_date: event.target.value })} type="date" value={draft.rental_start_date} /></label>
          <label>Rental end<input aria-label="Rental end" onChange={(event) => setDraft({ ...draft, rental_end_date: event.target.value })} type="date" value={draft.rental_end_date} /></label>
        </div>
      </fieldset>}
    </div>
  );
}

function assetPayload(draft: AssetDraft, includeType: boolean) {
  return {
    ...(includeType ? { asset_type: draft.asset_type } : {}),
    ownership_type: draft.ownership_type,
    registration_number: draft.registration_number || null,
    short_name: draft.short_name || null,
    manufacturer: draft.manufacturer || null,
    model: draft.model || null,
    model_year: draft.model_year ? Number(draft.model_year) : null,
    is_wheeled: draft.is_wheeled,
    supports_odometer_km: draft.supports_odometer_km,
    supports_hour_meter: draft.supports_hour_meter,
    chassis_number: draft.chassis_number || null,
    engine_number: draft.engine_number || null,
    rental_party_name: draft.ownership_type === "RENTED" ? draft.rental_party_name || null : null,
    rental_owner_phone_primary: draft.ownership_type === "RENTED" ? draft.rental_owner_phone_primary || null : null,
    rental_owner_phone_secondary: draft.ownership_type === "RENTED" ? draft.rental_owner_phone_secondary || null : null,
    rental_start_date: draft.ownership_type === "RENTED" ? draft.rental_start_date || null : null,
    rental_end_date: draft.ownership_type === "RENTED" ? draft.rental_end_date || null : null,
  };
}

type FleetSort =
  | "asset-asc"
  | "asset-desc"
  | "site-asc"
  | "site-desc"
  | "operator-asc"
  | "operator-desc"
  | "owned-first"
  | "rented-first"
  | "on-duty-first"
  | "off-duty-first"
  | "active-first"
  | "type-asc";

const fleetSortOptions: { value: FleetSort; label: string }[] = [
  { value: "asset-asc", label: "Asset name A–Z" },
  { value: "asset-desc", label: "Asset name Z–A" },
  { value: "site-asc", label: "Site A–Z" },
  { value: "site-desc", label: "Site Z–A" },
  { value: "operator-asc", label: "Driver / Operator A–Z" },
  { value: "operator-desc", label: "Driver / Operator Z–A" },
  { value: "owned-first", label: "Owned first" },
  { value: "rented-first", label: "Rented first" },
  { value: "on-duty-first", label: "On duty first" },
  { value: "off-duty-first", label: "Off duty first" },
  { value: "active-first", label: "Active first" },
  { value: "type-asc", label: "Asset type A–Z" },
];

export function FleetPanel({ assets, people = [], sites = [], apiRequest, reload, setError, openRelationshipManager, editAssetId = null, onEditHandled, onConfigureMaintenance }: Common & { assets: OwnerAsset[]; people?: OwnerPerson[]; sites?: OwnerSite[]; editAssetId?: string | null; onEditHandled?: () => void; onConfigureMaintenance?: (assetId: string) => void }) {
  const mutation = useOwnerAction({ reload, setError });
  const requestedEditAsset = editAssetId ? assets.find((asset) => asset.id === editAssetId) : undefined;
  const [draft, setDraft] = useState<AssetDraft>(() => requestedEditAsset ? draftForAsset(requestedEditAsset) : blankAsset);
  const [editingId, setEditingId] = useState(requestedEditAsset?.id ?? "");
  const [formOpen, setFormOpen] = useState(Boolean(requestedEditAsset));
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [ownershipFilter, setOwnershipFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [siteFilter, setSiteFilter] = useState("");
  const [fleetSort, setFleetSort] = useState<FleetSort>("asset-asc");
  const [historyAsset, setHistoryAsset] = useState<OwnerAsset | null>(null);
  const [deploymentHistory, setDeploymentHistory] = useState<AssetSiteDeployment[]>([]);
  const [assignmentHistory, setAssignmentHistory] = useState<DriverAssetAssignment[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");

  const shown = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const filtered = assets.filter((asset) => (!normalizedQuery || assetSearchText(asset).includes(normalizedQuery)) && (!typeFilter || asset.asset_type === typeFilter) && (!ownershipFilter || asset.ownership_type === ownershipFilter) && (!statusFilter || asset.status === statusFilter) && (!siteFilter || asset.current_deployment?.site_id === siteFilter));
    const byAssetName = (left: OwnerAsset, right: OwnerAsset, direction: SortDirection = "asc") => {
      const result = compareText(assetLabel(left), assetLabel(right));
      return (direction === "asc" ? result : -result) || compareText(left.id, right.id);
    };
    const byOptionalText = (left: string | null | undefined, right: string | null | undefined, direction: SortDirection) => {
      if (!left && !right) return 0;
      if (!left) return 1;
      if (!right) return -1;
      const result = compareText(left, right);
      return direction === "asc" ? result : -result;
    };
    const duty = (asset: OwnerAsset) => personForAsset(asset, people)?.has_active_duty ? "ON_DUTY" : asset.has_active_assignment ? "OFF_DUTY" : "UNASSIGNED";
    return [...filtered].sort((left, right) => {
      let primary = 0;
      if (fleetSort === "asset-asc") return byAssetName(left, right);
      if (fleetSort === "asset-desc") return byAssetName(left, right, "desc");
      if (fleetSort === "site-asc" || fleetSort === "site-desc") primary = byOptionalText(left.current_deployment?.site_name, right.current_deployment?.site_name, fleetSort === "site-asc" ? "asc" : "desc");
      if (fleetSort === "operator-asc" || fleetSort === "operator-desc") primary = byOptionalText(left.active_assignment?.driver_name, right.active_assignment?.driver_name, fleetSort === "operator-asc" ? "asc" : "desc");
      if (fleetSort === "owned-first") primary = Number(left.ownership_type === "RENTED") - Number(right.ownership_type === "RENTED");
      if (fleetSort === "rented-first") primary = Number(left.ownership_type === "OWNED") - Number(right.ownership_type === "OWNED");
      if (fleetSort === "on-duty-first") primary = Number(duty(left) !== "ON_DUTY") - Number(duty(right) !== "ON_DUTY");
      if (fleetSort === "off-duty-first") primary = Number(duty(left) === "ON_DUTY") - Number(duty(right) === "ON_DUTY");
      if (fleetSort === "active-first") primary = Number(left.status !== "ACTIVE") - Number(right.status !== "ACTIVE");
      if (fleetSort === "type-asc") primary = compareText(left.asset_type, right.asset_type);
      return primary || byAssetName(left, right);
    });
  }, [assets, fleetSort, ownershipFilter, people, query, siteFilter, statusFilter, typeFilter]);
  const closeForm = () => { setDraft(blankAsset); setEditingId(""); setFormOpen(false); onEditHandled?.(); };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const endpoint = editingId ? `/api/v1/owner/assets/${editingId}` : "/api/v1/owner/assets";
    const ok = await mutation.run(editingId ? "Asset updated." : "Asset added.", () => apiRequest(endpoint, { method: editingId ? "PATCH" : "POST", body: JSON.stringify(assetPayload(draft, !editingId)) }));
    if (ok) closeForm();
  };
  const openRelationshipHistory = async (asset: OwnerAsset) => {
    setHistoryAsset(asset);
    setDeploymentHistory([]);
    setAssignmentHistory([]);
    setHistoryError("");
    setHistoryLoading(true);
    try {
      const [deployments, assignments] = await Promise.all([
        apiRequest<AssetSiteDeployment[]>(`/api/v1/owner/assets/${asset.id}/deployments`),
        apiRequest<DriverAssetAssignment[]>(`/api/v1/owner/assets/${asset.id}/assignments`),
      ]);
      setDeploymentHistory(deployments);
      setAssignmentHistory(assignments);
    } catch (caught) {
      setHistoryError(caught instanceof Error ? caught.message : "Could not load relationship history.");
    } finally {
      setHistoryLoading(false);
    }
  };

  return (
    <section className="owner-panel">
      <PanelHeading description="Search and manage the complete owned and rented fleet. Internal asset codes are generated automatically." eyebrow="Fleet management" title="Fleet" action={<button onClick={() => { setEditingId(""); setDraft(blankAsset); setFormOpen(true); }} type="button">Add asset</button>} />
      <InlineFeedback error={mutation.localError} success={mutation.success} />
      {formOpen && <form className="owner-form-panel" onSubmit={(event) => void submit(event)}><div className="owner-form-heading"><div><h3>{editingId ? "Edit asset" : "Add asset"}</h3><p>Use the operational name and registration. The internal code is handled by Fleet Manager.</p></div></div><AssetFields draft={draft} editing={Boolean(editingId)} setDraft={setDraft} /><div className="owner-form-actions"><button className="secondary" onClick={closeForm} type="button">Cancel</button><button disabled={mutation.busy} type="submit">{editingId ? "Save asset" : "Create asset"}</button></div></form>}
      <FilterToolbar>
        <label className="owner-search-field"><span>Search fleet</span><input aria-label="Search fleet" onChange={(event) => setQuery(event.target.value)} placeholder="Name, registration, site or operator" type="search" value={query} /></label>
        <label>Asset type<select aria-label="Filter asset type" onChange={(event) => setTypeFilter(event.target.value)} value={typeFilter}><option value="">All types</option>{assetTypes.map((type) => <option key={type} value={type}>{title(type)}</option>)}</select></label>
        <label>Ownership<select aria-label="Filter ownership" onChange={(event) => setOwnershipFilter(event.target.value)} value={ownershipFilter}><option value="">Owned and rented</option><option value="OWNED">Owned</option><option value="RENTED">Rented</option></select></label>
        <label>Status<select aria-label="Filter status" onChange={(event) => setStatusFilter(event.target.value)} value={statusFilter}><option value="">All statuses</option><option value="ACTIVE">Active</option><option value="INACTIVE">Inactive</option></select></label>
        <label>Site<select aria-label="Filter site" onChange={(event) => setSiteFilter(event.target.value)} value={siteFilter}><option value="">All sites</option>{sites.filter((site) => site.status === "ACTIVE").map((site) => <option key={site.id} value={site.id}>{siteLabel(site)}</option>)}</select></label>
        <label>Sort by<select aria-label="Sort by" onChange={(event) => setFleetSort(event.target.value as FleetSort)} value={fleetSort}>{fleetSortOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
      </FilterToolbar>
      <OperationsTable label="Fleet assets" variant="fleet">
        <thead><tr>
          <th scope="col">Asset</th>
          <th scope="col">Current setup</th>
          <th scope="col">Driver / Operator</th>
          <th scope="col">Actions</th>
        </tr></thead>
        <tbody>
          {shown.length === 0 && <EmptyTableRow colSpan={4} detail="Adjust the search or filters, or add the first asset." title="No fleet assets match" />}
          {shown.map((asset) => { const person = personForAsset(asset, people); const dutyStatus = person?.has_active_duty ? "ON_DUTY" : asset.has_active_assignment ? "OFF_DUTY" : "UNASSIGNED"; return <tr key={asset.id}>
            <td data-label="Asset"><div className="owner-fleet-cell owner-fleet-asset"><strong>{assetLabel(asset)}</strong><span>{asset.registration_number || "No registration"}</span><span>{title(asset.asset_type)}</span><span>{[asset.manufacturer, asset.model].filter(Boolean).join(" ") || "Make / model not provided"}</span>{asset.ownership_type === "RENTED" && <div className="owner-fleet-rental"><span>Owner: {asset.rental_party_name || "Not provided"}</span><span>{asset.rental_owner_phone_primary ? `Primary: ${phoneDisplay(asset.rental_owner_phone_primary)}` : "Primary phone not provided"}</span>{asset.rental_owner_phone_secondary && <span>Alternate: {phoneDisplay(asset.rental_owner_phone_secondary)}</span>}</div>}</div></td>
            <td data-label="Current setup"><div className="owner-fleet-cell owner-fleet-setup"><div className="owner-fleet-ownership"><StatusChip status={asset.ownership_type} /></div><strong>{asset.current_deployment?.site_name || "Undeployed"}</strong><div className="owner-fleet-statuses"><StatusChip label={dutyStatus === "ON_DUTY" ? "On duty" : dutyStatus === "OFF_DUTY" ? "Off duty" : "Not assigned"} status={dutyStatus === "ON_DUTY" ? "ON_DUTY" : dutyStatus === "OFF_DUTY" ? "AVAILABLE" : "UNDEPLOYED"} /><StatusChip status={asset.status} /></div></div></td>
            <td data-label="Driver / Operator"><div className="owner-fleet-cell"><strong>{asset.active_assignment?.driver_name || "Unassigned"}</strong><span>{asset.active_assignment ? phoneDisplay(asset.active_assignment.driver_phone || person?.phone || "—") : "—"}</span></div></td>
            <td data-label="Actions"><div className="owner-row-actions owner-row-actions--fleet"><button className="owner-text-button" onClick={() => openRelationshipManager({ kind: "asset", assetId: asset.id, focus: asset.status === "INACTIVE" ? "lifecycle" : undefined, initialAction: asset.status === "INACTIVE" ? "REACTIVATE_ASSET" : undefined })} type="button">Manage</button><button className="owner-text-button" onClick={() => onConfigureMaintenance?.(asset.id)} type="button">Maintenance plan</button><button className="owner-text-button" onClick={() => void openRelationshipHistory(asset)} type="button">History</button></div></td>
          </tr>; })}
        </tbody>
      </OperationsTable>
      <DetailsDialog onClose={() => setHistoryAsset(null)} open={Boolean(historyAsset)} title={`${historyAsset ? assetLabel(historyAsset) : "Asset"} relationship history`}>
        <InlineFeedback error={historyError} />
        {historyLoading ? <div aria-busy="true" className="owner-skeleton-list"><span /><span /><span /></div> : <div className="owner-dialog-form"><OperationsTable label="Fleet deployment history"><thead><tr><th scope="col">Site</th><th scope="col">Started</th><th scope="col">Ended</th></tr></thead><tbody>{deploymentHistory.length === 0 && <EmptyTableRow colSpan={3} title="No deployment history" />}{deploymentHistory.map((item) => <tr key={item.id}><td data-label="Site">{item.site_name}</td><td data-label="Started">{dateTime(item.starts_at)}</td><td data-label="Ended">{item.ends_at ? dateTime(item.ends_at) : "Current"}</td></tr>)}</tbody></OperationsTable><OperationsTable label="Fleet assignment history"><thead><tr><th scope="col">Driver / Operator</th><th scope="col">Site</th><th scope="col">Started</th><th scope="col">Ended</th></tr></thead><tbody>{assignmentHistory.length === 0 && <EmptyTableRow colSpan={4} title="No assignment history" />}{assignmentHistory.map((item) => <tr key={item.assignment_id}><td data-label="Driver / Operator">{item.driver_name}</td><td data-label="Site">{item.site_name}</td><td data-label="Started">{dateTime(item.starts_at)}</td><td data-label="Ended">{item.ends_at ? dateTime(item.ends_at) : "Current"}</td></tr>)}</tbody></OperationsTable></div>}
      </DetailsDialog>
    </section>
  );
}

type PersonGroup = { userId: string; phone: string; displayName: string; authState: string; phoneAuthLinked: boolean; memberships: OwnerPerson[] };
type PeopleSort = "name" | "phone" | "roles" | "lifecycle" | "asset" | "site" | "status";

function authStateLabel(value: string) {
  return ({ READY: "Ready", PHONE_MISSING: "Phone missing", DUPLICATE_PHONE: "Duplicate phone", DISABLED: "Disabled" } as Record<string, string>)[value] ?? "Unavailable";
}

function phoneLoginLabel(group: PersonGroup) {
  if (group.authState !== "READY") return authStateLabel(group.authState);
  return group.phoneAuthLinked ? "Linked" : "Phone verification required";
}

function personGroups(people: OwnerPerson[]): PersonGroup[] {
  const groups = new Map<string, PersonGroup>();
  for (const membership of people) {
    const group = groups.get(membership.user_id) ?? { userId: membership.user_id, phone: membership.phone, displayName: membership.display_name, authState: membership.auth_state ?? "READY", phoneAuthLinked: membership.phone_auth_linked ?? false, memberships: [] };
    group.memberships.push(membership);
    if (membership.status === "ACTIVE") { group.displayName = membership.display_name; group.authState = membership.auth_state ?? "READY"; group.phoneAuthLinked = membership.phone_auth_linked ?? false; }
    groups.set(membership.user_id, group);
  }
  return [...groups.values()];
}

export function PeoplePanel({ people, assets = [], apiRequest, reload, setError, openRelationshipManager }: Common & { people: OwnerPerson[]; assets?: OwnerAsset[]; sites?: OwnerSite[] }) {
  const mutation = useOwnerAction({ reload, setError });
  const [query, setQuery] = useState(""); const [roleFilter, setRoleFilter] = useState(""); const [statusFilter, setStatusFilter] = useState("");
  const [phone, setPhone] = useState(""); const [name, setName] = useState(""); const [role, setRole] = useState<"DRIVER" | "SUPERVISOR">("DRIVER");
  const [inviteOpen, setInviteOpen] = useState(false); const [editing, setEditing] = useState<PersonGroup | null>(null); const [sortKey, setSortKey] = useState<PeopleSort>("name"); const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [editingName, setEditingName] = useState(""); const [editingPhone, setEditingPhone] = useState("");
  const assetById = useMemo(() => new Map(assets.map((asset) => [asset.id, asset])), [assets]);
  const changeSort = (next: PeopleSort) => { const value = toggleSort(sortKey, next, sortDirection); setSortKey(value.key); setSortDirection(value.direction); };
  const grouped = useMemo(() => personGroups(people), [people]);
  const shown = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const value = (group: PersonGroup, key: PeopleSort) => {
      const active = group.memberships.filter((item) => item.status !== "INACTIVE");
      const driver = active.find((item) => item.role === "DRIVER");
      const sites = active.flatMap((item) => item.sites.map((site) => site.site_name));
      return { name: group.displayName, phone: group.phone, roles: active.map((item) => item.role).join(" "), lifecycle: active.map((item) => item.status).join(" "), asset: driver?.current_asset_code ?? "", site: driver?.current_site_name ?? sites.join(" "), status: driver?.has_active_duty ? "ON_DUTY" : driver?.has_active_assignment ? "ASSIGNED" : "AVAILABLE" }[key];
    };
    return grouped
      .filter((group) => !normalizedQuery || `${group.displayName} ${group.phone} ${group.memberships.map((item) => `${item.role} ${item.current_site_name ?? ""}`).join(" ")}`.toLowerCase().includes(normalizedQuery))
      .filter((group) => !roleFilter || group.memberships.some((item) => item.role === roleFilter && item.status !== "INACTIVE"))
      .filter((group) => !statusFilter || group.memberships.some((item) => item.status === statusFilter))
      .sort((left, right) => (sortDirection === "asc" ? 1 : -1) * compareText(value(left, sortKey), value(right, sortKey)));
  }, [grouped, query, roleFilter, sortDirection, sortKey, statusFilter]);
  const grantRole = async (targetPhone: string, targetName: string, targetRole: "DRIVER" | "SUPERVISOR") => mutation.run(`${title(targetRole)} role granted.`, () => apiRequest("/api/v1/owner/people/invite", { method: "POST", body: JSON.stringify({ phone: targetPhone, display_name: targetName, role: targetRole }) }));
  const invite = async (event: FormEvent) => { event.preventDefault(); const ok = await grantRole(phone, name, role); if (ok) { setPhone(""); setName(""); setInviteOpen(false); } };
  const beginEditing = (group: PersonGroup) => { setEditing(group); setEditingName(group.displayName); setEditingPhone(group.phone); };
  const saveIdentity = async (event: FormEvent) => {
    event.preventDefault();
    if (!editing) return;
    const phoneChanged = editingPhone.trim() !== editing.phone.trim();
    if (phoneChanged && editing.phoneAuthLinked && !window.confirm("Changing this phone number will sign the person out and require Firebase phone verification on the new number. Continue?")) return;
    const membership = editing.memberships.find((item) => item.status === "ACTIVE") ?? editing.memberships[0];
    const success = phoneChanged ? "Phone updated. New number must be verified on next login." : "Person identity updated.";
    const ok = await mutation.run(success, () => apiRequest(`/api/v1/owner/people/${membership.membership_id}`, { method: "PATCH", body: JSON.stringify({ display_name: editingName, phone: editingPhone }) }));
    if (ok) setEditing(null);
  };
  return (
    <section className="owner-panel">
      <PanelHeading action={<button onClick={() => setInviteOpen(true)} type="button">Add person or role</button>} description="One person can hold multiple company roles without duplicate identity records." eyebrow="Organization" title="People" />
      <div className="owner-lifecycle-guide" role="note"><div><StatusChip status="INVITED" /><span>Saved and assignable; first login/onboarding is not yet complete.</span></div><div><StatusChip status="ACTIVE" /><span>Verified identity and active role access.</span></div><div><StatusChip label="Deactivated" status="DEACTIVATED" /><span>Role access removed while history is preserved.</span></div></div>
      <InlineFeedback error={mutation.localError} success={mutation.success} />
      {inviteOpen && <form className="owner-form-panel owner-form-panel--compact" onSubmit={(event) => void invite(event)}><div className="owner-form-heading"><div><h3>Add person or role</h3><p>If the phone already belongs to this company, Fleet Manager adds only the selected role.</p></div></div><div className="owner-form-grid"><label>Phone<input aria-label="Person phone" onChange={(event) => setPhone(event.target.value)} placeholder="Phone in E.164" required value={phone} /></label><label>Display name<input aria-label="Display name" onChange={(event) => setName(event.target.value)} required value={name} /></label><label>Role<select aria-label="Role" onChange={(event) => setRole(event.target.value as typeof role)} value={role}><option value="DRIVER">Driver / Operator</option><option value="SUPERVISOR">Supervisor</option></select></label></div><div className="owner-form-actions"><button className="secondary" onClick={() => setInviteOpen(false)} type="button">Cancel</button><button disabled={mutation.busy} type="submit">Add role</button></div></form>}
      <FilterToolbar><label className="owner-search-field"><span>Search people</span><input aria-label="Search people" onChange={(event) => setQuery(event.target.value)} placeholder="Name, phone, site or role" type="search" value={query} /></label><label>Role<select aria-label="Filter people role" onChange={(event) => setRoleFilter(event.target.value)} value={roleFilter}><option value="">All roles</option><option value="OWNER_ADMIN">Owner</option><option value="DRIVER">Driver / Operator</option><option value="SUPERVISOR">Supervisor</option></select></label><label>Lifecycle<select aria-label="Filter people lifecycle" onChange={(event) => setStatusFilter(event.target.value)} value={statusFilter}><option value="">All lifecycle states</option><option value="INVITED">Invited</option><option value="ACTIVE">Active</option><option value="INACTIVE">Deactivated</option></select></label></FilterToolbar>
      <OperationsTable label="People"><thead><tr>{([['name', 'Name'], ['phone', 'Phone'], ['roles', 'Role(s)'], ['lifecycle', 'Lifecycle'], ['asset', 'Current asset'], ['site', 'Current site'], ['status', 'Status']] as [PeopleSort, string][]).map(([key, label]) => <th aria-sort={sortKey === key ? (sortDirection === "asc" ? "ascending" : "descending") : "none"} key={key} scope="col"><SortButton active={sortKey === key} direction={sortDirection} label={label} onClick={() => changeSort(key)} /></th>)}<th scope="col">Actions</th></tr></thead><tbody>
        {shown.length === 0 && <EmptyTableRow colSpan={8} detail="Adjust the filters or add the first person." title="No people match" />}
        {shown.map((group) => { const active = group.memberships.filter((item) => item.status !== "INACTIVE"); const driver = active.find((item) => item.role === "DRIVER"); const currentAsset = driver?.current_asset_id ? assetById.get(driver.current_asset_id) : undefined; const personSites = [...new Set(active.flatMap((item) => item.sites.map((site) => site.site_name)))]; const operationalStatus = driver?.has_active_duty ? "On duty" : driver?.has_active_assignment ? "Assigned · off duty" : driver ? "Available" : active.some((item) => item.role === "OWNER_ADMIN") ? "Owner access" : `${personSites.length} site${personSites.length === 1 ? "" : "s"}`; return <tr key={group.userId}><td data-label="Name"><strong>{group.displayName}</strong></td><td data-label="Phone">{group.phone}<small>Phone login: {phoneLoginLabel(group)}</small></td><td data-label="Role(s)"><div className="owner-chip-list">{active.map((membership) => <span className="owner-chip" key={membership.membership_id}>{membership.role === "OWNER_ADMIN" ? "Owner" : title(membership.role)}</span>)}</div></td><td data-label="Lifecycle"><div className="owner-chip-list">{group.memberships.map((membership) => <StatusChip key={membership.membership_id} label={`${membership.role === "OWNER_ADMIN" ? "Owner" : title(membership.role)} · ${title(membership.status)}`} status={membership.status} />)}</div></td><td data-label="Current asset">{currentAsset ? <><strong>{assetLabel(currentAsset)}</strong><small>{currentAsset.registration_number || title(currentAsset.asset_type)}</small></> : <span className="owner-dim">—</span>}</td><td data-label="Current site">{driver?.current_site_name || personSites.join(", ") || <span className="owner-dim">—</span>}</td><td data-label="Status"><StatusChip label={operationalStatus} status={driver?.has_active_duty ? "ON_DUTY" : driver?.has_active_assignment ? "ASSIGNED" : "AVAILABLE"} /></td><td data-label="Actions"><button className="owner-text-button" onClick={() => beginEditing(group)} type="button">Manage person</button></td></tr>; })}
      </tbody></OperationsTable>
      <DetailsDialog onClose={() => setEditing(null)} open={Boolean(editing)} title={editing ? `Manage ${editing.displayName}` : "Manage person"}>
        {editing && <div className="owner-dialog-form">
          <form className="owner-form-grid" onSubmit={(event) => void saveIdentity(event)}><label>Name<input aria-label="Edit person name" onChange={(event) => setEditingName(event.target.value)} required value={editingName} /></label><label>Phone<input aria-label="Edit person phone" inputMode="tel" onChange={(event) => setEditingPhone(event.target.value)} required value={editingPhone} /></label><small>Phone login: {phoneLoginLabel(editing)}</small><small>Changing the phone signs the person out, disables the old Firebase login link, and requires verification of the new number.</small><button disabled={mutation.busy} type="submit">Save identity</button></form>
          <h3>Roles and operational setup</h3>
          <div className="owner-role-management">{editing.memberships.map((membership) => <div key={membership.membership_id}>
            <div><strong>{membership.role === "OWNER_ADMIN" ? "Owner" : title(membership.role)}</strong><StatusChip status={membership.status} /></div>
            {membership.role === "OWNER_ADMIN" ? <small>Sole Owner protection is enforced by the server.</small> : <button onClick={() => { openRelationshipManager({ kind: "person", membershipId: membership.membership_id }); setEditing(null); }} type="button">{membership.role === "SUPERVISOR" ? "Manage Site access" : membership.status === "INACTIVE" ? "Reactivate or assign" : "Manage assignment"}</button>}
          </div>)}</div>
          <h3>Add role</h3>
          <div className="owner-row-actions">{(["DRIVER", "SUPERVISOR"] as const).filter((candidate) => !editing.memberships.some((item) => item.role === candidate)).map((candidate) => <button disabled={mutation.busy} key={candidate} onClick={() => void grantRole(editing.phone, editing.displayName, candidate).then((ok) => { if (ok) setEditing(null); })} type="button">Add {candidate === "DRIVER" ? "Driver / Operator" : "Supervisor"}</button>)}</div>
        </div>}
      </DetailsDialog>
    </section>
  );
}

type SiteDraft = { name: string; short_name: string; location_description: string };
const blankSite: SiteDraft = { name: "", short_name: "", location_description: "" };
type SiteSort = "shortName" | "name" | "supervisors" | "assets" | "status";

export function SitesPanel({ sites, people, assets = [], apiRequest, reload, setError, openRelationshipManager }: Common & { sites: OwnerSite[]; people: OwnerPerson[]; assets?: OwnerAsset[] }) {
  const mutation = useOwnerAction({ reload, setError });
  const [draft, setDraft] = useState<SiteDraft>(blankSite); const [editing, setEditing] = useState<OwnerSite | null>(null); const [formOpen, setFormOpen] = useState(false); const [query, setQuery] = useState(""); const [statusFilter, setStatusFilter] = useState(""); const [details, setDetails] = useState<OwnerSite | null>(null); const [operation, setOperation] = useState<OwnerOperationIntent | null>(null); const [grant, setGrant] = useState(""); const [sortKey, setSortKey] = useState<SiteSort>("shortName"); const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const supervisors = people.filter((person) => person.role === "SUPERVISOR" && person.status === "ACTIVE");
  const changeSort = (next: SiteSort) => { const value = toggleSort(sortKey, next, sortDirection); setSortKey(value.key); setSortDirection(value.direction); };
  const shown = useMemo(() => { const value = (site: OwnerSite) => sortKey === "shortName" ? siteLabel(site) : sortKey === "name" ? `${site.name} ${site.location_description ?? ""}` : sortKey === "supervisors" ? site.supervisors.map((item) => item.display_name).join(" ") : sortKey === "assets" ? String(site.asset_count).padStart(12, "0") : site.status; return sites.filter((site) => `${site.short_name ?? ""} ${site.name} ${site.location_description ?? ""}`.toLowerCase().includes(query.trim().toLowerCase()) && (!statusFilter || site.status === statusFilter)).sort((left, right) => (sortDirection === "asc" ? 1 : -1) * compareText(value(left), value(right))); }, [query, sites, sortDirection, sortKey, statusFilter]);
  const submit = async (event: FormEvent) => { event.preventDefault(); const ok = await mutation.run("Site added.", () => apiRequest("/api/v1/owner/sites", { method: "POST", body: JSON.stringify({ name: draft.name, short_name: draft.short_name, location_description: draft.location_description || null }) })); if (ok) { setDraft(blankSite); setFormOpen(false); } };
  const save = async (event: FormEvent) => { event.preventDefault(); if (!editing) return; const ok = await mutation.run("Site updated.", () => apiRequest(`/api/v1/owner/sites/${editing.id}`, { method: "PATCH", body: JSON.stringify({ name: editing.name, short_name: editing.short_name, location_description: editing.location_description || null }) })); if (ok) setEditing(null); };
  return (
    <section className="owner-panel">
      <PanelHeading action={<button onClick={() => setFormOpen(true)} type="button">Add site</button>} description="Use a clear operational short name. Fleet Manager creates and protects the internal site code." eyebrow="Organization" title="Sites" />
      <InlineFeedback error={mutation.localError} success={mutation.success} />
      {formOpen && <form className="owner-form-panel owner-form-panel--compact" onSubmit={(event) => void submit(event)}><div className="owner-form-heading"><div><h3>Add site</h3><p>Site name is descriptive; short name is what teams see in daily operations.</p></div></div><div className="owner-form-grid"><label>Site name<input aria-label="Site name" onChange={(event) => setDraft({ ...draft, name: event.target.value })} required value={draft.name} /></label><label>Short name<input aria-label="Site short name" onChange={(event) => setDraft({ ...draft, short_name: event.target.value })} placeholder="e.g. ABL Roadwork" required value={draft.short_name} /></label><label>Location description<input aria-label="Site location" onChange={(event) => setDraft({ ...draft, location_description: event.target.value })} value={draft.location_description} /></label></div><div className="owner-form-actions"><button className="secondary" onClick={() => setFormOpen(false)} type="button">Cancel</button><button disabled={mutation.busy} type="submit">Create site</button></div></form>}
      <FilterToolbar><label className="owner-search-field"><span>Search sites</span><input aria-label="Search sites" onChange={(event) => setQuery(event.target.value)} placeholder="Short name, site name or location" type="search" value={query} /></label><label>Status<select aria-label="Filter site status" onChange={(event) => setStatusFilter(event.target.value)} value={statusFilter}><option value="">All statuses</option><option value="ACTIVE">Active</option><option value="INACTIVE">Inactive</option></select></label></FilterToolbar>
      <OperationsTable label="Sites"><thead><tr>{([['shortName', 'Short name'], ['name', 'Site name / location'], ['supervisors', 'Supervisors'], ['assets', 'Deployed assets'], ['status', 'Status']] as [SiteSort, string][]).map(([key, label]) => <th aria-sort={sortKey === key ? (sortDirection === "asc" ? "ascending" : "descending") : "none"} key={key} scope="col"><SortButton active={sortKey === key} direction={sortDirection} label={label} onClick={() => changeSort(key)} /></th>)}<th scope="col">Actions</th></tr></thead><tbody>
        {shown.length === 0 && <EmptyTableRow colSpan={6} detail="Adjust the filters or add the first site." title="No sites match" />}
        {shown.map((site) => <tr key={site.id}><td data-label="Short name"><strong>{siteLabel(site)}</strong></td><td data-label="Site name / location"><strong>{site.name}</strong><small>{site.location_description || "Location not set"}</small></td><td data-label="Supervisors">{site.supervisors.length ? site.supervisors.map((person) => person.display_name).join(", ") : <span className="owner-dim">None</span>}</td><td data-label="Deployed assets">{site.asset_count}</td><td data-label="Status"><StatusChip status={site.status} /></td><td data-label="Actions"><div className="owner-row-actions"><button className="owner-text-button" onClick={() => setEditing({ ...site })} type="button">Edit</button><button className="owner-text-button" onClick={() => { setDetails(site); setGrant(""); }} type="button">Details</button>{site.status === "ACTIVE" ? <button className="owner-text-button owner-text-button--danger" onClick={() => setOperation({ action: "DEACTIVATE_SITE", site_id: site.id, asset_resolutions: [] })} type="button">Deactivate</button> : <button className="owner-text-button" onClick={() => setOperation({ action: "REACTIVATE_SITE", site_id: site.id, selected_supervisor_ids: [], selected_asset_ids: [] })} type="button">Reactivate</button>}</div></td></tr>)}
      </tbody></OperationsTable>
      <DetailsDialog onClose={() => setEditing(null)} open={Boolean(editing)} title="Edit site">{editing && <form className="owner-dialog-form" onSubmit={(event) => void save(event)}><label>Site name<input aria-label="Edit site name" onChange={(event) => setEditing({ ...editing, name: event.target.value })} required value={editing.name} /></label><label>Short name<input aria-label="Edit site short name" onChange={(event) => setEditing({ ...editing, short_name: event.target.value })} required value={editing.short_name ?? ""} /></label><label>Location description<input aria-label="Edit location" onChange={(event) => setEditing({ ...editing, location_description: event.target.value || null })} value={editing.location_description ?? ""} /></label><div className="owner-form-actions"><button className="secondary" onClick={() => setEditing(null)} type="button">Cancel</button><button disabled={mutation.busy} type="submit">Save site</button></div></form>}</DetailsDialog>
      <DetailsDialog onClose={() => setDetails(null)} open={Boolean(details)} title={details ? `${siteLabel(details)} details` : "Site details"}>
        {details && <div className="owner-dialog-form">
          <dl className="owner-detail-list"><div><dt>Full site name</dt><dd>{details.name}</dd></div><div><dt>Location</dt><dd>{details.location_description || "Not set"}</dd></div></dl>
          <h3>Supervisor access</h3>
          <div className="owner-chip-list">{details.supervisors.map((supervisor) => <button className="owner-chip" key={supervisor.membership_id} onClick={() => { openRelationshipManager({ kind: "person", membershipId: supervisor.membership_id }); setDetails(null); }} type="button">{supervisor.display_name} · Manage</button>)}</div>
          {details.status === "ACTIVE" && <form className="owner-inline-operation" onSubmit={(event) => { event.preventDefault(); if (!grant) return; openRelationshipManager({ kind: "person", membershipId: grant, presetSiteId: details.id }); setDetails(null); }}><label>Manage Supervisor<select aria-label={`Supervisor for ${siteLabel(details)}`} onChange={(event) => setGrant(event.target.value)} required value={grant}><option value="">Choose Supervisor…</option>{supervisors.filter((person) => !details.supervisors.some((item) => item.membership_id === person.membership_id)).map((person) => <option key={person.membership_id} value={person.membership_id}>{person.display_name}</option>)}</select></label><button type="submit">Manage access</button></form>}
          <h3>Deployed assets</h3>
          <div className="owner-role-management">{assets.filter((asset) => asset.current_deployment?.site_id === details.id).map((asset) => <div key={asset.id}><div><strong>{assetLabel(asset)}</strong><StatusChip label={personForAsset(asset, people)?.has_active_duty ? "On duty" : asset.has_active_assignment ? "Off duty" : "Unassigned"} status={personForAsset(asset, people)?.has_active_duty ? "ON_DUTY" : "AVAILABLE"} /></div><button onClick={() => { openRelationshipManager({ kind: "asset", assetId: asset.id }); setDetails(null); }} type="button">Manage asset</button></div>)}</div>
          {!assets.some((asset) => asset.current_deployment?.site_id === details.id) && <p className="owner-dim">No assets are currently deployed here.</p>}
        </div>}
      </DetailsDialog>
      <OwnerRelationshipWizard apiRequest={apiRequest} assets={assets} initialIntent={operation} onClose={() => setOperation(null)} onComplete={reload} open={Boolean(operation)} people={people} sites={sites} />
    </section>
  );
}
