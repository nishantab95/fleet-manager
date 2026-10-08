"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { API_BASE, ApiError, fetchPrivateEvidence, request, type WebRequest } from "../../lib/api/client";
import type { Closure, CompanySettings, DashboardReport, DriverDutyReport, ReportTemplate, SiteDailyReport, TipperDailyReport } from "../../lib/types";
import { Metric } from "../shared/Ui";
import { EvidenceModal, type EvidenceDetails } from "../shared/EvidenceViewer";
import { title } from "./catalogs";
import { EmptyTableRow, OperationsTable, SortButton, StatusChip } from "./OwnerUi";

type Props = { accessToken: string; setError: (value: string) => void; apiRequest?: WebRequest };
const number = (value: number | null | undefined, suffix = "") => value == null ? "Unavailable" : `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`;
const meterSummary = (
  item: Pick<DriverDutyReport, "supports_odometer_km" | "supports_hour_meter" | "start_km" | "end_km" | "start_hmr" | "end_hmr" | "machine_hours">,
  display: typeof number,
) => [
  item.supports_odometer_km ? `${display(item.start_km)} / ${display(item.end_km)} km` : null,
  item.supports_hour_meter ? `${display(item.start_hmr)} / ${display(item.end_hmr)} HMR · ${display(item.machine_hours, " h")}` : null,
].filter((value): value is string => value !== null).join(" · ") || "Not configured";

