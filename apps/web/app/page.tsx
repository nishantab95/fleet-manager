"use client";

import { useState } from "react";
import type { FormEvent } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type MembershipRole = "OWNER_ADMIN" | "SUPERVISOR" | "DRIVER";
type Status = "ACTIVE" | "INACTIVE";
type Tab = "overview" | "sites" | "tippers" | "people" | "assignments" | "access";
type Tokens = { access_token: string; refresh_token: string; expires_in: number; role: MembershipRole };
type Membership = { membership_id: string; company_id: string; company_name: string; role: MembershipRole };
type Site = { id: string; name: string; code: string | null; status: Status };
type Tipper = { id: string; registration_number: string; short_name: string | null; status: Status };
type Person = { user_id: string; membership_id: string; phone: string; display_name: string; role: MembershipRole; status: Status; user_status: string };
type SupervisorAccess = { id: string; supervisor_membership_id: string; supervisor_name: string; site_id: string; site_name: string };
type Assignment = { id: string; driver_membership_id: string; driver_name: string; supervisor_membership_id: string; supervisor_name: string; tipper_id: string; registration_number: string; site_id: string; site_name: string; starts_at: string; ends_at: string | null };

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
  const [phase, setPhase] = useState<"phone" | "otp" | "membership" | "admin" | "denied">("phone");
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
    setPhase("phone");
    setError("");
  }

  if (phase !== "admin" || !tokens) {
    return (
      <main className="auth-shell">
        <section className="auth-card">
          <p className="eyebrow">Fleet Manager · Phase 3</p>
          <h1>Owner administration</h1>
          <p className="summary">Sign in with your phone, choose an active company membership, and manage the owned tipper fleet. Authentication state stays in memory and is cleared on reload or logout.</p>
          {phase === "phone" && <form className="stack" onSubmit={submitPhone}><label>Phone number<input value={phone} onChange={(event) => setPhone(event.target.value)} required /></label><button disabled={busy} type="submit">{busy ? "Requesting…" : "Send OTP"}</button></form>}
          {phase === "otp" && <form className="stack" onSubmit={submitOtp}><label>One-time code<input inputMode="numeric" maxLength={6} pattern="[0-9]{6}" value={otp} onChange={(event) => setOtp(event.target.value)} required /></label><button disabled={busy} type="submit">{busy ? "Checking…" : "Verify and continue"}</button><button className="secondary" type="button" onClick={() => setPhase("phone")}>Use another phone</button></form>}
          {phase === "membership" && <div className="stack"><h2>Choose company access</h2>{memberships.map((membership) => <button className="choice" disabled={busy} key={membership.membership_id} onClick={() => selectMembership(membership.membership_id)} type="button"><span>{membership.company_name}</span><small>{membership.role}</small></button>)}<button className="secondary" type="button" onClick={logout}>Cancel</button></div>}
          {phase === "denied" && <div className="notice error">This membership is not permitted to use owner administration.</div>}
          {error && <div className="notice error">{error}</div>}
        </section>
      </main>
    );
  }

  return <AdminShell accessToken={tokens.access_token} assignments={assignments} error={error} people={people} sites={sites} tab={tab} tippers={tippers} access={access} setError={setError} setTab={setTab} onLogout={logout} reload={() => loadAdminData(tokens.access_token)} />;
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
        <nav className="sidebar" aria-label="Administration sections">{(["overview", "sites", "tippers", "people", "assignments", "access"] as Tab[]).map((item) => <button className={props.tab === item ? "nav-item selected" : "nav-item"} key={item} onClick={() => props.setTab(item)} type="button">{item === "access" ? "Supervisor access" : item[0].toUpperCase() + item.slice(1)}</button>)}</nav>
        <section className="content">
          {props.error && <div className="notice error">{props.error}</div>}
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

function Metric({ label, value }: { label: string; value: number }) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div>; }
function Badge({ status }: { status: Status }) { return <span className={status === "ACTIVE" ? "badge active" : "badge"}>{status}</span>; }
function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: string[][] }) { return <label>{label}<select value={value} onChange={(event) => onChange(event.target.value)} required><option value="">Choose…</option>{options.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>; }
