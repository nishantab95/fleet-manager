"use client";

/* eslint-disable @next/next/no-img-element -- private object URLs cannot use the Next image loader */

import { Fragment, useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { fetchPrivateEvidence, type WebRequest } from "../../lib/api/client";
import type { OwnerAsset } from "../../lib/types";

type DueState = "NOT_DUE" | "DUE_SOON" | "DUE" | "OVERDUE" | "UNKNOWN";
type Basis = "CALENDAR_DAYS" | "ODOMETER_KM" | "HOUR_METER_HOURS";
type Criterion = {
  id: string; basis: Basis; interval_value: string; warning_value: string;
  baseline_value: string | null; baseline_date: string | null; state: DueState;
  current_value: string | null; due_value: string | null;
  current_date: string | null; due_date: string | null;
};
type PlanItem = {
  id: string; asset_id: string; task_code: string; task_label: string; action_type: string;
  description: string | null; enabled: boolean; state: DueState;
  triggered_by: Basis[]; criteria: Criterion[];
};
type Plan = {
  id: string | null; asset_id: string; asset_code: string; asset_type: string;
  manufacturer: string | null; model: string | null; model_year: number | null;
  is_wheeled: boolean; supports_odometer_km: boolean; supports_hour_meter: boolean;
  maintenance_responsibility: "OWNER_COMPANY" | "RENTER_COMPANY" | "SHARED";
  managed_by_current_company: boolean; management_message: string | null;
  source: string | null; source_template_id: string | null;
  source_template_version: string | null; items: PlanItem[];
};
type DueItem = PlanItem & { asset_code: string; site_name: string | null };
type Overview = {
  overdue: number; due: number; due_soon: number; unknown: number;
  open_work_orders: number; items: DueItem[];
};
type Template = {
  id: string; name: string; template_type: "COMPANY_STARTER" | "OEM_VERIFIED";
  confidence: "SUGGESTED" | "VERIFIED";
};
type TemplateItem = {
  id: string; template_id: string; task_code: string; task_label: string;
  action_type: string; description: string | null; enabled: boolean;
  criteria: Pick<Criterion, "basis" | "interval_value" | "warning_value">[];
};
type HistoryEvidence = { evidence_id: string; content_type: string; size_bytes: number };
type History = {
  id: string; asset_id: string; asset_code?: string; task_label: string; service_date: string;
  odometer_km: string | null; hour_meter: string | null; vendor: string | null;
  parts_cost?: string; labor_cost?: string; other_cost?: string; total_cost: string;
  notes: string | null; created_at?: string; site_name?: string | null;
  submitted_by?: string; approved_by?: string; status?: string; evidence?: HistoryEvidence[];
};
type Section = "overview" | "plans" | "history";

const sectionLabels: Record<Section, string> = {
  overview: "Overview",
  plans: "Asset Plans",
  history: "History",
};
const severityRank: Record<DueState, number> = {
  OVERDUE: 0, DUE: 1, DUE_SOON: 2, UNKNOWN: 3, NOT_DUE: 4,
};

function label(value: string) {
  return value.toLowerCase().replaceAll("_", " ").replace(/\b\w/g, (part) => part.toUpperCase());
}

function assetLabel(asset: OwnerAsset | undefined) {
  return asset ? asset.short_name || asset.registration_number || asset.asset_code : "Unknown asset";
}

function companyManages(asset: OwnerAsset) {
  return asset.ownership_type === "OWNED" && asset.maintenance_responsibility !== "RENTER_COMPANY";
}

function basisLabel(basis: Basis) {
  if (basis === "CALENDAR_DAYS") return "Date";
  if (basis === "ODOMETER_KM") return "KM";
  return "Hours";
}

function intervalText(criteria: Pick<Criterion, "basis" | "interval_value">[]) {
  if (criteria.length === 0) return ["Not scheduled"];
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
    return entry.baseline_value
      ? `${Number(entry.baseline_value).toLocaleString()} ${unit}`
      : `${unit} not set`;
  });
}

function nextDueText(criteria: Criterion[]) {
  if (criteria.length === 0) return ["Not scheduled"];
  return criteria.map((entry) => {
    if (entry.basis === "CALENDAR_DAYS") return entry.due_date ?? "Date unknown";
    const unit = entry.basis === "ODOMETER_KM" ? "km" : "h";
    return entry.due_value
      ? `${Number(entry.due_value).toLocaleString()} ${unit}`
      : `${unit} unknown`;
  });
}

