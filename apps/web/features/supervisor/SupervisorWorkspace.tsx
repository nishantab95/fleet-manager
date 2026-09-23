"use client";

import { useCallback, useEffect, useState } from "react";
import { API_BASE, ApiError, request, type WebRequest } from "../../lib/api/client";
import type { Site, SiteCompleteness, SupervisorEvent } from "../../lib/types";
import { WorkspaceHeader } from "../shared/Ui";
import { useAuth } from "../auth/AuthProvider";

export function SupervisorWorkspace() {
  const { request: apiRequest, logout, session } = useAuth();
  const [sites, setSites] = useState<Site[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { void apiRequest<Site[]>("/api/v1/supervisor/sites").then(setSites).catch((caught) => setError(caught instanceof Error ? caught.message : "Could not load permitted sites.")); }, [apiRequest]);
  return <SupervisorShell accessToken={session?.access_token ?? ""} apiRequest={apiRequest} error={error} sites={sites} setError={setError} onLogout={() => void logout()} />;
}

type SupervisorShellProps = { accessToken: string; error: string; sites: Site[]; setError: (value: string) => void; onLogout: () => void; apiRequest?: WebRequest };

export function SupervisorShell(props: SupervisorShellProps) {
  const [selectedSiteId, setSelectedSiteId] = useState(props.sites[0]?.id ?? "");
  const [reviewDate, setReviewDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [events, setEvents] = useState<SupervisorEvent[]>([]);
  const [completeness, setCompleteness] = useState<SiteCompleteness[]>([]);
  const [selectedEventIds, setSelectedEventIds] = useState<string[]>([]);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [busyEventId, setBusyEventId] = useState<string | null>(null);
  const [evidenceUrl, setEvidenceUrl] = useState<string | null>(null);
  const [evidenceEventId, setEvidenceEventId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const { accessToken, apiRequest, setError } = props;
  const call = useCallback(<T,>(path: string, options: RequestInit = {}) => apiRequest ? apiRequest<T>(path, options) : request<T>(path, options, accessToken), [accessToken, apiRequest]);
  const activeSiteId = props.sites.some((site) => site.id === selectedSiteId) ? selectedSiteId : props.sites[0]?.id ?? "";

  useEffect(() => {
    let active = true;
    async function load() {
      if (!activeSiteId) { setEvents([]); setCompleteness([]); return; }
      setLoading(true);
      try {
        const [nextEvents, nextCompleteness] = await Promise.all([
          call<SupervisorEvent[]>(`/api/v1/supervisor/sites/${activeSiteId}/events?review_date=${reviewDate}`),
          call<SiteCompleteness[]>(`/api/v1/supervisor/sites/${activeSiteId}/completeness?review_date=${reviewDate}`),
        ]);
        if (active) { setEvents(nextEvents); setCompleteness(nextCompleteness); setSelectedEventIds((current) => current.filter((id) => nextEvents.some((event) => event.event_id === id && event.verification_status === "PENDING_VERIFICATION"))); }
      } catch (caught) { if (active) setError(caught instanceof Error ? caught.message : "Could not load site operations."); }
      finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, [activeSiteId, call, setError, refreshKey, reviewDate]);

  useEffect(() => () => { if (evidenceUrl) URL.revokeObjectURL(evidenceUrl); }, [evidenceUrl]);

  const runVerification = async (event: SupervisorEvent, decision: "APPROVED" | "REJECTED" | "DISPUTED") => {
    const reason = reasons[event.event_id]?.trim() || null;
    if ((decision === "REJECTED" || decision === "DISPUTED") && !reason) { props.setError("A reason is required for rejection or dispute."); return; }
    setBusyEventId(event.event_id); props.setError("");
    try { await call(`/api/v1/supervisor/events/${event.event_id}/verify`, { method: "POST", body: JSON.stringify({ decision, reason, expected_status: event.verification_status }) }); setRefreshKey((value) => value + 1); }
    catch (caught) { props.setError(caught instanceof Error ? caught.message : "The verification could not be saved."); }
    finally { setBusyEventId(null); }
  };

  const approveSelected = async () => {
    if (!selectedEventIds.length) return;
    setBusyEventId("batch"); props.setError("");
    try { await call("/api/v1/supervisor/events/verify-batch", { method: "POST", body: JSON.stringify({ event_ids: selectedEventIds, decision: "APPROVED", expected_status: "PENDING_VERIFICATION" }) }); setSelectedEventIds([]); setRefreshKey((value) => value + 1); }
    catch (caught) { props.setError(caught instanceof Error ? caught.message : "The batch approval could not be saved."); }
    finally { setBusyEventId(null); }
  };

  const acknowledgeEmergency = async (event: SupervisorEvent) => {
    setBusyEventId(event.event_id); props.setError("");
    try { await call(`/api/v1/supervisor/events/${event.event_id}/emergency/acknowledge`, { method: "POST" }); setRefreshKey((value) => value + 1); }
    catch (caught) { props.setError(caught instanceof Error ? caught.message : "The emergency could not be acknowledged."); }
    finally { setBusyEventId(null); }
  };

  const resolveEmergency = async (event: SupervisorEvent) => {
    setBusyEventId(event.event_id); props.setError("");
    try { await call(`/api/v1/supervisor/events/${event.event_id}/emergency/resolve`, { method: "POST" }); setRefreshKey((value) => value + 1); }
    catch (caught) { props.setError(caught instanceof Error ? caught.message : "The emergency could not be resolved."); }
    finally { setBusyEventId(null); }
  };

  const viewEvidence = async (event: SupervisorEvent) => {
    props.setError("");
    try {
      const response = await fetch(`${API_BASE}/api/v1/supervisor/events/${event.event_id}/evidence`, { credentials: "include", headers: props.accessToken ? { Authorization: `Bearer ${props.accessToken}` } : undefined });
      if (!response.ok) throw new ApiError(response.status, "Evidence could not be loaded.");
      const nextUrl = URL.createObjectURL(await response.blob()); if (evidenceUrl) URL.revokeObjectURL(evidenceUrl); setEvidenceUrl(nextUrl); setEvidenceEventId(event.event_id);
    } catch (caught) { props.setError(caught instanceof Error ? caught.message : "Evidence could not be loaded."); }
  };

  const selectedSite = props.sites.find((site) => site.id === activeSiteId);
  return <main className="admin-shell">
    <WorkspaceHeader eyebrow="Supervisor · INTERNAL / QA REFERENCE" title="Site operations verification" onLogout={props.onLogout} />
    <div className="admin-layout"><section className="content">
      {props.error && <div className="notice error">{props.error}</div>}
      <div className="inline-form"><label>Assigned site<select value={activeSiteId} onChange={(event) => setSelectedSiteId(event.target.value)}><option value="">Choose a permitted site…</option>{props.sites.map((site) => <option key={site.id} value={site.id}>{site.name}{site.code ? ` · ${site.code}` : ""}</option>)}</select></label><label>Review date<input type="date" value={reviewDate} onChange={(event) => setReviewDate(event.target.value)} /></label><button className="secondary" disabled={loading} onClick={() => setRefreshKey((value) => value + 1)} type="button">{loading ? "Loading…" : "Refresh"}</button></div>
      {!props.sites.length && <div className="notice">No SupervisorSiteAccess assignment is available for this membership.</div>}
      {selectedSite && <><h2>{selectedSite.name} · daily completeness</h2><p className="muted">INTERNAL / QA REFERENCE. Review only the assigned site and date. Verification history is append-only.</p><div className="table-card">{completeness.length ? completeness.map((item) => <div className="table-row" key={item.assignment_id}><strong>{item.tipper_registration_number}</strong><span>{item.driver_name}</span><span>{item.has_start_reading ? `START ${item.start_reading_value ?? "✓"}` : "No START"}</span><span>{item.has_end_reading ? `END ${item.end_reading_value ?? "✓"}` : "No END"}</span>{item.odometer_regression && <span>KM exception: END &lt; START</span>}<span>{item.pending_trip_verification ? "Pending trip" : "Trip clear"}</span><span>{item.pending_diesel_verification ? "Pending diesel" : "Diesel clear"}</span><span>{item.unresolved_emergency ? "Emergency review" : "No unresolved emergency"}</span></div>) : <div className="table-row"><span>No assignments found for this date.</span></div>}</div>
      <div className="content-heading"><div><h2>Event review</h2><p className="muted">{events.length} event{events.length === 1 ? "" : "s"} · {events.filter((event) => event.verification_status === "PENDING_VERIFICATION").length} pending</p></div><button disabled={!selectedEventIds.length || busyEventId !== null} onClick={() => void approveSelected()} type="button">Approve selected ({selectedEventIds.length})</button></div>
      <div className="stack">{events.length ? events.map((event) => <article className="table-card" key={event.event_id}><div className="table-row"><div><strong>{event.event_type.replaceAll("_", " ")}</strong><span>{event.driver_name} · {event.tipper_registration_number}</span></div><span>{event.verification_status}</span>{event.verification_status === "PENDING_VERIFICATION" && <label><input checked={selectedEventIds.includes(event.event_id)} onChange={() => setSelectedEventIds((current) => current.includes(event.event_id) ? current.filter((id) => id !== event.event_id) : [...current, event.event_id])} type="checkbox" /> Select</label>}</div><div className="table-row"><span>Device {new Date(event.device_created_at).toLocaleString()}</span>{event.reading_type && <span>{event.reading_type.replaceAll("_", " ")}: {event.reading_value}</span>}{event.litres && <span>Diesel: {event.litres} L</span>}{event.emergency_category && <span>{event.emergency_category}: {event.emergency_description}</span>}{event.evidence_available && <button className="secondary" onClick={() => void viewEvidence(event)} type="button">View evidence</button>}</div>{event.emergency_status && <div className="table-row"><span>Emergency status: {event.emergency_status}</span>{event.emergency_status === "OPEN" && <button className="secondary" disabled={busyEventId !== null} onClick={() => void acknowledgeEmergency(event)} type="button">Acknowledge</button>}{event.emergency_status === "ACKNOWLEDGED" && <button className="secondary" disabled={busyEventId !== null} onClick={() => void resolveEmergency(event)} type="button">Resolve</button>}</div>}{event.verification_status === "PENDING_VERIFICATION" && <div className="stack"><label>Rejection/dispute reason<textarea value={reasons[event.event_id] ?? ""} onChange={(change) => setReasons((current) => ({ ...current, [event.event_id]: change.target.value }))} placeholder="Required for reject or dispute" /></label><div className="inline-form"><button disabled={busyEventId !== null} onClick={() => void runVerification(event, "APPROVED")} type="button">Approve</button><button className="secondary" disabled={busyEventId !== null} onClick={() => void runVerification(event, "REJECTED")} type="button">Reject</button><button className="secondary" disabled={busyEventId !== null} onClick={() => void runVerification(event, "DISPUTED")} type="button">Dispute</button></div></div>}<details><summary>Verification history ({event.verification_history.length})</summary>{event.verification_history.map((item, index) => <div className="table-row" key={`${event.event_id}-${index}`}><span>{item.status}</span><span>{item.actor_name ?? "System"}</span><span>{item.reason ?? "No reason"}</span><span>{new Date(item.created_at).toLocaleString()}</span></div>)}</details></article>) : <div className="notice">No operational events were captured for this site and date.</div>}</div>
      {evidenceUrl && <div className="notice"><a href={evidenceUrl} target="_blank" rel="noreferrer">Open evidence for {evidenceEventId}</a></div>}
      </>}
    </section></div>
  </main>;
}
