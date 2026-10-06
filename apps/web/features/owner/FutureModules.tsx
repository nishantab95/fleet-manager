"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { API_BASE, type WebRequest } from "../../lib/api/client";
import type {
  AssetCompliance,
  AssetDocument,
  AssetDocumentPolicy,
  AttendanceDay,
  AttendanceLocationSnapshot,
  CompensationProfile,
  FuelImportBatch,
  FuelReconciliation,
  FuelTransaction,
  GeofenceTransition,
  InAppNotification,
  LatestTelematics,
  MaintenanceRecord,
  MaintenanceSchedule,
  MaintenanceWorkOrder,
  OwnerAsset,
  OwnerPerson,
  OwnerSite,
  PayrollLine,
  PayrollPeriod,
  TelematicsMapping,
  TelematicsMeterDiscrepancy,
} from "../../lib/types";
import { EmptyTableRow, InlineFeedback, OperationsTable, PanelHeading, StatusChip } from "./OwnerUi";

type ModuleProps = {
  apiRequest: WebRequest;
  assets: OwnerAsset[];
  sites: OwnerSite[];
  accessToken: string;
  multiMeterEnabled?: boolean;
};

type WorkforceProps = Pick<ModuleProps, "apiRequest" | "accessToken"> & {
  people: OwnerPerson[];
  attendanceLocationEnabled: boolean;
};

function labelForAsset(assets: OwnerAsset[], id: string) {
  const asset = assets.find((item) => item.id === id);
  return asset ? asset.short_name || asset.registration_number || asset.asset_code : id;
}

function tone(status: string): "positive" | "warning" | "danger" | "neutral" | "info" {
  if (["ACTIVE", "VALID", "MATCHED", "COMPLETED", "IMPORTED", "NOT_DUE"].includes(status)) return "positive";
  if (["DUE_SOON", "EXPIRING_SOON", "SCHEDULED", "WITHIN_TOLERANCE", "UNREAD"].includes(status)) return "warning";
  if (["OVERDUE", "EXPIRED", "MISSING", "MISMATCH", "INVALID", "CANCELLED"].includes(status)) return "danger";
  if (["DUE", "IN_PROGRESS", "ENTER", "EXIT"].includes(status)) return "info";
  return "neutral";
}

function ModuleTabs<T extends string>({ values, active, onChange }: { values: readonly T[]; active: T; onChange: (value: T) => void }) {
  return <div aria-label="Module sections" className="owner-module-tabs" role="tablist">
    {values.map((value) => <button aria-selected={active === value} className={active === value ? "is-active" : ""} key={value} onClick={() => onChange(value)} role="tab" type="button">{value}</button>)}
  </div>;
}

