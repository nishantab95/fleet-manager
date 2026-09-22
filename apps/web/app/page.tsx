"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type MembershipRole = "OWNER_ADMIN" | "SUPERVISOR" | "DRIVER";
type Status = "ACTIVE" | "INACTIVE";
type Tab = "operations" | "overview" | "sites" | "tippers" | "people" | "assignments" | "access";
type Tokens = { access_token: string; refresh_token: string; expires_in: number; role: MembershipRole };
type Membership = { membership_id: string; company_id: string; company_name: string; role: MembershipRole };
type Site = { id: string; name: string; code: string | null; status: Status };
type Tipper = { id: string; registration_number: string; short_name: string | null; status: Status };
type Person = { user_id: string; membership_id: string; phone: string; display_name: string; role: MembershipRole; status: Status; user_status: string };
type SupervisorAccess = { id: string; supervisor_membership_id: string; supervisor_name: string; site_id: string; site_name: string };
type Assignment = { id: string; driver_membership_id: string; driver_name: string; supervisor_membership_id: string; supervisor_name: string; tipper_id: string; registration_number: string; site_id: string; site_name: string; starts_at: string; ends_at: string | null };
type VerificationStatus = "PENDING_VERIFICATION" | "APPROVED" | "REJECTED" | "DISPUTED" | "AMENDED";
type SupervisorHistory = { status: VerificationStatus; reason: string | null; actor_name: string | null; created_at: string };
type SupervisorEvent = { event_id: string; event_type: "TRIP_COMPLETE" | "KM_READING" | "DIESEL" | "EMERGENCY"; assignment_id: string; driver_name: string; tipper_registration_number: string; site_id: string; site_name: string; device_created_at: string; server_received_at: string; verification_status: VerificationStatus; reading_type: "START_READING" | "END_READING" | null; reading_value: string | null; litres: string | null; emergency_category: string | null; emergency_status: string | null; emergency_description: string | null; evidence_id: string | null; evidence_available: boolean; verification_history: SupervisorHistory[] };
type SiteCompleteness = { assignment_id: string; driver_name: string; tipper_registration_number: string; site_id: string; site_name: string; has_start_reading: boolean; has_end_reading: boolean; start_reading_value: string | null; end_reading_value: string | null; odometer_regression: boolean; pending_trip_verification: boolean; pending_diesel_verification: boolean; unresolved_emergency: boolean };
type ReportException = { code: string; description: string; assignment_id: string; tipper_id: string; tipper_registration_number: string; site_id: string; event_id: string | null };
type ReportHistory = { status: VerificationStatus; actor_name: string | null; reason: string | null; created_at: string };
type ReportEvent = { event_id: string; event_type: "TRIP_COMPLETE" | "KM_READING" | "DIESEL" | "EMERGENCY"; assignment_id: string; tipper_id: string; tipper_registration_number: string; site_id: string; site_name: string; driver_name: string; supervisor_name: string; device_created_at: string; server_received_at: string; verification_status: VerificationStatus; reading_type: string | null; reading_value: number | null; litres: number | null; emergency_category: string | null; emergency_status: string | null; emergency_description: string | null; evidence_available: boolean; verification_history: ReportHistory[] };
type ClosureHistory = { status: "OPEN" | "READY_TO_CLOSE" | "CLOSED" | "REOPENED"; actor_name: string | null; reason: string | null; created_at: string };
type Closure = { site_id: string; site_name: string; operational_date: string; reporting_timezone: string; workday_start_minutes: number; status: "OPEN" | "READY_TO_CLOSE" | "CLOSED" | "REOPENED"; blockers: ReportException[]; history: ClosureHistory[] };
type TipperDailyReport = { assignment_id: string; tipper_id: string; registration_number: string; short_name: string | null; site_id: string; site_name: string; driver_name: string; supervisor_name: string; assignment_starts_at: string; assignment_ends_at: string | null; approved_trip_count: number; pending_trip_count: number; disputed_trip_count: number; rejected_trip_count: number; start_km: number | null; end_km: number | null; distance_km: number | null; verified_diesel_issued: number; pending_diesel_count: number; disputed_diesel_count: number; unresolved_emergency_count: number; missing_start_reading: boolean; missing_end_reading: boolean; completeness_status: string; exceptions: ReportException[]; events: ReportEvent[] };
type SiteDailyReport = { site_id: string; site_name: string; operational_date: string; reporting_timezone: string; assigned_tippers_count: number; approved_trip_count: number; pending_trip_count: number; disputed_trip_count: number; total_km: number | null; verified_diesel_issued: number; missing_reading_count: number; unresolved_emergency_count: number; closure: Closure; tippers: TipperDailyReport[] };
type DashboardReport = { operational_date: string; reporting_timezone: string; workday_start_minutes: number; assigned_tippers_count: number; approved_trip_count: number; pending_trip_count: number; total_km: number | null; verified_diesel_issued: number; pending_verification_count: number; missing_reading_count: number; unresolved_emergency_count: number; sites_not_closed_count: number; complete_tippers_count: number; sites: SiteDailyReport[]; exceptions: ReportException[] };
type CompanySettings = { company_id: string; reporting_timezone: string; operational_day_start_minutes: number };

class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}, accessToken?: string): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch {
    throw new ApiError(0, "The API is unavailable. Start the backend and try again.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body?.detail;
    const message = typeof detail === "object" ? detail.message : detail;
    throw new ApiError(response.status, message ?? "The request could not be completed.");
  }
  return body as T;
}