function criterionReading(item: Criterion) {
  if (item.basis === "CALENDAR_DAYS") {
    return `${item.current_date ?? "Unknown"} / ${item.due_date ?? "Unknown"}`;
  }
  const unit = item.basis === "ODOMETER_KM" ? "km" : "h";
  return `${item.current_value ?? "Unknown"} / ${item.due_value ?? "Unknown"} ${unit}`;
}

type ItemDraft = {
  task_code: string; custom_label: string; action_type: string; enabled: boolean;
  days: string; days_warn: string; days_baseline: string;
  km: string; km_warn: string; km_baseline: string;
  hours: string; hours_warn: string; hours_baseline: string;
};

const blankItem: ItemDraft = {
  task_code: "CUSTOM", custom_label: "", action_type: "SERVICE", enabled: true,
  days: "", days_warn: "", days_baseline: "", km: "", km_warn: "", km_baseline: "",
  hours: "", hours_warn: "", hours_baseline: "",
};

function itemDraft(item: PlanItem): ItemDraft {
  const byBasis = new Map(item.criteria.map((criterion) => [criterion.basis, criterion]));
  const days = byBasis.get("CALENDAR_DAYS");
  const km = byBasis.get("ODOMETER_KM");
  const hours = byBasis.get("HOUR_METER_HOURS");
  return {
    task_code: item.task_code,
    custom_label: item.task_code === "CUSTOM" ? item.task_label : "",
    action_type: item.action_type,
    enabled: item.enabled,
    days: days?.interval_value ?? "",
    days_warn: days?.warning_value ?? "",
    days_baseline: days?.baseline_date ?? "",
    km: km?.interval_value ?? "",
    km_warn: km?.warning_value ?? "",
    km_baseline: km?.baseline_value ?? "",
    hours: hours?.interval_value ?? "",
    hours_warn: hours?.warning_value ?? "",
    hours_baseline: hours?.baseline_value ?? "",
  };
}

function criteriaForDraft(draft: ItemDraft) {
  return [
    draft.days ? {
      basis: "CALENDAR_DAYS", interval_value: draft.days,
      warning_value: draft.days_warn || "0", baseline_date: draft.days_baseline || null,
    } : null,
    draft.km ? {
      basis: "ODOMETER_KM", interval_value: draft.km,
      warning_value: draft.km_warn || "0", baseline_value: draft.km_baseline || null,
    } : null,
    draft.hours ? {
      basis: "HOUR_METER_HOURS", interval_value: draft.hours,
      warning_value: draft.hours_warn || "0", baseline_value: draft.hours_baseline || null,
    } : null,
  ].filter(Boolean);
}