async function downloadPrivate(path: string, token: string, fileName: string) {
  const response = await fetch(`${API_BASE}${path}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) throw new Error("Download failed.");
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

export function MaintenanceModule({ apiRequest, assets, accessToken, multiMeterEnabled = false }: ModuleProps) {
  const tabs = ["Overview", "Due", "Work Orders", "Schedules", "History"] as const;
  const [tab, setTab] = useState<(typeof tabs)[number]>("Overview");
  const [schedules, setSchedules] = useState<MaintenanceSchedule[]>([]);
  const [orders, setOrders] = useState<MaintenanceWorkOrder[]>([]);
  const [history, setHistory] = useState<MaintenanceRecord[]>([]);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const reload = useCallback(async () => {
    try {
      const [nextSchedules, nextOrders, nextHistory] = await Promise.all([
        apiRequest<MaintenanceSchedule[]>("/api/v1/owner/maintenance/schedules"),
        apiRequest<MaintenanceWorkOrder[]>("/api/v1/owner/maintenance/work-orders"),
        apiRequest<MaintenanceRecord[]>("/api/v1/owner/maintenance/history"),
      ]);
      setSchedules(nextSchedules); setOrders(nextOrders); setHistory(nextHistory); setError("");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Maintenance data could not be loaded."); }
  }, [apiRequest]);
  useEffect(() => { void Promise.resolve().then(reload); }, [reload]);
  const due = schedules.filter((item) => ["DUE_SOON", "DUE", "OVERDUE"].includes(item.due_status));
  const assetOptions = assets.map((asset) => <option key={asset.id} value={asset.id}>{labelForAsset(assets, asset.id)}</option>);

  const createSchedule = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setError(""); setSuccess("");
    const data = new FormData(event.currentTarget);
    const basis = String(data.get("interval_basis"));
    try {
      await apiRequest("/api/v1/owner/maintenance/schedules", { method: "POST", body: JSON.stringify({
        asset_id: data.get("asset_id"), maintenance_type: data.get("maintenance_type"),
        custom_label: data.get("custom_label") || null, interval_basis: basis,
        interval_value: data.get("interval_value"), warning_threshold: data.get("warning_threshold") || "0",
        last_service_meter: basis === "DATE" ? null : data.get("baseline") || null,
        last_service_date: basis === "DATE" ? data.get("baseline_date") || null : null,
      }) });
      event.currentTarget.reset(); setSuccess("Maintenance schedule created."); await reload();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Schedule could not be created."); }
  };
  const createOrder = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    try {
      await apiRequest("/api/v1/owner/maintenance/work-orders", { method: "POST", body: JSON.stringify({ asset_id: data.get("asset_id"), schedule_id: data.get("schedule_id") || null, title: data.get("title"), vendor_name: data.get("vendor_name") || null, scheduled_for: data.get("scheduled_for") || null }) });
      event.currentTarget.reset(); setSuccess("Work order created."); await reload();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Work order could not be created."); }
  };
  const completeOrder = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget); const id = String(data.get("work_order_id"));
    try {
      await apiRequest(`/api/v1/owner/maintenance/work-orders/${id}/complete`, { method: "POST", body: JSON.stringify({ performed_on: data.get("performed_on"), meter_value: multiMeterEnabled ? null : data.get("meter_value") || null, odometer_km: multiMeterEnabled ? data.get("odometer_km") || null : null, hour_meter_hours: multiMeterEnabled ? data.get("hour_meter_hours") || null : null, vendor_name: data.get("vendor_name") || null, labor_cost: data.get("labor_cost") || "0", parts_cost: data.get("parts_cost") || "0", other_cost: data.get("other_cost") || "0", notes: data.get("notes") || null }) });
      event.currentTarget.reset(); setSuccess("Work order completed and immutable service history created."); await reload();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Work order could not be completed."); }
  };
  const setScheduleStatus = async (item: MaintenanceSchedule) => {
    try { await apiRequest(`/api/v1/owner/maintenance/schedules/${item.id}/status`, { method: "PATCH", body: JSON.stringify({ status: item.status === "ACTIVE" ? "INACTIVE" : "ACTIVE" }) }); await reload(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Schedule could not be updated."); }
  };
  const setOrderStatus = async (id: string, status: string) => {
    try { await apiRequest(`/api/v1/owner/maintenance/work-orders/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) }); await reload(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Work order could not be updated."); }
  };

  return <div className="owner-page">
    <PanelHeading eyebrow="Asset care" title="Maintenance" description="Due-state monitoring, work orders, immutable service history, and cost tracking." action={<button className="secondary" onClick={() => void downloadPrivate("/api/v1/owner/maintenance/export.xlsx", accessToken, "maintenance.xlsx")} type="button">Export Excel</button>} />
    <ModuleTabs active={tab} onChange={setTab} values={tabs} />
    <InlineFeedback error={error} success={success} />
    {tab === "Overview" && <div className="owner-kpi-grid"><article><span>Active schedules</span><strong>{schedules.filter((x) => x.status === "ACTIVE").length}</strong></article><article><span>Attention needed</span><strong>{due.length}</strong></article><article><span>Open work orders</span><strong>{orders.filter((x) => !["COMPLETED", "CANCELLED"].includes(x.status)).length}</strong></article></div>}
    {tab === "Due" && <ScheduleTable assets={assets} rows={due} empty="No maintenance is due." />}
    {tab === "Schedules" && <>
      <form className="owner-form-panel" onSubmit={createSchedule}><div className="owner-form-heading"><div><h3>New schedule</h3><p>Unknown baselines remain unknown until a verified reading or service is recorded.</p></div></div><div className="owner-form-grid">
        <label>Asset<select name="asset_id" required><option value="">Select asset</option>{assetOptions}</select></label>
        <label>Maintenance type<select name="maintenance_type" required><option value="ENGINE_OIL">Engine oil</option><option value="HYDRAULIC_OIL">Hydraulic oil</option><option value="GENERAL_SERVICE">General service</option><option value="FITNESS_INSPECTION">Fitness inspection</option><option value="CUSTOM">Custom</option></select></label>
        <label>Custom label<input maxLength={120} name="custom_label" /></label>
        <label>Basis<select name="interval_basis" required><option value="KM">Kilometres</option><option value="HMR">Hour meter</option><option value="DATE">Calendar days</option></select></label>
        <label>Interval<input min="0.01" name="interval_value" required step="0.01" type="number" /></label>
        <label>Warning threshold<input min="0" name="warning_threshold" step="0.01" type="number" /></label>
        <label>Last meter baseline<input min="0" name="baseline" step="0.01" type="number" /></label>
        <label>Last service date<input name="baseline_date" type="date" /></label>
      </div><div className="owner-form-actions"><button type="submit">Create schedule</button></div></form>
      <ScheduleTable assets={assets} rows={schedules} empty="No schedules yet." onToggle={setScheduleStatus} />
    </>}
    {tab === "Work Orders" && <>
      <form className="owner-form-panel" onSubmit={createOrder}><div className="owner-form-heading"><div><h3>New work order</h3><p>Link to a recurring schedule when completion should reset its due baseline.</p></div></div><div className="owner-form-grid">
        <label>Asset<select name="asset_id" required><option value="">Select asset</option>{assetOptions}</select></label>
        <label>Schedule<select name="schedule_id"><option value="">Unscheduled</option>{schedules.map((x) => <option key={x.id} value={x.id}>{x.custom_label || x.maintenance_type} · {labelForAsset(assets, x.asset_id)}</option>)}</select></label>
        <label>Title<input maxLength={200} name="title" required /></label><label>Vendor / workshop<input name="vendor_name" /></label><label>Scheduled for<input name="scheduled_for" type="date" /></label>
      </div><div className="owner-form-actions"><button type="submit">Create work order</button></div></form>
      <OperationsTable label="Maintenance work orders"><thead><tr><th>Work order</th><th>Asset</th><th>Status</th><th>Vendor</th><th>Scheduled</th><th>Actions</th></tr></thead><tbody>{orders.length ? orders.map((item) => <tr key={item.id}><td data-label="Work order"><strong>{item.title}</strong></td><td data-label="Asset">{labelForAsset(assets, item.asset_id)}</td><td data-label="Status"><StatusChip status={item.status} tone={tone(item.status)} /></td><td data-label="Vendor">{item.vendor_name || "—"}</td><td data-label="Scheduled">{item.scheduled_for || "—"}</td><td data-label="Actions"><div className="owner-row-actions">{["DRAFT", "SCHEDULED"].includes(item.status) && <button className="owner-text-button" onClick={() => void setOrderStatus(item.id, "IN_PROGRESS")} type="button">Start</button>}{!["COMPLETED", "CANCELLED"].includes(item.status) && <button className="owner-text-button owner-text-button--danger" onClick={() => void setOrderStatus(item.id, "CANCELLED")} type="button">Cancel</button>}</div></td></tr>) : <EmptyTableRow colSpan={6} title="No work orders yet." />}</tbody></OperationsTable>
      <form className="owner-form-panel" onSubmit={completeOrder}><div className="owner-form-heading"><div><h3>Complete work order</h3><p>Completion creates an immutable service record and resets only criteria backed by supplied readings.</p></div></div><div className="owner-form-grid"><label>Work order<select name="work_order_id" required><option value="">Select open order</option>{orders.filter((x) => !["COMPLETED", "CANCELLED"].includes(x.status) && x.schedule_id).map((x) => <option key={x.id} value={x.id}>{x.title}</option>)}</select></label><label>Performed on<input name="performed_on" required type="date" /></label>{multiMeterEnabled ? <><label>Odometer km<input min="0" name="odometer_km" step="0.01" type="number" /></label><label>Hour meter<input min="0" name="hour_meter_hours" step="0.01" type="number" /></label></> : <label>Meter value<input min="0" name="meter_value" step="0.01" type="number" /></label>}<label>Vendor<input name="vendor_name" /></label><label>Labour cost<input min="0" name="labor_cost" step="0.01" type="number" /></label><label>Parts cost<input min="0" name="parts_cost" step="0.01" type="number" /></label><label>Other cost<input min="0" name="other_cost" step="0.01" type="number" /></label><label>Notes<input name="notes" /></label></div><div className="owner-form-actions"><button type="submit">Complete and record</button></div></form>
    </>}
    {tab === "History" && <OperationsTable label="Maintenance history"><thead><tr><th>Date</th><th>Asset</th><th>Meter</th><th>Vendor</th><th>Costs</th><th>Notes</th></tr></thead><tbody>{history.length ? history.map((item) => <tr key={item.id}><td data-label="Date">{item.performed_on}</td><td data-label="Asset">{labelForAsset(assets, item.asset_id)}</td><td data-label="Meter">{item.meter_value ?? "—"}</td><td data-label="Vendor">{item.vendor_name ?? "—"}</td><td data-label="Costs">₹{(Number(item.labor_cost) + Number(item.parts_cost) + Number(item.other_cost)).toFixed(2)}</td><td data-label="Notes">{item.notes ?? "—"}</td></tr>) : <EmptyTableRow colSpan={6} title="No completed service records." />}</tbody></OperationsTable>}
  </div>;
}