export function OwnerOperations({ accessToken, setError, apiRequest }: Props) {
  const call = useCallback(<T,>(path: string, options: RequestInit = {}) => apiRequest ? apiRequest<T>(path, options) : request<T>(path, options, accessToken), [accessToken, apiRequest]);
  const [report, setReport] = useState<DashboardReport | null>(null); const [duties, setDuties] = useState<DriverDutyReport[]>([]); const [settings, setSettings] = useState<CompanySettings | null>(null); const [templates, setTemplates] = useState<ReportTemplate[]>([]);
  const [operationalDate, setOperationalDate] = useState(""); const [selectedSiteId, setSelectedSiteId] = useState(""); const [siteReport, setSiteReport] = useState<SiteDailyReport | null>(null); const [selectedAsset, setSelectedAsset] = useState<TipperDailyReport | null>(null); const [templateId, setTemplateId] = useState("");
  const [timezone, setTimezone] = useState(""); const [dayStart, setDayStart] = useState("0"); const [reopenReason, setReopenReason] = useState(""); const [loading, setLoading] = useState(false); const [refresh, setRefresh] = useState(0); const [evidenceUrl, setEvidenceUrl] = useState<string | null>(null); const [evidenceDetails, setEvidenceDetails] = useState<EvidenceDetails | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      try {
        const query = operationalDate ? `?operational_date=${operationalDate}` : "";
        const [dashboard, company, dutyResult, templateResult] = await Promise.all([
          call<DashboardReport>(`/api/v1/reports/dashboard${query}`), call<CompanySettings>("/api/v1/admin/company"),
          call<DriverDutyReport[]>(`/api/v1/reports/duty${query}`).catch(() => []), call<ReportTemplate[]>("/api/v1/owner/report-templates").catch(() => []),
        ]);
        if (!active) return;
        const templateItems = Array.isArray(templateResult) ? templateResult.filter((item) => item.builtin_key !== "simple_site_workbook") : [];
        setReport(dashboard); setDuties(Array.isArray(dutyResult) ? dutyResult : []); setSettings(company); setTimezone(company.reporting_timezone); setDayStart(String(company.operational_day_start_minutes)); setTemplates(templateItems); setTemplateId((value) => value || templateItems.find((item) => item.is_default)?.id || templateItems[0]?.id || "");
        if (!operationalDate) setOperationalDate(dashboard.operational_date);
      } catch (caught) { if (active) setError(caught instanceof Error ? caught.message : "Could not load the owner dashboard."); }
      finally { if (active) setLoading(false); }
    }
    void load(); return () => { active = false; };
  }, [call, operationalDate, refresh, setError]);

  useEffect(() => {
    let active = true;
    if (!selectedSiteId || !operationalDate) return;
    void call<SiteDailyReport>(`/api/v1/reports/sites/${selectedSiteId}/daily?operational_date=${operationalDate}`).then((value) => { if (active) setSiteReport(value); }).catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "Could not load the site report."); });
    return () => { active = false; };
  }, [call, operationalDate, refresh, selectedSiteId, setError]);

  useEffect(() => () => { if (evidenceUrl) URL.revokeObjectURL(evidenceUrl); }, [evidenceUrl]);
  const selectedSite = report?.sites.find((site) => site.site_id === selectedSiteId) ?? null;
  const zone = selectedSite?.reporting_timezone ?? report?.reporting_timezone;
  const date = (value: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "short", timeStyle: "short", timeZone: zone }).format(new Date(value));

  const selectAsset = async (asset: TipperDailyReport) => {
    setError("");
    try { const items = await call<TipperDailyReport[]>(`/api/v1/reports/tippers/${asset.tipper_id}/daily?operational_date=${operationalDate}`); setSelectedAsset(items[0] ?? asset); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Could not load the asset report."); }
  };
  const changeClosure = async (action: "close" | "reopen") => {
    if (!selectedSite) return;
    if (action === "reopen" && !reopenReason.trim()) { setError("A reason is required to reopen a closed site day."); return; }
    try { await call<Closure>(`/api/v1/reports/sites/${selectedSite.site_id}/closure/${action}?operational_date=${operationalDate}`, { method: "POST", body: JSON.stringify({ reason: action === "reopen" ? reopenReason.trim() : null }) }); setReopenReason(""); setRefresh((value) => value + 1); }
    catch (caught) { setError(caught instanceof Error ? caught.message : `The site could not be ${action}d.`); }
  };
  const saveSettings = async () => {
    const minutes = Number(dayStart);
    if (!timezone.trim() || !Number.isInteger(minutes) || minutes < 0 || minutes > 1439) { setError("Use a valid IANA timezone and a day-start minute between 0 and 1439."); return; }
    try { const value = await call<CompanySettings>("/api/v1/admin/company", { method: "PATCH", body: JSON.stringify({ reporting_timezone: timezone.trim(), operational_day_start_minutes: minutes }) }); setSettings(value); setRefresh((item) => item + 1); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Company reporting settings could not be saved."); }
  };
  const download = async () => {
    try { const suffix = templateId ? `&template_id=${encodeURIComponent(templateId)}` : ""; const response = await fetch(`${API_BASE}/api/v1/reports/daily.xlsx?operational_date=${operationalDate}${suffix}`, { credentials: "include", headers: { Authorization: `Bearer ${accessToken}` } }); if (!response.ok) throw new ApiError(response.status, "The Excel report could not be downloaded."); const url = URL.createObjectURL(await response.blob()); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `fleet-report-${operationalDate}.xlsx`; anchor.click(); URL.revokeObjectURL(url); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "The Excel report could not be downloaded."); }
  };
  const viewEvidence = async (eventId: string) => {
    try { const result = await fetchPrivateEvidence(`/api/v1/reports/events/${eventId}/evidence`, accessToken); if (evidenceUrl) URL.revokeObjectURL(evidenceUrl); setEvidenceUrl(result.url); setEvidenceDetails({ ...result.metadata, eventId }); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Evidence could not be loaded."); }
  };

  return <section id="owner-operations">
    <div className="content-heading"><div><h2>Owner operations</h2><p className="muted">Approved records drive official totals. Tippers use trips and odometer readings; machinery uses hour-meter readings.</p></div><div className="inline-form"><label>Operational date<input type="date" value={operationalDate} onChange={(event) => { setOperationalDate(event.target.value); setSelectedSiteId(""); setSelectedAsset(null); }} /></label><label>Excel template<select value={templateId} onChange={(event) => setTemplateId(event.target.value)}><option value="">Server default</option>{templates.map((item) => <option key={item.id} value={item.id}>{item.name}{item.is_default ? " · Default" : ""}</option>)}</select></label><button className="secondary" disabled={loading} onClick={() => setRefresh((value) => value + 1)} type="button">{loading ? "Loading…" : "Refresh"}</button><button disabled={!report} onClick={() => void download()} type="button">Download Excel</button></div></div>
    {settings && <article className="table-card settings-card"><div className="content-heading"><div><h3>Company reporting settings</h3><p className="muted">Times are persisted in UTC and grouped using this reporting timezone.</p></div><button onClick={() => void saveSettings()} type="button">Save settings</button></div><div className="inline-form"><label>IANA timezone<input value={timezone} onChange={(event) => setTimezone(event.target.value)} /></label><label>Day start minute (0–1439)<input type="number" min="0" max="1439" value={dayStart} onChange={(event) => setDayStart(event.target.value)} /></label></div></article>}
    {report && <Dashboard report={report} duties={duties} number={number} date={date} selectedSiteId={selectedSiteId} onSelectSite={(id) => { setSelectedSiteId(id); setSelectedAsset(null); }} />}
    {selectedSite && <SiteDetail site={selectedSite} details={siteReport} selectedAsset={selectedAsset} number={number} onSelectAsset={selectAsset} reopenReason={reopenReason} setReopenReason={setReopenReason} changeClosure={changeClosure} />}
    {selectedAsset && <AssetDetail asset={selectedAsset} number={number} date={date} onEvidence={viewEvidence} />}
    {evidenceUrl && evidenceDetails && <EvidenceModal details={evidenceDetails} onClose={() => { URL.revokeObjectURL(evidenceUrl); setEvidenceUrl(null); setEvidenceDetails(null); }} url={evidenceUrl} />}
    {!report && !loading && <div className="notice">No dashboard data is available for this operational day.</div>}
  </section>;
}

function Dashboard({ report, duties, number: display, date, selectedSiteId, onSelectSite }: { report: DashboardReport; duties: DriverDutyReport[]; number: typeof number; date: (value: string) => string; selectedSiteId: string; onSelectSite: (id: string) => void }) {
  const emergencies = report.sites.flatMap((site) => site.tippers.flatMap((asset) => asset.events.filter((event) => event.emergency_status === "OPEN" || event.emergency_status === "ACKNOWLEDGED")));
  const [dutySort, setDutySort] = useState<"driver" | "asset" | "site" | "meter" | "diesel" | "duty" | "overtime" | "status">("driver"); const [dutyDirection, setDutyDirection] = useState<"asc" | "desc">("asc");
  const [siteSort, setSiteSort] = useState<"site" | "assigned" | "trips" | "km" | "diesel" | "closure">("site"); const [siteDirection, setSiteDirection] = useState<"asc" | "desc">("asc");
  const sortedDuties = useMemo(() => [...duties].sort((left, right) => { const value = (item: DriverDutyReport) => dutySort === "driver" ? item.driver_name : dutySort === "asset" ? (item.tipper_registration_number || item.asset_code) : dutySort === "site" ? item.site_name : dutySort === "meter" ? (item.end_km ?? item.end_hmr ?? -1) : dutySort === "diesel" ? item.verified_diesel_issued : dutySort === "duty" ? item.duty_start : dutySort === "overtime" ? item.overtime_minutes : item.status; const a = value(left); const b = value(right); const result = typeof a === "number" && typeof b === "number" ? a - b : String(a ?? "").localeCompare(String(b ?? ""), undefined, { numeric: true, sensitivity: "base" }); return dutyDirection === "asc" ? result : -result; }), [duties, dutyDirection, dutySort]);
  const sortedSites = useMemo(() => [...report.sites].sort((left, right) => { const value = (item: SiteDailyReport) => siteSort === "site" ? item.site_name : siteSort === "assigned" ? item.assigned_tippers_count : siteSort === "trips" ? item.approved_trip_count : siteSort === "km" ? (item.total_km ?? -1) : siteSort === "diesel" ? item.verified_diesel_issued : item.closure.status; const a = value(left); const b = value(right); const result = typeof a === "number" && typeof b === "number" ? a - b : String(a ?? "").localeCompare(String(b ?? ""), undefined, { numeric: true, sensitivity: "base" }); return siteDirection === "asc" ? result : -result; }), [report.sites, siteDirection, siteSort]);
  const changeDutySort = (next: typeof dutySort) => { setDutyDirection((current) => dutySort === next && current === "asc" ? "desc" : "asc"); setDutySort(next); };
  const changeSiteSort = (next: typeof siteSort) => { setSiteDirection((current) => siteSort === next && current === "asc" ? "desc" : "asc"); setSiteSort(next); };
  return <>
    {emergencies.length > 0 && <section className="emergency-panel"><h2>OPEN EMERGENCIES <span className="badge">{emergencies.length}</span></h2>{emergencies.map((event) => <article className="emergency-alert" key={event.event_id} role="alert"><div className="emergency-alert-details"><strong>{event.driver_name}</strong><span>{event.asset_code || event.tipper_registration_number} · {event.site_name}</span><span>{event.emergency_status} · {date(event.device_created_at)}</span></div>{event.driver_phone && <a className="call-driver" href={`tel:${event.driver_phone}`}>CALL DRIVER</a>}</article>)}</section>}
    <div className="metric-grid" id="owner-reports"><Metric label="Assigned assets" value={report.assigned_tippers_count} /><Metric label="Approved trips" value={report.approved_trip_count} /><Metric label="Total KM" value={display(report.total_km, " km")} /><Metric label="Diesel issued" value={display(report.verified_diesel_issued, " L")} /><Metric label="Drivers on duty" value={report.drivers_on_duty ?? duties.filter((item) => item.status === "ACTIVE").length} /><Metric label="Past regular duty" value={report.drivers_past_regular_duty ?? duties.filter((item) => item.status === "ACTIVE" && item.overtime_minutes > 0).length} /><Metric label="Pending verification" value={report.pending_verification_count} /><Metric label="Missing readings" value={report.missing_reading_count} /><Metric label="Open Emergencies" value={report.unresolved_emergency_count} /><Metric label="Sites not closed" value={report.sites_not_closed_count} /></div>
    <section className="stack" aria-labelledby="driver-duty-heading"><h2 id="driver-duty-heading">Driver / Operator duty</h2><OperationsTable label="Driver and operator duty"><thead><tr>{([['driver', 'Driver / Operator'], ['asset', 'Asset'], ['site', 'Site'], ['meter', 'Meter'], ['diesel', 'Diesel'], ['duty', 'Duty'], ['overtime', 'Overtime'], ['status', 'Status']] as [typeof dutySort, string][]).map(([key, label]) => <th aria-sort={dutySort === key ? (dutyDirection === "asc" ? "ascending" : "descending") : "none"} key={key} scope="col"><SortButton active={dutySort === key} direction={dutyDirection} label={label} onClick={() => changeDutySort(key)} /></th>)}</tr></thead><tbody>{sortedDuties.length === 0 && <EmptyTableRow colSpan={8} title="No duty sessions for this operational day" />}{sortedDuties.map((duty) => <tr key={duty.session_id}><td data-label="Driver / Operator"><strong>{duty.driver_name}</strong></td><td data-label="Asset">{duty.tipper_registration_number || duty.asset_code}<small>{title(duty.asset_type)}</small></td><td data-label="Site">{duty.site_name}</td><td data-label="Meter">{meterSummary(duty, display)}</td><td data-label="Diesel">{display(duty.verified_diesel_issued, " L")}{duty.pending_diesel_issued ? ` · ${display(duty.pending_diesel_issued, " L")} pending` : ""}</td><td data-label="Duty">{date(duty.duty_start)} – {duty.actual_duty_end ? date(duty.actual_duty_end) : "Open"}</td><td data-label="Overtime">{duty.overtime_minutes} min</td><td data-label="Status"><StatusChip status={duty.status} /></td></tr>)}</tbody></OperationsTable></section>
    <section><h2>Sites</h2><p className="muted">{report.complete_tippers_count} asset{report.complete_tippers_count === 1 ? "" : "s"} have complete approved readings.</p><OperationsTable label="Report sites"><thead><tr>{([['site', 'Site'], ['assigned', 'Assigned'], ['trips', 'Trips'], ['km', 'KM'], ['diesel', 'Diesel'], ['closure', 'Closure']] as [typeof siteSort, string][]).map(([key, label]) => <th aria-sort={siteSort === key ? (siteDirection === "asc" ? "ascending" : "descending") : "none"} key={key} scope="col"><SortButton active={siteSort === key} direction={siteDirection} label={label} onClick={() => changeSiteSort(key)} /></th>)}</tr></thead><tbody>{sortedSites.length === 0 && <EmptyTableRow colSpan={6} title="No assigned tippers were found for this operational day" />}{sortedSites.map((site) => <tr className={selectedSiteId === site.site_id ? "selected-row" : ""} key={site.site_id}><td data-label="Site"><button className="owner-text-button" onClick={() => onSelectSite(site.site_id)} type="button"><strong>{site.site_name}</strong></button></td><td data-label="Assigned">{site.assigned_tippers_count}</td><td data-label="Trips">{site.approved_trip_count} approved / {site.pending_trip_count} pending</td><td data-label="KM">{display(site.total_km, " km")}</td><td data-label="Diesel">{display(site.verified_diesel_issued, " L")}</td><td data-label="Closure"><StatusChip status={site.closure.status} /></td></tr>)}</tbody></OperationsTable></section>
    <section id="owner-exceptions"><h2>Exceptions</h2><div className="table-card">{report.exceptions.length ? report.exceptions.map((item, index) => <button className="table-row" key={`${item.code}-${index}`} onClick={() => onSelectSite(item.site_id)} type="button"><strong>{item.code}</strong><span>{item.tipper_registration_number}</span><span>{item.description}</span><span>Open site detail</span></button>) : <p className="empty-state">No exceptions for this operational day.</p>}</div></section>
  </>;
}

function SiteDetail({ site, details, selectedAsset, number: display, onSelectAsset, reopenReason, setReopenReason, changeClosure }: { site: SiteDailyReport; details: SiteDailyReport | null; selectedAsset: TipperDailyReport | null; number: typeof number; onSelectAsset: (asset: TipperDailyReport) => Promise<void>; reopenReason: string; setReopenReason: (value: string) => void; changeClosure: (action: "close" | "reopen") => Promise<void> }) {
  return <section className="stack" id="owner-closure"><div className="content-heading"><div><h2>{site.site_name} · daily detail</h2><p className="muted">{site.assigned_tippers_count} assigned asset{site.assigned_tippers_count === 1 ? "" : "s"} · {site.closure.status}</p></div><div className="inline-form">{site.closure.status === "CLOSED" ? <><input aria-label="Reopening reason" placeholder="Reason to reopen" value={reopenReason} onChange={(event) => setReopenReason(event.target.value)} /><button className="secondary" onClick={() => void changeClosure("reopen")} type="button">Reopen day</button></> : <button disabled={site.closure.blockers.length > 0} onClick={() => void changeClosure("close")} type="button">Close day</button>}</div></div>{site.closure.blockers.length > 0 && <div className="notice error"><strong>Closure blockers:</strong> {site.closure.blockers.map((item) => `${item.code}: ${item.description}`).join(" · ")}</div>}<div className="table-card"><div className="table-row"><strong>Asset</strong><span>Operator</span><span>Activity</span><span>Meter</span><span>Diesel</span><span>Completeness</span></div>{(details?.tippers ?? []).map((asset) => <button className={`table-row ${selectedAsset?.tipper_id === asset.tipper_id ? "selected-row" : ""}`} key={asset.assignment_id} onClick={() => void onSelectAsset(asset)} type="button"><strong>{asset.registration_number || asset.short_name || asset.tipper_id} · {title(asset.asset_type)}</strong><span>{asset.driver_name}</span><span>{asset.trips_state === "NOT_APPLICABLE" ? "Trips not applicable" : `${asset.approved_trip_count ?? 0} approved / ${asset.pending_trip_count ?? 0} pending`}</span><span>{meterSummary(asset, display)}</span><span>{display(asset.verified_diesel_issued, " L")}{asset.pending_diesel_issued ? ` · ${display(asset.pending_diesel_issued, " L")} pending` : ""}</span><span>{asset.completeness_status}</span></button>)}</div></section>;
}

function AssetDetail({ asset, number: display, date, onEvidence }: { asset: TipperDailyReport; number: typeof number; date: (value: string) => string; onEvidence: (eventId: string) => Promise<void> }) {
  const assetType = asset.asset_type ?? "TIPPER"; const label = asset.registration_number || asset.short_name || asset.tipper_id;
  return <section className="stack"><div><h2>{label} · event trace</h2><p className="muted">{title(assetType)} · {asset.driver_name} · {asset.site_name}</p></div><div className="metric-grid owner-detail-metrics">{asset.trips_state !== "NOT_APPLICABLE" && <Metric label="Approved Trips" value={asset.approved_trip_count ?? 0} />}{asset.supports_odometer_km && <><Metric label="Start KM" value={display(asset.start_km)} /><Metric label="End KM" value={display(asset.end_km)} /><Metric label="Distance KM" value={display(asset.distance_km, " km")} /><Metric label="KM / Approved Trip" value={display(asset.km_per_approved_trip)} /></>}{asset.supports_hour_meter && <><Metric label="Start HMR" value={display(asset.start_hmr)} /><Metric label="End HMR" value={display(asset.end_hmr)} /><Metric label="Machine hours" value={display(asset.machine_hours, " h")} /></>}<Metric label="Diesel Issued" value={display(asset.verified_diesel_issued, " L")} /><Metric label="Pending Diesel" value={display(asset.pending_diesel_issued, " L")} /><Metric label="Unresolved Emergencies" value={asset.unresolved_emergency_count} /><Metric label="Completeness" value={asset.completeness_status} /><Metric label="Closure" value={asset.closure_status} /></div>{asset.exceptions.length > 0 && <div className="notice error">{asset.exceptions.map((item) => `${item.code}: ${item.description}`).join(" · ")}</div>}<h3>Event trace</h3><div className="stack">{asset.events.map((event) => <article className="table-card" key={event.event_id}><div className="table-row"><strong>{title(event.event_type)}</strong><span>{event.verification_status}</span><span>{date(event.device_created_at)}</span><span>{event.reading_type ? `${title(event.reading_type)}: ${event.reading_value ?? "Unavailable"}${event.event_type === "HMR_READING" ? " HMR" : ""}` : event.litres != null ? `${event.litres} L` : ""}</span>{event.evidence_available && <button className="secondary" onClick={() => void onEvidence(event.event_id)} type="button">View evidence</button>}</div><details><summary>Verification history ({event.verification_history.length})</summary>{event.verification_history.map((history, index) => <div className="table-row" key={`${event.event_id}-${index}`}><span>{history.status}</span><span>{history.actor_name ?? "System"}</span><span>{history.reason ?? "No reason"}</span><span>{date(history.created_at)}</span></div>)}</details></article>)}</div></section>;
}
