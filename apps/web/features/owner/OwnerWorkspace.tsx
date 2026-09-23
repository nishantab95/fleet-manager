"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/AuthProvider";
import type { Assignment, Person, Site, SupervisorAccess, Tipper } from "../../lib/types";
import { Badge, Select, WorkspaceHeader } from "../shared/Ui";
import { OwnerOperations } from "./OwnerOperations";
import { pcRoleLabEnabled } from "../../lib/auth/config";

type Tab = "operations" | "overview" | "sites" | "tippers" | "people" | "assignments" | "access";

export function OwnerWorkspace() {
  const { session, request, logout } = useAuth();
  const [tab, setTab] = useState<Tab>("operations");
  const [error, setError] = useState("");
  const [sites, setSites] = useState<Site[]>([]);
  const [tippers, setTippers] = useState<Tipper[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [access, setAccess] = useState<SupervisorAccess[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const accessToken = session?.access_token ?? "";

  const loadAdminData = useCallback(async () => {
    try {
      const [nextSites, nextTippers, nextPeople, nextAccess, nextAssignments] = await Promise.all([
        request<Site[]>("/api/v1/admin/sites"), request<Tipper[]>("/api/v1/admin/tippers"), request<Person[]>("/api/v1/admin/people"),
        request<SupervisorAccess[]>("/api/v1/admin/supervisor-site-access"), request<Assignment[]>("/api/v1/admin/assignments"),
      ]);
      setSites(nextSites); setTippers(nextTippers); setPeople(nextPeople); setAccess(nextAccess); setAssignments(nextAssignments);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not load owner administration."); }
  }, [request]);

  // The workspace is loaded from the same authenticated APIs as the old shell.
  useEffect(() => { void Promise.resolve().then(() => loadAdminData()); }, [loadAdminData]);

  const run = async (action: () => Promise<void>) => {
    setError("");
    try { await action(); await loadAdminData(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "The request failed."); }
  };
  const activeSites = sites.filter((site) => site.status === "ACTIVE");
  const activeTippers = tippers.filter((tipper) => tipper.status === "ACTIVE");
  const drivers = people.filter((person) => person.role === "DRIVER" && person.status === "ACTIVE");
  const supervisors = people.filter((person) => person.role === "SUPERVISOR" && person.status === "ACTIVE");

  return <main className="admin-shell">
    <WorkspaceHeader activeRole="OWNER" eyebrow="Owner/Admin" qaNavigation={pcRoleLabEnabled} title="Administration" onLogout={() => void logout()} />
    {pcRoleLabEnabled && <nav className="owner-qa-links" aria-label="Owner QA sections"><a href="#owner-operations">Operations</a><a href="#owner-reports">Reports</a><a href="#owner-exceptions">Exceptions</a><a href="#owner-closure">Closure</a><button className="secondary" onClick={() => setTab("overview")} type="button">Administration</button></nav>}
    <div className="admin-layout">
      <nav className="sidebar" aria-label="Administration sections">{(["operations", "overview", "sites", "tippers", "people", "assignments", "access"] as Tab[]).map((item) => <button className={tab === item ? "nav-item selected" : "nav-item"} key={item} onClick={() => setTab(item)} type="button">{item === "access" ? "Supervisor access" : item === "operations" ? "Operations" : item[0].toUpperCase() + item.slice(1)}</button>)}</nav>
      <section className="content">
        {error && <div className="notice error">{error}</div>}
        {tab === "operations" && <OwnerOperations accessToken={accessToken} apiRequest={request} setError={setError} />}
        {tab === "overview" && <><h2>Company overview</h2><p className="muted">Owner/Admin PC workspace for the complete owned-tipper workflow.</p><div className="metric-grid"><div className="metric"><span>Sites</span><strong>{sites.length}</strong></div><div className="metric"><span>Owned tippers</span><strong>{tippers.length}</strong></div><div className="metric"><span>People</span><strong>{people.length}</strong></div><div className="metric"><span>Assignments</span><strong>{assignments.length}</strong></div></div></>}
        {tab === "sites" && <SitesPanel sites={sites} run={run} request={request} />}
        {tab === "tippers" && <TippersPanel tippers={tippers} run={run} request={request} />}
        {tab === "people" && <PeoplePanel people={people} run={run} request={request} />}
        {tab === "assignments" && <AssignmentsPanel assignments={assignments} drivers={drivers} supervisors={supervisors} tippers={activeTippers} sites={activeSites} run={run} request={request} />}
        {tab === "access" && <AccessPanel access={access} supervisors={supervisors} sites={activeSites} run={run} request={request} />}
      </section>
    </div>
  </main>;
}

type PanelProps = { run: (action: () => Promise<void>) => Promise<void>; request: <T>(path: string, options?: RequestInit) => Promise<T> };

function SitesPanel({ sites, run, request }: PanelProps & { sites: Site[] }) {
  const [name, setName] = useState(""); const [code, setCode] = useState(""); const [editing, setEditing] = useState<Site | null>(null);
  return <><h2>Sites</h2><form className="inline-form" onSubmit={(event) => { event.preventDefault(); void run(async () => { await request("/api/v1/admin/sites", { method: "POST", body: JSON.stringify({ name, code: code || null }) }); setName(""); setCode(""); }); }}><input aria-label="Site name" placeholder="Site name" value={name} onChange={(event) => setName(event.target.value)} required /><input aria-label="Site code" placeholder="Code" value={code} onChange={(event) => setCode(event.target.value)} /><button type="submit">Add site</button></form><div className="table-card">{sites.map((site) => editing?.id === site.id ? <form className="table-row" key={site.id} onSubmit={(event) => { event.preventDefault(); void run(async () => { await request(`/api/v1/admin/sites/${site.id}`, { method: "PATCH", body: JSON.stringify({ name: editing.name, code: editing.code, status: editing.status }) }); setEditing(null); }); }}><input value={editing.name} onChange={(event) => setEditing({ ...editing, name: event.target.value })} /><input value={editing.code ?? ""} onChange={(event) => setEditing({ ...editing, code: event.target.value || null })} /><select value={editing.status} onChange={(event) => setEditing({ ...editing, status: event.target.value as Site["status"] })}><option value="ACTIVE">Active</option><option value="INACTIVE">Inactive</option></select><button type="submit">Save</button><button className="secondary" type="button" onClick={() => setEditing(null)}>Cancel</button></form> : <div className="table-row" key={site.id}><strong>{site.name}</strong><span>{site.code ?? "No code"}</span><Badge status={site.status} /><button className="secondary" type="button" onClick={() => setEditing(site)}>Edit</button></div>)}</div></>;
}

function TippersPanel({ tippers, run, request }: PanelProps & { tippers: Tipper[] }) {
  const [registration, setRegistration] = useState(""); const [shortName, setShortName] = useState(""); const [editing, setEditing] = useState<Tipper | null>(null);
  return <><h2>Owned tippers</h2><form className="inline-form" onSubmit={(event) => { event.preventDefault(); void run(async () => { await request("/api/v1/admin/tippers", { method: "POST", body: JSON.stringify({ registration_number: registration, short_name: shortName || null }) }); setRegistration(""); setShortName(""); }); }}><input aria-label="Registration" placeholder="Registration" value={registration} onChange={(event) => setRegistration(event.target.value)} required /><input aria-label="Tipper name" placeholder="Short name" value={shortName} onChange={(event) => setShortName(event.target.value)} /><button type="submit">Add tipper</button></form><div className="table-card">{tippers.map((tipper) => editing?.id === tipper.id ? <form className="table-row" key={tipper.id} onSubmit={(event) => { event.preventDefault(); void run(async () => { await request(`/api/v1/admin/tippers/${tipper.id}`, { method: "PATCH", body: JSON.stringify({ registration_number: editing.registration_number, short_name: editing.short_name, status: editing.status }) }); setEditing(null); }); }}><input value={editing.registration_number} onChange={(event) => setEditing({ ...editing, registration_number: event.target.value })} /><input value={editing.short_name ?? ""} onChange={(event) => setEditing({ ...editing, short_name: event.target.value || null })} /><select value={editing.status} onChange={(event) => setEditing({ ...editing, status: event.target.value as Tipper["status"] })}><option value="ACTIVE">Active</option><option value="INACTIVE">Inactive</option></select><button type="submit">Save</button><button className="secondary" type="button" onClick={() => setEditing(null)}>Cancel</button></form> : <div className="table-row" key={tipper.id}><strong>{tipper.registration_number}</strong><span>{tipper.short_name ?? "Unnamed"}</span><Badge status={tipper.status} /><button className="secondary" type="button" onClick={() => setEditing(tipper)}>Edit</button></div>)}</div></>;
}

function PeoplePanel({ people, run, request }: PanelProps & { people: Person[] }) {
  const [phone, setPhone] = useState(""); const [name, setName] = useState(""); const [role, setRole] = useState<"DRIVER" | "SUPERVISOR">("DRIVER");
  return <><h2>People</h2><form className="inline-form" onSubmit={(event) => { event.preventDefault(); void run(async () => { await request("/api/v1/admin/people", { method: "POST", body: JSON.stringify({ phone, display_name: name, role }) }); setPhone(""); setName(""); }); }}><input aria-label="Person phone" placeholder="Phone in E.164" value={phone} onChange={(event) => setPhone(event.target.value)} required /><input aria-label="Display name" placeholder="Display name" value={name} onChange={(event) => setName(event.target.value)} required /><select value={role} onChange={(event) => setRole(event.target.value as "DRIVER" | "SUPERVISOR")}><option value="DRIVER">Driver</option><option value="SUPERVISOR">Supervisor</option></select><button type="submit">Add person</button></form><div className="table-card">{people.map((person) => <div className="table-row" key={person.membership_id}><strong>{person.display_name}</strong><span>{person.phone}</span><span>{person.role}</span><Badge status={person.status} /><button className="secondary" type="button" onClick={() => void run(async () => { await request(`/api/v1/admin/people/${person.membership_id}`, { method: "PATCH", body: JSON.stringify({ status: person.status === "ACTIVE" ? "INACTIVE" : "ACTIVE" }) }); })}>{person.status === "ACTIVE" ? "Deactivate" : "Activate"}</button></div>)}</div></>;
}

function AssignmentsPanel({ assignments, drivers, supervisors, tippers, sites, run, request }: PanelProps & { assignments: Assignment[]; drivers: Person[]; supervisors: Person[]; tippers: Tipper[]; sites: Site[] }) {
  const [driverId, setDriverId] = useState(""); const [supervisorId, setSupervisorId] = useState(""); const [tipperId, setTipperId] = useState(""); const [siteId, setSiteId] = useState(""); const [startsAt, setStartsAt] = useState(() => new Date().toISOString().slice(0, 16));
  return <><h2>Assignments</h2><form className="form-grid" onSubmit={(event) => { event.preventDefault(); void run(async () => { await request("/api/v1/admin/assignments", { method: "POST", body: JSON.stringify({ driver_membership_id: driverId, supervisor_membership_id: supervisorId, tipper_id: tipperId, site_id: siteId, starts_at: new Date(startsAt).toISOString() }) }); }); }}><Select label="Driver" value={driverId} onChange={setDriverId} options={drivers.map((person) => [person.membership_id, person.display_name])} /><Select label="Supervisor" value={supervisorId} onChange={setSupervisorId} options={supervisors.map((person) => [person.membership_id, person.display_name])} /><Select label="Tipper" value={tipperId} onChange={setTipperId} options={tippers.map((tipper) => [tipper.id, tipper.registration_number])} /><Select label="Site" value={siteId} onChange={setSiteId} options={sites.map((site) => [site.id, site.name])} /><label>Starts at<input type="datetime-local" value={startsAt} onChange={(event) => setStartsAt(event.target.value)} required /></label><button type="submit">Create assignment</button></form><div className="table-card">{assignments.map((assignment) => <div className="table-row" key={assignment.id}><strong>{assignment.driver_name} · {assignment.registration_number}</strong><span>{assignment.site_name}</span><span>{assignment.supervisor_name}</span><span>{assignment.ends_at ? "Closed" : "Active"}</span>{!assignment.ends_at && <button className="secondary" type="button" onClick={() => void run(async () => { await request(`/api/v1/admin/assignments/${assignment.id}/close`, { method: "POST", body: JSON.stringify({ ends_at: new Date().toISOString() }) }); })}>Close</button>}</div>)}</div></>;
}

function AccessPanel({ access, supervisors, sites, run, request }: PanelProps & { access: SupervisorAccess[]; supervisors: Person[]; sites: Site[] }) {
  const [supervisorId, setSupervisorId] = useState(""); const [siteId, setSiteId] = useState("");
  return <><h2>Supervisor site access</h2><form className="inline-form" onSubmit={(event) => { event.preventDefault(); void run(async () => { await request("/api/v1/admin/supervisor-site-access", { method: "POST", body: JSON.stringify({ supervisor_membership_id: supervisorId, site_id: siteId }) }); }); }}><Select label="Supervisor" value={supervisorId} onChange={setSupervisorId} options={supervisors.map((person) => [person.membership_id, person.display_name])} /><Select label="Site" value={siteId} onChange={setSiteId} options={sites.map((site) => [site.id, site.name])} /><button type="submit">Grant access</button></form><div className="table-card">{access.map((item) => <div className="table-row" key={item.id}><strong>{item.supervisor_name}</strong><span>{item.site_name}</span><button className="secondary" type="button" onClick={() => void run(async () => { await request(`/api/v1/admin/supervisor-site-access/${item.id}`, { method: "DELETE" }); })}>Revoke</button></div>)}</div></>;
}
