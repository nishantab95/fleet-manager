"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import type { OwnerAsset } from "../../lib/types";
import type { WebRequest } from "../../lib/api/client";

type DueState = "NOT_DUE" | "DUE_SOON" | "DUE" | "OVERDUE" | "UNKNOWN";
type Basis = "CALENDAR_DAYS" | "ODOMETER_KM" | "HOUR_METER_HOURS";
type Criterion = { id: string; basis: Basis; interval_value: string; warning_value: string; baseline_value: string | null; baseline_date: string | null; state: DueState; current_value: string | null; due_value: string | null; current_date: string | null; due_date: string | null };
type PlanItem = { id: string; asset_id: string; task_code: string; task_label: string; action_type: string; description: string | null; enabled: boolean; state: DueState; triggered_by: Basis[]; criteria: Criterion[] };
type Plan = { id: string | null; asset_id: string; asset_code: string; manufacturer: string | null; model: string | null; model_year: number | null; is_wheeled: boolean; supports_odometer_km: boolean; supports_hour_meter: boolean; maintenance_responsibility: "OWNER_COMPANY" | "RENTER_COMPANY" | "SHARED"; managed_by_current_company: boolean; management_message: string | null; source: string | null; source_template_id: string | null; source_template_version: string | null; items: PlanItem[] };
type DueItem = PlanItem & { asset_code: string; site_name: string | null };
type Overview = { overdue: number; due: number; due_soon: number; unknown: number; open_work_orders: number; items: DueItem[] };
type WorkOrder = { id: string; asset_id: string; schedule_id: string | null; title: string; description: string | null; status: "DRAFT" | "SCHEDULED" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED"; scheduled_for: string | null; service_date: string | null; completion_odometer_km: string | null; completion_hour_meter: string | null; vendor: string | null; parts_cost: string; labor_cost: string; other_cost: string; total_cost: string; notes: string | null };
type History = { id: string; asset_id: string; task_label: string; service_date: string; odometer_km: string | null; hour_meter: string | null; vendor: string | null; total_cost: string; notes: string | null };
type Template = { id: string; name: string; version: string; source_type: string; source_reference: string | null; verification_status: string; asset_type: string | null; manufacturer: string | null; model: string | null; model_year_min: number | null; model_year_max: number | null; is_generic: boolean };
type TemplateItem = { id: string; template_id: string; task_code: string; task_label: string; action_type: string; description: string | null; enabled: boolean; criteria: Pick<Criterion, "basis" | "interval_value" | "warning_value">[] };
type Section = "overview" | "due" | "plans" | "work-orders" | "history" | "templates";

const sectionLabels: Record<Section, string> = { overview: "Overview", due: "Due", plans: "Asset Plans", "work-orders": "Work Orders", history: "History", templates: "Templates" };
const taskOptions = ["ENGINE_SERVICE", "ENGINE_OIL", "ENGINE_OIL_FILTER", "AIR_FILTER_CLEAN", "AIR_FILTER_REPLACE", "FUEL_FILTER", "GREASING", "TYRE_PRESSURE_CHECK", "TYRE_INSPECTION", "TYRE_ROTATION", "TYRE_REPLACEMENT", "HUB_SERVICE", "WHEEL_BEARING_INSPECTION", "BRAKE_INSPECTION", "BRAKE_SERVICE", "TRANSMISSION_SERVICE", "DIFFERENTIAL_OIL", "HYDRAULIC_OIL", "HYDRAULIC_FILTER", "HYDRAULIC_HOSE_INSPECTION", "COOLANT", "BATTERY_INSPECTION", "BELT_HOSE_INSPECTION", "UNDERCARRIAGE_INSPECTION", "TRACK_TENSION_CHECK", "SWING_BEARING_GREASING", "GENERAL_INSPECTION", "CUSTOM"];

function label(value: string) { return value.toLowerCase().replaceAll("_", " ").replace(/\b\w/g, (part) => part.toUpperCase()); }
function assetLabel(asset: OwnerAsset | undefined) { return asset ? asset.short_name || asset.registration_number || asset.asset_code : "Unknown asset"; }
function criterionText(item: Criterion) {
  if (item.basis === "CALENDAR_DAYS") return `${item.current_date ?? "Unknown"} / ${item.due_date ?? "Unknown"}`;
  return `${item.current_value ?? "Unknown"} / ${item.due_value ?? "Unknown"} ${item.basis === "ODOMETER_KM" ? "km" : "h"}`;
}

type ItemDraft = { id?: string; task_code: string; custom_label: string; action_type: string; enabled: boolean; days: string; days_warn: string; days_baseline: string; km: string; km_warn: string; km_baseline: string; hours: string; hours_warn: string; hours_baseline: string };
const blankItem: ItemDraft = { task_code: "ENGINE_SERVICE", custom_label: "", action_type: "SERVICE", enabled: true, days: "", days_warn: "", days_baseline: "", km: "", km_warn: "", km_baseline: "", hours: "", hours_warn: "", hours_baseline: "" };
type TemplateDraft = { name: string; version: string; source_type: string; source_reference: string; verification_status: string; asset_type: string; manufacturer: string; model: string; model_year_min: string; model_year_max: string; is_generic: boolean };
const blankTemplate: TemplateDraft = { name: "", version: "1", source_type: "COMPANY_DEFAULT", source_reference: "", verification_status: "UNVERIFIED", asset_type: "", manufacturer: "", model: "", model_year_min: "", model_year_max: "", is_generic: true };

function itemDraft(item: PlanItem): ItemDraft {
  const byBasis = new Map(item.criteria.map((criterion) => [criterion.basis, criterion]));
  const days = byBasis.get("CALENDAR_DAYS"); const km = byBasis.get("ODOMETER_KM"); const hours = byBasis.get("HOUR_METER_HOURS");
  return { id: item.id, task_code: item.task_code, custom_label: item.task_code === "CUSTOM" ? item.task_label : "", action_type: item.action_type, enabled: item.enabled, days: days?.interval_value ?? "", days_warn: days?.warning_value ?? "", days_baseline: days?.baseline_date ?? "", km: km?.interval_value ?? "", km_warn: km?.warning_value ?? "", km_baseline: km?.baseline_value ?? "", hours: hours?.interval_value ?? "", hours_warn: hours?.warning_value ?? "", hours_baseline: hours?.baseline_value ?? "" };
}

function planRowKey(item: PlanItem) {
  const criteria = item.criteria.map((entry) => `${entry.basis}:${entry.interval_value}:${entry.warning_value}:${entry.baseline_value ?? entry.baseline_date ?? ""}`).join("|");
  return `${item.id}:${item.enabled}:${criteria}`;
}

function planColumns(plan: Plan) {
  return [
    "64px",
    "minmax(180px, 1.5fr)",
    "minmax(100px, 1fr)",
    ...(plan.is_wheeled && plan.supports_odometer_km ? ["minmax(100px, 1fr)"] : []),
    ...(plan.supports_hour_meter ? ["minmax(100px, 1fr)"] : []),
    "minmax(130px, 1fr)",
    "minmax(150px, 1.2fr)",
    "minmax(130px, 1fr)",
    "minmax(100px, .8fr)",
    "minmax(150px, auto)",
  ].join(" ");
}

function criteriaForDraft(draft: ItemDraft) {
  return [
    draft.days ? { basis: "CALENDAR_DAYS", interval_value: draft.days, warning_value: draft.days_warn || "0", baseline_date: draft.days_baseline || null } : null,
    draft.km ? { basis: "ODOMETER_KM", interval_value: draft.km, warning_value: draft.km_warn || "0", baseline_value: draft.km_baseline || null } : null,
    draft.hours ? { basis: "HOUR_METER_HOURS", interval_value: draft.hours, warning_value: draft.hours_warn || "0", baseline_value: draft.hours_baseline || null } : null,
  ].filter(Boolean);
}

export function Maintenance({ assets, apiRequest, initialAssetId, onInitialHandled }: { assets: OwnerAsset[]; apiRequest: WebRequest; initialAssetId?: string | null; onInitialHandled?: () => void }) {
  const [section, setSection] = useState<Section>(initialAssetId ? "plans" : "overview");
  const [selectedAssetId, setSelectedAssetId] = useState(initialAssetId || assets[0]?.id || "");
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

  const load = useCallback(async () => {
    setError("");
    try {
      const [nextOverview, nextOrders, nextHistory, nextTemplates] = await Promise.all([
        apiRequest<Overview>("/api/v1/owner/maintenance/overview"),
        apiRequest<WorkOrder[]>("/api/v1/owner/maintenance/work-orders"),
        apiRequest<History[]>("/api/v1/owner/maintenance/history"),
        apiRequest<Template[]>("/api/v1/owner/maintenance/templates"),
      ]);
      setOverview(nextOverview); setOrders(nextOrders); setHistory(nextHistory); setTemplates(nextTemplates);
      if (selectedAssetId) {
        const [nextPlan, nextMatches] = await Promise.all([
          apiRequest<Plan>(`/api/v1/owner/maintenance/plans/${selectedAssetId}`),
          apiRequest<Template[]>(`/api/v1/owner/maintenance/templates/matches/${selectedAssetId}`),
        ]);
        setPlan(nextPlan); setMatches(nextMatches);
      }
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not load maintenance data."); }
  }, [apiRequest, selectedAssetId]);

  useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [load]);
  useEffect(() => { if (!initialAssetId) return; const timer = window.setTimeout(() => { setSelectedAssetId(initialAssetId); setSection("plans"); onInitialHandled?.(); }, 0); return () => window.clearTimeout(timer); }, [initialAssetId, onInitialHandled]);

  const mutate = async (messageText: string, work: () => Promise<unknown>) => {
    setBusy(true); setError(""); setMessage("");
    try { await work(); setMessage(messageText); await load(); return true; }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Maintenance change could not be saved."); return false; }
    finally { setBusy(false); }
  };

  const saveItem = async (event: FormEvent) => {
    event.preventDefault(); if (!draft || !selectedAssetId) return;
    const criteria = criteriaForDraft(draft);
    const path = draft.id ? `/api/v1/owner/maintenance/plans/${selectedAssetId}/items/${draft.id}` : `/api/v1/owner/maintenance/plans/${selectedAssetId}/items`;
    const ok = await mutate("Maintenance item saved.", () => apiRequest(path, { method: draft.id ? "PUT" : "POST", body: JSON.stringify({ task_code: draft.task_code, custom_label: draft.task_code === "CUSTOM" ? draft.custom_label : null, action_type: draft.action_type, enabled: draft.enabled, criteria }) }));
    if (ok) setDraft(null);
  };

  const selectTemplate = async (templateId: string) => {
    setSelectedTemplateId(templateId); setTemplateItemDraft(null);
    if (!templateId) { setTemplateItems([]); return; }
    try { setTemplateItems(await apiRequest<TemplateItem[]>(`/api/v1/owner/maintenance/templates/${templateId}/items`)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Could not load template items."); }
  };

  const saveTemplateItem = async (event: FormEvent) => {
    event.preventDefault(); if (!templateItemDraft || !selectedTemplateId) return;
    const criteria = [
      templateItemDraft.days ? { basis: "CALENDAR_DAYS", interval_value: templateItemDraft.days, warning_value: templateItemDraft.days_warn || "0" } : null,
      templateItemDraft.km ? { basis: "ODOMETER_KM", interval_value: templateItemDraft.km, warning_value: templateItemDraft.km_warn || "0" } : null,
      templateItemDraft.hours ? { basis: "HOUR_METER_HOURS", interval_value: templateItemDraft.hours, warning_value: templateItemDraft.hours_warn || "0" } : null,
    ].filter(Boolean);
    const ok = await mutate("Template item added. Existing Asset plans were not changed.", () => apiRequest(`/api/v1/owner/maintenance/templates/${selectedTemplateId}/items`, { method: "POST", body: JSON.stringify({ task_code: templateItemDraft.task_code, custom_label: templateItemDraft.task_code === "CUSTOM" ? templateItemDraft.custom_label : null, action_type: templateItemDraft.action_type, enabled: templateItemDraft.enabled, criteria }) }));
    if (ok) { setTemplateItemDraft(null); await selectTemplate(selectedTemplateId); }
  };

  const complete = async (order: WorkOrder) => {
    const serviceDate = window.prompt("Service date (YYYY-MM-DD)", new Date().toISOString().slice(0, 10)); if (!serviceDate) return;
    const orderAsset = assets.find((asset) => asset.id === order.asset_id);
    const odometer = orderAsset?.supports_odometer_km ? window.prompt("Current odometer KM (leave blank if unavailable)", "") : null;
    const hours = orderAsset?.supports_hour_meter ? window.prompt("Current hour meter / HMR (leave blank if unavailable)", "") : null;
    const vendor = window.prompt("Vendor / workshop (optional)", "");
    const parts = window.prompt("Parts cost", "0"); const labor = window.prompt("Labor cost", "0"); const other = window.prompt("Other cost", "0"); const notes = window.prompt("Notes (optional)", "");
    await mutate("Work order completed and immutable history created.", () => apiRequest(`/api/v1/owner/maintenance/work-orders/${order.id}/complete`, { method: "POST", body: JSON.stringify({ service_date: serviceDate, odometer_km: odometer || null, hour_meter: hours || null, vendor: vendor || null, parts_cost: parts || "0", labor_cost: labor || "0", other_cost: other || "0", notes: notes || null }) }));
  };

  const due = useMemo(() => overview?.items ?? [], [overview]);
  const modelTemplate = matches.find((template) => !template.is_generic);
  const genericTemplate = matches.find((template) => template.is_generic);
  return <section className="owner-panel">
    <div className="content-heading"><div><p className="owner-section-eyebrow">Fleet management</p><h2>Maintenance</h2><p className="muted">Date, KM and operating-hour triggers are evaluated independently. The earliest due trigger wins.</p></div></div>
    <div className="owner-overview-actions" role="tablist">{(Object.keys(sectionLabels) as Section[]).map((item) => <button aria-selected={section === item} className={section === item ? "active" : "secondary"} key={item} onClick={() => setSection(item)} role="tab" type="button">{sectionLabels[item]}</button>)}</div>
    {error && <div className="notice error" role="alert">{error}</div>}{message && <div className="notice" role="status">{message}</div>}
    {section === "overview" && <><div className="owner-kpi-grid"><div><span>Overdue</span><strong>{overview?.overdue ?? 0}</strong></div><div><span>Due</span><strong>{overview?.due ?? 0}</strong></div><div><span>Due soon</span><strong>{overview?.due_soon ?? 0}</strong></div><div><span>Open work orders</span><strong>{overview?.open_work_orders ?? 0}</strong></div></div><DueTable items={due} assets={assets} /></>}
    {section === "due" && <><h3>Due maintenance</h3><p className="muted">The triggering measurement is shown first; unknown meters never hide a known due date or reading.</p><DueTable items={due} assets={assets} detailed /></>}
    {section === "plans" && <div className="stack">
      <label>Asset<select value={selectedAssetId} onChange={(event) => { setSelectedAssetId(event.target.value); setDraft(null); setCopySourceAssetId(""); }}>{assets.map((asset) => <option key={asset.id} value={asset.id}>{assetLabel(asset)}</option>)}</select></label>
      {plan && <><div className="table-card"><strong>MAINTENANCE SETUP</strong><span>{plan.asset_code}</span><span>{[plan.manufacturer, plan.model, plan.model_year].filter(Boolean).join(" ") || "Make / model / year not provided"}</span><span>{assets.find((asset) => asset.id === plan.asset_id)?.ownership_type ?? "OWNED"}</span><span>Meters: {[plan.supports_odometer_km && "KM", plan.supports_hour_meter && "HMR"].filter(Boolean).join(" + ")}</span>{plan.managed_by_current_company && <span>Plan: {label(plan.source ?? "CUSTOM")}{plan.source_template_version ? ` · v${plan.source_template_version}` : ""}</span>}</div>
      {!plan.managed_by_current_company ? <div className="notice"><strong>Managed by rental owner</strong><p>Operational KM/HMR continues to be recorded. This company does not configure service intervals or complete periodic maintenance for this Asset.</p></div> : <>
      <div className="owner-row-actions"><button onClick={() => setDraft(blankItem)} type="button">+ Add custom item</button>{!plan.id && modelTemplate && <button className="secondary" disabled={busy} onClick={() => void mutate("Template copied into this Asset plan.", () => apiRequest(`/api/v1/owner/maintenance/plans/${selectedAssetId}/apply-template`, { method: "POST", body: JSON.stringify({ template_id: modelTemplate.id }) }))} type="button">Apply template</button>}{!plan.id && !modelTemplate && genericTemplate && <button className="secondary" disabled={busy} onClick={() => void mutate("Company starter copied into this Asset plan.", () => apiRequest(`/api/v1/owner/maintenance/plans/${selectedAssetId}/apply-template`, { method: "POST", body: JSON.stringify({ template_id: genericTemplate.id }) }))} type="button">Apply company starter</button>}</div>
      {!plan.id && !modelTemplate && <div className="notice">No model-specific maintenance template is available. Use a company starter, copy a similar Asset plan, or start blank. No OEM intervals are invented.</div>}
      {!plan.id && <div className="inline-form"><label>Copy plan from similar Asset<select aria-label="Copy maintenance plan from Asset" onChange={(event) => setCopySourceAssetId(event.target.value)} value={copySourceAssetId}><option value="">Choose Asset…</option>{assets.filter((asset) => asset.id !== selectedAssetId && asset.ownership_type === "OWNED").map((asset) => <option key={asset.id} value={asset.id}>{assetLabel(asset)}</option>)}</select></label><button className="secondary" disabled={busy || !copySourceAssetId} onClick={() => void mutate("Maintenance plan copied without another Asset's service baselines.", () => apiRequest(`/api/v1/owner/maintenance/plans/${selectedAssetId}/copy`, { method: "POST", body: JSON.stringify({ source_asset_id: copySourceAssetId }) }))} type="button">Copy plan</button></div>}
      <div className="table-card maintenance-plan-table"><div className="table-row" style={{ gridTemplateColumns: planColumns(plan) }}><strong>On</strong><strong>Maintenance Item</strong><strong>Days</strong>{plan.is_wheeled && plan.supports_odometer_km && <strong>KM</strong>}{plan.supports_hour_meter && <strong>Hours</strong>}<strong>Warning</strong><strong>Last Service</strong><strong>Next Due</strong><strong>Status</strong><strong>Action</strong></div>{plan.items.length === 0 && <div className="table-row"><span>No maintenance items configured.</span></div>}{plan.items.map((item) => <PlanRow key={planRowKey(item)} item={item} plan={plan} busy={busy} onRemove={() => mutate("Custom maintenance item removed.", () => apiRequest(`/api/v1/owner/maintenance/plans/items/${item.id}`, { method: "DELETE" }))} onSave={(next) => mutate("Maintenance item saved.", () => apiRequest(`/api/v1/owner/maintenance/plans/${selectedAssetId}/items/${item.id}`, { method: "PUT", body: JSON.stringify({ task_code: next.task_code, custom_label: next.task_code === "CUSTOM" ? next.custom_label : null, action_type: next.action_type, enabled: next.enabled, criteria: criteriaForDraft(next) }) }))} />)}</div>
      {draft && <ItemEditor draft={draft} plan={plan} setDraft={setDraft} onSubmit={saveItem} busy={busy} />}</>}</>}
    </div>}
    {section === "work-orders" && <div className="stack"><form className="inline-form" onSubmit={(event) => { event.preventDefault(); if (!selectedAssetId || !workTitle.trim()) return; void mutate("Work order created.", () => apiRequest("/api/v1/owner/maintenance/work-orders", { method: "POST", body: JSON.stringify({ asset_id: selectedAssetId, title: workTitle }) })).then((ok) => { if (ok) setWorkTitle(""); }); }}><label>Asset<select value={selectedAssetId} onChange={(event) => setSelectedAssetId(event.target.value)}>{assets.filter((asset) => asset.ownership_type === "OWNED").map((asset) => <option key={asset.id} value={asset.id}>{assetLabel(asset)}</option>)}</select></label><label>Work order title<input required value={workTitle} onChange={(event) => setWorkTitle(event.target.value)} /></label><button disabled={busy} type="submit">Create draft</button></form>{orders.map((order) => <div className="table-card" key={order.id}><div className="table-row"><strong>{order.title}</strong><span>{assetLabel(assets.find((asset) => asset.id === order.asset_id))}</span><span>{label(order.status)}</span><span>{order.scheduled_for ?? "Not scheduled"}</span><span>Total ₹{order.total_cost}</span></div>{!(["COMPLETED", "CANCELLED"] as string[]).includes(order.status) && <div className="owner-row-actions">{order.status === "DRAFT" && <button className="secondary" onClick={() => void mutate("Work order scheduled.", () => apiRequest(`/api/v1/owner/maintenance/work-orders/${order.id}/transition`, { method: "POST", body: JSON.stringify({ status: "SCHEDULED" }) }))} type="button">Schedule</button>}{order.status !== "IN_PROGRESS" && <button className="secondary" onClick={() => void mutate("Work started.", () => apiRequest(`/api/v1/owner/maintenance/work-orders/${order.id}/transition`, { method: "POST", body: JSON.stringify({ status: "IN_PROGRESS" }) }))} type="button">Start</button>}<button onClick={() => void complete(order)} type="button">Complete</button><button className="secondary" onClick={() => void mutate("Work order cancelled.", () => apiRequest(`/api/v1/owner/maintenance/work-orders/${order.id}/transition`, { method: "POST", body: JSON.stringify({ status: "CANCELLED" }) }))} type="button">Cancel</button></div>}</div>)}</div>}
    {section === "history" && <div className="table-card"><div className="table-row"><strong>Date</strong><strong>Asset</strong><strong>Service</strong><strong>KM</strong><strong>HMR</strong><strong>Vendor</strong><strong>Cost</strong><strong>Notes</strong></div>{history.map((item) => <div className="table-row" key={item.id}><span>{item.service_date}</span><span>{assetLabel(assets.find((asset) => asset.id === item.asset_id))}</span><span>{item.task_label}</span><span>{item.odometer_km ?? "N/A"}</span><span>{item.hour_meter ?? "N/A"}</span><span>{item.vendor ?? "—"}</span><span>₹{item.total_cost}</span><span>{item.notes ?? "—"}</span></div>)}</div>}
    {section === "templates" && <div className="stack"><div className="notice">Manufacturer-specific intervals must come from verified OEM/service data. Templates are versioned and copied into Asset plans; later edits never rewrite an existing plan.</div><form className="owner-form-panel" onSubmit={(event) => { event.preventDefault(); void mutate("Maintenance template created.", () => apiRequest("/api/v1/owner/maintenance/templates", { method: "POST", body: JSON.stringify({ name: templateDraft.name, version: templateDraft.version, source_type: templateDraft.source_type, source_reference: templateDraft.source_reference || null, verification_status: templateDraft.verification_status, asset_type: templateDraft.asset_type || null, manufacturer: templateDraft.manufacturer || null, model: templateDraft.model || null, model_year_min: templateDraft.model_year_min ? Number(templateDraft.model_year_min) : null, model_year_max: templateDraft.model_year_max ? Number(templateDraft.model_year_max) : null, is_generic: templateDraft.is_generic }) })).then((ok) => { if (ok) setTemplateDraft(blankTemplate); }); }}><div className="owner-form-grid"><label>Template name<input required value={templateDraft.name} onChange={(event) => setTemplateDraft({ ...templateDraft, name: event.target.value })} /></label><label>Version<input required value={templateDraft.version} onChange={(event) => setTemplateDraft({ ...templateDraft, version: event.target.value })} /></label><label>Source type<select value={templateDraft.source_type} onChange={(event) => setTemplateDraft({ ...templateDraft, source_type: event.target.value })}><option value="COMPANY_DEFAULT">Company default</option><option value="OEM">OEM</option><option value="OTHER">Other</option></select></label><label>Verification<select value={templateDraft.verification_status} onChange={(event) => setTemplateDraft({ ...templateDraft, verification_status: event.target.value })}><option value="UNVERIFIED">Unverified</option><option value="VERIFIED">Verified</option></select></label><label>Source reference<input required={templateDraft.source_type === "OEM" && templateDraft.verification_status === "VERIFIED"} value={templateDraft.source_reference} onChange={(event) => setTemplateDraft({ ...templateDraft, source_reference: event.target.value })} /></label><label>Asset type<select value={templateDraft.asset_type} onChange={(event) => setTemplateDraft({ ...templateDraft, asset_type: event.target.value })}><option value="">Any</option>{["TIPPER", "EXCAVATOR", "BACKHOE_LOADER", "ROLLER", "GRADER"].map((item) => <option key={item}>{item}</option>)}</select></label><label>Manufacturer<input value={templateDraft.manufacturer} onChange={(event) => setTemplateDraft({ ...templateDraft, manufacturer: event.target.value })} /></label><label>Model<input value={templateDraft.model} onChange={(event) => setTemplateDraft({ ...templateDraft, model: event.target.value })} /></label><label>Year from<input min="1900" max="2200" type="number" value={templateDraft.model_year_min} onChange={(event) => setTemplateDraft({ ...templateDraft, model_year_min: event.target.value })} /></label><label>Year to<input min="1900" max="2200" type="number" value={templateDraft.model_year_max} onChange={(event) => setTemplateDraft({ ...templateDraft, model_year_max: event.target.value })} /></label><label><input checked={templateDraft.is_generic} onChange={(event) => setTemplateDraft({ ...templateDraft, is_generic: event.target.checked })} type="checkbox" /> Generic fallback</label></div><button disabled={busy} type="submit">Create template version</button></form><label>Review template<select aria-label="Review maintenance template" value={selectedTemplateId} onChange={(event) => void selectTemplate(event.target.value)}><option value="">Choose template…</option>{templates.map((template) => <option key={template.id} value={template.id}>{template.name} · v{template.version}</option>)}</select></label>{selectedTemplateId && <><div className="owner-row-actions"><button onClick={() => setTemplateItemDraft(blankItem)} type="button">Add template item</button></div><div className="table-card">{templateItems.length === 0 && <div className="table-row"><span>No template items yet.</span></div>}{templateItems.map((item) => <div className="table-row" key={item.id}><strong>{item.task_label}</strong><span>{label(item.action_type)}</span><span>{item.criteria.map((criterion) => `${label(criterion.basis)} ${criterion.interval_value} (warn ${criterion.warning_value})`).join(" · ")}</span><span>{item.enabled ? "Enabled" : "Disabled"}</span></div>)}</div>{templateItemDraft && <TemplateItemEditor draft={templateItemDraft} setDraft={setTemplateItemDraft} onSubmit={saveTemplateItem} busy={busy} />}</>}{templates.map((template) => <div className="table-card" key={template.id}><div className="table-row"><strong>{template.name}</strong><span>v{template.version}</span><span>{label(template.source_type)}</span><span>{label(template.verification_status)}</span><span>{[template.manufacturer, template.model, template.model_year_min && `${template.model_year_min}–${template.model_year_max ?? ""}`].filter(Boolean).join(" · ") || "Generic editable starter"}</span><span>{template.source_reference ?? "No source reference"}</span></div></div>)}</div>}
  </section>;
}

function DueTable({ items, assets, detailed = false }: { items: DueItem[]; assets: OwnerAsset[]; detailed?: boolean }) {
  return <div className="table-card"><div className="table-row"><strong>Asset</strong><strong>Site</strong><strong>Maintenance item</strong><strong>Trigger</strong><strong>Current / due</strong><strong>Status</strong></div>{items.length === 0 && <div className="table-row"><span>No due maintenance items.</span></div>}{items.map((item) => <div className="table-row" key={item.id}><span>{assetLabel(assets.find((asset) => asset.id === item.asset_id)) || item.asset_code}</span><span>{item.site_name ?? "Undeployed"}</span><span>{item.task_label}{detailed && <small>{item.criteria.map((entry) => `${label(entry.basis)} ${entry.state}`).join(" · ")}</small>}</span><span>{item.triggered_by.map(label).join(" + ")}</span><span>{item.criteria.map(criterionText).join(" · ")}</span><strong>{label(item.state)}</strong></div>)}</div>;
}

function PlanRow({ item, plan, busy, onSave, onRemove }: { item: PlanItem; plan: Plan; busy: boolean; onSave: (draft: ItemDraft) => Promise<unknown>; onRemove: () => Promise<unknown> }) {
  const [draft, setDraft] = useState(() => itemDraft(item));
  const nextDue = item.criteria.map((entry) => entry.due_date ?? (entry.due_value ? `${entry.due_value} ${entry.basis === "ODOMETER_KM" ? "km" : "h"}` : "Unknown")).join(" · ");
  const field = (name: keyof ItemDraft, ariaLabel: string, type: "number" | "date" = "number") => <input aria-label={`${ariaLabel} — ${item.task_label}`} min={type === "number" ? "0" : undefined} onChange={(event) => setDraft({ ...draft, [name]: event.target.value })} step={type === "number" ? "0.01" : undefined} type={type} value={String(draft[name] ?? "")} />;
  return <div className="table-row maintenance-plan-row" style={{ gridTemplateColumns: planColumns(plan) }}>
    <span><input aria-label={`Enabled — ${item.task_label}`} checked={draft.enabled} onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })} type="checkbox" /></span>
    <span><strong>{item.task_label}</strong><small>{label(item.action_type)}</small></span>
    <span>{field("days", "Days")}</span>
    {plan.is_wheeled && plan.supports_odometer_km && <span>{field("km", "KM")}</span>}
    {plan.supports_hour_meter && <span>{field("hours", "Hours")}</span>}
    <span className="stack compact-stack">{field("days_warn", "Days warning")}{plan.is_wheeled && plan.supports_odometer_km && field("km_warn", "KM warning")}{plan.supports_hour_meter && field("hours_warn", "Hours warning")}</span>
    <span className="stack compact-stack">{field("days_baseline", "Last service date", "date")}{plan.is_wheeled && plan.supports_odometer_km && field("km_baseline", "Last service KM")}{plan.supports_hour_meter && field("hours_baseline", "Last service HMR")}</span>
    <span>{nextDue || "Unknown"}</span>
    <strong>{label(item.state)}</strong>
    <span className="owner-row-actions"><button disabled={busy || (!draft.days && !draft.km && !draft.hours)} onClick={() => void onSave(draft)} type="button">Save</button>{item.task_code === "CUSTOM" && <button className="owner-text-button owner-text-button--danger" disabled={busy} onClick={() => void onRemove()} type="button">Remove</button>}</span>
  </div>;
}

