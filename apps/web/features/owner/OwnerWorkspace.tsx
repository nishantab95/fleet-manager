"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/AuthProvider";
import type { OwnerAsset, OwnerPerson, OwnerSite } from "../../lib/types";
import { WorkspaceHeader } from "../shared/Ui";
import { OwnerOperations } from "./OwnerOperations";
import { AssignmentsPanel, DeploymentsPanel, FleetOverview, FleetPanel, PeoplePanel, SitesPanel } from "./OwnerManagement";
import { ReportTemplates } from "./ReportTemplates";
import { pcRoleLabEnabled } from "../../lib/auth/config";

type Tab = "operations" | "fleet" | "people" | "sites" | "deployments" | "assignments" | "templates";

export function OwnerWorkspace() {
  const { session, request, logout } = useAuth();
  const [tab, setTab] = useState<Tab>("operations");
  const [error, setError] = useState("");
  const [assets, setAssets] = useState<OwnerAsset[]>([]);
  const [people, setPeople] = useState<OwnerPerson[]>([]);
  const [sites, setSites] = useState<OwnerSite[]>([]);

  const reload = useCallback(async () => {
    setError("");
    try {
      const [nextAssets, nextPeople, nextSites] = await Promise.all([
        request<OwnerAsset[]>("/api/v1/owner/assets"),
        request<OwnerPerson[]>("/api/v1/owner/people"),
        request<OwnerSite[]>("/api/v1/owner/sites"),
      ]);
      setAssets(nextAssets); setPeople(nextPeople); setSites(nextSites);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load Owner management data.");
    }
  }, [request]);

  useEffect(() => { void Promise.resolve().then(reload); }, [reload]);

  const labels: Record<Tab, string> = {
    operations: "Operations", fleet: "Fleet", people: "People", sites: "Sites",
    deployments: "Deployments", assignments: "Assignments", templates: "Report templates",
  };

  return <main className="admin-shell">
    <WorkspaceHeader activeRole="OWNER" eyebrow="Owner/Admin" qaNavigation={pcRoleLabEnabled} title="Fleet command centre" onLogout={() => void logout()} />
    {pcRoleLabEnabled && <nav className="owner-qa-links" aria-label="Owner QA sections"><a href="#owner-operations">Operations</a><a href="#owner-reports">Reports</a><a href="#owner-exceptions">Exceptions</a><a href="#owner-closure">Closure</a></nav>}
    <div className="admin-layout">
      <nav className="sidebar" aria-label="Owner sections">{(Object.keys(labels) as Tab[]).map((item) => <button className={tab === item ? "nav-item selected" : "nav-item"} key={item} onClick={() => setTab(item)} type="button">{labels[item]}</button>)}</nav>
      <section className="content">
        {error && <div className="notice error" role="alert">{error}</div>}
        {tab === "operations" && <><FleetOverview assets={assets} /><OwnerOperations accessToken={session?.access_token ?? ""} apiRequest={request} setError={setError} /></>}
        {tab === "fleet" && <FleetPanel assets={assets} apiRequest={request} reload={reload} setError={setError} />}
        {tab === "people" && <PeoplePanel people={people} apiRequest={request} reload={reload} setError={setError} />}
        {tab === "sites" && <SitesPanel sites={sites} people={people} apiRequest={request} reload={reload} setError={setError} />}
        {tab === "deployments" && <DeploymentsPanel assets={assets} sites={sites} apiRequest={request} reload={reload} setError={setError} />}
        {tab === "assignments" && <AssignmentsPanel assets={assets} apiRequest={request} reload={reload} setError={setError} />}
        {tab === "templates" && <ReportTemplates apiRequest={request} setError={setError} />}
      </section>
    </div>
  </main>;
}
