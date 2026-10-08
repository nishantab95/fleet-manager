"use client";

import { Fragment, useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import type { WebRequest } from "../../lib/api/client";
import type { OwnerAsset } from "../../lib/types";

type DueState = "NOT_DUE" | "DUE_SOON" | "DUE" | "OVERDUE" | "UNKNOWN";
type Basis = "CALENDAR_DAYS" | "ODOMETER_KM" | "HOUR_METER_HOURS";
type Criterion = { id: string; basis: Basis; interval_value: string; warning_value: string; baseline_value: string | null; baseline_date: string | null; state: DueState; current_value: string | null; due_value: string | null; current_date: string | null; due_date: string | null };
type PlanItem = { id: string; asset_id: string; task_code: string; task_label: string; action_type: string; description: string | null; enabled: boolean; state: DueState; triggered_by: Basis[]; criteria: Criterion[] };
type Plan = { id: string | null; asset_id: string; asset_code: string; asset_type: string; manufacturer: string | null; model: string | null; model_year: number | null; is_wheeled: boolean; supports_odometer_km: boolean; supports_hour_meter: boolean; maintenance_responsibility: "OWNER_COMPANY" | "RENTER_COMPANY" | "SHARED"; managed_by_current_company: boolean; management_message: string | null; source: string | null; source_template_id: string | null; source_template_version: string | null; items: PlanItem[] };
type DueItem = PlanItem & { asset_code: string; site_name: string | null };
type Overview = { overdue: number; due: number; due_soon: number; unknown: number; open_work_orders: number; items: DueItem[] };
type WorkOrder = { id: string; asset_id: string; schedule_id: string | null; title: string; description: string | null; status: "DRAFT" | "SCHEDULED" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED"; scheduled_for: string | null; service_date: string | null; completion_odometer_km: string | null; completion_hour_meter: string | null; vendor: string | null; parts_cost: string; labor_cost: string; other_cost: string; total_cost: string; notes: string | null };
type History = { id: string; asset_id: string; task_label: string; service_date: string; odometer_km: string | null; hour_meter: string | null; vendor: string | null; total_cost: string; notes: string | null };
type Template = { id: string; name: string; version: string; template_type: "COMPANY_STARTER" | "OEM_VERIFIED"; confidence: "SUGGESTED" | "VERIFIED"; category: string; applicability: "WHEELED" | "NON_WHEELED"; source_name: string; source_type: string; source_reference: string | null; verification_status: string; asset_type: string | null; manufacturer: string | null; model: string | null; model_year_min: number | null; model_year_max: number | null; notes: string | null; is_generic: boolean };
type TemplateItem = { id: string; template_id: string; task_code: string; task_label: string; action_type: string; description: string | null; enabled: boolean; criteria: Pick<Criterion, "basis" | "interval_value" | "warning_value">[] };
type Section = "overview" | "due" | "plans" | "work-orders" | "history" | "templates";

const sectionLabels: Record<Section, string> = { overview: "Overview", due: "Due", plans: "Asset Plans", "work-orders": "Work Orders", history: "History", templates: "Templates" };
const taskOptions = ["ENGINE_SERVICE", "ENGINE_OIL", "ENGINE_OIL_FILTER", "AIR_FILTER_CLEAN", "AIR_FILTER_REPLACE", "FUEL_FILTER", "GREASING", "TYRE_PRESSURE_CHECK", "TYRE_INSPECTION", "TYRE_ROTATION", "TYRE_REPLACEMENT", "HUB_SERVICE", "WHEEL_BEARING_INSPECTION", "BRAKE_INSPECTION", "BRAKE_SERVICE", "TRANSMISSION_SERVICE", "DIFFERENTIAL_OIL", "HYDRAULIC_OIL", "HYDRAULIC_FILTER", "HYDRAULIC_HOSE_INSPECTION", "COOLANT", "BATTERY_INSPECTION", "BELT_HOSE_INSPECTION", "UNDERCARRIAGE_INSPECTION", "TRACK_TENSION_CHECK", "SWING_BEARING_GREASING", "GENERAL_INSPECTION", "CUSTOM"];

function label(value: string) { return value.toLowerCase().replaceAll("_", " ").replace(/\b\w/g, (part) => part.toUpperCase()); }
function assetLabel(asset: OwnerAsset | undefined) { return asset ? asset.short_name || asset.registration_number || asset.asset_code : "Unknown asset"; }
function companyManages(asset: OwnerAsset) { return asset.ownership_type === "OWNED" && asset.maintenance_responsibility !== "RENTER_COMPANY"; }

function intervalText(criteria: Pick<Criterion, "basis" | "interval_value">[]) {
  if (criteria.length === 0) return ["Set interval"];
  return criteria.map((entry) => {
    const value = Number(entry.interval_value).toLocaleString();
    if (entry.basis === "CALENDAR_DAYS") return `${value} days`;
    if (entry.basis === "ODOMETER_KM") return `${value} km`;
    return `${value} h`;
  });
}

function warningText(criteria: Pick<Criterion, "basis" | "warning_value">[]) {
  if (criteria.length === 0) return ["—"];
  return criteria.map((entry) => {
    const value = Number(entry.warning_value).toLocaleString();
    if (entry.basis === "CALENDAR_DAYS") return `${value} d`;
    if (entry.basis === "ODOMETER_KM") return `${value} km`;
    return `${value} h`;
  });
}

function lastServiceText(criteria: Criterion[]) {
  if (criteria.length === 0) return ["Not set"];
  return criteria.map((entry) => {
    if (entry.basis === "CALENDAR_DAYS") return entry.baseline_date ?? "Date not set";
    const unit = entry.basis === "ODOMETER_KM" ? "km" : "h";
    return entry.baseline_value ? `${Number(entry.baseline_value).toLocaleString()} ${unit}` : `${unit} not set`;
  });
}

function nextDueText(criteria: Criterion[]) {
  if (criteria.length === 0) return ["Not scheduled"];
  return criteria.map((entry) => {
    if (entry.basis === "CALENDAR_DAYS") return entry.due_date ?? "Date unknown";
    const unit = entry.basis === "ODOMETER_KM" ? "km" : "h";
    return entry.due_value ? `${Number(entry.due_value).toLocaleString()} ${unit}` : `${unit} unknown`;
  });
}

function criterionText(item: Criterion) {
  if (item.basis === "CALENDAR_DAYS") return `${item.current_date ?? "Unknown"} / ${item.due_date ?? "Unknown"}`;
  return `${item.current_value ?? "Unknown"} / ${item.due_value ?? "Unknown"} ${item.basis === "ODOMETER_KM" ? "km" : "h"}`;
}

type ItemDraft = { id?: string; task_code: string; custom_label: string; action_type: string; enabled: boolean; days: string; days_warn: string; days_baseline: string; km: string; km_warn: string; km_baseline: string; hours: string; hours_warn: string; hours_baseline: string };
const blankItem: ItemDraft = { task_code: "ENGINE_SERVICE", custom_label: "", action_type: "SERVICE", enabled: true, days: "", days_warn: "", days_baseline: "", km: "", km_warn: "", km_baseline: "", hours: "", hours_warn: "", hours_baseline: "" };
type TemplateDraft = { name: string; version: string; template_type: "COMPANY_STARTER" | "OEM_VERIFIED"; confidence: "SUGGESTED" | "VERIFIED"; category: string; applicability: "WHEELED" | "NON_WHEELED"; source_name: string; source_reference: string; asset_type: string; manufacturer: string; model: string; model_year_min: string; model_year_max: string; notes: string; is_generic: boolean };
const blankTemplate: TemplateDraft = { name: "", version: "1", template_type: "COMPANY_STARTER", confidence: "SUGGESTED", category: "CUSTOM", applicability: "WHEELED", source_name: "Company maintenance policy", source_reference: "", asset_type: "", manufacturer: "", model: "", model_year_min: "", model_year_max: "", notes: "", is_generic: true };

function itemDraft(item: PlanItem | TemplateItem): ItemDraft {
  const byBasis = new Map(item.criteria.map((criterion) => [criterion.basis, criterion]));
  const days = byBasis.get("CALENDAR_DAYS"); const km = byBasis.get("ODOMETER_KM"); const hours = byBasis.get("HOUR_METER_HOURS");
  return { id: item.id, task_code: item.task_code, custom_label: item.task_code === "CUSTOM" ? item.task_label : "", action_type: item.action_type, enabled: item.enabled, days: days?.interval_value ?? "", days_warn: days?.warning_value ?? "", days_baseline: days && "baseline_date" in days ? days.baseline_date ?? "" : "", km: km?.interval_value ?? "", km_warn: km?.warning_value ?? "", km_baseline: km && "baseline_value" in km ? km.baseline_value ?? "" : "", hours: hours?.interval_value ?? "", hours_warn: hours?.warning_value ?? "", hours_baseline: hours && "baseline_value" in hours ? hours.baseline_value ?? "" : "" };
}

function criteriaForDraft(draft: ItemDraft, includeBaselines = true) {
  return [
    draft.days ? { basis: "CALENDAR_DAYS", interval_value: draft.days, warning_value: draft.days_warn || "0", ...(includeBaselines ? { baseline_date: draft.days_baseline || null } : {}) } : null,
    draft.km ? { basis: "ODOMETER_KM", interval_value: draft.km, warning_value: draft.km_warn || "0", ...(includeBaselines ? { baseline_value: draft.km_baseline || null } : {}) } : null,
    draft.hours ? { basis: "HOUR_METER_HOURS", interval_value: draft.hours, warning_value: draft.hours_warn || "0", ...(includeBaselines ? { baseline_value: draft.hours_baseline || null } : {}) } : null,
  ].filter(Boolean);
}

export function Maintenance({ assets, apiRequest, initialAssetId, onInitialHandled }: { assets: OwnerAsset[]; apiRequest: WebRequest; initialAssetId?: string | null; onInitialHandled?: () => void }) {
  const managedAssets = useMemo(() => assets.filter(companyManages), [assets]);
  const [section, setSection] = useState<Section>(initialAssetId ? "plans" : "overview");
  const [selectedAssetId, setSelectedAssetId] = useState(initialAssetId || managedAssets[0]?.id || "");
  const [workOrderAssetId, setWorkOrderAssetId] = useState(managedAssets[0]?.id || "");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [orders, setOrders] = useState<WorkOrder[]>([]);
  const [history, setHistory] = useState<History[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [matches, setMatches] = useState<Template[]>([]);
  const [draft, setDraft] = useState<ItemDraft | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [workTitle, setWorkTitle] = useState("");
  const [templateDraft, setTemplateDraft] = useState<TemplateDraft>(blankTemplate);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [templateItems, setTemplateItems] = useState<TemplateItem[]>([]);
  const [templateItemDraft, setTemplateItemDraft] = useState<ItemDraft | null>(null);
  const [copySourceAssetId, setCopySourceAssetId] = useState("");
  const [applyTemplateId, setApplyTemplateId] = useState("");
  const [previewItems, setPreviewItems] = useState<TemplateItem[]>([]);

  const load = useCallback(async () => {
    setError("");
    try {
      const [nextOverview, nextOrders, nextHistory, nextTemplates] = await Promise.all([
        apiRequest<Overview>("/api/v1/owner/maintenance/overview"), apiRequest<WorkOrder[]>("/api/v1/owner/maintenance/work-orders"), apiRequest<History[]>("/api/v1/owner/maintenance/history"), apiRequest<Template[]>("/api/v1/owner/maintenance/templates"),
      ]);
      setOverview(nextOverview); setOrders(nextOrders); setHistory(nextHistory); setTemplates(nextTemplates);
      if (selectedAssetId) {
        const nextPlan = await apiRequest<Plan>(`/api/v1/owner/maintenance/plans/${selectedAssetId}`);
        setPlan(nextPlan);
        if (nextPlan.managed_by_current_company) {
          const nextMatches = await apiRequest<Template[]>(`/api/v1/owner/maintenance/templates/matches/${selectedAssetId}`);
          setMatches(nextMatches);
          setApplyTemplateId((current) => current && nextMatches.some((entry) => entry.id === current) ? current : nextMatches[0]?.id ?? "");
        } else { setMatches([]); setApplyTemplateId(""); }
      } else { setPlan(null); setMatches([]); }
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not load maintenance data."); }
  }, [apiRequest, selectedAssetId]);

  useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [load]);
  useEffect(() => { if (!initialAssetId) return; const timer = window.setTimeout(() => { setSelectedAssetId(initialAssetId); setSection("plans"); onInitialHandled?.(); }, 0); return () => window.clearTimeout(timer); }, [initialAssetId, onInitialHandled]);
  useEffect(() => {
    if (!managedAssets[0] || (selectedAssetId && workOrderAssetId)) return;
    const timer = window.setTimeout(() => {
      if (!selectedAssetId) setSelectedAssetId(managedAssets[0].id);
      if (!workOrderAssetId) setWorkOrderAssetId(managedAssets[0].id);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [managedAssets, selectedAssetId, workOrderAssetId]);

  const mutate = async (messageText: string, work: () => Promise<unknown>) => {
    setBusy(true); setError(""); setMessage("");
    try { await work(); setMessage(messageText); await load(); return true; }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Maintenance change could not be saved."); return false; }
    finally { setBusy(false); }
  };

  const saveItem = async (event: FormEvent) => {
    event.preventDefault(); if (!draft || !selectedAssetId) return;
    const path = draft.id ? `/api/v1/owner/maintenance/plans/${selectedAssetId}/items/${draft.id}` : `/api/v1/owner/maintenance/plans/${selectedAssetId}/items`;
    const ok = await mutate("Maintenance item saved.", () => apiRequest(path, { method: draft.id ? "PUT" : "POST", body: JSON.stringify({ task_code: draft.task_code, custom_label: draft.task_code === "CUSTOM" ? draft.custom_label : null, action_type: draft.action_type, enabled: draft.enabled, criteria: criteriaForDraft(draft) }) }));
    if (ok) setDraft(null);
  };

  const selectTemplate = async (templateId: string) => {
    setSelectedTemplateId(templateId); setTemplateItemDraft(null);
    if (!templateId) { setTemplateItems([]); return; }
    try { setTemplateItems(await apiRequest<TemplateItem[]>(`/api/v1/owner/maintenance/templates/${templateId}/items`)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Could not load template items."); }
  };

  const previewTemplate = async () => {
    if (!applyTemplateId) return;
    try { setPreviewItems(await apiRequest<TemplateItem[]>(`/api/v1/owner/maintenance/templates/${applyTemplateId}/items`)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Could not preview this template."); }
  };

  const saveTemplateItem = async (event: FormEvent) => {
    event.preventDefault(); if (!templateItemDraft || !selectedTemplateId) return;
    const path = templateItemDraft.id ? `/api/v1/owner/maintenance/templates/${selectedTemplateId}/items/${templateItemDraft.id}` : `/api/v1/owner/maintenance/templates/${selectedTemplateId}/items`;
    const ok = await mutate("Template item saved. Existing Asset plans were not changed.", () => apiRequest(path, { method: templateItemDraft.id ? "PUT" : "POST", body: JSON.stringify({ task_code: templateItemDraft.task_code, custom_label: templateItemDraft.task_code === "CUSTOM" ? templateItemDraft.custom_label : null, action_type: templateItemDraft.action_type, enabled: templateItemDraft.enabled, criteria: criteriaForDraft(templateItemDraft, false) }) }));
    if (ok) { setTemplateItemDraft(null); await selectTemplate(selectedTemplateId); }
  };

  const complete = async (order: WorkOrder) => {
    const serviceDate = window.prompt("Service date (YYYY-MM-DD)", new Date().toISOString().slice(0, 10)); if (!serviceDate) return;
    const orderAsset = assets.find((asset) => asset.id === order.asset_id);
    const odometer = orderAsset?.supports_odometer_km ? window.prompt("Current odometer KM (leave blank if unavailable)", "") : null;
    const hours = orderAsset?.supports_hour_meter ? window.prompt("Current hour meter / HMR (leave blank if unavailable)", "") : null;
    const vendor = window.prompt("Vendor / workshop (optional)", ""); const parts = window.prompt("Parts cost", "0"); const labor = window.prompt("Labor cost", "0"); const other = window.prompt("Other cost", "0"); const notes = window.prompt("Notes (optional)", "");
    await mutate("Work order completed and immutable history created.", () => apiRequest(`/api/v1/owner/maintenance/work-orders/${order.id}/complete`, { method: "POST", body: JSON.stringify({ service_date: serviceDate, odometer_km: odometer || null, hour_meter: hours || null, vendor: vendor || null, parts_cost: parts || "0", labor_cost: labor || "0", other_cost: other || "0", notes: notes || null }) }));
  };

  const due = useMemo(() => overview?.items ?? [], [overview]);
  const selectedTemplate = templates.find((entry) => entry.id === selectedTemplateId);
  const applyingTemplate = matches.find((entry) => entry.id === applyTemplateId);
  const selectedAsset = assets.find((asset) => asset.id === selectedAssetId);
  const directRentedContext = Boolean(selectedAsset && !companyManages(selectedAsset));

  return <section className="owner-panel maintenance-page">
    <header className="owner-section-heading maintenance-heading"><div><p className="owner-section-eyebrow">Fleet management</p><h2>Maintenance</h2><p className="muted">Date, KM and hour triggers — whichever comes first.</p></div></header>
    <div className="maintenance-tabs" role="tablist">{(Object.keys(sectionLabels) as Section[]).map((item) => <button aria-selected={section === item} className={section === item ? "active" : "secondary"} key={item} onClick={() => setSection(item)} role="tab" type="button">{sectionLabels[item]}</button>)}</div>
    {error && <div className="notice error" role="alert">{error}</div>}{message && <div className="notice" role="status">{message}</div>}

    {section === "overview" && <div className="maintenance-section"><div className="owner-kpi-grid maintenance-kpis"><div><span>Overdue</span><strong>{overview?.overdue ?? 0}</strong></div><div><span>Due</span><strong>{overview?.due ?? 0}</strong></div><div><span>Due soon</span><strong>{overview?.due_soon ?? 0}</strong></div><div><span>Open work orders</span><strong>{overview?.open_work_orders ?? 0}</strong></div></div><DueTable items={due} assets={managedAssets} /></div>}
    {section === "due" && <div className="maintenance-section"><div className="maintenance-section-copy"><h3>Due maintenance</h3><p className="muted">The triggering measurement is shown first; an unknown meter never hides a known due date or reading.</p></div><DueTable items={due} assets={managedAssets} detailed /></div>}

    {section === "plans" && <div className="maintenance-section">{directRentedContext ? <div className="maintenance-external" role="status"><strong>Maintenance managed by rental owner.</strong></div> : <>
      {managedAssets.length === 0 ? <div className="notice">No company-maintained Assets are available.</div> : <label className="maintenance-asset-picker">Asset<select aria-label="Maintenance Asset" value={selectedAssetId} onChange={(event) => { setSelectedAssetId(event.target.value); setDraft(null); setCopySourceAssetId(""); setPreviewItems([]); }}>{managedAssets.map((asset) => <option key={asset.id} value={asset.id}>{assetLabel(asset)}</option>)}</select></label>}
      {plan?.managed_by_current_company && <><div className="maintenance-plan-header"><div><span className="owner-section-eyebrow">Maintenance plan</span><strong>{plan.asset_code}</strong></div><div><span>{[plan.manufacturer, plan.model, plan.model_year].filter(Boolean).join(" · ") || "Make / model / year not provided"}</span><span className="owner-status-chip owner-status-chip--active">Owned</span></div><div><span>Meters: {[plan.supports_odometer_km && "KM", plan.supports_hour_meter && "HMR"].filter(Boolean).join(" + ")}</span><span>Plan: {label(plan.source ?? "CUSTOM")}{plan.source_template_version ? ` · v${plan.source_template_version}` : ""}</span></div></div>
      <div className="maintenance-plan-actions">{!plan.id && matches.length > 0 && <><label>Template<select aria-label="Template to apply" value={applyTemplateId} onChange={(event) => { setApplyTemplateId(event.target.value); setPreviewItems([]); }}>{matches.map((entry) => <option key={entry.id} value={entry.id}>{entry.name} · {entry.confidence === "VERIFIED" ? "Verified" : "Suggested"}</option>)}</select></label><button className="secondary" disabled={!applyTemplateId} onClick={() => void previewTemplate()} type="button">Preview</button></>}{!plan.id && <><label>Copy plan<select aria-label="Copy maintenance plan from Asset" onChange={(event) => setCopySourceAssetId(event.target.value)} value={copySourceAssetId}><option value="">Choose Asset…</option>{managedAssets.filter((asset) => asset.id !== selectedAssetId).map((asset) => <option key={asset.id} value={asset.id}>{assetLabel(asset)}</option>)}</select></label><button className="secondary" disabled={busy || !copySourceAssetId} onClick={() => void mutate("Maintenance plan copied without another Asset's service baselines.", () => apiRequest(`/api/v1/owner/maintenance/plans/${selectedAssetId}/copy`, { method: "POST", body: JSON.stringify({ source_asset_id: copySourceAssetId }) }))} type="button">Copy plan</button></>}<button onClick={() => setDraft({ ...blankItem })} type="button">+ Custom item</button></div>
      {!plan.id && matches.length === 0 && <div className="notice">No matching template is available. Copy a similar Asset plan or start blank. No OEM intervals are invented.</div>}
      {applyingTemplate && previewItems.length > 0 && <TemplatePreview template={applyingTemplate} items={previewItems} busy={busy} onApply={() => void mutate("Template copied into this Asset plan.", () => apiRequest(`/api/v1/owner/maintenance/plans/${selectedAssetId}/apply-template`, { method: "POST", body: JSON.stringify({ template_id: applyingTemplate.id }) })).then((ok) => { if (ok) setPreviewItems([]); })} onClose={() => setPreviewItems([])} />}
      <div className="maintenance-plan-table" role="table" aria-label="Maintenance plan items"><div className="maintenance-plan-row maintenance-plan-row--header" role="row"><strong role="columnheader">On</strong><strong role="columnheader">Maintenance item</strong><strong role="columnheader">Triggers</strong><strong role="columnheader">Warning</strong><strong role="columnheader">Last service</strong><strong role="columnheader">Next due</strong><strong role="columnheader">Status</strong><strong role="columnheader">Actions</strong></div>{plan.items.length === 0 && <div className="maintenance-empty">No maintenance items configured.</div>}{plan.items.map((item) => <PlanRow busy={busy} item={item} key={item.id} plan={plan} onRemove={() => mutate("Custom maintenance item removed.", () => apiRequest(`/api/v1/owner/maintenance/plans/items/${item.id}`, { method: "DELETE" }))} onSave={(next) => mutate("Maintenance item saved.", () => apiRequest(`/api/v1/owner/maintenance/plans/${selectedAssetId}/items/${item.id}`, { method: "PUT", body: JSON.stringify({ task_code: next.task_code, custom_label: next.task_code === "CUSTOM" ? next.custom_label : null, action_type: next.action_type, enabled: next.enabled, criteria: criteriaForDraft(next) }) }))} />)}</div>
      {draft && <ItemEditor busy={busy} draft={draft} plan={plan} setDraft={setDraft} onSubmit={saveItem} />}</>}</>}</div>}

    {section === "work-orders" && <div className="maintenance-section"><form className="maintenance-toolbar" onSubmit={(event) => { event.preventDefault(); if (!workOrderAssetId || !workTitle.trim()) return; void mutate("Work order created.", () => apiRequest("/api/v1/owner/maintenance/work-orders", { method: "POST", body: JSON.stringify({ asset_id: workOrderAssetId, title: workTitle }) })).then((ok) => { if (ok) setWorkTitle(""); }); }}><label>Asset<select aria-label="Work order Asset" value={workOrderAssetId} onChange={(event) => setWorkOrderAssetId(event.target.value)}>{managedAssets.map((asset) => <option key={asset.id} value={asset.id}>{assetLabel(asset)}</option>)}</select></label><label>Work order title<input required value={workTitle} onChange={(event) => setWorkTitle(event.target.value)} /></label><button disabled={busy || !workOrderAssetId} type="submit">Create draft</button></form><div className="maintenance-card-list">{orders.map((order) => <article className="maintenance-list-card" key={order.id}><div><strong>{order.title}</strong><span>{assetLabel(managedAssets.find((asset) => asset.id === order.asset_id))}</span></div><span className="owner-status-chip">{label(order.status)}</span><span>{order.scheduled_for ?? "Not scheduled"}</span><span>Total ₹{order.total_cost}</span>{!(["COMPLETED", "CANCELLED"] as string[]).includes(order.status) && <div className="owner-row-actions">{order.status === "DRAFT" && <button className="secondary" onClick={() => void mutate("Work order scheduled.", () => apiRequest(`/api/v1/owner/maintenance/work-orders/${order.id}/transition`, { method: "POST", body: JSON.stringify({ status: "SCHEDULED" }) }))} type="button">Schedule</button>}{order.status !== "IN_PROGRESS" && <button className="secondary" onClick={() => void mutate("Work started.", () => apiRequest(`/api/v1/owner/maintenance/work-orders/${order.id}/transition`, { method: "POST", body: JSON.stringify({ status: "IN_PROGRESS" }) }))} type="button">Start</button>}<button onClick={() => void complete(order)} type="button">Complete</button><button className="secondary" onClick={() => void mutate("Work order cancelled.", () => apiRequest(`/api/v1/owner/maintenance/work-orders/${order.id}/transition`, { method: "POST", body: JSON.stringify({ status: "CANCELLED" }) }))} type="button">Cancel</button></div>}</article>)}</div></div>}

    {section === "history" && <div className="maintenance-section"><div className="table-card"><table className="owner-table maintenance-history-table"><thead><tr><th>Date</th><th>Asset</th><th>Service</th><th>KM</th><th>HMR</th><th>Vendor</th><th>Cost</th><th>Notes</th></tr></thead><tbody>{history.map((entry) => <tr key={entry.id}><td>{entry.service_date}</td><td>{assetLabel(managedAssets.find((asset) => asset.id === entry.asset_id))}</td><td>{entry.task_label}</td><td>{entry.odometer_km ?? "N/A"}</td><td>{entry.hour_meter ?? "N/A"}</td><td>{entry.vendor ?? "—"}</td><td>₹{entry.total_cost}</td><td>{entry.notes ?? "—"}</td></tr>)}</tbody></table></div></div>}

    {section === "templates" && <div className="maintenance-section"><div className="notice">Company starters are suggested and editable. OEM-verified references apply only to an exact manufacturer/model match. Applying either copies an independent snapshot into the Asset plan.</div><details className="maintenance-template-create"><summary>Create a template version</summary><TemplateCreateForm busy={busy} draft={templateDraft} setDraft={setTemplateDraft} onSubmit={(event) => { event.preventDefault(); const isOem = templateDraft.template_type === "OEM_VERIFIED"; void mutate("Maintenance template created.", () => apiRequest("/api/v1/owner/maintenance/templates", { method: "POST", body: JSON.stringify({ ...templateDraft, source_type: isOem ? "OEM" : "COMPANY_DEFAULT", verification_status: templateDraft.confidence === "VERIFIED" ? "VERIFIED" : "UNVERIFIED", source_reference: templateDraft.source_reference || null, asset_type: templateDraft.asset_type || null, manufacturer: templateDraft.manufacturer || null, model: templateDraft.model || null, model_year_min: templateDraft.model_year_min ? Number(templateDraft.model_year_min) : null, model_year_max: templateDraft.model_year_max ? Number(templateDraft.model_year_max) : null, notes: templateDraft.notes || null }) })).then((ok) => { if (ok) setTemplateDraft(blankTemplate); }); }} /></details><div className="maintenance-template-grid">{templates.map((template) => <article className="maintenance-template-card" key={template.id}><div className="maintenance-template-card__title"><div><strong>{template.name}</strong><span>v{template.version} · {label(template.category)}</span></div><span className={`owner-status-chip ${template.confidence === "VERIFIED" ? "owner-status-chip--positive" : "owner-status-chip--warning"}`}>{template.confidence === "VERIFIED" ? "OEM verified" : "Starter · suggested"}</span></div><p>{template.notes}</p><dl><div><dt>Applicability</dt><dd>{label(template.applicability)}</dd></div><div><dt>Source</dt><dd>{template.source_name}</dd></div>{template.manufacturer && <div><dt>Exact match</dt><dd>{template.manufacturer} · {template.model}</dd></div>}</dl><button className="secondary" onClick={() => void selectTemplate(template.id)} type="button">Review and edit</button></article>)}</div>{selectedTemplate && <section className="maintenance-template-editor"><header><div><p className="owner-section-eyebrow">Template items</p><h3>{selectedTemplate.name}</h3><p>{selectedTemplate.confidence === "VERIFIED" ? "Verified reference — exact model only." : "Suggested — verify against the manufacturer service manual."}</p></div><button onClick={() => setTemplateItemDraft({ ...blankItem })} type="button">+ Add item</button></header><div className="maintenance-template-items">{templateItems.length === 0 && <p>No template items yet.</p>}{templateItems.map((item) => <div className="maintenance-template-item" key={item.id}><div><strong>{item.task_label}</strong><span>{label(item.action_type)}</span></div><div className="maintenance-cell-stack">{intervalText(item.criteria).map((text) => <span key={text}>{text}</span>)}</div><span>{item.criteria.length ? `Warn ${warningText(item.criteria).join(" / ")}` : "Owner sets interval"}</span><button className="secondary" onClick={() => setTemplateItemDraft(itemDraft(item))} type="button">Edit</button></div>)}</div>{templateItemDraft && <TemplateItemEditor allowKm={selectedTemplate.applicability === "WHEELED"} busy={busy} draft={templateItemDraft} setDraft={setTemplateItemDraft} onSubmit={saveTemplateItem} />}</section>}</div>}
  </section>;
}

function DueTable({ items, assets, detailed = false }: { items: DueItem[]; assets: OwnerAsset[]; detailed?: boolean }) {
  return <div className="table-card"><table className="owner-table maintenance-due-table"><thead><tr><th>Asset</th><th>Site</th><th>Item</th><th>Trigger</th><th>Due</th><th>Status</th></tr></thead><tbody>{items.length === 0 ? <tr><td colSpan={6}>No due maintenance items.</td></tr> : items.map((item) => <tr key={item.id}><td>{assetLabel(assets.find((asset) => asset.id === item.asset_id)) || item.asset_code}</td><td>{item.site_name ?? "Undeployed"}</td><td><strong>{item.task_label}</strong>{detailed && <small>{item.criteria.map((entry) => `${label(entry.basis)} ${entry.state}`).join(" · ")}</small>}</td><td>{item.triggered_by.map(label).join(" + ")}</td><td>{item.criteria.map(criterionText).join(" · ")}</td><td><span className="owner-status-chip">{label(item.state)}</span></td></tr>)}</tbody></table></div>;
}

function PlanRow({ item, plan, busy, onSave, onRemove }: { item: PlanItem; plan: Plan; busy: boolean; onSave: (draft: ItemDraft) => Promise<unknown>; onRemove: () => Promise<unknown> }) {
  const [editing, setEditing] = useState(false); const [draft, setDraft] = useState(() => itemDraft(item));
  const save = async (event: FormEvent) => { event.preventDefault(); await onSave(draft); setEditing(false); };
  return <Fragment><div className="maintenance-plan-row" role="row"><span role="cell"><input aria-label={`Enabled — ${item.task_label}`} checked={item.enabled} disabled readOnly type="checkbox" /></span><span role="cell"><strong>{item.task_label}</strong><small>{label(item.action_type)}</small></span><span className="maintenance-cell-stack" role="cell">{intervalText(item.criteria).map((text) => <span key={text}>{text}</span>)}</span><span className="maintenance-cell-stack" role="cell">{warningText(item.criteria).map((text) => <span key={text}>{text}</span>)}</span><span className="maintenance-cell-stack" role="cell">{lastServiceText(item.criteria).map((text) => <span key={text}>{text}</span>)}</span><span className="maintenance-cell-stack" role="cell">{nextDueText(item.criteria).map((text) => <span key={text}>{text}</span>)}</span><span role="cell"><span className="owner-status-chip">{item.criteria.length ? label(item.state) : "Not scheduled"}</span></span><span role="cell"><button className="secondary" onClick={() => setEditing((current) => !current)} type="button">{editing ? "Close" : "Edit"}</button></span></div>{editing && <form className="maintenance-inline-editor" onSubmit={save}><ItemFields allowKm={plan.is_wheeled && plan.supports_odometer_km} allowHours={plan.supports_hour_meter} draft={draft} includeBaselines setDraft={setDraft} /><div className="owner-form-actions"><button className="secondary" onClick={() => { setDraft(itemDraft(item)); setEditing(false); }} type="button">Cancel</button>{item.task_code === "CUSTOM" && <button className="owner-text-button owner-text-button--danger" disabled={busy} onClick={() => void onRemove()} type="button">Remove</button>}<button disabled={busy || (!draft.days && !draft.km && !draft.hours)} type="submit">Save</button></div></form>}</Fragment>;
}

function ItemFields({ draft, setDraft, allowKm, allowHours, includeBaselines }: { draft: ItemDraft; setDraft: (next: ItemDraft) => void; allowKm: boolean; allowHours: boolean; includeBaselines: boolean }) {
  return <div className="maintenance-editor-fields"><label>Task<select value={draft.task_code} onChange={(event) => setDraft({ ...draft, task_code: event.target.value })}>{taskOptions.map((entry) => <option key={entry} value={entry}>{label(entry)}</option>)}</select></label>{draft.task_code === "CUSTOM" && <label>Task name<input required value={draft.custom_label} onChange={(event) => setDraft({ ...draft, custom_label: event.target.value })} /></label>}<label>Action<select value={draft.action_type} onChange={(event) => setDraft({ ...draft, action_type: event.target.value })}>{["INSPECT", "CLEAN", "LUBRICATE", "SERVICE", "REPLACE"].map((entry) => <option key={entry}>{entry}</option>)}</select></label><label className="maintenance-checkbox"><input checked={draft.enabled} onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })} type="checkbox" /> Enabled</label><fieldset><legend>Days</legend><label>Every days<input aria-label="Every days" min="1" step="1" type="number" value={draft.days} onChange={(event) => setDraft({ ...draft, days: event.target.value })} /></label><label>Warn before<input aria-label="Warn days before" min="0" step="1" type="number" value={draft.days_warn} onChange={(event) => setDraft({ ...draft, days_warn: event.target.value })} /></label>{includeBaselines && <label>Last service<input aria-label="Last service date" type="date" value={draft.days_baseline} onChange={(event) => setDraft({ ...draft, days_baseline: event.target.value })} /></label>}</fieldset>{allowKm && <fieldset><legend>KM</legend><label>Every KM<input aria-label="Every KM" min="0.01" step="0.01" type="number" value={draft.km} onChange={(event) => setDraft({ ...draft, km: event.target.value })} /></label><label>Warn before<input aria-label="Warn KM before" min="0" step="0.01" type="number" value={draft.km_warn} onChange={(event) => setDraft({ ...draft, km_warn: event.target.value })} /></label>{includeBaselines && <label>Last service<input aria-label="Last service KM" min="0" step="0.01" type="number" value={draft.km_baseline} onChange={(event) => setDraft({ ...draft, km_baseline: event.target.value })} /></label>}</fieldset>}{allowHours && <fieldset><legend>Hours</legend><label>Every hours<input aria-label="Every hours" min="0.01" step="0.01" type="number" value={draft.hours} onChange={(event) => setDraft({ ...draft, hours: event.target.value })} /></label><label>Warn before<input aria-label="Warn hours before" min="0" step="0.01" type="number" value={draft.hours_warn} onChange={(event) => setDraft({ ...draft, hours_warn: event.target.value })} /></label>{includeBaselines && <label>Last service<input aria-label="Last service HMR" min="0" step="0.01" type="number" value={draft.hours_baseline} onChange={(event) => setDraft({ ...draft, hours_baseline: event.target.value })} /></label>}</fieldset>}</div>;
}

function ItemEditor({ draft, plan, setDraft, onSubmit, busy }: { draft: ItemDraft; plan: Plan; setDraft: (next: ItemDraft | null) => void; onSubmit: (event: FormEvent) => void; busy: boolean }) {
  return <form className="owner-form-panel maintenance-item-editor" onSubmit={onSubmit}><div className="owner-form-heading"><div><h3>Add custom maintenance item</h3><p>Add an uncommon task; routine items stay visible in the list.</p></div></div><ItemFields allowHours={plan.supports_hour_meter} allowKm={plan.is_wheeled && plan.supports_odometer_km} draft={draft} includeBaselines setDraft={setDraft} /><div className="owner-form-actions"><button className="secondary" onClick={() => setDraft(null)} type="button">Cancel</button><button disabled={busy || (!draft.days && !draft.km && !draft.hours)} type="submit">Add item</button></div></form>;
}

function TemplateItemEditor({ draft, setDraft, onSubmit, busy, allowKm }: { draft: ItemDraft; setDraft: (next: ItemDraft | null) => void; onSubmit: (event: FormEvent) => void; busy: boolean; allowKm: boolean }) {
  return <form className="owner-form-panel maintenance-item-editor" onSubmit={onSubmit}><div className="owner-form-heading"><div><h3>{draft.id ? "Edit template item" : "Add template item"}</h3><p>Intervals may be left blank when a generic value is not defensible.</p></div></div><ItemFields allowHours draft={draft} includeBaselines={false} allowKm={allowKm} setDraft={setDraft} /><div className="owner-form-actions"><button className="secondary" onClick={() => setDraft(null)} type="button">Cancel</button><button disabled={busy} type="submit">Save template item</button></div></form>;
}

function TemplatePreview({ template, items, busy, onApply, onClose }: { template: Template; items: TemplateItem[]; busy: boolean; onApply: () => void; onClose: () => void }) {
  return <section className="maintenance-template-preview" aria-label="Template preview"><header><div><p className="owner-section-eyebrow">Template preview</p><h3>{template.name}</h3><p><strong>Type:</strong> {template.template_type === "COMPANY_STARTER" ? "Company Starter" : "OEM Verified Reference"}</p><p><strong>Status:</strong> {template.confidence === "SUGGESTED" ? "Suggested — verify against manufacturer service manual" : "Verified — exact manufacturer/model only"}</p></div><button className="secondary" onClick={onClose} type="button">Close</button></header><div className="maintenance-preview-list">{items.map((entry) => <div key={entry.id}><strong>{entry.task_label}</strong><span>{intervalText(entry.criteria).join(" / ")}</span></div>)}</div><div className="owner-form-actions"><button disabled={busy} onClick={onApply} type="button">Apply to Asset</button></div></section>;
}

function TemplateCreateForm({ draft, setDraft, onSubmit, busy }: { draft: TemplateDraft; setDraft: (next: TemplateDraft) => void; onSubmit: (event: FormEvent) => void; busy: boolean }) {
  const set = <K extends keyof TemplateDraft>(key: K, value: TemplateDraft[K]) => setDraft({ ...draft, [key]: value });
  return <form className="owner-form-panel" onSubmit={onSubmit}><div className="owner-form-grid"><label>Template name<input required value={draft.name} onChange={(event) => set("name", event.target.value)} /></label><label>Version<input required value={draft.version} onChange={(event) => set("version", event.target.value)} /></label><label>Type<select value={draft.template_type} onChange={(event) => { const type = event.target.value as TemplateDraft["template_type"]; setDraft({ ...draft, template_type: type, confidence: type === "OEM_VERIFIED" ? "VERIFIED" : "SUGGESTED", is_generic: type === "COMPANY_STARTER" }); }}><option value="COMPANY_STARTER">Company starter</option><option value="OEM_VERIFIED">OEM verified reference</option></select></label><label>Confidence<select value={draft.confidence} onChange={(event) => set("confidence", event.target.value as TemplateDraft["confidence"])}><option value="SUGGESTED">Suggested</option><option value="VERIFIED">Verified</option></select></label><label>Category<select value={draft.category} onChange={(event) => set("category", event.target.value)}>{["HEAVY_TIPPER_10_WHEEL", "TRACKED_EXCAVATOR", "BACKHOE_LOADER", "ROAD_ROLLER_COMPACTOR", "WHEEL_LOADER", "MOTOR_GRADER", "CUSTOM"].map((entry) => <option key={entry}>{entry}</option>)}</select></label><label>Applicability<select value={draft.applicability} onChange={(event) => set("applicability", event.target.value as TemplateDraft["applicability"])}><option value="WHEELED">Wheeled</option><option value="NON_WHEELED">Non-wheeled</option></select></label><label>Source name<input required value={draft.source_name} onChange={(event) => set("source_name", event.target.value)} /></label><label>Source reference<input required={draft.template_type === "OEM_VERIFIED"} value={draft.source_reference} onChange={(event) => set("source_reference", event.target.value)} /></label><label>Asset type<select value={draft.asset_type} onChange={(event) => set("asset_type", event.target.value)}><option value="">Catalog only</option>{["TIPPER", "EXCAVATOR", "BACKHOE_LOADER", "ROLLER", "GRADER"].map((entry) => <option key={entry}>{entry}</option>)}</select></label><label>Manufacturer<input required={draft.template_type === "OEM_VERIFIED"} value={draft.manufacturer} onChange={(event) => set("manufacturer", event.target.value)} /></label><label>Model<input required={draft.template_type === "OEM_VERIFIED"} value={draft.model} onChange={(event) => set("model", event.target.value)} /></label><label>Year from<input min="1900" max="2200" type="number" value={draft.model_year_min} onChange={(event) => set("model_year_min", event.target.value)} /></label><label>Year to<input min="1900" max="2200" type="number" value={draft.model_year_max} onChange={(event) => set("model_year_max", event.target.value)} /></label><label className="owner-form-grid__wide">Notes<textarea value={draft.notes} onChange={(event) => set("notes", event.target.value)} /></label></div><div className="owner-form-actions"><button disabled={busy} type="submit">Create template version</button></div></form>;
}