function ScheduleTable({ assets, rows, empty, onToggle }: { assets: OwnerAsset[]; rows: MaintenanceSchedule[]; empty: string; onToggle?: (item: MaintenanceSchedule) => void }) {
  return <OperationsTable label="Maintenance schedules"><thead><tr><th>Asset</th><th>Service</th><th>Triggers</th><th>Current</th><th>Next due</th><th>Due state</th><th>Status</th>{onToggle && <th>Action</th>}</tr></thead><tbody>{rows.length ? rows.map((item) => <tr key={item.id}><td data-label="Asset">{labelForAsset(assets, item.asset_id)}</td><td data-label="Service"><strong>{item.custom_label || item.maintenance_type.replaceAll("_", " ")}</strong></td><td data-label="Triggers">{item.criteria.length ? item.criteria.map((criterion) => <small key={criterion.id}>{criterion.basis.replaceAll("_", " ")} · every {criterion.interval_value} · <strong>{criterion.due_status}</strong></small>) : `${item.interval_basis} every ${item.interval_value}`}</td><td data-label="Current">{item.interval_basis === "DATE" ? "Calendar" : item.current_meter ?? "UNKNOWN"}</td><td data-label="Next due">{item.next_due_date ?? item.next_due_meter ?? "See triggers"}</td><td data-label="Due state"><StatusChip status={item.due_status} tone={tone(item.due_status)} /></td><td data-label="Status"><StatusChip status={item.status} /></td>{onToggle && <td data-label="Action"><button className="owner-text-button" onClick={() => onToggle(item)} type="button">{item.status === "ACTIVE" ? "Deactivate" : "Activate"}</button></td>}</tr>) : <EmptyTableRow colSpan={onToggle ? 8 : 7} title={empty} />}</tbody></OperationsTable>;
}

export function DocumentsModule({ apiRequest, assets, accessToken }: ModuleProps) {
  const tabs = ["Compliance", "Documents", "Policies"] as const;
  const [tab, setTab] = useState<(typeof tabs)[number]>("Compliance");
  const [matrix, setMatrix] = useState<AssetCompliance[]>([]); const [documents, setDocuments] = useState<AssetDocument[]>([]); const [policies, setPolicies] = useState<AssetDocumentPolicy[]>([]); const [error, setError] = useState(""); const [success, setSuccess] = useState("");
  const reload = useCallback(async () => { try { const [a, b, c] = await Promise.all([apiRequest<AssetCompliance[]>("/api/v1/owner/asset-documents/compliance"), apiRequest<AssetDocument[]>("/api/v1/owner/asset-documents"), apiRequest<AssetDocumentPolicy[]>("/api/v1/owner/asset-documents/policies")]); setMatrix(a); setDocuments(b); setPolicies(c); setError(""); } catch (caught) { setError(caught instanceof Error ? caught.message : "Compliance data could not be loaded."); } }, [apiRequest]);
  useEffect(() => { void Promise.resolve().then(reload); }, [reload]);
  const savePolicy = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); try { await apiRequest("/api/v1/owner/asset-documents/policies", { method: "PUT", body: JSON.stringify({ asset_type: data.get("asset_type"), ownership_type: data.get("ownership_type") || null, document_type: data.get("document_type"), required: data.get("required") === "on", expiry_warning_days: Number(data.get("expiry_warning_days") || 30) }) }); setSuccess("Compliance policy saved."); await reload(); } catch (caught) { setError(caught instanceof Error ? caught.message : "Policy could not be saved."); } };
  const uploadDocument = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); const file = data.get("file"); if (!(file instanceof File)) return; try { const upload = new FormData(); upload.append("file", file); const evidence = await apiRequest<{ evidence_object_id: string }>(`/api/v1/owner/asset-documents/evidence?upload_id=${crypto.randomUUID()}`, { method: "POST", body: upload }); await apiRequest("/api/v1/owner/asset-documents", { method: "POST", body: JSON.stringify({ asset_id: data.get("asset_id"), document_type: data.get("document_type"), expiry_warning_days: Number(data.get("expiry_warning_days") || 30), evidence_object_id: evidence.evidence_object_id, document_number: data.get("document_number") || null, issue_date: data.get("issue_date") || null, expiry_date: data.get("expiry_date") || null, issuer: data.get("issuer") || null, notes: null }) }); event.currentTarget.reset(); setSuccess("Private document uploaded."); await reload(); } catch (caught) { setError(caught instanceof Error ? caught.message : "Document could not be uploaded."); } };
  return <div className="owner-page"><PanelHeading eyebrow="Compliance" title="Asset documents" description="Policy-driven requirements, expiry visibility, private files, and revision-ready document records." action={<button className="secondary" onClick={() => void downloadPrivate("/api/v1/owner/asset-documents/export.xlsx", accessToken, "asset-compliance.xlsx")} type="button">Export Excel</button>} /><ModuleTabs active={tab} onChange={setTab} values={tabs} /><InlineFeedback error={error} success={success} />
    {tab === "Compliance" && <OperationsTable label="Asset compliance matrix"><thead><tr><th>Asset</th><th>Type</th><th>Document</th><th>Required</th><th>Status</th><th>Expiry</th></tr></thead><tbody>{matrix.length ? matrix.map((item) => <tr key={`${item.asset_id}-${item.policy_id}`}><td data-label="Asset"><strong>{item.asset_code}</strong></td><td data-label="Type">{item.asset_type}</td><td data-label="Document">{item.document_type.replaceAll("_", " ")}</td><td data-label="Required">{item.required ? "Yes" : "No"}</td><td data-label="Status"><StatusChip status={item.status} tone={tone(item.status)} /></td><td data-label="Expiry">{item.expiry_date || "—"}</td></tr>) : <EmptyTableRow colSpan={6} title="Add policies to build the compliance matrix." />}</tbody></OperationsTable>}
    {tab === "Documents" && <><form className="owner-form-panel" onSubmit={uploadDocument}><div className="owner-form-heading"><div><h3>Upload private document</h3><p>PDF, JPEG, PNG, and WebP are stored behind the authenticated private-file boundary.</p></div></div><div className="owner-form-grid"><label>Asset<select name="asset_id" required><option value="">Select asset</option>{assets.map((x) => <option key={x.id} value={x.id}>{labelForAsset(assets, x.id)}</option>)}</select></label><label>Document type<select name="document_type" required><option value="REGISTRATION_CERTIFICATE">Registration certificate</option><option value="INSURANCE">Insurance</option><option value="FITNESS_CERTIFICATE">Fitness certificate</option><option value="POLLUTION_CERTIFICATE">Pollution certificate</option><option value="ROAD_TAX">Road tax</option><option value="PERMIT">Permit</option><option value="RENTAL_AGREEMENT">Rental agreement</option><option value="WARRANTY">Warranty</option></select></label><label>Document number<input name="document_number" /></label><label>Issuer<input name="issuer" /></label><label>Issue date<input name="issue_date" type="date" /></label><label>Expiry date<input name="expiry_date" type="date" /></label><label>Warning days<input defaultValue="30" min="0" name="expiry_warning_days" type="number" /></label><label>Private file<input accept="application/pdf,image/jpeg,image/png,image/webp" name="file" required type="file" /></label></div><div className="owner-form-actions"><button type="submit">Upload document</button></div></form><OperationsTable label="Asset documents"><thead><tr><th>Asset</th><th>Document</th><th>Number</th><th>Revision</th><th>Expiry</th><th>Status</th><th>File</th></tr></thead><tbody>{documents.length ? documents.map((item) => <tr key={item.id}><td data-label="Asset">{labelForAsset(assets, item.asset_id)}</td><td data-label="Document">{item.document_type.replaceAll("_", " ")}</td><td data-label="Number">{item.document_number || "—"}</td><td data-label="Revision">{item.revision_number}</td><td data-label="Expiry">{item.expiry_date || "—"}</td><td data-label="Status"><StatusChip status={item.expiry_status} tone={tone(item.expiry_status)} /></td><td data-label="File"><button className="owner-text-button" onClick={() => void downloadPrivate(`/api/v1/owner/asset-documents/${item.id}/file`, accessToken, `${item.document_type}.bin`)} type="button">Download</button></td></tr>) : <EmptyTableRow colSpan={7} title="No documents uploaded." />}</tbody></OperationsTable></>}
    {tab === "Policies" && <><form className="owner-form-panel" onSubmit={savePolicy}><div className="owner-form-heading"><div><h3>Company document policy</h3><p>Set requirements by asset type and optional ownership scope.</p></div></div><div className="owner-form-grid"><label>Asset type<select name="asset_type" required>{["TIPPER", "EXCAVATOR", "BACKHOE_LOADER", "ROLLER", "GRADER"].map((x) => <option key={x}>{x.replaceAll("_", " ")}</option>)}</select></label><label>Ownership<select name="ownership_type"><option value="">All ownership</option><option>OWNED</option><option>RENTED</option></select></label><label>Document type<select name="document_type"><option>REGISTRATION_CERTIFICATE</option><option>INSURANCE</option><option>FITNESS_CERTIFICATE</option><option>POLLUTION_CERTIFICATE</option><option>ROAD_TAX</option><option>PERMIT</option><option>PURCHASE_INVOICE</option><option>RENTAL_AGREEMENT</option><option>WARRANTY</option></select></label><label>Warning days<input defaultValue="30" min="0" name="expiry_warning_days" required type="number" /></label><label className="checkbox"><input defaultChecked name="required" type="checkbox" /> Required</label></div><div className="owner-form-actions"><button type="submit">Save policy</button></div></form><OperationsTable label="Document policies"><thead><tr><th>Asset type</th><th>Ownership</th><th>Document</th><th>Required</th><th>Warning</th></tr></thead><tbody>{policies.length ? policies.map((item) => <tr key={item.id}><td data-label="Asset type">{item.asset_type}</td><td data-label="Ownership">{item.ownership_type || "ALL"}</td><td data-label="Document">{item.document_type}</td><td data-label="Required">{item.required ? "Yes" : "No"}</td><td data-label="Warning">{item.expiry_warning_days} days</td></tr>) : <EmptyTableRow colSpan={5} title="No document policies." />}</tbody></OperationsTable></>}
  </div>;
}

