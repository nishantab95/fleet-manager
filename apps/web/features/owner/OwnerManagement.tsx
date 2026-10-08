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
    asset.rental_party_name,
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

function toggleSort<T extends string>(selected: T, next: T, direction: SortDirection) {
  return { key: next, direction: selected === next && direction === "asc" ? "desc" as const : "asc" as const };
}

function compareText(left: string | null | undefined, right: string | null | undefined) {
  return (left ?? "").localeCompare(right ?? "", undefined, { numeric: true, sensitivity: "base" });
}

export function FleetOverview({ assets }: { assets: OwnerAsset[] }) {
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
  rental_party_name: string;
  rental_start_date: string;
  rental_end_date: string;
};

const blankAsset: AssetDraft = {
  asset_type: "TIPPER", ownership_type: "OWNED", registration_number: "", short_name: "",
  manufacturer: "", model: "", rental_party_name: "", rental_start_date: "", rental_end_date: "",
};

function AssetFields({ draft, editing, setDraft }: { draft: AssetDraft; editing: boolean; setDraft: (draft: AssetDraft) => void }) {
  const machinery = draft.asset_type !== "TIPPER";
  return (
    <div className="owner-form-grid">
      <label>Asset type<select aria-label="Asset type" disabled={editing} onChange={(event) => setDraft({ ...draft, asset_type: event.target.value as FleetAssetType })} value={draft.asset_type}>{assetTypes.map((type) => <option key={type} value={type}>{title(type)}</option>)}</select></label>
      <label>Ownership<select aria-label="Ownership" onChange={(event) => setDraft({ ...draft, ownership_type: event.target.value as AssetOwnershipType })} value={draft.ownership_type}><option value="OWNED">Owned</option><option value="RENTED">Rented</option></select></label>
      {!machinery && <label>Registration<input aria-label="Registration" onChange={(event) => setDraft({ ...draft, registration_number: event.target.value })} required value={draft.registration_number} /></label>}
      <label>Short name<input aria-label="Short name" onChange={(event) => setDraft({ ...draft, short_name: event.target.value })} placeholder={machinery ? "e.g. North excavator" : "e.g. BENZ-1"} required={machinery} value={draft.short_name} /></label>
      <label>Manufacturer<input aria-label="Manufacturer" onChange={(event) => setDraft({ ...draft, manufacturer: event.target.value })} value={draft.manufacturer} /></label>
      <label>Model<input aria-label="Model" onChange={(event) => setDraft({ ...draft, model: event.target.value })} value={draft.model} /></label>
      {draft.ownership_type === "RENTED" && <><label>Rental party<input aria-label="Rental party" onChange={(event) => setDraft({ ...draft, rental_party_name: event.target.value })} required value={draft.rental_party_name} /></label><label>Rental start<input aria-label="Rental start" onChange={(event) => setDraft({ ...draft, rental_start_date: event.target.value })} type="date" value={draft.rental_start_date} /></label><label>Rental end<input aria-label="Rental end" onChange={(event) => setDraft({ ...draft, rental_end_date: event.target.value })} type="date" value={draft.rental_end_date} /></label></>}
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
    rental_party_name: draft.ownership_type === "RENTED" ? draft.rental_party_name || null : null,
    rental_start_date: draft.ownership_type === "RENTED" ? draft.rental_start_date || null : null,
    rental_end_date: draft.ownership_type === "RENTED" ? draft.rental_end_date || null : null,
  };
}

type FleetSort = "name" | "registration" | "type" | "ownership" | "manufacturer" | "site" | "operator" | "duty" | "status";