export function Maintenance({
  assets,
  apiRequest,
  accessToken = "",
  initialAssetId,
  onInitialHandled,
}: {
  assets: OwnerAsset[];
  apiRequest: WebRequest;
  accessToken?: string;
  initialAssetId?: string | null;
  onInitialHandled?: () => void;
}) {
  const managedAssets = useMemo(() => assets.filter(companyManages), [assets]);
  const [section, setSection] = useState<Section>(initialAssetId ? "plans" : "overview");
  const [selectedAssetId, setSelectedAssetId] = useState(initialAssetId || managedAssets[0]?.id || "");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [history, setHistory] = useState<History[]>([]);
  const [matches, setMatches] = useState<Template[]>([]);
  const [recommendedPreview, setRecommendedPreview] = useState<TemplateItem[] | null>(null);
  const [customDraft, setCustomDraft] = useState<ItemDraft | null>(null);
  const [copyOpen, setCopyOpen] = useState(false);
  const [copySourceAssetId, setCopySourceAssetId] = useState("");
  const [copyPreview, setCopyPreview] = useState<Plan | null>(null);
  const [copyError, setCopyError] = useState("");
  const [historyAssetId, setHistoryAssetId] = useState("");
  const [historyFrom, setHistoryFrom] = useState("");
  const [historyTo, setHistoryTo] = useState("");
  const [expandedHistoryId, setExpandedHistoryId] = useState<string | null>(null);
  const [evidenceUrl, setEvidenceUrl] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const [nextOverview, nextHistory] = await Promise.all([
        apiRequest<Overview>("/api/v1/owner/maintenance/overview"),
        apiRequest<History[]>("/api/v1/owner/maintenance/history"),
      ]);
      setOverview(nextOverview);
      setHistory(nextHistory);
      if (!selectedAssetId) {
        setPlan(null);
        setMatches([]);
        return;
      }
      const nextPlan = await apiRequest<Plan>(`/api/v1/owner/maintenance/plans/${selectedAssetId}`);
      setPlan(nextPlan);
      if (!nextPlan.managed_by_current_company) {
        setMatches([]);
        return;
      }
      setMatches(await apiRequest<Template[]>(
        `/api/v1/owner/maintenance/templates/matches/${selectedAssetId}`,
      ));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load maintenance data.");
    }
  }, [apiRequest, selectedAssetId]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    if (!initialAssetId) return;
    const timer = window.setTimeout(() => {
      setSelectedAssetId(initialAssetId);
      setSection("plans");
      onInitialHandled?.();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [initialAssetId, onInitialHandled]);

  useEffect(() => {
    if (selectedAssetId || !managedAssets[0]) return;
    const timer = window.setTimeout(() => setSelectedAssetId(managedAssets[0].id), 0);
    return () => window.clearTimeout(timer);
  }, [managedAssets, selectedAssetId]);

  useEffect(() => () => {
    if (evidenceUrl) URL.revokeObjectURL(evidenceUrl);
  }, [evidenceUrl]);

  const mutate = async (messageText: string, work: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await work();
      setMessage(messageText);
      await load();
      return true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Maintenance change could not be saved.");
      return false;
    } finally {
      setBusy(false);
    }
  };

  const recommended = matches[0];
  const selectedAsset = assets.find((asset) => asset.id === selectedAssetId);
  const directRentedContext = Boolean(selectedAsset && !companyManages(selectedAsset));
  const dueItems = useMemo(
    () => (overview?.items ?? [])
      .filter((item) => item.state !== "NOT_DUE")
      .sort((a, b) => severityRank[a.state] - severityRank[b.state]),
    [overview],
  );
  const filteredHistory = useMemo(() => history.filter((entry) => {
    if (historyAssetId && entry.asset_id !== historyAssetId) return false;
    if (historyFrom && entry.service_date < historyFrom) return false;
    if (historyTo && entry.service_date > historyTo) return false;
    return true;
  }), [history, historyAssetId, historyFrom, historyTo]);

  const previewRecommendation = async () => {
    if (!recommended) return;
    setError("");
    try {
      setRecommendedPreview(await apiRequest<TemplateItem[]>(
        `/api/v1/owner/maintenance/templates/${recommended.id}/items`,
      ));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not preview the recommended plan.");
    }
  };

  const applyRecommendation = async () => {
    if (!recommended || !selectedAssetId) return;
    const ok = await mutate(
      "Recommended plan applied. You can adjust any interval below.",
      () => apiRequest(`/api/v1/owner/maintenance/plans/${selectedAssetId}/apply-template`, {
        method: "POST",
        body: JSON.stringify({ template_id: recommended.id }),
      }),
    );
    if (ok) setRecommendedPreview(null);
  };

  const previewCopy = async () => {
    if (!copySourceAssetId) return;
    setCopyError("");
    setCopyPreview(null);
    try {
      const source = await apiRequest<Plan>(`/api/v1/owner/maintenance/plans/${copySourceAssetId}`);
      if (!source.id || source.items.length === 0) {
        setCopyError("That Asset does not have a maintenance plan to copy.");
        return;
      }
      setCopyPreview(source);
    } catch (caught) {
      setCopyError(caught instanceof Error ? caught.message : "Could not preview that Asset plan.");
    }
  };

  const copyPlan = async () => {
    if (!copyPreview || !selectedAssetId) return;
    const ok = await mutate(
      "Maintenance plan copied without service baselines.",
      () => apiRequest(`/api/v1/owner/maintenance/plans/${selectedAssetId}/copy`, {
        method: "POST",
        body: JSON.stringify({ source_asset_id: copyPreview.asset_id }),
      }),
    );
    if (ok) {
      setCopyOpen(false);
      setCopyPreview(null);
      setCopySourceAssetId("");
    }
  };

  const saveCustomItem = async (event: FormEvent) => {
    event.preventDefault();
    if (!customDraft || !selectedAssetId) return;
    const ok = await mutate(
      "Custom maintenance item added.",
      () => apiRequest(`/api/v1/owner/maintenance/plans/${selectedAssetId}/items`, {
        method: "POST",
        body: JSON.stringify({
          task_code: "CUSTOM",
          custom_label: customDraft.custom_label,
          action_type: customDraft.action_type,
          enabled: customDraft.enabled,
          criteria: criteriaForDraft(customDraft),
        }),
      }),
    );
    if (ok) setCustomDraft(null);
  };

  const openEvidence = async (recordId: string, evidenceId: string) => {
    setError("");
    try {
      const result = await fetchPrivateEvidence(
        `/api/v1/owner/maintenance/history/${recordId}/evidence/${evidenceId}`,
        accessToken,
      );
      if (evidenceUrl) URL.revokeObjectURL(evidenceUrl);
      setEvidenceUrl(result.url);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load proof photo.");
    }
  };

  return <section className="owner-panel maintenance-page">
    <header className="owner-section-heading maintenance-heading">
      <div>
        <p className="owner-section-eyebrow">Fleet management</p>
        <h2>Maintenance</h2>
        <p className="muted">See what needs attention, configure each Asset, and review service history.</p>
      </div>
    </header>

    <div className="maintenance-tabs" role="tablist">
      {(Object.keys(sectionLabels) as Section[]).map((item) => <button
        aria-selected={section === item}
        className={section === item ? "active" : "secondary"}
        key={item}
        onClick={() => setSection(item)}
        role="tab"
        type="button"
      >{sectionLabels[item]}</button>)}
    </div>

    {error && <div className="notice error" role="alert">{error}</div>}
    {message && <div className="notice" role="status">{message}</div>}

    {section === "overview" && <div className="maintenance-section">
      <div aria-label="Maintenance alert totals" className="maintenance-counters">
        <span className="maintenance-counter maintenance-counter--overdue"><strong>{overview?.overdue ?? 0}</strong> Overdue</span>
        <span className="maintenance-counter maintenance-counter--due"><strong>{overview?.due ?? 0}</strong> Due</span>
        <span className="maintenance-counter maintenance-counter--soon"><strong>{overview?.due_soon ?? 0}</strong> Due Soon</span>
      </div>
      <DueTable assets={managedAssets} items={dueItems} />
    </div>}

    {section === "plans" && <div className="maintenance-section">
      {directRentedContext ? <div className="maintenance-external" role="status">
        <strong>Maintenance managed by rental owner.</strong>
      </div> : <>
        {managedAssets.length === 0
          ? <div className="notice">No company-maintained Assets are available.</div>
          : <label className="maintenance-asset-picker">Asset
              <select
                aria-label="Maintenance Asset"
                value={selectedAssetId}
                onChange={(event) => {
                  setSelectedAssetId(event.target.value);
                  setRecommendedPreview(null);
                  setCustomDraft(null);
                  setCopyOpen(false);
                }}
              >
                {managedAssets.map((asset) => <option key={asset.id} value={asset.id}>
                  {assetLabel(asset)}
                </option>)}
              </select>
            </label>}

        {plan?.managed_by_current_company && <>
          <div className="maintenance-plan-header">
            <div><span className="owner-section-eyebrow">Asset plan</span><strong>{plan.asset_code}</strong></div>
            <span>{[plan.manufacturer, plan.model, plan.model_year].filter(Boolean).join(" · ") || "Make / model / year not provided"}</span>
            <span>{[plan.supports_odometer_km && "KM", plan.supports_hour_meter && "HMR"].filter(Boolean).join(" + ") || "Date only"}</span>
            <span className="owner-status-chip owner-status-chip--active">Owned</span>
          </div>

          {!plan.id && recommended && <section className="maintenance-recommendation">
            <div>
              <p className="owner-section-eyebrow">Recommended plan</p>
              <h3>{recommended.template_type === "OEM_VERIFIED" ? "Exact OEM plan" : "Starter plan"}</h3>
              <p>{recommended.name}</p>
            </div>
            <div className="owner-row-actions">
              <button className="secondary" onClick={() => void previewRecommendation()} type="button">Preview</button>
              <button disabled={busy} onClick={() => void applyRecommendation()} type="button">Apply Plan</button>
            </div>
          </section>}

          {recommendedPreview && recommended && <RecommendedPreview
            busy={busy}
            items={recommendedPreview}
            name={recommended.name}
            onApply={() => void applyRecommendation()}
            onClose={() => setRecommendedPreview(null)}
          />}

          <div className="maintenance-plan-actions">
            <button onClick={() => setCustomDraft({ ...blankItem })} type="button">+ Custom Item</button>
            <button
              className="secondary"
              onClick={() => {
                setCopyOpen((current) => !current);
                setCopyError("");
                setCopyPreview(null);
              }}
              type="button"
            >Copy from another Asset</button>
          </div>

          {copyOpen && <section className="maintenance-copy-panel">
            <div className="maintenance-copy-controls">
              <label>Source Asset
                <select
                  aria-label="Copy maintenance plan from Asset"
                  value={copySourceAssetId}
                  onChange={(event) => {
                    setCopySourceAssetId(event.target.value);
                    setCopyError("");
                    setCopyPreview(null);
                  }}
                >
                  <option value="">Choose Asset…</option>
                  {managedAssets.filter((asset) => asset.id !== selectedAssetId).map((asset) => <option key={asset.id} value={asset.id}>
                    {assetLabel(asset)}
                  </option>)}
                </select>
              </label>
              <button className="secondary" disabled={!copySourceAssetId} onClick={() => void previewCopy()} type="button">Preview</button>
            </div>
            {copyError && <p className="maintenance-inline-error" role="alert">{copyError}</p>}
            {copyPreview && <div className="maintenance-copy-preview">
              <strong>{copyPreview.asset_code} · {copyPreview.items.length} maintenance items</strong>
              <span>{copyPreview.items.map((item) => item.task_label).join(" · ")}</span>
              <button disabled={busy} onClick={() => void copyPlan()} type="button">Copy Plan</button>
            </div>}
          </section>}

          {customDraft && <CustomItemEditor
            allowHours={plan.supports_hour_meter}
            allowKm={plan.supports_odometer_km}
            busy={busy}
            draft={customDraft}
            onCancel={() => setCustomDraft(null)}
            onSubmit={saveCustomItem}
            setDraft={setCustomDraft}
          />}

          <PlanTable
            apiRequest={apiRequest}
            busy={busy}
            onChanged={load}
            onError={setError}
            onMessage={setMessage}
            plan={plan}
          />
        </>}
      </>}
    </div>}

    {section === "history" && <div className="maintenance-section">
      <div className="maintenance-history-filters">
        <label>Asset
          <select aria-label="History Asset" value={historyAssetId} onChange={(event) => setHistoryAssetId(event.target.value)}>
            <option value="">All Assets</option>
            {managedAssets.map((asset) => <option key={asset.id} value={asset.id}>{assetLabel(asset)}</option>)}
          </select>
        </label>
        <label>From<input aria-label="History from date" type="date" value={historyFrom} onChange={(event) => setHistoryFrom(event.target.value)} /></label>
        <label>To<input aria-label="History to date" type="date" value={historyTo} onChange={(event) => setHistoryTo(event.target.value)} /></label>
      </div>
      <HistoryTable
        assets={managedAssets}
        expandedId={expandedHistoryId}
        history={filteredHistory}
        onEvidence={openEvidence}
        onToggle={(id) => setExpandedHistoryId((current) => current === id ? null : id)}
      />
    </div>}

    {evidenceUrl && <div aria-label="Maintenance proof photo" aria-modal="true" className="maintenance-evidence-modal" role="dialog">
      <div>
        <button className="secondary" onClick={() => setEvidenceUrl(null)} type="button">Close</button>
        <img alt="Maintenance service proof" src={evidenceUrl} />
      </div>
    </div>}
  </section>;
}