export function NotificationBell({ apiRequest, onNavigate }: { apiRequest: WebRequest; onNavigate: (tab: "maintenance" | "documents") => void }) {
  const [open, setOpen] = useState(false); const [items, setItems] = useState<InAppNotification[]>([]);
  const reload = useCallback(async () => { setItems(await apiRequest<InAppNotification[]>("/api/v1/owner/notifications")); }, [apiRequest]);
  useEffect(() => { void Promise.resolve().then(reload).catch(() => undefined); }, [reload]);
  const unread = items.filter((x) => x.state === "UNREAD").length;
  const mark = async (id: string) => { await apiRequest(`/api/v1/owner/notifications/${id}`, { method: "PATCH", body: JSON.stringify({ state: "READ" }) }); await reload(); };
  return <div className="owner-notifications"><button aria-expanded={open} aria-label={`Notifications, ${unread} unread`} className="owner-notification-button" onClick={() => setOpen((value) => !value)} type="button">🔔{unread > 0 && <span>{unread}</span>}</button>{open && <section aria-label="Notifications" className="owner-notification-popover"><div><strong>Notifications</strong><button className="owner-text-button" onClick={async () => { await apiRequest("/api/v1/owner/notifications/read-all", { method: "POST" }); await reload(); }} type="button">Mark all read</button></div>{items.length ? items.slice(0, 20).map((item) => <button className={item.state === "UNREAD" ? "is-unread" : ""} key={item.id} onClick={() => { void mark(item.id); const tab = item.deep_link?.tab; if (tab === "maintenance" || tab === "documents") onNavigate(tab); setOpen(false); }} type="button"><strong>{item.title}</strong><span>{item.body}</span><small>{new Date(item.created_at).toLocaleString()}</small></button>) : <p>No notifications.</p>}</section>}</div>;
}

