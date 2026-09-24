"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchPrivateEvidence, request, type WebRequest } from "../../lib/api/client";
import type { Site, SiteCompleteness, SupervisorEvent } from "../../lib/types";
import { Metric, WorkspaceHeader } from "../shared/Ui";
import { EvidenceModal, type EvidenceDetails } from "../shared/EvidenceViewer";
import { useAuth } from "../auth/AuthProvider";
import { pcRoleLabEnabled } from "../../lib/auth/config";

export function SupervisorWorkspace() {
  const { request: apiRequest, logout, session } = useAuth();
  const [sites, setSites] = useState<Site[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    void apiRequest<Site[]>("/api/v1/supervisor/sites")
      .then(setSites)
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Could not load permitted sites."));
  }, [apiRequest]);

  return <SupervisorShell accessToken={session?.access_token ?? ""} apiRequest={apiRequest} error={error} sites={sites} setError={setError} onLogout={() => void logout()} />;
}

type SupervisorShellProps = {
  accessToken: string;
  error: string;
  sites: Site[];
  setError: (value: string) => void;
  onLogout: () => void;
  apiRequest?: WebRequest;
};

type TipperReviewGroup = {
  assignmentId: string;
  tipperRegistrationNumber: string;
  driverName: string;
  events: SupervisorEvent[];
  pendingCount: number;
};

const normalEventTypes = new Set(["TRIP_COMPLETE", "KM_READING", "DIESEL"]);

function eventTime(value: string) {
  return new Date(value).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
}