function DueTable({ items, assets }: { items: DueItem[]; assets: OwnerAsset[] }) {
  return <div className="table-card">
    <table className="owner-table maintenance-due-table">
      <thead><tr>
        <th>Asset</th><th>Site</th><th>Maintenance Item</th><th>Triggered By</th>
        <th>Current / Due</th><th>Status</th>
      </tr></thead>
      <tbody>{items.length === 0
        ? <tr><td colSpan={6}>No maintenance needs immediate attention.</td></tr>
        : items.map((item) => {
            const triggered = item.criteria.filter((criterion) => item.triggered_by.includes(criterion.basis));
            return <tr key={item.id}>
              <td>{assets.find((asset) => asset.id === item.asset_id)
                ? assetLabel(assets.find((asset) => asset.id === item.asset_id))
                : item.asset_code}</td>
              <td>{item.site_name ?? "Undeployed"}</td>
              <td><details className="maintenance-due-details"><summary>{item.task_label}</summary>
                <div>{item.criteria.map((criterion) => <span key={criterion.id}>
                  {basisLabel(criterion.basis)}: {criterionReading(criterion)} · {label(criterion.state)}
                </span>)}</div>
              </details></td>
              <td>{item.triggered_by.map(basisLabel).join(" + ")}</td>
              <td>{triggered.map(criterionReading).join(" · ") || "Unknown"}</td>
              <td><span className={`owner-status-chip maintenance-status--${item.state.toLowerCase()}`}>{label(item.state)}</span></td>
            </tr>;
          })}</tbody>
    </table>
  </div>;
}