export function TelematicsModule({ apiRequest, assets, sites }: ModuleProps) {
  const tabs = ["Latest", "Mappings", "Geofence timeline", "Meter checks", "Simulator"] as const; const [tab, setTab] = useState<(typeof tabs)[number]>("Latest"); const [mappings, setMappings] = useState<TelematicsMapping[]>([]); const [latest, setLatest] = useState<LatestTelematics[]>([]); const [transitions, setTransitions] = useState<GeofenceTransition[]>([]); const [discrepancies, setDiscrepancies] = useState<TelematicsMeterDiscrepancy[]>([]); const [error, setError] = useState(""); const [success, setSuccess] = useState("");
  const reload = useCallback(async () => { try { const [a, b, c, d] = await Promise.all([apiRequest<TelematicsMapping[]>("/api/v1/owner/telematics/mappings"), apiRequest<LatestTelematics[]>("/api/v1/owner/telematics/latest"), apiRequest<GeofenceTransition[]>("/api/v1/owner/telematics/transitions"), apiRequest<TelematicsMeterDiscrepancy[]>("/api/v1/owner/telematics/meter-discrepancies")]); setMappings(a); setLatest(b); setTransitions(c); setDiscrepancies(d); setError(""); } catch (caught) { setError(caught instanceof Error ? caught.message : "Telematics data could not be loaded."); } }, [apiRequest]); useEffect(() => { void Promise.resolve().then(reload); }, [reload]);
  const createMapping = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); try { await apiRequest("/api/v1/owner/telematics/mappings", { method: "POST", body: JSON.stringify({ asset_id: data.get("asset_id"), provider: data.get("provider"), provider_vehicle_id: data.get("provider_vehicle_id") }) }); event.currentTarget.reset(); setSuccess("Mapping created."); await reload(); } catch (caught) { setError(caught instanceof Error ? caught.message : "Mapping could not be created."); } };
  const setGeofence = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); try { await apiRequest("/api/v1/owner/telematics/geofences", { method: "PUT", body: JSON.stringify({ site_id: data.get("site_id"), radius_m: data.get("radius_m") }) }); setSuccess("Site geofence saved."); } catch (caught) { setError(caught instanceof Error ? caught.message : "Geofence could not be saved."); } };
  const simulate = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); const id = String(data.get("mapping_id")); try { await apiRequest(`/api/v1/owner/telematics/mappings/${id}/positions`, { method: "POST", body: JSON.stringify({ provider_event_id: crypto.randomUUID(), recorded_at: new Date().toISOString(), latitude: data.get("latitude"), longitude: data.get("longitude"), speed_kph: data.get("speed_kph") || null, heading: null, ignition_state: true, odometer_km: data.get("odometer_km") || null, engine_hours: data.get("engine_hours") || null, battery_voltage: data.get("battery_voltage") || null }) }); setSuccess("Simulated position ingested."); await reload(); } catch (caught) { setError(caught instanceof Error ? caught.message : "Position could not be ingested."); } };
  return <div className="owner-page"><PanelHeading eyebrow="Fleet telemetry" title="Telematics" description="Vendor-neutral mappings, idempotent position ingestion, freshness, and circular site-geofence transitions." /><ModuleTabs active={tab} onChange={setTab} values={tabs} /><InlineFeedback error={error} success={success} />
    {tab === "Latest" && <OperationsTable label="Latest telematics positions"><thead><tr><th>Asset</th><th>Provider vehicle</th><th>Recorded</th><th>Coordinates</th><th>Speed</th><th>Odometer / hours</th><th>Battery</th><th>Freshness</th></tr></thead><tbody>{latest.length ? latest.map((item) => <tr key={item.mapping.id}><td data-label="Asset">{labelForAsset(assets, item.mapping.asset_id)}</td><td data-label="Provider vehicle">{item.mapping.provider} · {item.mapping.provider_vehicle_id}</td><td data-label="Recorded">{item.position ? new Date(item.position.recorded_at).toLocaleString() : "Never"}</td><td data-label="Coordinates">{item.position ? `${item.position.latitude}, ${item.position.longitude}` : "—"}</td><td data-label="Speed">{item.position?.speed_kph ?? "—"}</td><td data-label="Odometer / hours">{item.position?.odometer_km ?? "—"} km · {item.position?.engine_hours ?? "—"} h</td><td data-label="Battery">{item.position?.battery_voltage ?? "—"} V</td><td data-label="Freshness"><StatusChip label={item.stale ? "STALE" : "FRESH"} status={item.stale ? "STALE" : "ACTIVE"} tone={item.stale ? "warning" : "positive"} /></td></tr>) : <EmptyTableRow colSpan={8} title="No telematics mappings." />}</tbody></OperationsTable>}
    {tab === "Mappings" && <><form className="owner-form-panel" onSubmit={createMapping}><div className="owner-form-grid"><label>Asset<select name="asset_id" required><option value="">Select asset</option>{assets.map((x) => <option key={x.id} value={x.id}>{labelForAsset(assets, x.id)}</option>)}</select></label><label>Provider<input name="provider" required /></label><label>Provider vehicle ID<input name="provider_vehicle_id" required /></label></div><div className="owner-form-actions"><button type="submit">Create mapping</button></div></form><form className="owner-form-panel" onSubmit={setGeofence}><div className="owner-form-grid"><label>Site<select name="site_id" required><option value="">Select site</option>{sites.map((x) => <option key={x.id} value={x.id}>{x.short_name || x.name}</option>)}</select></label><label>Radius (metres)<input min="1" name="radius_m" required step="0.01" type="number" /></label></div><div className="owner-form-actions"><button type="submit">Save geofence</button></div></form></>}
    {tab === "Geofence timeline" && <OperationsTable label="Geofence transition timeline"><thead><tr><th>Time</th><th>Asset</th><th>Site</th><th>Transition</th><th>Distance</th></tr></thead><tbody>{transitions.length ? transitions.map((item) => <tr key={item.id}><td data-label="Time">{new Date(item.occurred_at).toLocaleString()}</td><td data-label="Asset">{labelForAsset(assets, item.asset_id)}</td><td data-label="Site">{sites.find((x) => x.id === item.site_id)?.short_name || item.site_id}</td><td data-label="Transition"><StatusChip status={item.transition_type} tone="info" /></td><td data-label="Distance">{item.distance_m} m</td></tr>) : <EmptyTableRow colSpan={5} title="No geofence transitions." />}</tbody></OperationsTable>}
    {tab === "Meter checks" && <OperationsTable label="Telemetry versus verified manual meters"><thead><tr><th>Asset</th><th>Meter</th><th>Telemetry</th><th>Manual</th><th>Difference</th><th>Tolerance</th><th>Status</th></tr></thead><tbody>{discrepancies.length ? discrepancies.map((item) => <tr key={item.id}><td data-label="Asset">{labelForAsset(assets, item.asset_id)}</td><td data-label="Meter">{item.meter_type.replaceAll("_", " ")}</td><td data-label="Telemetry">{item.telemetry_value}</td><td data-label="Manual">{item.manual_value ?? "UNKNOWN"}</td><td data-label="Difference">{item.difference ?? "—"}</td><td data-label="Tolerance">{item.tolerance}</td><td data-label="Status"><StatusChip status={item.status} tone={tone(item.status)} /></td></tr>) : <EmptyTableRow colSpan={7} title="No meter comparisons." />}</tbody></OperationsTable>}
    {tab === "Simulator" && <form className="owner-form-panel" onSubmit={simulate}><div className="owner-form-heading"><div><h3>Local position simulator</h3><p>Posts through the same authenticated ingestion API as a future provider adapter.</p></div></div><div className="owner-form-grid"><label>Mapping<select name="mapping_id" required><option value="">Select mapping</option>{mappings.map((x) => <option key={x.id} value={x.id}>{x.provider} · {labelForAsset(assets, x.asset_id)}</option>)}</select></label><label>Latitude<input name="latitude" required step="0.000001" type="number" /></label><label>Longitude<input name="longitude" required step="0.000001" type="number" /></label><label>Speed km/h<input min="0" name="speed_kph" step="0.01" type="number" /></label><label>Odometer km<input min="0" name="odometer_km" step="0.01" type="number" /></label><label>Engine hours<input min="0" name="engine_hours" step="0.01" type="number" /></label><label>Battery voltage<input min="0" name="battery_voltage" step="0.001" type="number" /></label></div><div className="owner-form-actions"><button type="submit">Ingest simulated position</button></div></form>}
  </div>;
}

