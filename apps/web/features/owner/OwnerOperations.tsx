"use client";

import { useCallback, useEffect, useState } from "react";
import { API_BASE, ApiError, request, type WebRequest } from "../../lib/api/client";
import type { Closure, CompanySettings, DashboardReport, SiteDailyReport, TipperDailyReport } from "../../lib/types";
import { Metric } from "../shared/Ui";

type OwnerOperationsProps = { accessToken: string; setError: (value: string) => void; apiRequest?: WebRequest };

export function OwnerOperations(props: OwnerOperationsProps) {
  const { accessToken, setError } = props;
  const { apiRequest } = props;
  const call = useCallback(<T,>(path: string, options: RequestInit = {}) => apiRequest ? apiRequest<T>(path, options) : request<T>(path, options, accessToken), [accessToken, apiRequest]);
  const [report, setReport] = useState<DashboardReport | null>(null);
  const [operationalDate, setOperationalDate] = useState("");
  const [selectedSiteId, setSelectedSiteId] = useState("");
  const [siteReport, setSiteReport] = useState<SiteDailyReport | null>(null);
  const [tipperReports, setTipperReports] = useState<TipperDailyReport[]>([]);
  const [selectedTipperId, setSelectedTipperId] = useState("");
  const [reopenReason, setReopenReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [evidenceUrl, setEvidenceUrl] = useState<string | null>(null);
  const [evidenceEventId, setEvidenceEventId] = useState<string | null>(null);
  const [settings, setSettings] = useState<CompanySettings | null>(null);
  const [reportingTimezone, setReportingTimezone] = useState("");
  const [workdayStartMinutes, setWorkdayStartMinutes] = useState("0");
  const [settingsSaving, setSettingsSaving] = useState(false);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      try {
        const query = operationalDate ? `?operational_date=${operationalDate}` : "";
        const [next, nextSettings] = await Promise.all([
          call<DashboardReport>(`/api/v1/reports/dashboard${query}`),
          call<CompanySettings>("/api/v1/admin/company"),
        ]);
        if (active) {
          setReport(next);
          setSettings(nextSettings);
          setReportingTimezone(nextSettings.reporting_timezone);
          setWorkdayStartMinutes(String(nextSettings.operational_day_start_minutes));
          if (!operationalDate) setOperationalDate(next.operational_date);
        }
      } catch (caught) {
        if (active) setError(caught instanceof Error ? caught.message : "Could not load the owner dashboard.");
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, [accessToken, call, operationalDate, refreshKey, setError]);

  useEffect(() => {
    let active = true;
    async function load() {
      if (!selectedSiteId || !operationalDate) { if (active) setSiteReport(null); return; }
      setDetailLoading(true);
      try {
        const next = await call<SiteDailyReport>(`/api/v1/reports/sites/${selectedSiteId}/daily?operational_date=${operationalDate}`);
        if (active) setSiteReport(next);
      } catch (caught) {
        if (active) setError(caught instanceof Error ? caught.message : "Could not load the site report.");
      } finally {
        if (active) setDetailLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, [accessToken, call, operationalDate, refreshKey, selectedSiteId, setError]);

  useEffect(() => () => { if (evidenceUrl) URL.revokeObjectURL(evidenceUrl); }, [evidenceUrl]);

  const selectedSite = report?.sites.find((site) => site.site_id === selectedSiteId) ?? null;
  const selectedTipper = tipperReports.find((tipper) => tipper.tipper_id === selectedTipperId) ?? null;
  const displayNumber = (value: number | null, suffix = "") => value === null ? "Unavailable" : `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`;
  const displayDate = (value: string) => new Date(value).toLocaleString();
  const selectSite = (siteId: string) => { setSelectedSiteId(siteId); setSelectedTipperId(""); setTipperReports([]); setReopenReason(""); };

  const loadTipper = async (tipper: TipperDailyReport) => {
    setDetailLoading(true); props.setError("");
    try {
      setTipperReports(await call<TipperDailyReport[]>(`/api/v1/reports/tippers/${tipper.tipper_id}/daily?operational_date=${operationalDate}`));
      setSelectedTipperId(tipper.tipper_id);
    } catch (caught) { props.setError(caught instanceof Error ? caught.message : "Could not load the tipper report."); }
    finally { setDetailLoading(false); }
  };

  const closeSelectedSite = async () => {
    if (!selectedSite) return;
    props.setError("");
    try { await call<Closure>(`/api/v1/reports/sites/${selectedSite.site_id}/closure/close?operational_date=${operationalDate}`, { method: "POST", body: JSON.stringify({ reason: null }) }); setRefreshKey((value) => value + 1); }
    catch (caught) { props.setError(caught instanceof Error ? caught.message : "The site could not be closed."); }
  };

  const reopenSelectedSite = async () => {
    if (!selectedSite || !reopenReason.trim()) { props.setError("A reason is required to reopen a closed site day."); return; }
    props.setError("");
    try { await call<Closure>(`/api/v1/reports/sites/${selectedSite.site_id}/closure/reopen?operational_date=${operationalDate}`, { method: "POST", body: JSON.stringify({ reason: reopenReason.trim() }) }); setReopenReason(""); setRefreshKey((value) => value + 1); }
    catch (caught) { props.setError(caught instanceof Error ? caught.message : "The site could not be reopened."); }
  };

  const saveSettings = async () => {
    const minutes = Number(workdayStartMinutes);
    if (!reportingTimezone.trim() || !Number.isInteger(minutes) || minutes < 0 || minutes > 1439) { props.setError("Use a valid IANA timezone and a day-start minute between 0 and 1439."); return; }
    setSettingsSaving(true); props.setError("");
    try {
      const next = await call<CompanySettings>("/api/v1/admin/company", { method: "PATCH", body: JSON.stringify({ reporting_timezone: reportingTimezone.trim(), operational_day_start_minutes: minutes }) });
      setSettings(next); setReportingTimezone(next.reporting_timezone); setWorkdayStartMinutes(String(next.operational_day_start_minutes)); setRefreshKey((value) => value + 1);
    } catch (caught) { props.setError(caught instanceof Error ? caught.message : "Company reporting settings could not be saved."); }
    finally { setSettingsSaving(false); }
  };

  const downloadExcel = async () => {
    props.setError("");
    try {
      const response = await fetch(`${API_BASE}/api/v1/reports/daily.xlsx?operational_date=${operationalDate}`, { credentials: "include", headers: { Authorization: `Bearer ${accessToken}` } });
      if (!response.ok) throw new ApiError(response.status, "The Excel report could not be downloaded.");
      const url = URL.createObjectURL(await response.blob()); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `fleet-report-${operationalDate}.xlsx`; anchor.click(); URL.revokeObjectURL(url);
    } catch (caught) { props.setError(caught instanceof Error ? caught.message : "The Excel report could not be downloaded."); }
  };

  const viewEvidence = async (eventId: string) => {
    props.setError("");
    try {
      const response = await fetch(`${API_BASE}/api/v1/reports/events/${eventId}/evidence`, { credentials: "include", headers: { Authorization: `Bearer ${accessToken}` } });
      if (!response.ok) throw new ApiError(response.status, "Evidence could not be loaded.");
      const nextUrl = URL.createObjectURL(await response.blob()); if (evidenceUrl) URL.revokeObjectURL(evidenceUrl); setEvidenceUrl(nextUrl); setEvidenceEventId(eventId);
    } catch (caught) { props.setError(caught instanceof Error ? caught.message : "Evidence could not be loaded."); }
  };

  return <>
    <div className="content-heading" id="owner-operations"><div><h2>Owner operations</h2><p className="muted">Official totals use approved events only. Reporting day: {report?.reporting_timezone ?? "company timezone"}, starting at {report ? `${Math.floor(report.workday_start_minutes / 60).toString().padStart(2, "0")}:${(report.workday_start_minutes % 60).toString().padStart(2, "0")}` : "configured time"}.</p></div><div className="inline-form"><label>Operational date<input type="date" value={operationalDate} onChange={(event) => { setOperationalDate(event.target.value); setSelectedSiteId(""); setTipperReports([]); }} /></label><button className="secondary" disabled={loading} onClick={() => setRefreshKey((value) => value + 1)} type="button">{loading ? "Loading…" : "Refresh"}</button><button disabled={!report} onClick={downloadExcel} type="button">Download Excel</button></div></div>
    {settings && <div className="table-card settings-card"><div className="content-heading"><div><h3>Company reporting settings</h3><p className="muted">The operational day is stored and calculated in this IANA timezone. Times are persisted in UTC.</p></div><button disabled={settingsSaving} onClick={saveSettings} type="button">{settingsSaving ? "Saving…" : "Save settings"}</button></div><div className="inline-form"><label>IANA timezone<input value={reportingTimezone} onChange={(event) => setReportingTimezone(event.target.value)} /></label><label>Day start minute (0–1439)<input type="number" min="0" max="1439" value={workdayStartMinutes} onChange={(event) => setWorkdayStartMinutes(event.target.value)} /></label></div></div>}
    {report && <><div className="metric-grid" id="owner-reports"><Metric label="Assigned tippers" value={report.assigned_tippers_count} /><Metric label="Approved trips" value={report.approved_trip_count} /><Metric label="Total KM" value={report.total_km === null ? "Unavailable" : displayNumber(report.total_km, " km")} /><Metric label="Diesel issued" value={displayNumber(report.verified_diesel_issued, " L")} /><Metric label="Pending verification" value={report.pending_verification_count} /><Metric label="Missing readings" value={report.missing_reading_count} /><Metric label="Unresolved emergencies" value={report.unresolved_emergency_count} /><Metric label="Sites not closed" value={report.sites_not_closed_count} /></div><div className="content-heading"><div><h2>Sites</h2><p className="muted">{report.complete_tippers_count} tipper{report.complete_tippers_count === 1 ? "" : "s"} have complete approved readings for this operational day.</p></div></div><div className="table-card"><div className="table-row"><strong>Site</strong><span>Assigned</span><span>Trips</span><span>KM</span><span>Diesel</span><span>Closure</span></div>{report.sites.length ? report.sites.map((site) => <button className={selectedSiteId === site.site_id ? "table-row selected-row" : "table-row"} key={site.site_id} onClick={() => selectSite(site.site_id)} type="button"><strong>{site.site_name}</strong><span>{site.assigned_tippers_count}</span><span>{site.approved_trip_count} approved / {site.pending_trip_count} pending</span><span>{displayNumber(site.total_km, " km")}</span><span>{displayNumber(site.verified_diesel_issued, " L")}</span><span>{site.closure.status}</span></button>) : <div className="table-row"><span>No assigned tippers were found for this operational day.</span></div>}</div><div className="content-heading" id="owner-exceptions"><div><h2>Exceptions</h2><p className="muted">Operational blockers remain visible until resolved or explicitly reviewed.</p></div></div><div className="table-card">{report.exceptions.length ? report.exceptions.map((item, index) => <button className="table-row" key={`${item.code}-${item.assignment_id}-${index}`} onClick={() => selectSite(item.site_id)}><strong>{item.code}</strong><span>{item.tipper_registration_number}</span><span>{item.description}</span><span>Open site detail</span></button>) : <div className="table-row"><span>No exceptions for this operational day.</span></div>}</div></>}
    {selectedSite && <section className="stack" id="owner-closure"><div className="content-heading"><div><h2>{selectedSite.site_name} · daily detail</h2><p className="muted">{selectedSite.assigned_tippers_count} assigned tipper{selectedSite.assigned_tippers_count === 1 ? "" : "s"} · {selectedSite.closure.status} · {selectedSite.reporting_timezone}</p></div><div className="inline-form">{selectedSite.closure.status === "CLOSED" ? <><input aria-label="Reopening reason" placeholder="Reason to reopen" value={reopenReason} onChange={(event) => setReopenReason(event.target.value)} /><button className="secondary" onClick={reopenSelectedSite} type="button">Reopen day</button></> : <button disabled={selectedSite.closure.blockers.length > 0} onClick={closeSelectedSite} type="button">Close day</button>}</div></div>{selectedSite.closure.blockers.length > 0 && <div className="notice error"><strong>Closure blockers:</strong> {selectedSite.closure.blockers.map((item) => `${item.code}: ${item.description}`).join(" · ")}</div>}<div className="table-card"><div className="table-row"><strong>Tipper</strong><span>Driver</span><span>Trips</span><span>Start / End KM</span><span>Distance</span><span>Completeness</span></div>{(siteReport?.tippers ?? []).map((tipper) => <button className={selectedTipperId === tipper.tipper_id ? "table-row selected-row" : "table-row"} key={tipper.assignment_id} onClick={() => void loadTipper(tipper)}><strong>{tipper.registration_number}</strong><span>{tipper.driver_name}</span><span>{tipper.approved_trip_count} approved / {tipper.pending_trip_count} pending</span><span>{displayNumber(tipper.start_km)} / {displayNumber(tipper.end_km)}</span><span>{displayNumber(tipper.distance_km, " km")}</span><span>{tipper.completeness_status}</span></button>)}</div>{detailLoading && <div className="notice">Loading detail…</div>}</section>}
    {selectedTipper && <section className="stack"><div className="content-heading"><div><h2>{selectedTipper.registration_number} · event trace</h2><p className="muted">{selectedTipper.driver_name} · assignment {selectedTipper.assignment_id} · approved trip count {selectedTipper.approved_trip_count}</p></div></div><div className="metric-grid"><Metric label="Start KM" value={displayNumber(selectedTipper.start_km)} /><Metric label="End KM" value={displayNumber(selectedTipper.end_km)} /><Metric label="Distance KM" value={displayNumber(selectedTipper.distance_km, " km")} /><Metric label="Diesel issued" value={displayNumber(selectedTipper.verified_diesel_issued, " L")} /></div>{selectedTipper.exceptions.length > 0 && <div className="notice error">{selectedTipper.exceptions.map((item) => `${item.code}: ${item.description}`).join(" · ")}</div>}<div className="stack">{selectedTipper.events.map((event) => <article className="table-card" key={event.event_id}><div className="table-row"><strong>{event.event_type.replaceAll("_", " ")}</strong><span>{event.verification_status}</span><span>{displayDate(event.device_created_at)}</span>{event.evidence_available && <button className="secondary" onClick={() => void viewEvidence(event.event_id)} type="button">View evidence</button>}</div><div className="table-row"><span>{event.reading_type ? `${event.reading_type}: ${event.reading_value ?? ""}` : ""}</span><span>{event.litres === null ? "" : `${event.litres} L`}</span><span>{event.emergency_category ?? ""} {event.emergency_description ?? ""}</span><span>Received {displayDate(event.server_received_at)}</span></div><details><summary>Verification history ({event.verification_history.length})</summary>{event.verification_history.map((history, index) => <div className="table-row" key={`${event.event_id}-${index}`}><span>{history.status}</span><span>{history.actor_name ?? "System"}</span><span>{history.reason ?? "No reason"}</span><span>{displayDate(history.created_at)}</span></div>)}</details></article>)}</div>{evidenceUrl && <div className="notice"><a href={evidenceUrl} rel="noreferrer" target="_blank">Open evidence for {evidenceEventId}</a></div>}</section>}
    {!report && !loading && <div className="notice">No dashboard data is available for this operational day.</div>}
  </>;
}