function PlanTable({
  plan, apiRequest, busy, onChanged, onError, onMessage,
}: {
  plan: Plan; apiRequest: WebRequest; busy: boolean; onChanged: () => Promise<void>;
  onError: (value: string) => void; onMessage: (value: string) => void;
}) {
  const save = async (item: PlanItem, draft: ItemDraft) => {
    onError("");
    try {
      await apiRequest(`/api/v1/owner/maintenance/plans/${plan.asset_id}/items/${item.id}`, {
        method: "PUT",
        body: JSON.stringify({
          task_code: item.task_code,
          custom_label: item.task_code === "CUSTOM" ? draft.custom_label : null,
          action_type: draft.action_type,
          enabled: draft.enabled,
          criteria: criteriaForDraft(draft),
        }),
      });
      onMessage("Maintenance item saved.");
      await onChanged();
      return true;
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Maintenance item could not be saved.");
      return false;
    }
  };
  const remove = async (item: PlanItem) => {
    onError("");
    try {
      await apiRequest(`/api/v1/owner/maintenance/plans/items/${item.id}`, { method: "DELETE" });
      onMessage("Custom maintenance item removed.");
      await onChanged();
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Maintenance item could not be removed.");
    }
  };

  return <div className="maintenance-plan-table" role="table" aria-label="Maintenance plan items">
    <div className="maintenance-plan-row maintenance-plan-row--header" role="row">
      <strong role="columnheader">On</strong><strong role="columnheader">Maintenance Item</strong>
      <strong role="columnheader">Interval</strong><strong role="columnheader">Warning</strong>
      <strong role="columnheader">Last Service</strong><strong role="columnheader">Next Due</strong>
      <strong role="columnheader">Status</strong><strong role="columnheader">Actions</strong>
    </div>
    {plan.items.length === 0 && <div className="maintenance-empty">No maintenance items configured.</div>}
    {plan.items.map((item) => <PlanRow
      allowHours={plan.supports_hour_meter}
      allowKm={plan.supports_odometer_km}
      busy={busy}
      item={item}
      key={item.id}
      onRemove={() => remove(item)}
      onSave={(draft) => save(item, draft)}
    />)}
  </div>;
}