export function FuelModule({ apiRequest, accessToken }: ModuleProps) {
  const tabs = ["Import", "Transactions", "Reconciliation"] as const; const [tab, setTab] = useState<(typeof tabs)[number]>("Import"); const [batches, setBatches] = useState<FuelImportBatch[]>([]); const [transactions, setTransactions] = useState<FuelTransaction[]>([]); const [reconciliations, setReconciliations] = useState<FuelReconciliation[]>([]); const [error, setError] = useState(""); const [success, setSuccess] = useState("");
  const reload = useCallback(async () => { try { const [a, b, c] = await Promise.all([apiRequest<FuelImportBatch[]>("/api/v1/owner/fuel/imports"), apiRequest<FuelTransaction[]>("/api/v1/owner/fuel/transactions"), apiRequest<FuelReconciliation[]>("/api/v1/owner/fuel/reconciliations")]); setBatches(a); setTransactions(b); setReconciliations(c); setError(""); } catch (caught) { setError(caught instanceof Error ? caught.message : "Fuel integration data could not be loaded."); } }, [apiRequest]); useEffect(() => { void Promise.resolve().then(reload); }, [reload]);
  const importCsv = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); try { await apiRequest("/api/v1/owner/fuel/imports", { method: "POST", body: data }); event.currentTarget.reset(); setSuccess("Fuel file imported. Review row statuses before reconciliation."); await reload(); } catch (caught) { setError(caught instanceof Error ? caught.message : "Fuel CSV could not be imported."); } };
  const reconcile = async (batchId: string) => { try { await apiRequest(`/api/v1/owner/fuel/imports/${batchId}/reconcile`, { method: "POST", body: JSON.stringify({ tolerance_litres: "1.000", time_window_minutes: 720 }) }); setSuccess("Reconciliation completed."); await reload(); } catch (caught) { setError(caught instanceof Error ? caught.message : "Reconciliation failed."); } };
  const resolve = async (id: string) => { const reason = window.prompt("Mandatory resolution reason"); if (!reason?.trim()) return; try { await apiRequest(`/api/v1/owner/fuel/reconciliations/${id}/resolve`, { method: "POST", body: JSON.stringify({ reason }) }); await reload(); } catch (caught) { setError(caught instanceof Error ? caught.message : "Resolution could not be saved."); } };
  return <div className="owner-page"><PanelHeading eyebrow="Fuel controls" title="Fuel reconciliation" description="Strict CSV imports, exact asset mapping, duplicate visibility, and auditable matching to verified driver diesel events." action={<button className="secondary" onClick={() => void downloadPrivate("/api/v1/owner/fuel/export.xlsx", accessToken, "fuel-reconciliation.xlsx")} type="button">Export Excel</button>} /><ModuleTabs active={tab} onChange={setTab} values={tabs} /><InlineFeedback error={error} success={success} />
    {tab === "Import" && <><form className="owner-form-panel" onSubmit={importCsv}><div className="owner-form-heading"><div><h3>Import fuel CSV</h3><p>Asset identifiers must exactly match registration number or asset code; the importer never guesses.</p></div></div><div className="owner-form-grid"><label>Source name<input maxLength={120} name="source_name" required /></label><label>CSV file<input accept="text/csv,.csv" name="file" required type="file" /></label></div><div className="owner-form-actions"><button className="secondary" onClick={() => void downloadPrivate("/api/v1/owner/fuel/template.csv", accessToken, "fuel-import-template.csv")} type="button">Download template</button><button type="submit">Import CSV</button></div></form><OperationsTable label="Fuel import batches"><thead><tr><th>File</th><th>Source</th><th>Status</th><th>Total</th><th>Imported</th><th>Rejected</th><th>Action</th></tr></thead><tbody>{batches.length ? batches.map((item) => <tr key={item.id}><td data-label="File">{item.file_name}</td><td data-label="Source">{item.source_name}</td><td data-label="Status"><StatusChip status={item.status} tone={tone(item.status)} /></td><td data-label="Total">{item.total_rows}</td><td data-label="Imported">{item.imported_rows}</td><td data-label="Rejected">{item.rejected_rows}</td><td data-label="Action"><button className="owner-text-button" onClick={() => void reconcile(item.id)} type="button">Reconcile</button></td></tr>) : <EmptyTableRow colSpan={7} title="No imports yet." />}</tbody></OperationsTable></>}
    {tab === "Transactions" && <OperationsTable label="External fuel transactions"><thead><tr><th>External ID</th><th>Asset identifier</th><th>Occurred</th><th>Litres</th><th>Source</th><th>Row status</th><th>Reason</th></tr></thead><tbody>{transactions.length ? transactions.map((item) => <tr key={item.id}><td data-label="External ID">{item.external_transaction_id}</td><td data-label="Asset identifier">{item.asset_identifier}</td><td data-label="Occurred">{item.occurred_at ? new Date(item.occurred_at).toLocaleString() : "—"}</td><td data-label="Litres">{item.litres ?? "—"}</td><td data-label="Source">{item.source_name}</td><td data-label="Row status"><StatusChip status={item.row_status} tone={tone(item.row_status)} /></td><td data-label="Reason">{item.error_message || "—"}</td></tr>) : <EmptyTableRow colSpan={7} title="No imported transactions." />}</tbody></OperationsTable>}
    {tab === "Reconciliation" && <OperationsTable label="Fuel reconciliations"><thead><tr><th>Transaction</th><th>Driver event</th><th>Status</th><th>Difference</th><th>Tolerance</th><th>Resolution</th></tr></thead><tbody>{reconciliations.length ? reconciliations.map((item) => <tr key={item.id}><td data-label="Transaction">{item.external_transaction_id}</td><td data-label="Driver event">{item.operational_event_id || "—"}</td><td data-label="Status"><StatusChip status={item.status} tone={tone(item.status)} /></td><td data-label="Difference">{item.difference_litres ?? "—"}</td><td data-label="Tolerance">{item.tolerance_litres}</td><td data-label="Resolution">{item.manually_resolved ? item.resolution_reason : <button className="owner-text-button" onClick={() => void resolve(item.id)} type="button">Resolve with reason</button>}</td></tr>) : <EmptyTableRow colSpan={6} title="No reconciliations yet." />}</tbody></OperationsTable>}
  </div>;
}