function ItemEditor({ draft, plan, setDraft, onSubmit, busy }: { draft: ItemDraft; plan: Plan; setDraft: (next: ItemDraft | null) => void; onSubmit: (event: FormEvent) => void; busy: boolean }) {
  return <form className="owner-form-panel" onSubmit={onSubmit}><div className="owner-form-heading"><div><h3>Add custom maintenance item</h3><p>Add one uncommon task here. Routine interval changes stay directly editable in the list.</p></div></div><div className="owner-form-grid"><label>Task<select value={draft.task_code} onChange={(event) => setDraft({ ...draft, task_code: event.target.value })}>{taskOptions.map((item) => <option key={item} value={item}>{label(item)}</option>)}</select></label>{draft.task_code === "CUSTOM" && <label>Custom task name<input required value={draft.custom_label} onChange={(event) => setDraft({ ...draft, custom_label: event.target.value })} /></label>}<label>Action<select value={draft.action_type} onChange={(event) => setDraft({ ...draft, action_type: event.target.value })}>{["INSPECT", "CLEAN", "LUBRICATE", "SERVICE", "REPLACE"].map((item) => <option key={item}>{item}</option>)}</select></label><label><input checked={draft.enabled} onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })} type="checkbox" /> Enabled</label><label>Every days<input min="1" step="1" type="number" value={draft.days} onChange={(event) => setDraft({ ...draft, days: event.target.value })} /></label><label>Warn days before<input min="0" step="1" type="number" value={draft.days_warn} onChange={(event) => setDraft({ ...draft, days_warn: event.target.value })} /></label><label>Last service date<input type="date" value={draft.days_baseline} onChange={(event) => setDraft({ ...draft, days_baseline: event.target.value })} /></label>{plan.is_wheeled && plan.supports_odometer_km && <><label>Every KM<input min="0.01" step="0.01" type="number" value={draft.km} onChange={(event) => setDraft({ ...draft, km: event.target.value })} /></label><label>Warn KM before<input min="0" step="0.01" type="number" value={draft.km_warn} onChange={(event) => setDraft({ ...draft, km_warn: event.target.value })} /></label><label>Last service KM<input min="0" step="0.01" type="number" value={draft.km_baseline} onChange={(event) => setDraft({ ...draft, km_baseline: event.target.value })} /></label></>}{plan.supports_hour_meter && <><label>Every hours<input min="0.01" step="0.01" type="number" value={draft.hours} onChange={(event) => setDraft({ ...draft, hours: event.target.value })} /></label><label>Warn hours before<input min="0" step="0.01" type="number" value={draft.hours_warn} onChange={(event) => setDraft({ ...draft, hours_warn: event.target.value })} /></label><label>Last service HMR<input min="0" step="0.01" type="number" value={draft.hours_baseline} onChange={(event) => setDraft({ ...draft, hours_baseline: event.target.value })} /></label></>}</div><div className="owner-form-actions"><button className="secondary" onClick={() => setDraft(null)} type="button">Cancel</button><button disabled={busy || (!draft.days && !draft.km && !draft.hours)} type="submit">Add item</button></div></form>;
}