function PlanRow({
  item, allowKm, allowHours, busy, onSave, onRemove,
}: {
  item: PlanItem; allowKm: boolean; allowHours: boolean; busy: boolean;
  onSave: (draft: ItemDraft) => Promise<boolean>; onRemove: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(() => itemDraft(item));
  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (await onSave(draft)) setEditing(false);
  };
  return <Fragment>
    <div className="maintenance-plan-row" role="row">
      <span role="cell"><input aria-label={`Enabled — ${item.task_label}`} checked={item.enabled} disabled readOnly type="checkbox" /></span>
      <span role="cell"><strong>{item.task_label}</strong><small>{label(item.action_type)}</small></span>
      <span className="maintenance-cell-stack" role="cell">{intervalText(item.criteria).map((text) => <span key={text}>{text}</span>)}</span>
      <span className="maintenance-cell-stack" role="cell">{warningText(item.criteria).map((text) => <span key={text}>{text}</span>)}</span>
      <span className="maintenance-cell-stack" role="cell">{lastServiceText(item.criteria).map((text) => <span key={text}>{text}</span>)}</span>
      <span className="maintenance-cell-stack" role="cell">{nextDueText(item.criteria).map((text) => <span key={text}>{text}</span>)}</span>
      <span role="cell"><span className="owner-status-chip">{item.criteria.length ? label(item.state) : "Not scheduled"}</span></span>
      <span role="cell"><button className="secondary" onClick={() => setEditing((current) => !current)} type="button">{editing ? "Close" : "Edit"}</button></span>
    </div>
    {editing && <form className="maintenance-inline-editor" onSubmit={save}>
      <ItemFields allowHours={allowHours} allowKm={allowKm} draft={draft} nameEditable={item.task_code === "CUSTOM"} setDraft={setDraft} />
      <p className="muted maintenance-field-help">Leave an interval blank to disable that trigger.</p>
      <div className="owner-form-actions">
        <button className="secondary" onClick={() => { setDraft(itemDraft(item)); setEditing(false); }} type="button">Cancel</button>
        {item.task_code === "CUSTOM" && <button className="owner-text-button owner-text-button--danger" disabled={busy} onClick={() => void onRemove()} type="button">Remove</button>}
        <button disabled={busy} type="submit">Save</button>
      </div>
    </form>}
  </Fragment>;
}