function eventClock(value: string) {
  return new Date(value).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function sortByTime(left: SupervisorEvent, right: SupervisorEvent) {
  return new Date(left.device_created_at).getTime() - new Date(right.device_created_at).getTime();
}

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
  const [evidenceDetails, setEvidenceDetails] = useState<EvidenceDetails | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [emergencyNotice, setEmergencyNotice] = useState("");
  const seenOpenEmergencyIds = useRef<Set<string> | null>(null);
  const { accessToken, apiRequest, setError } = props;
  const call = useCallback(<T,>(path: string, options: RequestInit = {}) => apiRequest ? apiRequest<T>(path, options) : request<T>(path, options, accessToken), [accessToken, apiRequest]);
  const activeSiteId = props.sites.some((site) => site.id === selectedSiteId) ? selectedSiteId : props.sites[0]?.id ?? "";

  const normalEvents = useMemo(() => events.filter((event) => normalEventTypes.has(event.event_type)), [events]);
  const emergencyEvents = useMemo(() => events.filter((event) => event.event_type === "EMERGENCY"), [events]);
  const openEmergencies = useMemo(
    () => emergencyEvents.filter((event) => event.emergency_status === "OPEN" || event.emergency_status === "ACKNOWLEDGED"),
    [emergencyEvents],
  );
  const groups = useMemo(() => {
    const grouped = new Map<string, TipperReviewGroup>();
    for (const item of completeness) {
      grouped.set(item.assignment_id, {
        assignmentId: item.assignment_id,
        tipperRegistrationNumber: item.tipper_registration_number,
        driverName: item.driver_name,
        events: [],
        pendingCount: 0,
      });
    }
    for (const event of normalEvents) {
      const group = grouped.get(event.assignment_id) ?? {
        assignmentId: event.assignment_id,
        tipperRegistrationNumber: event.tipper_registration_number,
        driverName: event.driver_name,
        events: [],
        pendingCount: 0,
      };
      group.events.push(event);
      if (event.verification_status === "PENDING_VERIFICATION") group.pendingCount += 1;
      grouped.set(event.assignment_id, group);
    }
    return [...grouped.values()].sort((left, right) => left.tipperRegistrationNumber.localeCompare(right.tipperRegistrationNumber));
  }, [completeness, normalEvents]);

  const pendingTrips = normalEvents.filter((event) => event.event_type === "TRIP_COMPLETE" && event.verification_status === "PENDING_VERIFICATION").length;
  const pendingKm = normalEvents.filter((event) => event.event_type === "KM_READING" && event.verification_status === "PENDING_VERIFICATION").length;
  const pendingDiesel = normalEvents.filter((event) => event.event_type === "DIESEL" && event.verification_status === "PENDING_VERIFICATION").length;

  useEffect(() => {
    seenOpenEmergencyIds.current = null;
  }, [activeSiteId]);

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
        if (active) {
          const nextOpenIds = new Set(nextEvents.filter((event) => event.emergency_status === "OPEN").map((event) => event.event_id));
          const previousOpenIds = seenOpenEmergencyIds.current;
          if (previousOpenIds && [...nextOpenIds].some((id) => !previousOpenIds.has(id))) {
            setEmergencyNotice("New OPEN emergency received. Contact the driver now.");
          } else setEmergencyNotice("");
          seenOpenEmergencyIds.current = nextOpenIds;
          setEvents(nextEvents);
          setCompleteness(nextCompleteness);
          setSelectedEventIds((current) => current.filter((id) => nextEvents.some((event) => event.event_id === id && normalEventTypes.has(event.event_type) && event.verification_status === "PENDING_VERIFICATION")));
        }
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
      const result = await fetchPrivateEvidence(`/api/v1/supervisor/events/${event.event_id}/evidence`, props.accessToken);
      if (evidenceUrl) URL.revokeObjectURL(evidenceUrl);
      setEvidenceUrl(result.url);
      setEvidenceDetails({ ...result.metadata, eventId: event.event_id });
    } catch (caught) { props.setError(caught instanceof Error ? caught.message : "Evidence could not be loaded."); }
  };

  const closeEvidence = () => {
    if (evidenceUrl) URL.revokeObjectURL(evidenceUrl);
    setEvidenceUrl(null);
    setEvidenceDetails(null);
  };

  const selectedSite = props.sites.find((site) => site.id === activeSiteId);
  const toggleSelection = (eventId: string) => setSelectedEventIds((current) => current.includes(eventId) ? current.filter((id) => id !== eventId) : [...current, eventId]);

  const renderVerificationControls = (event: SupervisorEvent) => event.verification_status === "PENDING_VERIFICATION" && <div className="stack compact-stack">
    <label>Rejection/dispute reason<textarea value={reasons[event.event_id] ?? ""} onChange={(change) => setReasons((current) => ({ ...current, [event.event_id]: change.target.value }))} placeholder="Required for reject or dispute" /></label>
    <div className="inline-form"><button disabled={busyEventId !== null} onClick={() => void runVerification(event, "APPROVED")} type="button">Approve</button><button className="secondary" disabled={busyEventId !== null} onClick={() => void runVerification(event, "REJECTED")} type="button">Reject</button><button className="secondary" disabled={busyEventId !== null} onClick={() => void runVerification(event, "DISPUTED")} type="button">Dispute</button></div>
  </div>;

  const renderHistory = (event: SupervisorEvent) => <details><summary>Verification history ({event.verification_history.length})</summary>{event.verification_history.map((item, index) => <div className="table-row" key={`${event.event_id}-${index}`}><span>{item.status}</span><span>{item.actor_name ?? "System"}</span><span>{item.reason ?? "No reason"}</span><span>{eventTime(item.created_at)}</span></div>)}</details>;

  const renderReviewRow = (event: SupervisorEvent, label: string, detail: string) => <article className="table-card supervisor-event-card" key={event.event_id}>
    <div className="table-row"><div><strong>{label}</strong><span>{detail}</span></div><span>{eventTime(event.device_created_at)}</span><span>{event.verification_status}</span>{event.verification_status === "PENDING_VERIFICATION" && <label className="row-check"><input checked={selectedEventIds.includes(event.event_id)} onChange={() => toggleSelection(event.event_id)} type="checkbox" /> Select</label>}</div>
    <div className="table-row">{event.event_type === "KM_READING" && <span>{event.reading_value ?? "Unavailable"} km</span>}{event.event_type === "DIESEL" && <span>{event.litres ?? "Unavailable"} L</span>}{event.evidence_available && <button className="secondary" onClick={() => void viewEvidence(event)} type="button">View Photo</button>}</div>
    {renderVerificationControls(event)}
    {renderHistory(event)}
  </article>;

  const renderTipperGroup = (group: TipperReviewGroup, index: number) => {
    const trips = group.events.filter((event) => event.event_type === "TRIP_COMPLETE").sort(sortByTime);
    const km = group.events.filter((event) => event.event_type === "KM_READING").sort(sortByTime);
    const diesel = group.events.filter((event) => event.event_type === "DIESEL").sort(sortByTime);
    return <details className="tipper-review-group" key={group.assignmentId} open={index === 0}>
      <summary><span><strong>{group.tipperRegistrationNumber}</strong> · {group.driverName}</span><span className={group.pendingCount ? "badge" : "badge active"}>{group.pendingCount} pending</span></summary>
      <div className="tipper-review-body">
        <section className="review-section"><h3>TRIPS</h3>{trips.length ? trips.map((event, tripIndex) => renderReviewRow(event, `Trip ${tripIndex + 1}`, event.driver_name)) : <p className="muted">No Trip Complete events.</p>}</section>
        <section className="review-section"><h3>KM READINGS</h3>{km.length ? km.map((event) => renderReviewRow(event, event.reading_type === "START_READING" ? "START KM" : "END KM", event.reading_type === "START_READING" ? "Start odometer reading" : "End odometer reading")) : <p className="muted">No KM readings.</p>}</section>
        <section className="review-section"><h3>DIESEL</h3>{diesel.length ? diesel.map((event) => renderReviewRow(event, "Diesel issued / recorded", event.driver_name)) : <p className="muted">No Diesel events.</p>}</section>
      </div>
    </details>;
  };

  return <main className="admin-shell">
    <WorkspaceHeader activeRole="SUPERVISOR" eyebrow="Supervisor · INTERNAL / QA REFERENCE" qaNavigation={pcRoleLabEnabled} title="Site operations verification" onLogout={props.onLogout} />
    <div className="admin-layout single-column"><section className="content">
      {props.error && <div className="notice error">{props.error}</div>}
      <div className="inline-form"><label>Assigned site<select value={activeSiteId} onChange={(event) => setSelectedSiteId(event.target.value)}><option value="">Choose a permitted site…</option>{props.sites.map((site) => <option key={site.id} value={site.id}>{site.name}{site.code ? ` · ${site.code}` : ""}</option>)}</select></label><label>Review date<input type="date" value={reviewDate} onChange={(event) => setReviewDate(event.target.value)} /></label><button className="secondary" disabled={loading} onClick={() => setRefreshKey((value) => value + 1)} type="button">{loading ? "Loading…" : "Refresh"}</button></div>
      {!props.sites.length && <div className="notice">No SupervisorSiteAccess assignment is available for this membership.</div>}
      {emergencyNotice && <div className="notice error emergency-toast" role="status"><strong>{emergencyNotice}</strong></div>}
      {openEmergencies.length > 0 && <section className="emergency-panel" aria-labelledby="supervisor-emergency-heading"><div className="content-heading"><div><h2 id="supervisor-emergency-heading">EMERGENCY <span className="badge">{openEmergencies.length} open</span></h2><p className="muted">Contact the driver immediately. Emergency alerts use their own lifecycle and are not verification records.</p></div></div>{openEmergencies.map((event) => <article className="emergency-alert" key={event.event_id} role="alert"><div className="emergency-alert-details"><strong>{event.driver_name}</strong><span>Tipper {event.tipper_registration_number}</span><span>{event.site_name}</span><span>{event.emergency_status} · {eventClock(event.device_created_at)}</span></div><div className="inline-form emergency-actions">{event.driver_phone && <a className="call-driver" href={`tel:${event.driver_phone}`}>CALL DRIVER</a>}{event.emergency_status === "OPEN" && <button className="secondary" disabled={busyEventId !== null} onClick={() => void acknowledgeEmergency(event)} type="button">ACKNOWLEDGE</button>}{event.emergency_status === "ACKNOWLEDGED" && <button className="secondary" disabled={busyEventId !== null} onClick={() => void resolveEmergency(event)} type="button">RESOLVE</button>}</div></article>)}</section>}
      {selectedSite && <><div className="metric-grid supervisor-qa-summary"><Metric label="Pending Trips" value={pendingTrips} /><Metric label="Pending KM" value={pendingKm} /><Metric label="Pending Diesel" value={pendingDiesel} /><Metric label="Open Emergencies" value={openEmergencies.length} /></div><h2>{selectedSite.name} · daily completeness</h2><p className="muted">Review only the assigned site and date. Verification history is append-only.</p><div className="table-card">{completeness.length ? completeness.map((item) => <div className="table-row" key={item.assignment_id}><strong>{item.tipper_registration_number}</strong><span>{item.driver_name}</span><span>{item.has_start_reading ? `START ${item.start_reading_value ?? "✓"}` : "No START"}</span><span>{item.has_end_reading ? `END ${item.end_reading_value ?? "✓"}` : "No END"}</span>{item.odometer_regression && <span>KM exception: END &lt; START</span>}<span>{item.pending_trip_verification ? "Pending trip" : "Trip clear"}</span><span>{item.pending_diesel_verification ? "Pending diesel" : "Diesel clear"}</span><span>{item.unresolved_emergency ? "Emergency review" : "No unresolved emergency"}</span></div>) : <div className="table-row"><span>No assignments found for this date.</span></div>}</div>
      <div className="content-heading"><div><h2>Operations by tipper</h2><p className="muted">{normalEvents.length} operational event{normalEvents.length === 1 ? "" : "s"} · {normalEvents.filter((event) => event.verification_status === "PENDING_VERIFICATION").length} actionable pending</p></div><button disabled={!selectedEventIds.length || busyEventId !== null} onClick={() => void approveSelected()} type="button">Approve selected ({selectedEventIds.length})</button></div>
      <div className="stack">{groups.length ? groups.map(renderTipperGroup) : <div className="notice">No operational events were captured for this site and date.</div>}</div>
      </>}
      {evidenceUrl && evidenceDetails && <EvidenceModal details={evidenceDetails} onClose={closeEvidence} url={evidenceUrl} />}
    </section></div>
  </main>;
}
