"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { pcRoleLabEnabled } from "../../lib/auth/config";
import type { OwnerAsset, OwnerPerson, OwnerSite } from "../../lib/types";
import { useAuth } from "../auth/AuthProvider";
import { FleetAmbientScene } from "./FleetAmbientScene";
import { AssignmentsPanel, DeploymentsPanel, FleetOverview, FleetPanel, PeoplePanel, SitesPanel } from "./OwnerManagement";
import { OwnerOperations } from "./OwnerOperations";
import { ReportTemplates } from "./ReportTemplates";

type Tab = "operations" | "fleet" | "deployments" | "assignments" | "people" | "sites" | "reports" | "templates";

const navigation: { label: string; items: { id: Tab; label: string }[] }[] = [
  { label: "Overview", items: [{ id: "operations", label: "Operations" }] },
  {
    label: "Fleet management",
    items: [
      { id: "fleet", label: "Fleet" },
      { id: "deployments", label: "Deployments" },
      { id: "assignments", label: "Assignments" },
    ],
  },
  {
    label: "Organization",
    items: [
      { id: "people", label: "People" },
      { id: "sites", label: "Sites" },
    ],
  },
  {
    label: "Reporting",
    items: [
      { id: "reports", label: "Reports" },
      { id: "templates", label: "Report templates" },
    ],
  },
];

function CommandMetric({ label, value, tone = "default" }: { label: string; value: number; tone?: "default" | "attention" }) {
  return <div className={`owner-command-metric owner-command-metric--${tone}`}><span>{label}</span><strong key={value}>{value}</strong></div>;
}

function WorkspaceSkeleton() {
  return <div aria-label="Loading Owner workspace" aria-live="polite" className="owner-skeleton" role="status">
    <span className="sr-only">Loading Owner workspace…</span>
    <div className="owner-skeleton__heading" />
    <div className="owner-skeleton__toolbar" />
    {[0, 1, 2, 3, 4].map((row) => <div className="owner-skeleton__row" key={row} />)}
  </div>;
}

export function OwnerWorkspace() {
  const { session, request, logout } = useAuth();
  const [tab, setTab] = useState<Tab>("operations");
  const [error, setError] = useState("");
  const [assets, setAssets] = useState<OwnerAsset[]>([]);
  const [people, setPeople] = useState<OwnerPerson[]>([]);
  const [sites, setSites] = useState<OwnerSite[]>([]);
  const [initialLoading, setInitialLoading] = useState(true);
  const [pageVisible, setPageVisible] = useState(true);

  const reload = useCallback(async () => {
    setError("");
    try {
      const [nextAssets, nextPeople, nextSites] = await Promise.all([
        request<OwnerAsset[]>("/api/v1/owner/assets"),
        request<OwnerPerson[]>("/api/v1/owner/people"),
        request<OwnerSite[]>("/api/v1/owner/sites"),
      ]);
      setAssets(nextAssets);
      setPeople(nextPeople);
      setSites(nextSites);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load Owner management data.");
    } finally {
      setInitialLoading(false);
    }
  }, [request]);

  useEffect(() => { void Promise.resolve().then(reload); }, [reload]);
  useEffect(() => {
    document.title = "Fleet command centre · Fleet Manager";
    const updateVisibility = () => setPageVisible(document.visibilityState !== "hidden");
    updateVisibility();
    document.addEventListener("visibilitychange", updateVisibility);
    return () => document.removeEventListener("visibilitychange", updateVisibility);
  }, []);

  const summary = useMemo(() => {
    const active = assets.filter((asset) => asset.status === "ACTIVE");
    return {
      active: active.length,
      onDuty: people.filter((person) => person.has_active_duty).length,
      unassigned: active.filter((asset) => !asset.has_active_assignment).length,
      undeployed: active.filter((asset) => !asset.current_deployment).length,
    };
  }, [assets, people]);

  const showTab = (nextTab: Tab) => {
    setError("");
    setTab(nextTab);
    window.scrollTo({ top: 0 });
  };

  return <main className="admin-shell owner-shell" data-page-visible={pageVisible ? "true" : "false"}>
    <header className="owner-topbar">
      <FleetAmbientScene />
      <div className="owner-topbar__identity">
        <p className="owner-topbar__eyebrow">Fleet Manager · Owner/Admin</p>
        <h1>Fleet command centre</h1>
      </div>
      <div aria-label="Current fleet summary" className="owner-command-strip" role="group">
        <CommandMetric label="Active assets" value={summary.active} />
        <CommandMetric label="On duty" value={summary.onDuty} />
        <CommandMetric label="Unassigned" tone={summary.unassigned > 0 ? "attention" : "default"} value={summary.unassigned} />
        <CommandMetric label="Undeployed" tone={summary.undeployed > 0 ? "attention" : "default"} value={summary.undeployed} />
      </div>
      <div className="owner-topbar__actions">
        {pcRoleLabEnabled && <nav aria-label="PC test lab navigation" className="owner-role-nav"><a href="/lab">Test lab</a><a href="/driver-test">Driver</a><a href="/supervisor">Supervisor</a><a aria-current="page" href="/owner">Owner</a></nav>}
        <button className="owner-logout" onClick={() => void logout()} type="button">Log out</button>
      </div>
    </header>

    <div className="owner-layout">
      <nav aria-label="Owner sections" className="owner-sidebar">
        {navigation.map((group) => <section className="owner-nav-group" key={group.label}>
          <h2>{group.label}</h2>
          {group.items.map((item) => <button aria-current={tab === item.id ? "page" : undefined} className={tab === item.id ? "owner-nav-item is-active" : "owner-nav-item"} key={item.id} onClick={() => showTab(item.id)} type="button"><span aria-hidden="true" className="owner-nav-item__marker" />{item.label}</button>)}
        </section>)}
      </nav>

      <section aria-busy={initialLoading} className="content owner-content">
        {error && <div aria-live="assertive" className="notice error owner-feedback" role="alert">{error}</div>}
        {initialLoading ? <WorkspaceSkeleton /> : <div className="owner-panel" key={tab}>
          {tab === "operations" && <>
            <FleetOverview assets={assets} />
            <div aria-label="Quick operations" className="owner-overview-shortcuts" role="group"><span>Quick operations</span><div className="owner-overview-actions"><button className="secondary" onClick={() => showTab("fleet")} type="button">Review fleet</button><button className="secondary" onClick={() => showTab("deployments")} type="button">Deploy assets</button><button onClick={() => showTab("assignments")} type="button">Assign operators</button></div></div>
          </>}
          {tab === "fleet" && <FleetPanel assets={assets} people={people} sites={sites} apiRequest={request} reload={reload} setError={setError} />}
          {tab === "people" && <PeoplePanel people={people} assets={assets} apiRequest={request} reload={reload} setError={setError} />}
          {tab === "sites" && <SitesPanel sites={sites} people={people} apiRequest={request} reload={reload} setError={setError} />}
          {tab === "deployments" && <DeploymentsPanel assets={assets} sites={sites} people={people} apiRequest={request} reload={reload} setError={setError} />}
          {tab === "assignments" && <AssignmentsPanel assets={assets} people={people} apiRequest={request} reload={reload} setError={setError} />}
          {tab === "reports" && <OwnerOperations accessToken={session?.access_token ?? ""} apiRequest={request} setError={setError} />}
          {tab === "templates" && <ReportTemplates apiRequest={request} setError={setError} />}
        </div>}
      </section>
    </div>
  </main>;
}