function TemplateItemEditor({ draft, setDraft, onSubmit, busy }: { draft: ItemDraft; setDraft: (next: ItemDraft | null) => void; onSubmit: (event: FormEvent) => void; busy: boolean }) {
  return <form className="owner-form-panel" onSubmit={onSubmit}><div className="owner-form-heading"><div><h3>Add template item</h3><p>Use validated source intervals only. Incompatible meter triggers are omitted when the template is copied to an Asset.</p></div></div><div className="owner-form-grid"><label>Task<select value={draft.task_code} onChange={(event) => setDraft({ ...draft, task_code: event.target.value })}>{taskOptions.map((item) => <option key={item} value={item}>{label(item)}</option>)}</select></label>{draft.task_code === "CUSTOM" && <label>Custom task name<input required value={draft.custom_label} onChange={(event) => setDraft({ ...draft, custom_label: event.target.value })} /></label>}<label>Action<select value={draft.action_type} onChange={(event) => setDraft({ ...draft, action_type: event.target.value })}>{["INSPECT", "CLEAN", "LUBRICATE", "SERVICE", "REPLACE"].map((item) => <option key={item}>{item}</option>)}</select></label><label>Every days<input min="1" step="1" type="number" value={draft.days} onChange={(event) => setDraft({ ...draft, days: event.target.value })} /></label><label>Warn days before<input min="0" step="1" type="number" value={draft.days_warn} onChange={(event) => setDraft({ ...draft, days_warn: event.target.value })} /></label><label>Every KM<input min="0.01" step="0.01" type="number" value={draft.km} onChange={(event) => setDraft({ ...draft, km: event.target.value })} /></label><label>Warn KM before<input min="0" step="0.01" type="number" value={draft.km_warn} onChange={(event) => setDraft({ ...draft, km_warn: event.target.value })} /></label><label>Every hours<input min="0.01" step="0.01" type="number" value={draft.hours} onChange={(event) => setDraft({ ...draft, hours: event.target.value })} /></label><label>Warn hours before<input min="0" step="0.01" type="number" value={draft.hours_warn} onChange={(event) => setDraft({ ...draft, hours_warn: event.target.value })} /></label></div><div className="owner-form-actions"><button className="secondary" onClick={() => setDraft(null)} type="button">Cancel</button><button disabled={busy || (!draft.days && !draft.km && !draft.hours)} type="submit">Add template item</button></div></form>;
}