export default function HomePage() {
  const [phase, setPhase] = useState<"phone" | "otp" | "membership" | "admin" | "supervisor" | "denied">("phone");
  const [phone, setPhone] = useState("");
  const [otp, setOtp] = useState("");
  const [challengeId, setChallengeId] = useState("");
  const [preSessionToken, setPreSessionToken] = useState("");
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [tokens, setTokens] = useState<Tokens | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<Tab>("overview");
  const [sites, setSites] = useState<Site[]>([]);
  const [tippers, setTippers] = useState<Tipper[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [access, setAccess] = useState<SupervisorAccess[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [supervisorSites, setSupervisorSites] = useState<Site[]>([]);

  async function loadAdminData(accessToken: string) {
    const [nextSites, nextTippers, nextPeople, nextAccess, nextAssignments] = await Promise.all([
      request<Site[]>("/api/v1/admin/sites", {}, accessToken),
      request<Tipper[]>("/api/v1/admin/tippers", {}, accessToken),
      request<Person[]>("/api/v1/admin/people", {}, accessToken),
      request<SupervisorAccess[]>("/api/v1/admin/supervisor-site-access", {}, accessToken),
      request<Assignment[]>("/api/v1/admin/assignments", {}, accessToken),
    ]);
    setSites(nextSites);
    setTippers(nextTippers);
    setPeople(nextPeople);
    setAccess(nextAccess);
    setAssignments(nextAssignments);
  }

  async function loadSupervisorSites(accessToken: string) {
    const nextSites = await request<Site[]>("/api/v1/supervisor/sites", {}, accessToken);
    setSupervisorSites(nextSites);
    setPhase("supervisor");
  }

  async function submitPhone(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await request<{ challenge_id: string }>("/api/v1/auth/otp/request", { method: "POST", body: JSON.stringify({ phone }) });
      setChallengeId(result.challenge_id);
      setPhase("otp");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not request an OTP.");
    } finally {
      setBusy(false);
    }
  }

  async function submitOtp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const verified = await request<{ pre_session_token: string }>("/api/v1/auth/otp/verify", { method: "POST", body: JSON.stringify({ challenge_id: challengeId, otp }) });
      const options = await request<{ memberships: Membership[] }>("/api/v1/auth/memberships", { method: "POST", body: JSON.stringify({ pre_session_token: verified.pre_session_token }) });
      setPreSessionToken(verified.pre_session_token);
      setMemberships(options.memberships);
      setPhase("membership");
      if (options.memberships.length === 0) setError("No active company membership is available.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The OTP could not be verified.");
    } finally {
      setBusy(false);
    }
  }

  async function selectMembership(membershipId: string) {
    setBusy(true);
    setError("");
    try {
      const nextTokens = await request<Tokens>("/api/v1/auth/session", { method: "POST", body: JSON.stringify({ pre_session_token: preSessionToken, membership_id: membershipId }) });
      setTokens(nextTokens);
      if (nextTokens.role === "SUPERVISOR") {
        await loadSupervisorSites(nextTokens.access_token);
        return;
      }
      if (nextTokens.role !== "OWNER_ADMIN") {
        setPhase("denied");
        return;
      }
      await loadAdminData(nextTokens.access_token);
      setPhase("admin");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create a session.");
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    if (tokens) await request<void>("/api/v1/auth/logout", { method: "POST" }, tokens.access_token).catch(() => undefined);
    setTokens(null);
    setPreSessionToken("");
    setMemberships([]);
    setSupervisorSites([]);
    setPhase("phone");
    setError("");
  }

  if (phase === "supervisor" && tokens) {
    return <SupervisorShell accessToken={tokens.access_token} error={error} sites={supervisorSites} setError={setError} onLogout={logout} />;
  }

  if (phase !== "admin" || !tokens) {
    return (
      <main className="auth-shell">
        <section className="auth-card">
          <p className="eyebrow">Fleet Manager · Secure access</p>
          <h1>Choose your operations workspace</h1>
          <p className="summary">Sign in with your phone and choose an active company membership. Owners manage the fleet; supervisors review only their assigned sites. Authentication state stays in memory and is cleared on reload or logout.</p>
          {phase === "phone" && <form className="stack" onSubmit={submitPhone}><label>Phone number<input value={phone} onChange={(event) => setPhone(event.target.value)} required /></label><button disabled={busy} type="submit">{busy ? "Requesting…" : "Send OTP"}</button></form>}
          {phase === "otp" && <form className="stack" onSubmit={submitOtp}><label>One-time code<input inputMode="numeric" maxLength={6} pattern="[0-9]{6}" value={otp} onChange={(event) => setOtp(event.target.value)} required /></label><button disabled={busy} type="submit">{busy ? "Checking…" : "Verify and continue"}</button><button className="secondary" type="button" onClick={() => setPhase("phone")}>Use another phone</button></form>}
          {phase === "membership" && <div className="stack"><h2>Choose company access</h2>{memberships.map((membership) => <button className="choice" disabled={busy} key={membership.membership_id} onClick={() => selectMembership(membership.membership_id)} type="button"><span>{membership.company_name}</span><small>{membership.role}</small></button>)}<button className="secondary" type="button" onClick={logout}>Cancel</button></div>}
          {phase === "denied" && <div className="notice error">This membership is not permitted to use an available web workspace.</div>}
          {error && <div className="notice error">{error}</div>}
        </section>
      </main>
    );
  }

  return <AdminShell accessToken={tokens.access_token} assignments={assignments} error={error} people={people} sites={sites} tab={tab} tippers={tippers} access={access} setError={setError} setTab={setTab} onLogout={logout} reload={() => loadAdminData(tokens.access_token)} />;
}

type SupervisorShellProps = { accessToken: string; error: string; sites: Site[]; setError: (value: string) => void; onLogout: () => void };