export function WorkforceModule({ apiRequest, accessToken, people, attendanceLocationEnabled }: WorkforceProps) {
  const tabs = ["Attendance", "Compensation", "Overtime", "Payroll"] as const;
  const [tab, setTab] = useState<(typeof tabs)[number]>("Attendance");
  const [profiles, setProfiles] = useState<CompensationProfile[]>([]);
  const [attendance, setAttendance] = useState<AttendanceDay[]>([]);
  const [periods, setPeriods] = useState<PayrollPeriod[]>([]);
  const [lines, setLines] = useState<PayrollLine[]>([]);
  const [locations, setLocations] = useState<AttendanceLocationSnapshot[]>([]);
  const [selectedPeriod, setSelectedPeriod] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const now = new Date();
  const firstDay = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
  const lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().slice(0, 10);
  const drivers = people.filter((person) => person.role === "DRIVER" && person.status !== "INACTIVE");

  const reload = useCallback(async () => {
    try {
      const [nextProfiles, nextAttendance, nextPeriods, nextLocations] = await Promise.all([
        apiRequest<CompensationProfile[]>("/api/v1/owner/workforce/compensation"),
        apiRequest<AttendanceDay[]>(`/api/v1/owner/workforce/attendance?starts_on=${firstDay}&ends_on=${lastDay}`),
        apiRequest<PayrollPeriod[]>("/api/v1/owner/workforce/payroll-periods"),
        attendanceLocationEnabled ? apiRequest<AttendanceLocationSnapshot[]>("/api/v1/owner/attendance-location/snapshots") : Promise.resolve([]),
      ]);
      setProfiles(nextProfiles); setAttendance(nextAttendance); setPeriods(nextPeriods); setLocations(nextLocations); setError("");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Workforce data could not be loaded."); }
  }, [apiRequest, attendanceLocationEnabled, firstDay, lastDay]);
  useEffect(() => { void Promise.resolve().then(reload); }, [reload]);
  useEffect(() => {
    if (!selectedPeriod) return;
    void apiRequest<PayrollLine[]>(`/api/v1/owner/workforce/payroll-periods/${selectedPeriod}/lines`).then(setLines).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "Payroll lines could not be loaded."));
  }, [apiRequest, selectedPeriod]);

  const createProfile = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    try {
      await apiRequest("/api/v1/owner/workforce/compensation", { method: "POST", body: JSON.stringify({ membership_id: data.get("membership_id"), pay_basis: data.get("pay_basis"), base_amount: data.get("base_amount"), effective_from: data.get("effective_from"), effective_to: data.get("effective_to") || null, standard_duty_minutes: Number(data.get("standard_duty_minutes")), overtime_rate_per_hour: data.get("overtime_rate_per_hour") || "0", notes: null }) });
      event.currentTarget.reset(); setSuccess("Effective-dated compensation profile created."); await reload();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Compensation profile could not be created."); }
  };
  const createPeriod = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    try {
      const period = await apiRequest<PayrollPeriod>("/api/v1/owner/workforce/payroll-periods", { method: "POST", body: JSON.stringify({ starts_on: data.get("starts_on"), ends_on: data.get("ends_on") }) });
      setSelectedPeriod(period.id); setSuccess("Draft payroll calculated from attendance snapshots."); await reload();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Payroll period could not be created."); }
  };
  const transition = async (period: PayrollPeriod) => {
    const next = period.status === "DRAFT" ? "REVIEWED" : "FINALIZED";
    try { await apiRequest(`/api/v1/owner/workforce/payroll-periods/${period.id}/status`, { method: "PATCH", body: JSON.stringify({ status: next }) }); setSuccess(`Payroll ${next.toLowerCase()}.`); await reload(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Payroll status could not be changed."); }
  };
  const adjust = async (line: PayrollLine) => {
    const amount = window.prompt("Adjustment amount (negative is allowed)"); const reason = window.prompt("Mandatory adjustment reason");
    if (!amount || !reason?.trim()) return;
    try { const updated = await apiRequest<PayrollLine>(`/api/v1/owner/workforce/payroll-lines/${line.id}/adjustments`, { method: "POST", body: JSON.stringify({ amount, reason }) }); setLines((current) => current.map((item) => item.id === updated.id ? updated : item)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Adjustment could not be saved."); }
  };

  return <div className="owner-page">
    <PanelHeading eyebrow="Workforce" title="Attendance & payroll" description="Duty-session attendance, effective-dated compensation, overtime exceptions, and review/finalize payroll controls." />
    <ModuleTabs active={tab} onChange={setTab} values={tabs} /><InlineFeedback error={error} success={success} />
    {tab === "Attendance" && <><OperationsTable label="Attendance by day"><thead><tr><th>Date</th><th>Driver / Operator</th><th>Duty</th><th>Overtime</th><th>Calculation</th><th>Location evidence</th></tr></thead><tbody>{attendance.length ? attendance.map((item) => <tr key={`${item.membership_id}-${item.operational_date}`}><td data-label="Date">{item.operational_date}</td><td data-label="Driver / Operator"><strong>{item.display_name}</strong></td><td data-label="Duty">{item.duty_minutes} min</td><td data-label="Overtime">{item.overtime_minutes} min</td><td data-label="Calculation"><StatusChip status={item.state} tone={tone(item.state)} /></td><td data-label="Location evidence"><StatusChip status={item.location_confidence} /></td></tr>) : <EmptyTableRow colSpan={6} title="No attendance rows." />}</tbody></OperationsTable>{attendanceLocationEnabled && <OperationsTable label="Consent-based location evidence"><thead><tr><th>Captured</th><th>Driver</th><th>Source</th><th>Capture</th><th>Confidence</th><th>Distances</th></tr></thead><tbody>{locations.length ? locations.map((item) => <tr key={item.id}><td data-label="Captured">{new Date(item.captured_at_device).toLocaleString()}</td><td data-label="Driver">{drivers.find((driver) => driver.membership_id === item.membership_id)?.display_name || item.membership_id}</td><td data-label="Source">{item.source}</td><td data-label="Capture"><StatusChip status={item.status} /></td><td data-label="Confidence"><StatusChip status={item.confidence} tone={tone(item.confidence)} /></td><td data-label="Distances">Site {item.site_distance_m ?? "—"} m · asset {item.asset_distance_m ?? "—"} m</td></tr>) : <EmptyTableRow colSpan={6} title="No location evidence captured." />}</tbody></OperationsTable>}</>}
    {tab === "Compensation" && <><form className="owner-form-panel" onSubmit={createProfile}><div className="owner-form-heading"><div><h3>New compensation profile</h3><p>Date ranges may not overlap. Amounts are calculated with Decimal money arithmetic.</p></div></div><div className="owner-form-grid"><label>Driver / Operator<select name="membership_id" required><option value="">Select person</option>{drivers.map((item) => <option key={item.membership_id} value={item.membership_id}>{item.display_name}</option>)}</select></label><label>Pay basis<select name="pay_basis"><option>MONTHLY</option><option>DAILY</option><option>HOURLY</option></select></label><label>Base amount<input min="0" name="base_amount" required step="0.01" type="number" /></label><label>Effective from<input name="effective_from" required type="date" /></label><label>Effective to<input name="effective_to" type="date" /></label><label>Standard duty minutes<input defaultValue="600" min="1" name="standard_duty_minutes" required type="number" /></label><label>Overtime per hour<input defaultValue="0" min="0" name="overtime_rate_per_hour" step="0.01" type="number" /></label></div><div className="owner-form-actions"><button type="submit">Create profile</button></div></form><OperationsTable label="Compensation profiles"><thead><tr><th>Driver</th><th>Basis</th><th>Base</th><th>Effective</th><th>Standard duty</th><th>Overtime rate</th></tr></thead><tbody>{profiles.length ? profiles.map((item) => <tr key={item.id}><td data-label="Driver">{drivers.find((driver) => driver.membership_id === item.membership_id)?.display_name || item.membership_id}</td><td data-label="Basis">{item.pay_basis}</td><td data-label="Base">₹{item.base_amount}</td><td data-label="Effective">{item.effective_from} → {item.effective_to || "ongoing"}</td><td data-label="Standard duty">{item.standard_duty_minutes} min</td><td data-label="Overtime rate">₹{item.overtime_rate_per_hour}/h</td></tr>) : <EmptyTableRow colSpan={6} title="No compensation profiles." />}</tbody></OperationsTable></>}
    {tab === "Overtime" && <OperationsTable label="Overtime exceptions"><thead><tr><th>Date</th><th>Driver / Operator</th><th>Duty minutes</th><th>Overtime minutes</th><th>State</th></tr></thead><tbody>{attendance.filter((item) => item.overtime_minutes > 0 || item.state !== "COMPLETE").length ? attendance.filter((item) => item.overtime_minutes > 0 || item.state !== "COMPLETE").map((item) => <tr key={`${item.membership_id}-${item.operational_date}`}><td data-label="Date">{item.operational_date}</td><td data-label="Driver / Operator">{item.display_name}</td><td data-label="Duty minutes">{item.duty_minutes}</td><td data-label="Overtime minutes"><strong>{item.overtime_minutes}</strong></td><td data-label="State"><StatusChip status={item.state} tone={tone(item.state)} /></td></tr>) : <EmptyTableRow colSpan={5} title="No overtime or attendance exceptions." />}</tbody></OperationsTable>}
    {tab === "Payroll" && <><form className="owner-form-panel owner-form-panel--compact" onSubmit={createPeriod}><div className="owner-form-heading"><div><h3>Create draft payroll</h3><p>Review freezes the calculation for approval; finalize makes the payroll immutable.</p></div></div><div className="owner-form-grid"><label>Starts on<input defaultValue={firstDay} name="starts_on" required type="date" /></label><label>Ends on<input defaultValue={lastDay} name="ends_on" required type="date" /></label></div><div className="owner-form-actions"><button type="submit">Calculate draft</button></div></form><OperationsTable label="Payroll periods"><thead><tr><th>Period</th><th>Status</th><th>Reviewed</th><th>Finalized</th><th>Actions</th></tr></thead><tbody>{periods.length ? periods.map((item) => <tr key={item.id}><td data-label="Period"><button className="owner-text-button" onClick={() => setSelectedPeriod(item.id)} type="button">{item.starts_on} → {item.ends_on}</button></td><td data-label="Status"><StatusChip status={item.status} tone={tone(item.status)} /></td><td data-label="Reviewed">{item.reviewed_at ? new Date(item.reviewed_at).toLocaleString() : "—"}</td><td data-label="Finalized">{item.finalized_at ? new Date(item.finalized_at).toLocaleString() : "—"}</td><td data-label="Actions"><div className="owner-row-actions">{item.status !== "FINALIZED" && <button className="owner-text-button" onClick={() => void transition(item)} type="button">{item.status === "DRAFT" ? "Review" : "Finalize"}</button>}<button className="owner-text-button" onClick={() => void downloadPrivate(`/api/v1/owner/workforce/payroll-periods/${item.id}/export.xlsx`, accessToken, `payroll-${item.starts_on}.xlsx`)} type="button">Export</button></div></td></tr>) : <EmptyTableRow colSpan={5} title="No payroll periods." />}</tbody></OperationsTable>{selectedPeriod && <OperationsTable label="Payroll lines"><thead><tr><th>Driver</th><th>Basis</th><th>Base</th><th>Duty / overtime</th><th>Overtime pay</th><th>Adjustments</th><th>Gross</th><th>State</th></tr></thead><tbody>{lines.length ? lines.map((item) => <tr key={item.id}><td data-label="Driver">{item.display_name_snapshot}</td><td data-label="Basis">{item.pay_basis_snapshot}</td><td data-label="Base">₹{item.base_pay}</td><td data-label="Duty / overtime">{item.duty_minutes} / {item.overtime_minutes} min</td><td data-label="Overtime pay">₹{item.overtime_amount}</td><td data-label="Adjustments"><button className="owner-text-button" onClick={() => void adjust(item)} type="button">₹{item.adjustment_amount}</button></td><td data-label="Gross"><strong>₹{item.calculated_gross_pay}</strong></td><td data-label="State"><StatusChip status={item.calculation_state} tone={tone(item.calculation_state)} /></td></tr>) : <EmptyTableRow colSpan={8} title="No payroll lines." />}</tbody></OperationsTable>}</>}
  </div>;
}