function ItemFields({
  draft, setDraft, allowKm, allowHours, nameEditable,
}: {
  draft: ItemDraft; setDraft: (next: ItemDraft) => void; allowKm: boolean;
  allowHours: boolean; nameEditable: boolean;
}) {
  return <div className="maintenance-editor-fields">
    {nameEditable && <label>Maintenance Item<input required value={draft.custom_label} onChange={(event) => setDraft({ ...draft, custom_label: event.target.value })} /></label>}
    <label>Action<select value={draft.action_type} onChange={(event) => setDraft({ ...draft, action_type: event.target.value })}>
      {["INSPECT", "CLEAN", "LUBRICATE", "SERVICE", "REPLACE"].map((entry) => <option key={entry}>{entry}</option>)}
    </select></label>
    <label className="maintenance-checkbox"><input checked={draft.enabled} onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })} type="checkbox" /> On</label>
    <fieldset><legend>Date</legend>
      <label>Every days<input aria-label="Every days" min="1" step="1" type="number" value={draft.days} onChange={(event) => setDraft({ ...draft, days: event.target.value })} /></label>
      <label>Warning days<input aria-label="Warn days before" min="0" step="1" type="number" value={draft.days_warn} onChange={(event) => setDraft({ ...draft, days_warn: event.target.value })} /></label>
      <label>Last service<input aria-label="Last service date" type="date" value={draft.days_baseline} onChange={(event) => setDraft({ ...draft, days_baseline: event.target.value })} /></label>
    </fieldset>
    {allowKm && <fieldset><legend>KM</legend>
      <label>Every KM<input aria-label="Every KM" min="0.01" step="0.01" type="number" value={draft.km} onChange={(event) => setDraft({ ...draft, km: event.target.value })} /></label>
      <label>Warning KM<input aria-label="Warn KM before" min="0" step="0.01" type="number" value={draft.km_warn} onChange={(event) => setDraft({ ...draft, km_warn: event.target.value })} /></label>
      <label>Last service<input aria-label="Last service KM" min="0" step="0.01" type="number" value={draft.km_baseline} onChange={(event) => setDraft({ ...draft, km_baseline: event.target.value })} /></label>
    </fieldset>}
    {allowHours && <fieldset><legend>Hours</legend>
      <label>Every hours<input aria-label="Every hours" min="0.01" step="0.01" type="number" value={draft.hours} onChange={(event) => setDraft({ ...draft, hours: event.target.value })} /></label>
      <label>Warning hours<input aria-label="Warn hours before" min="0" step="0.01" type="number" value={draft.hours_warn} onChange={(event) => setDraft({ ...draft, hours_warn: event.target.value })} /></label>
      <label>Last service<input aria-label="Last service HMR" min="0" step="0.01" type="number" value={draft.hours_baseline} onChange={(event) => setDraft({ ...draft, hours_baseline: event.target.value })} /></label>
    </fieldset>}
  </div>;
}