function SupervisorShell(props: SupervisorShellProps) {
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
  const activeSiteId = props.sites.some((site) => site.id === selectedSiteId) ? selectedSiteId : props.sites[0]?.id ?? "";
  const { accessToken, setError } = props;

  useEffect(() => {
    let active = true;
    async function load() {
      if (!activeSiteId) {
        setEvents([]);
        setCompleteness([]);
        return;
      }
      setLoading(true);
      try {
        const [nextEvents, nextCompleteness] = await Promise.all([
          request<SupervisorEvent[]>(`/api/v1/supervisor/sites/${activeSiteId}/events?review_date=${reviewDate}`, {}, accessToken),
          request<SiteCompleteness[]>(`/api/v1/supervisor/sites/${activeSiteId}/completeness?review_date=${reviewDate}`, {}, accessToken),
        ]);
        if (active) {
          setEvents(nextEvents);
          setCompleteness(nextCompleteness);
          setSelectedEventIds((current) => current.filter((id) => nextEvents.some((event) => event.event_id === id && event.verification_status === "PENDING_VERIFICATION")));
        }
      } catch (caught) {
        if (active) setError(caught instanceof Error ? caught.message : "Could not load site operations.");
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [accessToken, activeSiteId, refreshKey, reviewDate, setError]);

  useEffect(() => () => {
    if (evidenceUrl) URL.revokeObjectURL(evidenceUrl);
  }, [evidenceUrl]);

  const runVerification = async (event: SupervisorEvent, decision: "APPROVED" | "REJECTED" | "DISPUTED") => {
    const reason = reasons[event.event_id]?.trim() || null;
    if ((decision === "REJECTED" || decision === "DISPUTED") && !reason) {
      props.setError("A reason is required for rejection or dispute.");
      return;
    }
    setBusyEventId(event.event_id);
    props.setError("");
    try {
      await request<SupervisorEvent>(`/api/v1/supervisor/events/${event.event_id}/verify`, { method: "POST", body: JSON.stringify({ decision, reason, expected_status: event.verification_status }) }, props.accessToken);
      setRefreshKey((value) => value + 1);
    } catch (caught) {
      props.setError(caught instanceof Error ? caught.message : "The verification could not be saved.");
    } finally {
      setBusyEventId(null);
    }
  };

  const approveSelected = async () => {
    if (!selectedEventIds.length) return;
    setBusyEventId("batch");
    props.setError("");
    try {
      await request<{ events: SupervisorEvent[] }>("/api/v1/supervisor/events/verify-batch", { method: "POST", body: JSON.stringify({ event_ids: selectedEventIds, decision: "APPROVED", expected_status: "PENDING_VERIFICATION" }) }, props.accessToken);
      setSelectedEventIds([]);
      setRefreshKey((value) => value + 1);
    } catch (caught) {
      props.setError(caught instanceof Error ? caught.message : "The batch approval could not be saved.");
    } finally {
      setBusyEventId(null);
    }
  };

  const acknowledgeEmergency = async (event: SupervisorEvent) => {
    setBusyEventId(event.event_id);
    props.setError("");
    try {
      await request<SupervisorEvent>(`/api/v1/supervisor/events/${event.event_id}/emergency/acknowledge`, { method: "POST" }, props.accessToken);
      setRefreshKey((value) => value + 1);
    } catch (caught) {
      props.setError(caught instanceof Error ? caught.message : "The emergency could not be acknowledged.");
    } finally {
      setBusyEventId(null);
    }
  };

  const viewEvidence = async (event: SupervisorEvent) => {
    props.setError("");
    try {
      const response = await fetch(`${API_BASE}/api/v1/supervisor/events/${event.event_id}/evidence`, { headers: { Authorization: `Bearer ${props.accessToken}` } });
      if (!response.ok) throw new ApiError(response.status, "Evidence could not be loaded.");
      const nextUrl = URL.createObjectURL(await response.blob());
      if (evidenceUrl) URL.revokeObjectURL(evidenceUrl);
      setEvidenceUrl(nextUrl);
      setEvidenceEventId(event.event_id);
    } catch (caught) {
      props.setError(caught instanceof Error ? caught.message : "Evidence could not be loaded.");
    }
  };

  const toggleEvent = (eventId: string) => setSelectedEventIds((current) => current.includes(eventId) ? current.filter((id) => id !== eventId) : [...current, eventId]);
  const selectedSite = props.sites.find((site) => site.id === selectedSiteId);

  return (
    <main className="admin-shell">
      <header className="topbar"><div><p className="eyebrow">Fleet Manager · Supervisor</p><h1>Site operations verification</h1></div><button className="secondary" onClick={props.onLogout} type="button">Log out</button></header>
      <div className="admin-layout">
        <section className="content">
          {props.error && <div className="notice error">{props.error}</div>}
          <div className="inline-form"><label>Assigned site<select value={selectedSiteId} onChange={(event) => setSelectedSiteId(event.target.value)}><option value="">Choose a permitted site…</option>{props.sites.map((site) => <option key={site.id} value={site.id}>{site.name}{site.code ? ` · ${site.code}` : ""}</option>)}</select></label><label>Review date<input type="date" value={reviewDate} onChange={(event) => setReviewDate(event.target.value)} /></label><button className="secondary" disabled={loading} onClick={() => setRefreshKey((value) => value + 1)} type="button">{loading ? "Loading…" : "Refresh"}</button></div>
          {!props.sites.length && <div className="notice">No SupervisorSiteAccess assignment is available for this membership.</div>}
          {selectedSite && <><h2>{selectedSite.name} · daily completeness</h2><p className="muted">Review only the assigned site and date. Verification history is append-only; completed decisions are never silently edited.</p><div className="table-card">{completeness.length ? completeness.map((item) => <div className="table-row" key={item.assignment_id}><strong>{item.tipper_registration_number}</strong><span>{item.driver_name}</span><span>{item.has_start_reading ? `START ${item.start_reading_value ?? "✓"}` : "No START"}</span><span>{item.has_end_reading ? `END ${item.end_reading_value ?? "✓"}` : "No END"}</span>{item.odometer_regression && <span>KM exception: END &lt; START</span>}<span>{item.pending_trip_verification ? "Pending trip" : "Trip clear"}</span><span>{item.pending_diesel_verification ? "Pending diesel" : "Diesel clear"}</span><span>{item.unresolved_emergency ? "Emergency review" : "No unresolved emergency"}</span></div>) : <div className="table-row"><span>No assignments found for this date.</span></div>}</div>
          <div className="content-heading"><div><h2>Event review</h2><p className="muted">{events.length} event{events.length === 1 ? "" : "s"} · {events.filter((event) => event.verification_status === "PENDING_VERIFICATION").length} pending</p></div><button disabled={!selectedEventIds.length || busyEventId !== null} onClick={approveSelected} type="button">Approve selected ({selectedEventIds.length})</button></div>
          <div className="stack">{events.length ? events.map((event) => <article className="table-card" key={event.event_id}><div className="table-row"><div><strong>{event.event_type.replaceAll("_", " ")}</strong><span>{event.driver_name} · {event.tipper_registration_number}</span></div><span>{event.verification_status}</span>{event.verification_status === "PENDING_VERIFICATION" && <label><input checked={selectedEventIds.includes(event.event_id)} onChange={() => toggleEvent(event.event_id)} type="checkbox" /> Select</label>}</div><div className="table-row"><span>Device {new Date(event.device_created_at).toLocaleString()}</span>{event.reading_type && <span>{event.reading_type.replaceAll("_", " ")}: {event.reading_value}</span>}{event.litres && <span>Diesel: {event.litres} L</span>}{event.emergency_category && <span>{event.emergency_category}: {event.emergency_description}</span>}{event.evidence_available && <button className="secondary" onClick={() => viewEvidence(event)} type="button">View evidence</button>}</div>{event.emergency_status && <div className="table-row"><span>Emergency status: {event.emergency_status}</span>{event.emergency_status === "OPEN" && <button className="secondary" disabled={busyEventId !== null} onClick={() => acknowledgeEmergency(event)} type="button">Acknowledge</button>}</div>}{event.verification_status === "PENDING_VERIFICATION" && <div className="stack"><label>Rejection/dispute reason<textarea value={reasons[event.event_id] ?? ""} onChange={(change) => setReasons((current) => ({ ...current, [event.event_id]: change.target.value }))} placeholder="Required for reject or dispute" /></label><div className="inline-form"><button disabled={busyEventId !== null} onClick={() => runVerification(event, "APPROVED")} type="button">Approve</button><button className="secondary" disabled={busyEventId !== null} onClick={() => runVerification(event, "REJECTED")} type="button">Reject</button><button className="secondary" disabled={busyEventId !== null} onClick={() => runVerification(event, "DISPUTED")} type="button">Dispute</button></div></div>}<details><summary>Verification history ({event.verification_history.length})</summary><div className="stack">{event.verification_history.map((item, index) => <div className="table-row" key={`${event.event_id}-${index}`}><span>{item.status}</span><span>{item.actor_name ?? "System"}</span><span>{item.reason ?? "No reason"}</span><span>{new Date(item.created_at).toLocaleString()}</span></div>)}</div></details></article>) : <div className="notice">No operational events were captured for this site and date.</div>}</div>
          {evidenceUrl && <div className="notice"><a href={evidenceUrl} target="_blank" rel="noreferrer">Open evidence for {evidenceEventId}</a></div>}
          </>}
        </section>
      </div>
    </main>
  );
}

type OwnerOperationsProps = { accessToken: string; setError: (value: string) => void };

export function OwnerOperations(props: OwnerOperationsProps) {
  const { accessToken, setError } = props;
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
          request<DashboardReport>(`/api/v1/reports/dashboard${query}`, {}, accessToken),
          request<CompanySettings>("/api/v1/admin/company", {}, accessToken),
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
    return () => {
      active = false;
    };
  }, [accessToken, operationalDate, refreshKey, setError]);

  useEffect(() => {
    let active = true;
    async function load() {
      if (!selectedSiteId || !operationalDate) {
        if (active) setSiteReport(null);
        return;
      }
      setDetailLoading(true);
      try {
        const next = await request<SiteDailyReport>(`/api/v1/reports/sites/${selectedSiteId}/daily?operational_date=${operationalDate}`, {}, accessToken);
        if (active) setSiteReport(next);
      } catch (caught) {
        if (active) setError(caught instanceof Error ? caught.message : "Could not load the site report.");
      } finally {
        if (active) setDetailLoading(false);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [accessToken, operationalDate, refreshKey, selectedSiteId, setError]);

  useEffect(() => () => {
    if (evidenceUrl) URL.revokeObjectURL(evidenceUrl);
  }, [evidenceUrl]);

  const selectedSite = report?.sites.find((site) => site.site_id === selectedSiteId) ?? null;
  const selectedTipper = tipperReports.find((tipper) => tipper.tipper_id === selectedTipperId) ?? null;
  const displayNumber = (value: number | null, suffix = "") => value === null ? "Unavailable" : `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`;
  const displayDate = (value: string) => new Date(value).toLocaleString();
  const selectSite = (siteId: string) => {
    setSelectedSiteId(siteId);
    setSelectedTipperId("");
    setTipperReports([]);
    setReopenReason("");
  };

  const loadTipper = async (tipper: TipperDailyReport) => {
    setDetailLoading(true);
    props.setError("");
    try {
      const next = await request<TipperDailyReport[]>(`/api/v1/reports/tippers/${tipper.tipper_id}/daily?operational_date=${operationalDate}`, {}, props.accessToken);
      setTipperReports(next);
      setSelectedTipperId(tipper.tipper_id);
    } catch (caught) {
      props.setError(caught instanceof Error ? caught.message : "Could not load the tipper report.");
    } finally {
      setDetailLoading(false);
    }
  };

  const closeSelectedSite = async () => {
    if (!selectedSite) return;
    props.setError("");
    try {
      await request<Closure>(`/api/v1/reports/sites/${selectedSite.site_id}/closure/close?operational_date=${operationalDate}`, { method: "POST", body: JSON.stringify({ reason: null }) }, props.accessToken);
      setRefreshKey((value) => value + 1);
    } catch (caught) {
      props.setError(caught instanceof Error ? caught.message : "The site could not be closed.");
    }
  };

  const reopenSelectedSite = async () => {
    if (!selectedSite || !reopenReason.trim()) {
      props.setError("A reason is required to reopen a closed site day.");
      return;
    }
    props.setError("");
    try {
      await request<Closure>(`/api/v1/reports/sites/${selectedSite.site_id}/closure/reopen?operational_date=${operationalDate}`, { method: "POST", body: JSON.stringify({ reason: reopenReason.trim() }) }, props.accessToken);
      setReopenReason("");
      setRefreshKey((value) => value + 1);
    } catch (caught) {
      props.setError(caught instanceof Error ? caught.message : "The site could not be reopened.");
    }
  };

  const saveSettings = async () => {
    const minutes = Number(workdayStartMinutes);
    if (!reportingTimezone.trim() || !Number.isInteger(minutes) || minutes < 0 || minutes > 1439) {
      props.setError("Use a valid IANA timezone and a day-start minute between 0 and 1439.");
      return;
    }
    setSettingsSaving(true);
    props.setError("");
    try {
      const next = await request<CompanySettings>("/api/v1/admin/company", { method: "PATCH", body: JSON.stringify({ reporting_timezone: reportingTimezone.trim(), operational_day_start_minutes: minutes }) }, props.accessToken);
      setSettings(next);
      setReportingTimezone(next.reporting_timezone);
      setWorkdayStartMinutes(String(next.operational_day_start_minutes));
      setRefreshKey((value) => value + 1);
    } catch (caught) {
      props.setError(caught instanceof Error ? caught.message : "Company reporting settings could not be saved.");
    } finally {
      setSettingsSaving(false);
    }
  };

  const downloadExcel = async () => {
    props.setError("");
    try {
      const response = await fetch(`${API_BASE}/api/v1/reports/daily.xlsx?operational_date=${operationalDate}`, { headers: { Authorization: `Bearer ${props.accessToken}` } });
      if (!response.ok) throw new ApiError(response.status, "The Excel report could not be downloaded.");
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `fleet-report-${operationalDate}.xlsx`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      props.setError(caught instanceof Error ? caught.message : "The Excel report could not be downloaded.");
    }
  };

  const viewEvidence = async (eventId: string) => {
    props.setError("");
    try {
      const response = await fetch(`${API_BASE}/api/v1/reports/events/${eventId}/evidence`, { headers: { Authorization: `Bearer ${props.accessToken}` } });
      if (!response.ok) throw new ApiError(response.status, "Evidence could not be loaded.");
      const nextUrl = URL.createObjectURL(await response.blob());
      if (evidenceUrl) URL.revokeObjectURL(evidenceUrl);
      setEvidenceUrl(nextUrl);
      setEvidenceEventId(eventId);
    } catch (caught) {
      props.setError(caught instanceof Error ? caught.message : "Evidence could not be loaded.");
    }
  };

  return <>
    <div className="content-heading"><div><h2>Owner operations</h2><p className="muted">Official totals use approved events only. Reporting day: {report?.reporting_timezone ?? "company timezone"}, starting at {report ? `${Math.floor(report.workday_start_minutes / 60).toString().padStart(2, "0")}:${(report.workday_start_minutes % 60).toString().padStart(2, "0")}` : "configured time"}.</p></div><div className="inline-form"><label>Operational date<input type="date" value={operationalDate} onChange={(event) => { setOperationalDate(event.target.value); setSelectedSiteId(""); setTipperReports([]); }} /></label><button className="secondary" disabled={loading} onClick={() => setRefreshKey((value) => value + 1)} type="button">{loading ? "Loading…" : "Refresh"}</button><button disabled={!report} onClick={downloadExcel} type="button">Download Excel</button></div></div>
    {settings && <div className="table-card settings-card"><div className="content-heading"><div><h3>Company reporting settings</h3><p className="muted">The operational day is stored and calculated in this IANA timezone. Times are persisted in UTC.</p></div><button disabled={settingsSaving} onClick={saveSettings} type="button">{settingsSaving ? "Saving…" : "Save settings"}</button></div><div className="inline-form"><label>IANA timezone<input value={reportingTimezone} onChange={(event) => setReportingTimezone(event.target.value)} /></label><label>Day start minute (0–1439)<input type="number" min="0" max="1439" value={workdayStartMinutes} onChange={(event) => setWorkdayStartMinutes(event.target.value)} /></label></div></div>}
    {report && <>
      <div className="metric-grid"><Metric label="Assigned tippers" value={report.assigned_tippers_count} /><Metric label="Approved trips" value={report.approved_trip_count} /><Metric label="Total KM" value={report.total_km === null ? "Unavailable" : displayNumber(report.total_km, " km")} /><Metric label="Diesel issued" value={displayNumber(report.verified_diesel_issued, " L")} /><Metric label="Pending verification" value={report.pending_verification_count} /><Metric label="Missing readings" value={report.missing_reading_count} /><Metric label="Unresolved emergencies" value={report.unresolved_emergency_count} /><Metric label="Sites not closed" value={report.sites_not_closed_count} /></div>
      <div className="content-heading"><div><h2>Sites</h2><p className="muted">{report.complete_tippers_count} tipper{report.complete_tippers_count === 1 ? "" : "s"} have complete approved readings for this operational day.</p></div></div>
      <div className="table-card"><div className="table-row"><strong>Site</strong><span>Assigned</span><span>Trips</span><span>KM</span><span>Diesel</span><span>Closure</span></div>{report.sites.length ? report.sites.map((site) => <button className={selectedSiteId === site.site_id ? "table-row selected-row" : "table-row"} key={site.site_id} onClick={() => selectSite(site.site_id)} type="button"><strong>{site.site_name}</strong><span>{site.assigned_tippers_count}</span><span>{site.approved_trip_count} approved / {site.pending_trip_count} pending</span><span>{displayNumber(site.total_km, " km")}</span><span>{displayNumber(site.verified_diesel_issued, " L")}</span><span>{site.closure.status}</span></button>) : <div className="table-row"><span>No assigned tippers were found for this operational day.</span></div>}</div>
      <div className="content-heading"><div><h2>Exceptions</h2><p className="muted">Operational blockers remain visible until resolved or explicitly reviewed.</p></div></div>
      <div className="table-card">{report.exceptions.length ? report.exceptions.map((item, index) => <button className="table-row" key={`${item.code}-${item.assignment_id}-${index}`} onClick={() => selectSite(item.site_id)} type="button"><strong>{item.code}</strong><span>{item.tipper_registration_number}</span><span>{item.description}</span><span>Open site detail</span></button>) : <div className="table-row"><span>No exceptions for this operational day.</span></div>}</div>
    </>}
    {selectedSite && <section className="stack"><div className="content-heading"><div><h2>{selectedSite.site_name} · daily detail</h2><p className="muted">{selectedSite.assigned_tippers_count} assigned tipper{selectedSite.assigned_tippers_count === 1 ? "" : "s"} · {selectedSite.closure.status} · {selectedSite.reporting_timezone}</p></div><div className="inline-form">{selectedSite.closure.status === "CLOSED" ? <><input aria-label="Reopening reason" placeholder="Reason to reopen" value={reopenReason} onChange={(event) => setReopenReason(event.target.value)} /><button className="secondary" onClick={reopenSelectedSite} type="button">Reopen day</button></> : <button disabled={selectedSite.closure.blockers.length > 0} onClick={closeSelectedSite} type="button">Close day</button>}</div></div>{selectedSite.closure.blockers.length > 0 && <div className="notice error"><strong>Closure blockers:</strong> {selectedSite.closure.blockers.map((item) => `${item.code}: ${item.description}`).join(" · ")}</div>}<div className="table-card"><div className="table-row"><strong>Tipper</strong><span>Driver</span><span>Trips</span><span>Start / End KM</span><span>Distance</span><span>Completeness</span></div>{(siteReport?.tippers ?? []).map((tipper) => <button className={selectedTipperId === tipper.tipper_id ? "table-row selected-row" : "table-row"} key={tipper.assignment_id} onClick={() => loadTipper(tipper)} type="button"><strong>{tipper.registration_number}</strong><span>{tipper.driver_name}</span><span>{tipper.approved_trip_count} approved / {tipper.pending_trip_count} pending</span><span>{displayNumber(tipper.start_km)} / {displayNumber(tipper.end_km)}</span><span>{displayNumber(tipper.distance_km, " km")}</span><span>{tipper.completeness_status}</span></button>)}</div>{detailLoading && <div className="notice">Loading detail…</div>}</section>}
    {selectedTipper && <section className="stack"><div className="content-heading"><div><h2>{selectedTipper.registration_number} · event trace</h2><p className="muted">{selectedTipper.driver_name} · assignment {selectedTipper.assignment_id} · approved trip count {selectedTipper.approved_trip_count}</p></div></div><div className="metric-grid"><Metric label="Start KM" value={displayNumber(selectedTipper.start_km)} /><Metric label="End KM" value={displayNumber(selectedTipper.end_km)} /><Metric label="Distance KM" value={displayNumber(selectedTipper.distance_km, " km")} /><Metric label="Diesel issued" value={displayNumber(selectedTipper.verified_diesel_issued, " L")} /></div>{selectedTipper.exceptions.length > 0 && <div className="notice error">{selectedTipper.exceptions.map((item) => `${item.code}: ${item.description}`).join(" · ")}</div>}<div className="stack">{selectedTipper.events.map((event) => <article className="table-card" key={event.event_id}><div className="table-row"><strong>{event.event_type.replaceAll("_", " ")}</strong><span>{event.verification_status}</span><span>{displayDate(event.device_created_at)}</span>{event.evidence_available && <button className="secondary" onClick={() => viewEvidence(event.event_id)} type="button">View evidence</button>}</div><div className="table-row"><span>{event.reading_type ? `${event.reading_type}: ${event.reading_value ?? ""}` : ""}</span><span>{event.litres === null ? "" : `${event.litres} L`}</span><span>{event.emergency_category ?? ""} {event.emergency_description ?? ""}</span><span>Received {displayDate(event.server_received_at)}</span></div><details><summary>Verification history ({event.verification_history.length})</summary>{event.verification_history.map((history, index) => <div className="table-row" key={`${event.event_id}-${index}`}><span>{history.status}</span><span>{history.actor_name ?? "System"}</span><span>{history.reason ?? "No reason"}</span><span>{displayDate(history.created_at)}</span></div>)}</details></article>)}</div>{evidenceUrl && <div className="notice"><a href={evidenceUrl} rel="noreferrer" target="_blank">Open evidence for {evidenceEventId}</a></div>}</section>}
    {!report && !loading && <div className="notice">No dashboard data is available for this operational day.</div>}
  </>;
}

type AdminShellProps = { accessToken: string; assignments: Assignment[]; error: string; people: Person[]; sites: Site[]; tab: Tab; tippers: Tipper[]; access: SupervisorAccess[]; setError: (value: string) => void; setTab: (value: Tab) => void; onLogout: () => void; reload: () => Promise<void> };

function AdminShell(props: AdminShellProps) {
  const [siteName, setSiteName] = useState("");
  const [siteCode, setSiteCode] = useState("");
  const [editingSite, setEditingSite] = useState<Site | null>(null);
  const [tipperRegistration, setTipperRegistration] = useState("");
  const [tipperName, setTipperName] = useState("");
  const [editingTipper, setEditingTipper] = useState<Tipper | null>(null);
  const [personPhone, setPersonPhone] = useState("");
  const [personName, setPersonName] = useState("");
  const [personRole, setPersonRole] = useState<"DRIVER" | "SUPERVISOR">("DRIVER");
  const [supervisorId, setSupervisorId] = useState("");
  const [siteId, setSiteId] = useState("");
  const [driverId, setDriverId] = useState("");
  const [tipperId, setTipperId] = useState("");
  const [assignmentSiteId, setAssignmentSiteId] = useState("");
  const [assignmentSupervisorId, setAssignmentSupervisorId] = useState("");
  const [startsAt, setStartsAt] = useState(() => new Date().toISOString().slice(0, 16));

  const run = async (action: () => Promise<void>) => {
    props.setError("");
    try {
      await action();
      await props.reload();
    } catch (caught) {
      props.setError(caught instanceof Error ? caught.message : "The request failed.");
    }
  };
  const createSite = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); await run(async () => { await request<Site>("/api/v1/admin/sites", { method: "POST", body: JSON.stringify({ name: siteName, code: siteCode || null }) }, props.accessToken); setSiteName(""); setSiteCode(""); }); };
  const saveSite = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); if (!editingSite) return; await run(async () => { await request<Site>(`/api/v1/admin/sites/${editingSite.id}`, { method: "PATCH", body: JSON.stringify({ name: editingSite.name, code: editingSite.code, status: editingSite.status }) }, props.accessToken); setEditingSite(null); }); };
  const createTipper = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); await run(async () => { await request<Tipper>("/api/v1/admin/tippers", { method: "POST", body: JSON.stringify({ registration_number: tipperRegistration, short_name: tipperName || null }) }, props.accessToken); setTipperRegistration(""); setTipperName(""); }); };
  const saveTipper = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); if (!editingTipper) return; await run(async () => { await request<Tipper>(`/api/v1/admin/tippers/${editingTipper.id}`, { method: "PATCH", body: JSON.stringify({ registration_number: editingTipper.registration_number, short_name: editingTipper.short_name, status: editingTipper.status }) }, props.accessToken); setEditingTipper(null); }); };
  const createPerson = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); await run(async () => { await request<Person>("/api/v1/admin/people", { method: "POST", body: JSON.stringify({ phone: personPhone, display_name: personName, role: personRole }) }, props.accessToken); setPersonPhone(""); setPersonName(""); }); };
  const togglePerson = async (person: Person) => run(async () => { await request<Person>(`/api/v1/admin/people/${person.membership_id}`, { method: "PATCH", body: JSON.stringify({ status: person.status === "ACTIVE" ? "INACTIVE" : "ACTIVE" }) }, props.accessToken); });
  const grantAccess = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); await run(async () => { await request<SupervisorAccess>("/api/v1/admin/supervisor-site-access", { method: "POST", body: JSON.stringify({ supervisor_membership_id: supervisorId, site_id: siteId }) }, props.accessToken); }); };
  const createAssignment = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); await run(async () => { await request<Assignment>("/api/v1/admin/assignments", { method: "POST", body: JSON.stringify({ driver_membership_id: driverId, supervisor_membership_id: assignmentSupervisorId, tipper_id: tipperId, site_id: assignmentSiteId, starts_at: new Date(startsAt).toISOString() }) }, props.accessToken); }); };
  const closeAssignment = async (assignment: Assignment) => run(async () => { await request<Assignment>(`/api/v1/admin/assignments/${assignment.id}/close`, { method: "POST", body: JSON.stringify({ ends_at: new Date().toISOString() }) }, props.accessToken); });
  const activeSites = props.sites.filter((site) => site.status === "ACTIVE");
  const activeTippers = props.tippers.filter((tipper) => tipper.status === "ACTIVE");
  const drivers = props.people.filter((person) => person.role === "DRIVER" && person.status === "ACTIVE");
  const supervisors = props.people.filter((person) => person.role === "SUPERVISOR" && person.status === "ACTIVE");

  return (
    <main className="admin-shell">
      <header className="topbar"><div><p className="eyebrow">Fleet Manager · Owner/Admin</p><h1>Administration</h1></div><button className="secondary" onClick={props.onLogout} type="button">Log out</button></header>
      <div className="admin-layout">
        <nav className="sidebar" aria-label="Administration sections">{(["operations", "overview", "sites", "tippers", "people", "assignments", "access"] as Tab[]).map((item) => <button className={props.tab === item ? "nav-item selected" : "nav-item"} key={item} onClick={() => props.setTab(item)} type="button">{item === "access" ? "Supervisor access" : item === "operations" ? "Operations" : item[0].toUpperCase() + item.slice(1)}</button>)}</nav>
        <section className="content">
          {props.error && <div className="notice error">{props.error}</div>}
          {props.tab === "operations" && <OwnerOperations accessToken={props.accessToken} setError={props.setError} />}
          {props.tab === "overview" && <><h2>Company overview</h2><p className="muted">Manage the owned-tipper foundation. Operational reporting is not part of this administration shell.</p><div className="metric-grid"><Metric label="Sites" value={props.sites.length} /><Metric label="Owned tippers" value={props.tippers.length} /><Metric label="People" value={props.people.length} /><Metric label="Assignments" value={props.assignments.length} /></div></>}
          {props.tab === "sites" && <><h2>Sites</h2><form className="inline-form" onSubmit={createSite}><input aria-label="Site name" placeholder="Site name" value={siteName} onChange={(event) => setSiteName(event.target.value)} required /><input aria-label="Site code" placeholder="Code" value={siteCode} onChange={(event) => setSiteCode(event.target.value)} /><button type="submit">Add site</button></form><div className="table-card">{props.sites.map((site) => editingSite?.id === site.id ? <form className="table-row" key={site.id} onSubmit={saveSite}><input value={editingSite.name} onChange={(event) => setEditingSite({ ...editingSite, name: event.target.value })} /><input value={editingSite.code ?? ""} onChange={(event) => setEditingSite({ ...editingSite, code: event.target.value || null })} /><select value={editingSite.status} onChange={(event) => setEditingSite({ ...editingSite, status: event.target.value as Status })}><option value="ACTIVE">Active</option><option value="INACTIVE">Inactive</option></select><button type="submit">Save</button><button className="secondary" type="button" onClick={() => setEditingSite(null)}>Cancel</button></form> : <div className="table-row" key={site.id}><strong>{site.name}</strong><span>{site.code ?? "No code"}</span><Badge status={site.status} /><button className="secondary" type="button" onClick={() => setEditingSite(site)}>Edit</button></div>)}</div></>}
          {props.tab === "tippers" && <><h2>Owned tippers</h2><form className="inline-form" onSubmit={createTipper}><input aria-label="Registration" placeholder="Registration" value={tipperRegistration} onChange={(event) => setTipperRegistration(event.target.value)} required /><input aria-label="Tipper name" placeholder="Short name" value={tipperName} onChange={(event) => setTipperName(event.target.value)} /><button type="submit">Add tipper</button></form><div className="table-card">{props.tippers.map((tipper) => editingTipper?.id === tipper.id ? <form className="table-row" key={tipper.id} onSubmit={saveTipper}><input value={editingTipper.registration_number} onChange={(event) => setEditingTipper({ ...editingTipper, registration_number: event.target.value })} /><input value={editingTipper.short_name ?? ""} onChange={(event) => setEditingTipper({ ...editingTipper, short_name: event.target.value || null })} /><select value={editingTipper.status} onChange={(event) => setEditingTipper({ ...editingTipper, status: event.target.value as Status })}><option value="ACTIVE">Active</option><option value="INACTIVE">Inactive</option></select><button type="submit">Save</button><button className="secondary" type="button" onClick={() => setEditingTipper(null)}>Cancel</button></form> : <div className="table-row" key={tipper.id}><strong>{tipper.registration_number}</strong><span>{tipper.short_name ?? "Unnamed"}</span><Badge status={tipper.status} /><button className="secondary" type="button" onClick={() => setEditingTipper(tipper)}>Edit</button></div>)}</div></>}
          {props.tab === "people" && <><h2>People</h2><form className="inline-form" onSubmit={createPerson}><input aria-label="Person phone" placeholder="Phone in E.164" value={personPhone} onChange={(event) => setPersonPhone(event.target.value)} required /><input aria-label="Display name" placeholder="Display name" value={personName} onChange={(event) => setPersonName(event.target.value)} required /><select value={personRole} onChange={(event) => setPersonRole(event.target.value as "DRIVER" | "SUPERVISOR")}><option value="DRIVER">Driver</option><option value="SUPERVISOR">Supervisor</option></select><button type="submit">Add person</button></form><div className="table-card">{props.people.map((person) => <div className="table-row" key={person.membership_id}><strong>{person.display_name}</strong><span>{person.phone}</span><span>{person.role}</span><Badge status={person.status} /><button className="secondary" type="button" onClick={() => togglePerson(person)}>{person.status === "ACTIVE" ? "Deactivate" : "Activate"}</button></div>)}</div></>}
          {props.tab === "assignments" && <><h2>Assignments</h2><form className="form-grid" onSubmit={createAssignment}><Select label="Driver" value={driverId} onChange={setDriverId} options={drivers.map((person) => [person.membership_id, person.display_name])} /><Select label="Supervisor" value={assignmentSupervisorId} onChange={setAssignmentSupervisorId} options={supervisors.map((person) => [person.membership_id, person.display_name])} /><Select label="Tipper" value={tipperId} onChange={setTipperId} options={activeTippers.map((tipper) => [tipper.id, tipper.registration_number])} /><Select label="Site" value={assignmentSiteId} onChange={setAssignmentSiteId} options={activeSites.map((site) => [site.id, site.name])} /><label>Starts at<input type="datetime-local" value={startsAt} onChange={(event) => setStartsAt(event.target.value)} required /></label><button type="submit">Create assignment</button></form><div className="table-card">{props.assignments.map((assignment) => <div className="table-row" key={assignment.id}><strong>{assignment.driver_name} · {assignment.registration_number}</strong><span>{assignment.site_name}</span><span>{assignment.supervisor_name}</span><span>{assignment.ends_at ? "Closed" : "Active"}</span>{!assignment.ends_at && <button className="secondary" type="button" onClick={() => closeAssignment(assignment)}>Close</button>}</div>)}</div></>}
          {props.tab === "access" && <><h2>Supervisor site access</h2><form className="inline-form" onSubmit={grantAccess}><Select label="Supervisor" value={supervisorId} onChange={setSupervisorId} options={supervisors.map((person) => [person.membership_id, person.display_name])} /><Select label="Site" value={siteId} onChange={setSiteId} options={activeSites.map((site) => [site.id, site.name])} /><button type="submit">Grant access</button></form><div className="table-card">{props.access.map((item) => <div className="table-row" key={item.id}><strong>{item.supervisor_name}</strong><span>{item.site_name}</span><button className="secondary" type="button" onClick={() => run(async () => { await request<void>(`/api/v1/admin/supervisor-site-access/${item.id}`, { method: "DELETE" }, props.accessToken); })}>Revoke</button></div>)}</div></>}
        </section>
      </div>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div>; }
function Badge({ status }: { status: Status }) { return <span className={status === "ACTIVE" ? "badge active" : "badge"}>{status}</span>; }
function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: string[][] }) { return <label>{label}<select value={value} onChange={(event) => onChange(event.target.value)} required><option value="">Choose…</option>{options.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>; }