export function FleetPanel({ assets, people = [], sites = [], apiRequest, reload, setError }: Common & { assets: OwnerAsset[]; people?: OwnerPerson[]; sites?: OwnerSite[] }) {
  const mutation = useOwnerAction({ reload, setError });
  const [draft, setDraft] = useState<AssetDraft>(blankAsset);
  const [editingId, setEditingId] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [ownershipFilter, setOwnershipFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [siteFilter, setSiteFilter] = useState("");
  const [sortKey, setSortKey] = useState<FleetSort>("name");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [manageAsset, setManageAsset] = useState<OwnerAsset | null>(null);
  const [operation, setOperation] = useState<OwnerOperationIntent | null>(null);
  const [historyAsset, setHistoryAsset] = useState<OwnerAsset | null>(null);
  const [deploymentHistory, setDeploymentHistory] = useState<AssetSiteDeployment[]>([]);
  const [assignmentHistory, setAssignmentHistory] = useState<DriverAssetAssignment[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");

  const shown = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const filtered = assets.filter((asset) => (!normalizedQuery || assetSearchText(asset).includes(normalizedQuery)) && (!typeFilter || asset.asset_type === typeFilter) && (!ownershipFilter || asset.ownership_type === ownershipFilter) && (!statusFilter || asset.status === statusFilter) && (!siteFilter || asset.current_deployment?.site_id === siteFilter));
    const value = (asset: OwnerAsset) => sortKey === "name" ? assetLabel(asset) : sortKey === "registration" ? asset.registration_number : sortKey === "type" ? asset.asset_type : sortKey === "ownership" ? asset.ownership_type : sortKey === "manufacturer" ? `${asset.manufacturer ?? ""} ${asset.model ?? ""}` : sortKey === "site" ? asset.current_deployment?.site_name : sortKey === "operator" ? asset.active_assignment?.driver_name : sortKey === "duty" ? (personForAsset(asset, people)?.has_active_duty ? "ON_DUTY" : asset.has_active_assignment ? "OFF_DUTY" : "UNASSIGNED") : asset.status;
    return [...filtered].sort((left, right) => { const result = compareText(value(left), value(right)); return sortDirection === "asc" ? result : -result; });
  }, [assets, ownershipFilter, people, query, siteFilter, sortDirection, sortKey, statusFilter, typeFilter]);

  const changeSort = (next: FleetSort) => { const value = toggleSort(sortKey, next, sortDirection); setSortKey(value.key); setSortDirection(value.direction); };
  const edit = (asset: OwnerAsset) => {
    setEditingId(asset.id);
    setDraft({ asset_type: asset.asset_type, ownership_type: asset.ownership_type, registration_number: asset.registration_number ?? "", short_name: asset.short_name ?? "", manufacturer: asset.manufacturer ?? "", model: asset.model ?? "", rental_party_name: asset.rental_party_name ?? "", rental_start_date: asset.rental_start_date ?? "", rental_end_date: asset.rental_end_date ?? "" });
    setFormOpen(true);
  };
  const closeForm = () => { setDraft(blankAsset); setEditingId(""); setFormOpen(false); };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const endpoint = editingId ? `/api/v1/owner/assets/${editingId}` : "/api/v1/owner/assets";
    const ok = await mutation.run(editingId ? "Asset updated." : "Asset added.", () => apiRequest(endpoint, { method: editingId ? "PATCH" : "POST", body: JSON.stringify(assetPayload(draft, !editingId)) }));
    if (ok) closeForm();
  };
  const openRelationshipHistory = async (asset: OwnerAsset) => {
    setManageAsset(null);
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
      </FilterToolbar>
      <OperationsTable label="Fleet assets">
        <thead><tr>
          <th aria-sort={sortKey === "name" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"} scope="col"><SortButton active={sortKey === "name"} direction={sortDirection} label="Short name" onClick={() => changeSort("name")} /></th>
          <th aria-sort={sortKey === "registration" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"} scope="col"><SortButton active={sortKey === "registration"} direction={sortDirection} label="Registration" onClick={() => changeSort("registration")} /></th>
          <th aria-sort={sortKey === "type" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"} scope="col"><SortButton active={sortKey === "type"} direction={sortDirection} label="Type" onClick={() => changeSort("type")} /></th>
          <th aria-sort={sortKey === "ownership" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"} scope="col"><SortButton active={sortKey === "ownership"} direction={sortDirection} label="Ownership" onClick={() => changeSort("ownership")} /></th>
          <th aria-sort={sortKey === "manufacturer" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"} scope="col"><SortButton active={sortKey === "manufacturer"} direction={sortDirection} label="Manufacturer / model" onClick={() => changeSort("manufacturer")} /></th><th aria-sort={sortKey === "site" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"} scope="col"><SortButton active={sortKey === "site"} direction={sortDirection} label="Current site" onClick={() => changeSort("site")} /></th><th aria-sort={sortKey === "operator" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"} scope="col"><SortButton active={sortKey === "operator"} direction={sortDirection} label="Driver / Operator" onClick={() => changeSort("operator")} /></th><th aria-sort={sortKey === "duty" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"} scope="col"><SortButton active={sortKey === "duty"} direction={sortDirection} label="Duty" onClick={() => changeSort("duty")} /></th>
          <th aria-sort={sortKey === "status" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"} scope="col"><SortButton active={sortKey === "status"} direction={sortDirection} label="Asset status" onClick={() => changeSort("status")} /></th><th scope="col">Actions</th>
        </tr></thead>
        <tbody>
          {shown.length === 0 && <EmptyTableRow colSpan={10} detail="Adjust the search or filters, or add the first asset." title="No fleet assets match" />}
          {shown.map((asset) => { const person = personForAsset(asset, people); return <tr key={asset.id}>
            <td data-label="Short name"><strong>{assetLabel(asset)}</strong><details className="owner-technical"><summary>Technical details</summary><code>{asset.asset_code}</code></details></td>
            <td data-label="Registration"><strong>{asset.registration_number || "—"}</strong></td><td data-label="Type">{title(asset.asset_type)}</td>
            <td data-label="Ownership"><StatusChip status={asset.ownership_type} />{asset.ownership_type === "RENTED" && <small>{asset.rental_party_name || "Rental party not set"}</small>}</td>
            <td data-label="Manufacturer / model">{[asset.manufacturer, asset.model].filter(Boolean).join(" ") || "—"}</td><td data-label="Current site">{asset.current_deployment?.site_name || <span className="owner-dim">Undeployed</span>}</td><td data-label="Driver / Operator">{asset.active_assignment?.driver_name || <span className="owner-dim">Unassigned</span>}</td>
            <td data-label="Duty">{person?.has_active_duty ? <StatusChip label="On duty" status="ON_DUTY" /> : <StatusChip label={asset.has_active_assignment ? "Off duty" : "Not assigned"} status="AVAILABLE" />}</td><td data-label="Asset status"><StatusChip status={asset.status} /></td>
            <td data-label="Actions"><div className="owner-row-actions"><button className="owner-text-button" onClick={() => edit(asset)} type="button">Edit</button>{asset.status === "ACTIVE" ? <button className="owner-text-button" onClick={() => setManageAsset(asset)} type="button">Manage</button> : <button className="owner-text-button" onClick={() => setOperation({ action: "REACTIVATE_ASSET", asset_id: asset.id, site_id: null, driver_membership_id: null, activate_membership: false, regular_duty_minutes: 600 })} type="button">Reactivate</button>}</div></td>
          </tr>; })}
        </tbody>
      </OperationsTable>
      <DetailsDialog onClose={() => setManageAsset(null)} open={Boolean(manageAsset)} title={`Manage ${manageAsset ? assetLabel(manageAsset) : "asset"}`}>
        {manageAsset && <div className="owner-dialog-form"><dl className="owner-detail-list"><div><dt>Current Site</dt><dd>{manageAsset.current_deployment?.site_name || "Undeployed"}</dd></div><div><dt>Driver / Operator</dt><dd>{manageAsset.active_assignment?.driver_name || "Unassigned"}</dd></div></dl><div className="owner-management-actions">{!manageAsset.current_deployment && <button onClick={() => { setOperation({ action: "DEPLOY_ASSET", asset_id: manageAsset.id }); setManageAsset(null); }} type="button">Deploy</button>}{manageAsset.current_deployment && <><button onClick={() => { setOperation({ action: "MOVE_DEPLOYMENT", asset_id: manageAsset.id }); setManageAsset(null); }} type="button">Move Site</button><button onClick={() => { setOperation({ action: "REMOVE_DEPLOYMENT", asset_id: manageAsset.id }); setManageAsset(null); }} type="button">Remove from Site</button></>}{!manageAsset.has_active_assignment && <button onClick={() => { setOperation({ action: "ASSIGN_DRIVER", asset_id: manageAsset.id }); setManageAsset(null); }} type="button">Assign Driver / Operator</button>}{manageAsset.has_active_assignment && <><button onClick={() => { setOperation({ action: "REASSIGN_DRIVER", asset_id: manageAsset.id, regular_duty_minutes: manageAsset.active_assignment?.regular_duty_minutes ?? 600 }); setManageAsset(null); }} type="button">Change Driver / Operator</button><button onClick={() => { setOperation({ action: "END_ASSIGNMENT", asset_id: manageAsset.id }); setManageAsset(null); }} type="button">End assignment</button></>}<button onClick={() => void openRelationshipHistory(manageAsset)} type="button">View relationship history</button><button className="owner-text-button--danger" onClick={() => { setOperation({ action: "DEACTIVATE_ASSET", asset_id: manageAsset.id }); setManageAsset(null); }} type="button">Deactivate asset</button></div></div>}
      </DetailsDialog>
      <OwnerRelationshipWizard apiRequest={apiRequest} assets={assets} initialIntent={operation} onClose={() => setOperation(null)} onComplete={reload} open={Boolean(operation)} people={people} sites={sites} />
      <DetailsDialog onClose={() => setHistoryAsset(null)} open={Boolean(historyAsset)} title={`${historyAsset ? assetLabel(historyAsset) : "Asset"} relationship history`}>
        <InlineFeedback error={historyError} />
        {historyLoading ? <div aria-busy="true" className="owner-skeleton-list"><span /><span /><span /></div> : <div className="owner-dialog-form"><OperationsTable label="Fleet deployment history"><thead><tr><th scope="col">Site</th><th scope="col">Started</th><th scope="col">Ended</th></tr></thead><tbody>{deploymentHistory.length === 0 && <EmptyTableRow colSpan={3} title="No deployment history" />}{deploymentHistory.map((item) => <tr key={item.id}><td data-label="Site">{item.site_name}</td><td data-label="Started">{dateTime(item.starts_at)}</td><td data-label="Ended">{item.ends_at ? dateTime(item.ends_at) : "Current"}</td></tr>)}</tbody></OperationsTable><OperationsTable label="Fleet assignment history"><thead><tr><th scope="col">Driver / Operator</th><th scope="col">Site</th><th scope="col">Started</th><th scope="col">Ended</th></tr></thead><tbody>{assignmentHistory.length === 0 && <EmptyTableRow colSpan={4} title="No assignment history" />}{assignmentHistory.map((item) => <tr key={item.assignment_id}><td data-label="Driver / Operator">{item.driver_name}</td><td data-label="Site">{item.site_name}</td><td data-label="Started">{dateTime(item.starts_at)}</td><td data-label="Ended">{item.ends_at ? dateTime(item.ends_at) : "Current"}</td></tr>)}</tbody></OperationsTable></div>}
      </DetailsDialog>
    </section>
  );
}

type PersonGroup = { userId: string; phone: string; displayName: string; memberships: OwnerPerson[] };
type PeopleSort = "name" | "phone" | "roles" | "lifecycle" | "asset" | "site" | "status";

function personGroups(people: OwnerPerson[]): PersonGroup[] {
  const groups = new Map<string, PersonGroup>();
  for (const membership of people) {
    const group = groups.get(membership.user_id) ?? { userId: membership.user_id, phone: membership.phone, displayName: membership.display_name, memberships: [] };
    group.memberships.push(membership);
    if (membership.status === "ACTIVE") group.displayName = membership.display_name;
    groups.set(membership.user_id, group);
  }
  return [...groups.values()];
}

export function PeoplePanel({ people, assets = [], sites = [], apiRequest, reload, setError }: Common & { people: OwnerPerson[]; assets?: OwnerAsset[]; sites?: OwnerSite[] }) {
  const mutation = useOwnerAction({ reload, setError });
  const [query, setQuery] = useState(""); const [roleFilter, setRoleFilter] = useState(""); const [statusFilter, setStatusFilter] = useState("");
  const [phone, setPhone] = useState(""); const [name, setName] = useState(""); const [role, setRole] = useState<"DRIVER" | "SUPERVISOR">("DRIVER");
  const [inviteOpen, setInviteOpen] = useState(false); const [editing, setEditing] = useState<PersonGroup | null>(null); const [operation, setOperation] = useState<OwnerOperationIntent | null>(null); const [sortKey, setSortKey] = useState<PeopleSort>("name"); const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
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
  return (
    <section className="owner-panel">
      <PanelHeading action={<button onClick={() => setInviteOpen(true)} type="button">Add person or role</button>} description="One person can hold multiple company roles without duplicate identity records." eyebrow="Organization" title="People" />
      <div className="owner-lifecycle-guide" role="note"><div><StatusChip status="INVITED" /><span>Saved and assignable; first login/onboarding is not yet complete.</span></div><div><StatusChip status="ACTIVE" /><span>Verified identity and active role access.</span></div><div><StatusChip label="Deactivated" status="DEACTIVATED" /><span>Role access removed while history is preserved.</span></div></div>
      <InlineFeedback error={mutation.localError} success={mutation.success} />
      {inviteOpen && <form className="owner-form-panel owner-form-panel--compact" onSubmit={(event) => void invite(event)}><div className="owner-form-heading"><div><h3>Add person or role</h3><p>If the phone already belongs to this company, Fleet Manager adds only the selected role.</p></div></div><div className="owner-form-grid"><label>Phone<input aria-label="Person phone" onChange={(event) => setPhone(event.target.value)} placeholder="Phone in E.164" required value={phone} /></label><label>Display name<input aria-label="Display name" onChange={(event) => setName(event.target.value)} required value={name} /></label><label>Role<select aria-label="Role" onChange={(event) => setRole(event.target.value as typeof role)} value={role}><option value="DRIVER">Driver / Operator</option><option value="SUPERVISOR">Supervisor</option></select></label></div><div className="owner-form-actions"><button className="secondary" onClick={() => setInviteOpen(false)} type="button">Cancel</button><button disabled={mutation.busy} type="submit">Add role</button></div></form>}
      <FilterToolbar><label className="owner-search-field"><span>Search people</span><input aria-label="Search people" onChange={(event) => setQuery(event.target.value)} placeholder="Name, phone, site or role" type="search" value={query} /></label><label>Role<select aria-label="Filter people role" onChange={(event) => setRoleFilter(event.target.value)} value={roleFilter}><option value="">All roles</option><option value="OWNER_ADMIN">Owner</option><option value="DRIVER">Driver / Operator</option><option value="SUPERVISOR">Supervisor</option></select></label><label>Lifecycle<select aria-label="Filter people lifecycle" onChange={(event) => setStatusFilter(event.target.value)} value={statusFilter}><option value="">All lifecycle states</option><option value="INVITED">Invited</option><option value="ACTIVE">Active</option><option value="INACTIVE">Deactivated</option></select></label></FilterToolbar>
      <OperationsTable label="People"><thead><tr>{([['name', 'Name'], ['phone', 'Phone'], ['roles', 'Role(s)'], ['lifecycle', 'Lifecycle'], ['asset', 'Current asset'], ['site', 'Current site'], ['status', 'Status']] as [PeopleSort, string][]).map(([key, label]) => <th aria-sort={sortKey === key ? (sortDirection === "asc" ? "ascending" : "descending") : "none"} key={key} scope="col"><SortButton active={sortKey === key} direction={sortDirection} label={label} onClick={() => changeSort(key)} /></th>)}<th scope="col">Actions</th></tr></thead><tbody>
        {shown.length === 0 && <EmptyTableRow colSpan={8} detail="Adjust the filters or add the first person." title="No people match" />}
        {shown.map((group) => { const active = group.memberships.filter((item) => item.status !== "INACTIVE"); const driver = active.find((item) => item.role === "DRIVER"); const currentAsset = driver?.current_asset_id ? assetById.get(driver.current_asset_id) : undefined; const personSites = [...new Set(active.flatMap((item) => item.sites.map((site) => site.site_name)))]; const operationalStatus = driver?.has_active_duty ? "On duty" : driver?.has_active_assignment ? "Assigned · off duty" : driver ? "Available" : active.some((item) => item.role === "OWNER_ADMIN") ? "Owner access" : `${personSites.length} site${personSites.length === 1 ? "" : "s"}`; return <tr key={group.userId}><td data-label="Name"><strong>{group.displayName}</strong></td><td data-label="Phone">{group.phone}</td><td data-label="Role(s)"><div className="owner-chip-list">{active.map((membership) => <span className="owner-chip" key={membership.membership_id}>{membership.role === "OWNER_ADMIN" ? "Owner" : title(membership.role)}</span>)}</div></td><td data-label="Lifecycle"><div className="owner-chip-list">{group.memberships.map((membership) => <StatusChip key={membership.membership_id} label={`${membership.role === "OWNER_ADMIN" ? "Owner" : title(membership.role)} · ${title(membership.status)}`} status={membership.status} />)}</div></td><td data-label="Current asset">{currentAsset ? <><strong>{assetLabel(currentAsset)}</strong><small>{currentAsset.registration_number || title(currentAsset.asset_type)}</small></> : <span className="owner-dim">—</span>}</td><td data-label="Current site">{driver?.current_site_name || personSites.join(", ") || <span className="owner-dim">—</span>}</td><td data-label="Status"><StatusChip label={operationalStatus} status={driver?.has_active_duty ? "ON_DUTY" : driver?.has_active_assignment ? "ASSIGNED" : "AVAILABLE"} /></td><td data-label="Actions"><button className="owner-text-button" onClick={() => setEditing(group)} type="button">Manage person</button></td></tr>; })}
      </tbody></OperationsTable>
      <DetailsDialog onClose={() => setEditing(null)} open={Boolean(editing)} title={editing ? `Manage ${editing.displayName}` : "Manage person"}>{editing && <div className="owner-dialog-form"><dl className="owner-detail-list"><div><dt>Name</dt><dd>{editing.displayName}</dd></div><div><dt>Phone</dt><dd>{editing.phone}</dd></div></dl><h3>Roles and operational setup</h3><div className="owner-role-management">{editing.memberships.map((membership) => <div key={membership.membership_id}><div><strong>{membership.role === "OWNER_ADMIN" ? "Owner" : title(membership.role)}</strong><StatusChip status={membership.status} /></div>{membership.role === "OWNER_ADMIN" ? <small>Sole Owner protection is enforced by the server.</small> : <div className="owner-row-actions">{membership.status === "INACTIVE" ? <button onClick={() => { setOperation({ action: "ACTIVATE_PERSON", person_membership_id: membership.membership_id, selected_site_ids: [] }); setEditing(null); }} type="button">Reactivate</button> : <>{membership.role === "SUPERVISOR" && <button onClick={() => { setOperation({ action: "SET_SUPERVISOR_SITES", person_membership_id: membership.membership_id, selected_site_ids: membership.sites.map((site) => site.site_id) }); setEditing(null); }} type="button">Manage Site access</button>}{membership.role === "DRIVER" && !membership.has_active_assignment && <button onClick={() => { setOperation({ action: "ASSIGN_DRIVER", driver_membership_id: membership.membership_id }); setEditing(null); }} type="button">Assign asset</button>}<button className="owner-text-button--danger" onClick={() => { setOperation({ action: "DEACTIVATE_PERSON", person_membership_id: membership.membership_id }); setEditing(null); }} type="button">Deactivate role</button></>}</div>}</div>)}</div><h3>Add role</h3><div className="owner-row-actions">{(["DRIVER", "SUPERVISOR"] as const).filter((candidate) => !editing.memberships.some((item) => item.role === candidate)).map((candidate) => <button disabled={mutation.busy} key={candidate} onClick={() => void grantRole(editing.phone, editing.displayName, candidate).then((ok) => { if (ok) setEditing(null); })} type="button">Add {candidate === "DRIVER" ? "Driver / Operator" : "Supervisor"}</button>)}</div></div>}</DetailsDialog>
      <OwnerRelationshipWizard apiRequest={apiRequest} assets={assets} initialIntent={operation} onClose={() => setOperation(null)} onComplete={reload} open={Boolean(operation)} people={people} sites={sites} />
    </section>
  );
}

type SiteDraft = { name: string; short_name: string; location_description: string };
const blankSite: SiteDraft = { name: "", short_name: "", location_description: "" };
type SiteSort = "shortName" | "name" | "supervisors" | "assets" | "status";

export function SitesPanel({ sites, people, assets = [], apiRequest, reload, setError }: Common & { sites: OwnerSite[]; people: OwnerPerson[]; assets?: OwnerAsset[] }) {
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
      <DetailsDialog onClose={() => setDetails(null)} open={Boolean(details)} title={details ? `${siteLabel(details)} details` : "Site details"}>{details && <div className="owner-dialog-form"><dl className="owner-detail-list"><div><dt>Full site name</dt><dd>{details.name}</dd></div><div><dt>Internal code</dt><dd><code>{details.code}</code></dd></div><div><dt>Location</dt><dd>{details.location_description || "Not set"}</dd></div></dl><h3>Supervisor access</h3><div className="owner-chip-list">{details.supervisors.map((supervisor) => <span className="owner-chip" key={supervisor.membership_id}>{supervisor.display_name}<button aria-label={`Revoke ${supervisor.display_name} from ${siteLabel(details)}`} onClick={() => void mutation.run("Supervisor access removed.", () => apiRequest(`/api/v1/owner/sites/${details.id}/supervisors/${supervisor.membership_id}`, { method: "DELETE" })).then((ok) => { if (ok) setDetails(null); })} type="button">×</button></span>)}</div>{details.status === "ACTIVE" && <form className="owner-inline-operation" onSubmit={(event) => { event.preventDefault(); if (!grant) return; void mutation.run("Supervisor access granted.", () => apiRequest(`/api/v1/owner/sites/${details.id}/supervisors`, { method: "POST", body: JSON.stringify({ supervisor_membership_id: grant }) })).then((ok) => { if (ok) setDetails(null); }); }}><label>Grant Supervisor<select aria-label={`Supervisor for ${siteLabel(details)}`} onChange={(event) => setGrant(event.target.value)} required value={grant}><option value="">Choose Supervisor…</option>{supervisors.filter((person) => !details.supervisors.some((item) => item.membership_id === person.membership_id)).map((person) => <option key={person.membership_id} value={person.membership_id}>{person.display_name}</option>)}</select></label><button disabled={mutation.busy} type="submit">Grant access</button></form>}</div>}</DetailsDialog>
      <OwnerRelationshipWizard apiRequest={apiRequest} assets={assets} initialIntent={operation} onClose={() => setOperation(null)} onComplete={reload} open={Boolean(operation)} people={people} sites={sites} />
    </section>
  );
}

type DeploymentSort = "asset" | "registration" | "type" | "ownership" | "site" | "operator" | "duty" | "date";

export function DeploymentsPanel({ assets, sites, people = [], apiRequest, reload, setError, onViewAssignments }: Common & { assets: OwnerAsset[]; sites: OwnerSite[]; people?: OwnerPerson[]; onViewAssignments?: () => void }) {
  const mutation = useOwnerAction({ reload, setError });
  const selectable = assets.filter((asset) => asset.status === "ACTIVE" && !asset.current_deployment);
  const deployed = assets.filter((asset) => asset.current_deployment);
  const activeSites = sites.filter((site) => site.status === "ACTIVE");
  const [assetId, setAssetId] = useState(""); const [siteId, setSiteId] = useState(""); const [query, setQuery] = useState(""); const [operation, setOperation] = useState<OwnerOperationIntent | null>(null); const [historyAsset, setHistoryAsset] = useState<OwnerAsset | null>(null); const [history, setHistory] = useState<AssetSiteDeployment[]>([]); const [historyLoading, setHistoryLoading] = useState(false); const [historyError, setHistoryError] = useState(""); const [sortKey, setSortKey] = useState<DeploymentSort>("asset"); const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const selectedAsset = assets.find((asset) => asset.id === assetId);
  const changeSort = (next: DeploymentSort) => { const value = toggleSort(sortKey, next, sortDirection); setSortKey(value.key); setSortDirection(value.direction); };
  const shown = useMemo(() => { const value = (asset: OwnerAsset) => sortKey === "asset" ? assetLabel(asset) : sortKey === "registration" ? asset.registration_number : sortKey === "type" ? asset.asset_type : sortKey === "ownership" ? asset.ownership_type : sortKey === "site" ? asset.current_deployment?.site_name : sortKey === "operator" ? asset.active_assignment?.driver_name : sortKey === "duty" ? (personForAsset(asset, people)?.has_active_duty ? "ON_DUTY" : asset.has_active_assignment ? "OFF_DUTY" : "UNASSIGNED") : asset.current_deployment?.starts_at; return deployed.filter((asset) => !query.trim() || assetSearchText(asset).includes(query.trim().toLowerCase())).sort((left, right) => (sortDirection === "asc" ? 1 : -1) * compareText(value(left), value(right))); }, [deployed, people, query, sortDirection, sortKey]);
  const deploy = (event: FormEvent) => { event.preventDefault(); setOperation({ action: "DEPLOY_ASSET", asset_id: assetId, site_id: siteId }); };
  const openHistory = async (asset: OwnerAsset) => { setHistoryAsset(asset); setHistory([]); setHistoryError(""); setHistoryLoading(true); try { setHistory(await apiRequest<AssetSiteDeployment[]>(`/api/v1/owner/assets/${asset.id}/deployments`)); } catch (caught) { setHistoryError(caught instanceof Error ? caught.message : "Could not load deployment history."); } finally { setHistoryLoading(false); } };
  return (
    <section className="owner-panel">
      <PanelHeading description="Deploy available assets, then manage current site placement from the table." eyebrow="Fleet management" title="Deployments" />
      <InlineFeedback error={mutation.localError} success={mutation.success} />
      <form className="owner-operation-strip" onSubmit={(event) => void deploy(event)}><div><p className="owner-section-eyebrow">New deployment</p><h3>Deploy asset</h3><p>Only active, currently undeployed assets are available.</p></div><label>Asset<select aria-label="Asset" onChange={(event) => setAssetId(event.target.value)} required value={assetId}><option value="">Choose undeployed asset…</option>{selectable.map((asset) => <option key={asset.id} value={asset.id}>{assetLabel(asset)} · {title(asset.asset_type)}</option>)}</select></label><label>Destination site<select aria-label="Destination site" onChange={(event) => setSiteId(event.target.value)} required value={siteId}><option value="">Choose site…</option>{activeSites.map((site) => <option key={site.id} value={site.id}>{siteLabel(site)}</option>)}</select></label><button disabled={mutation.busy || !selectedAsset} type="submit">Deploy asset</button></form>
      <FilterToolbar><label className="owner-search-field"><span>Search deployed assets</span><input aria-label="Search deployed assets" onChange={(event) => setQuery(event.target.value)} placeholder="Asset, registration, site or operator" type="search" value={query} /></label></FilterToolbar>
      <OperationsTable label="Current deployments"><thead><tr>{([['asset', 'Asset'], ['registration', 'Registration'], ['type', 'Type'], ['ownership', 'Ownership'], ['site', 'Current site'], ['operator', 'Driver / Operator'], ['duty', 'Duty'], ['date', 'Deployment date']] as [DeploymentSort, string][]).map(([key, label]) => <th aria-sort={sortKey === key ? (sortDirection === "asc" ? "ascending" : "descending") : "none"} key={key} scope="col"><SortButton active={sortKey === key} direction={sortDirection} label={label} onClick={() => changeSort(key)} /></th>)}<th scope="col">Actions</th></tr></thead><tbody>
        {shown.length === 0 && <EmptyTableRow colSpan={9} detail="Use Deploy asset above when an active asset and site are ready." title="No current deployments" />}
        {shown.map((asset) => { const person = personForAsset(asset, people); return <tr key={asset.id}><td data-label="Asset"><strong>{assetLabel(asset)}</strong></td><td data-label="Registration">{asset.registration_number || "—"}</td><td data-label="Type">{title(asset.asset_type)}</td><td data-label="Ownership"><StatusChip status={asset.ownership_type} /></td><td data-label="Current site"><strong>{asset.current_deployment?.site_name}</strong></td><td data-label="Driver / Operator">{asset.active_assignment?.driver_name || <span className="owner-dim">Unassigned</span>}</td><td data-label="Duty">{person?.has_active_duty ? <StatusChip label="On duty" status="ON_DUTY" /> : <StatusChip label={asset.has_active_assignment ? "Off duty" : "Not assigned"} status="AVAILABLE" />}</td><td data-label="Deployment date">{asset.current_deployment ? dateTime(asset.current_deployment.starts_at) : "—"}</td><td data-label="Actions"><div className="owner-row-actions"><button className="owner-text-button" onClick={() => setOperation({ action: "MOVE_DEPLOYMENT", asset_id: asset.id })} type="button">Move</button><button className="owner-text-button owner-text-button--danger" onClick={() => setOperation({ action: "REMOVE_DEPLOYMENT", asset_id: asset.id })} type="button">Remove deployment</button><button className="owner-text-button" onClick={() => void openHistory(asset)} type="button">View history</button></div></td></tr>; })}
      </tbody></OperationsTable>
      <OwnerRelationshipWizard apiRequest={apiRequest} assets={assets} initialIntent={operation} onClose={() => setOperation(null)} onComplete={async () => { setAssetId(""); setSiteId(""); await reload(); }} onViewAssignments={onViewAssignments} open={Boolean(operation)} people={people} sites={sites} />
      <DetailsDialog onClose={() => setHistoryAsset(null)} open={Boolean(historyAsset)} title={`${historyAsset ? assetLabel(historyAsset) : "Asset"} deployment history`}><InlineFeedback error={historyError} />{historyLoading ? <div aria-busy="true" className="owner-skeleton-list"><span /><span /><span /></div> : <OperationsTable label="Deployment history"><thead><tr><th scope="col">Site</th><th scope="col">Started</th><th scope="col">Ended</th><th scope="col">Status</th></tr></thead><tbody>{history.length === 0 && <EmptyTableRow colSpan={4} title="No deployment history" />}{history.map((item) => <tr key={item.id}><td data-label="Site"><strong>{item.site_name}</strong></td><td data-label="Started">{dateTime(item.starts_at)}</td><td data-label="Ended">{item.ends_at ? dateTime(item.ends_at) : "—"}</td><td data-label="Status"><StatusChip label={item.ends_at ? "Completed" : "Current"} status={item.ends_at ? "INACTIVE" : "DEPLOYED"} /></td></tr>)}</tbody></OperationsTable>}</DetailsDialog>
    </section>
  );
}

type AssignmentSort = "asset" | "registration" | "type" | "ownership" | "site" | "operator" | "phone" | "regularDuty" | "duty" | "date";

export function AssignmentsPanel({ assets, people = [], sites = [], apiRequest, reload }: Common & { assets: OwnerAsset[]; people?: OwnerPerson[]; sites?: OwnerSite[] }) {
  const selectable = assets.filter((asset) => asset.status === "ACTIVE" && !asset.has_active_assignment);
  const assigned = assets.filter((asset) => asset.active_assignment);
  const availableDrivers = people.filter((person) => person.role === "DRIVER" && !person.has_active_assignment);
  const [assetId, setAssetId] = useState(""); const [driverId, setDriverId] = useState(""); const [siteId, setSiteId] = useState(""); const [minutes, setMinutes] = useState("600"); const [query, setQuery] = useState(""); const [operation, setOperation] = useState<OwnerOperationIntent | null>(null); const [historyAsset, setHistoryAsset] = useState<OwnerAsset | null>(null); const [history, setHistory] = useState<DriverAssetAssignment[]>([]); const [historyLoading, setHistoryLoading] = useState(false); const [historyError, setHistoryError] = useState(""); const [sortKey, setSortKey] = useState<AssignmentSort>("asset"); const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const selected = assets.find((asset) => asset.id === assetId);
  const changeSort = (next: AssignmentSort) => { const value = toggleSort(sortKey, next, sortDirection); setSortKey(value.key); setSortDirection(value.direction); };
  const shown = useMemo(() => { const value = (asset: OwnerAsset) => { const assignment = asset.active_assignment; const person = personForAsset(asset, people); return sortKey === "asset" ? assetLabel(asset) : sortKey === "registration" ? asset.registration_number : sortKey === "type" ? asset.asset_type : sortKey === "ownership" ? asset.ownership_type : sortKey === "site" ? assignment?.site_name : sortKey === "operator" ? assignment?.driver_name : sortKey === "phone" ? person?.phone : sortKey === "regularDuty" ? String(assignment?.regular_duty_minutes ?? 0).padStart(8, "0") : sortKey === "duty" ? (person?.has_active_duty ? "ON_DUTY" : "OFF_DUTY") : assignment?.starts_at; }; return assigned.filter((asset) => !query.trim() || assetSearchText(asset).includes(query.trim().toLowerCase())).sort((left, right) => (sortDirection === "asc" ? 1 : -1) * compareText(value(left), value(right))); }, [assigned, people, query, sortDirection, sortKey]);
  const assign = (event: FormEvent) => { event.preventDefault(); setOperation({ action: "ASSIGN_DRIVER", asset_id: assetId, driver_membership_id: driverId, site_id: selected?.current_deployment ? selected.current_deployment.site_id : siteId || null, activate_membership: false, regular_duty_minutes: Number(minutes) }); };
  const openHistory = async (asset: OwnerAsset) => { setHistoryAsset(asset); setHistory([]); setHistoryError(""); setHistoryLoading(true); try { setHistory(await apiRequest<DriverAssetAssignment[]>(`/api/v1/owner/assets/${asset.id}/assignments`)); } catch (caught) { setHistoryError(caught instanceof Error ? caught.message : "Could not load assignment history."); } finally { setHistoryLoading(false); } };
  return (
    <section className="owner-panel">
      <PanelHeading description="Pre-assign invited or active Drivers / Operators to deployed assets. Ownership does not change eligibility." eyebrow="Fleet management" title="Assignments" />
      <form className="owner-operation-strip" onSubmit={assign}><div><p className="owner-section-eyebrow">New assignment</p><h3>Assign Driver / Operator</h3><p>Choose an available asset. Undeployed assets can be deployed and assigned in one operation.</p></div><label>Asset<select aria-label="Assignment asset" onChange={(event) => { setAssetId(event.target.value); setSiteId(""); }} required value={assetId}><option value="">Choose available asset…</option>{selectable.map((asset) => <option key={asset.id} value={asset.id}>{assetLabel(asset)} · {asset.current_deployment?.site_name || "Undeployed"}</option>)}</select></label><label>Driver / Operator<select aria-label="Driver / Operator" disabled={!assetId} onChange={(event) => setDriverId(event.target.value)} required value={driverId}><option value="">Choose eligible person…</option>{availableDrivers.map((candidate) => <option key={candidate.membership_id} value={candidate.membership_id}>{candidate.display_name} · {candidate.phone} · {candidate.status}</option>)}</select></label>{selected && !selected.current_deployment && <label>Deploy to<select aria-label="Assignment Site" onChange={(event) => setSiteId(event.target.value)} required value={siteId}><option value="">Choose Site…</option>{sites.filter((site) => site.status === "ACTIVE").map((site) => <option key={site.id} value={site.id}>{siteLabel(site)}</option>)}</select></label>}<label>Regular duty<select aria-label="Regular duty" onChange={(event) => setMinutes(event.target.value)} value={minutes}><option value="480">8 hours</option><option value="600">10 hours</option><option value="720">12 hours</option></select></label><button disabled={!selected || !driverId || (!selected.current_deployment && !siteId)} type="submit">Review assignment</button></form>
      <FilterToolbar><label className="owner-search-field"><span>Search assignments</span><input aria-label="Search assignments" onChange={(event) => setQuery(event.target.value)} placeholder="Asset, registration, site or operator" type="search" value={query} /></label></FilterToolbar>
      <OperationsTable label="Current assignments"><thead><tr>{([['asset', 'Asset'], ['registration', 'Registration'], ['type', 'Type'], ['ownership', 'Ownership'], ['site', 'Site'], ['operator', 'Driver / Operator'], ['phone', 'Phone'], ['regularDuty', 'Regular duty'], ['duty', 'Duty status'], ['date', 'Assignment since']] as [AssignmentSort, string][]).map(([key, label]) => <th aria-sort={sortKey === key ? (sortDirection === "asc" ? "ascending" : "descending") : "none"} key={key} scope="col"><SortButton active={sortKey === key} direction={sortDirection} label={label} onClick={() => changeSort(key)} /></th>)}<th scope="col">Actions</th></tr></thead><tbody>
        {shown.length === 0 && <EmptyTableRow colSpan={11} detail="Assign an eligible Driver / Operator using the form above." title="No current assignments" />}
        {shown.map((asset) => { const assignment = asset.active_assignment!; const person = personForAsset(asset, people); return <tr key={asset.id}><td data-label="Asset"><strong>{assetLabel(asset)}</strong></td><td data-label="Registration">{asset.registration_number || "—"}</td><td data-label="Type">{title(asset.asset_type)}</td><td data-label="Ownership"><StatusChip status={asset.ownership_type} /></td><td data-label="Site">{assignment.site_name}</td><td data-label="Driver / Operator"><strong>{assignment.driver_name}</strong>{person?.status === "INVITED" && <small>Invited · first login pending</small>}</td><td data-label="Phone">{person?.phone || "—"}</td><td data-label="Regular duty">{(assignment.regular_duty_minutes ?? 600) / 60} hours</td><td data-label="Duty status">{person?.has_active_duty ? <StatusChip label="On duty" status="ON_DUTY" /> : <StatusChip label="Off duty" status="AVAILABLE" />}</td><td data-label="Assignment since">{dateTime(assignment.starts_at)}</td><td data-label="Actions"><div className="owner-row-actions"><button className="owner-text-button" onClick={() => setOperation({ action: "REASSIGN_DRIVER", asset_id: asset.id, regular_duty_minutes: assignment.regular_duty_minutes ?? 600 })} type="button">Change Driver / Operator</button><button className="owner-text-button owner-text-button--danger" onClick={() => setOperation({ action: "END_ASSIGNMENT", asset_id: asset.id })} type="button">End assignment</button><button className="owner-text-button" onClick={() => void openHistory(asset)} type="button">View history</button></div></td></tr>; })}
      </tbody></OperationsTable>
      <OwnerRelationshipWizard apiRequest={apiRequest} assets={assets} initialIntent={operation} onClose={() => setOperation(null)} onComplete={async () => { setAssetId(""); setDriverId(""); setSiteId(""); await reload(); }} open={Boolean(operation)} people={people} sites={sites} />
      <DetailsDialog onClose={() => setHistoryAsset(null)} open={Boolean(historyAsset)} title={`${historyAsset ? assetLabel(historyAsset) : "Asset"} assignment history`}><InlineFeedback error={historyError} />{historyLoading ? <div aria-busy="true" className="owner-skeleton-list"><span /><span /><span /></div> : <OperationsTable label="Assignment history"><thead><tr><th scope="col">Driver / Operator</th><th scope="col">Site</th><th scope="col">Regular duty</th><th scope="col">Started</th><th scope="col">Ended</th></tr></thead><tbody>{history.length === 0 && <EmptyTableRow colSpan={5} title="No assignment history" />}{history.map((item) => <tr key={item.assignment_id}><td data-label="Driver / Operator"><strong>{item.driver_name}</strong></td><td data-label="Site">{item.site_name}</td><td data-label="Regular duty">{item.regular_duty_minutes / 60} hours</td><td data-label="Started">{dateTime(item.starts_at)}</td><td data-label="Ended">{item.ends_at ? dateTime(item.ends_at) : <StatusChip label="Current" status="ACTIVE" />}</td></tr>)}</tbody></OperationsTable>}</DetailsDialog>
    </section>
  );
}