function CustomItemEditor({
  draft, setDraft, allowKm, allowHours, busy, onSubmit, onCancel,
}: {
  draft: ItemDraft; setDraft: (next: ItemDraft) => void; allowKm: boolean;
  allowHours: boolean; busy: boolean; onSubmit: (event: FormEvent) => void; onCancel: () => void;
}) {
  return <form className="owner-form-panel maintenance-item-editor" onSubmit={onSubmit}>
    <div className="owner-form-heading"><div><h3>Add custom maintenance item</h3><p>Intervals and warnings are optional.</p></div></div>
    <ItemFields allowHours={allowHours} allowKm={allowKm} draft={draft} nameEditable setDraft={setDraft} />
    <div className="owner-form-actions">
      <button className="secondary" onClick={onCancel} type="button">Cancel</button>
      <button disabled={busy} type="submit">Add Item</button>
    </div>
  </form>;
}

function RecommendedPreview({
  name, items, busy, onApply, onClose,
}: {
  name: string; items: TemplateItem[]; busy: boolean; onApply: () => void; onClose: () => void;
}) {
  return <section aria-label="Recommended plan preview" className="maintenance-template-preview">
    <header><div><p className="owner-section-eyebrow">Plan preview</p><h3>{name}</h3></div><button className="secondary" onClick={onClose} type="button">Close</button></header>
    <div className="maintenance-preview-list">{items.map((item) => <div key={item.id}>
      <strong>{item.task_label}</strong><span>{intervalText(item.criteria).join(" / ")}</span>
    </div>)}</div>
    <div className="owner-form-actions"><button disabled={busy} onClick={onApply} type="button">Apply Plan</button></div>
  </section>;
}

function HistoryTable({
  history, assets, expandedId, onToggle, onEvidence,
}: {
  history: History[]; assets: OwnerAsset[]; expandedId: string | null;
  onToggle: (id: string) => void;
  onEvidence: (recordId: string, evidenceId: string) => Promise<void>;
}) {
  return <div className="table-card">
    <table className="owner-table maintenance-history-table">
      <thead><tr>
        <th>Date</th><th>Asset</th><th>Site</th><th>Maintenance Item</th><th>KM</th><th>HMR</th>
        <th>Submitted by</th><th>Approved by</th><th>Status</th>
      </tr></thead>
      <tbody>{history.length === 0
        ? <tr><td colSpan={9}>No service history matches these filters.</td></tr>
        : history.map((entry) => <Fragment key={entry.id}>
            <tr className="maintenance-history-row" onClick={() => onToggle(entry.id)}>
              <td>{entry.service_date}</td>
              <td>{assets.find((asset) => asset.id === entry.asset_id)
                ? assetLabel(assets.find((asset) => asset.id === entry.asset_id))
                : entry.asset_code ?? "Unknown asset"}</td>
              <td>{entry.site_name ?? "—"}</td><td><button className="owner-text-button" type="button">{entry.task_label}</button></td>
              <td>{entry.odometer_km ?? "—"}</td><td>{entry.hour_meter ?? "—"}</td>
              <td>{entry.submitted_by ?? "—"}</td><td>{entry.approved_by ?? "—"}</td>
              <td><span className="owner-status-chip owner-status-chip--positive">{label(entry.status ?? "COMPLETED")}</span></td>
            </tr>
            {expandedId === entry.id && <tr className="maintenance-history-detail"><td colSpan={9}>
              <div>
                <dl>
                  <div><dt>Vendor</dt><dd>{entry.vendor ?? "—"}</dd></div>
                  <div><dt>Total cost</dt><dd>₹{entry.total_cost}</dd></div>
                  <div><dt>Notes</dt><dd>{entry.notes ?? "—"}</dd></div>
                  <div><dt>Audit</dt><dd>{entry.created_at
                    ? `Recorded ${new Date(entry.created_at).toLocaleString()}`
                    : "Recorded timestamp unavailable"}</dd></div>
                </dl>
                <div className="maintenance-proof-list">
                  <strong>Proof photos</strong>
                  {(entry.evidence ?? []).length === 0 && <span>None attached</span>}
                  {(entry.evidence ?? []).map((proof, index) => <button className="secondary" key={proof.evidence_id} onClick={() => void onEvidence(entry.id, proof.evidence_id)} type="button">Photo {index + 1}</button>)}
                </div>
              </div>
            </td></tr>}
          </Fragment>)}</tbody>
    </table>
  </div>;
}
