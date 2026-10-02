"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { pcRoleLabEnabled } from "../../lib/auth/config";
import type { OwnerAsset, OwnerPerson, OwnerSite } from "../../lib/types";
import { useAuth } from "../auth/AuthProvider";
import { FleetAmbientScene } from "./FleetAmbientScene";
import { AssignmentsPanel, DeploymentsPanel, FleetOverview, FleetPanel, PeoplePanel, SitesPanel } from "./OwnerManagement";
import { OwnerOperations } from "./OwnerOperations";
import { ReportTemplates } from "./ReportTemplates";

type Tab = "operations" | "fleet" | "deployments" | "assignments" | "people" | "sites" | "reports" | "templates";
type NavIcon = "operations" | "fleet" | "deployments" | "assignments" | "people" | "sites" | "reports" | "templates";

const navigation: { label: string; items: { id: Tab; label: string; icon: NavIcon }[] }[] = [
  { label: "Overview", items: [{ id: "operations", label: "Operations", icon: "operations" }] },
  {
    label: "Fleet management",
    items: [
      { id: "fleet", label: "Fleet", icon: "fleet" },
      { id: "deployments", label: "Deployments", icon: "deployments" },
      { id: "assignments", label: "Assignments", icon: "assignments" },
    ],
  },
  {
    label: "Organization",
    items: [
      { id: "people", label: "People", icon: "people" },
      { id: "sites", label: "Sites", icon: "sites" },
    ],
  },
  {
    label: "Reporting",
    items: [
      { id: "reports", label: "Reports", icon: "reports" },
      { id: "templates", label: "Report templates", icon: "templates" },
    ],
  },
];

function NavGlyph({ icon }: { icon: NavIcon }) {
  const paths: Record<NavIcon, ReactNode> = {
    operations: <><path d="M4 13h6V4H4v9Zm0 7h6v-4H4v4Zm10 0h6v-9h-6v9Zm0-16v4h6V4h-6Z" /></>,
    fleet: <><path d="M3 7.5h12.5l3 4.5H21v5h-2.2a3 3 0 0 1-5.6 0H9.8a3 3 0 0 1-5.6 0H3V7.5Z" /><path d="M6 7.5 8 4h6l1.5 3.5M6.8 18a1.2 1.2 0 1 0 0-2.4A1.2 1.2 0 0 0 6.8 18Zm9.2 0a1.2 1.2 0 1 0 0-2.4A1.2 1.2 0 0 0 16 18Z" /></>,
    deployments: <><path d="M12 3v12m0 0-4-4m4 4 4-4" /><path d="M5 15v5h14v-5" /></>,
    assignments: <><path d="M9 5h10v15H5V5h4Zm0 0V3h6v2" /><path d="m8 12 2 2 5-5" /></>,
    people: <><path d="M16 20v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M18 8a3 3 0 0 1 0 6m4 6v-2a4 4 0 0 0-3-3.87" /></>,
    sites: <><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></>,
    reports: <><path d="M4 20V10m6 10V4m6 16v-7m4 7H2" /></>,
    templates: <><path d="M6 3h9l4 4v14H6V3Z" /><path d="M15 3v5h5M9 12h7m-7 4h7" /></>,
  };
  return <svg aria-hidden="true" className="owner-nav-item__icon" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" viewBox="0 0 24 24">{paths[icon]}</svg>;
}

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
  const [sidebarPinned, setSidebarPinned] = useState(false);

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
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setSidebarPinned(window.localStorage.getItem("fleet-owner-sidebar-pinned") === "true");
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  const toggleSidebarPin = () => {
    setSidebarPinned((current) => {
      const next = !current;
      window.localStorage.setItem("fleet-owner-sidebar-pinned", String(next));
      return next;
    });
  };

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

    <div className="owner-layout" data-sidebar-pinned={sidebarPinned ? "true" : "false"}>
      <nav aria-label="Owner sections" className="owner-sidebar">
        <button aria-label={sidebarPinned ? "Unpin sidebar" : "Pin sidebar"} aria-pressed={sidebarPinned} className="owner-sidebar-pin" onClick={toggleSidebarPin} type="button">
          <svg aria-hidden="true" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" viewBox="0 0 24 24"><path d="m9 4 6 0 1 6 3 3H5l3-3 1-6Zm3 9v8" /></svg>
          <span>{sidebarPinned ? "Unpin sidebar" : "Pin sidebar"}</span>
        </button>
        {navigation.map((group) => <section className="owner-nav-group" key={group.label}>
          <h2>{group.label}</h2>
          {group.items.map((item) => <button aria-current={tab === item.id ? "page" : undefined} aria-label={item.label} className={tab === item.id ? "owner-nav-item is-active" : "owner-nav-item"} data-tooltip={item.label} key={item.id} onClick={() => showTab(item.id)} title={item.label} type="button"><span aria-hidden="true" className="owner-nav-item__marker" /><NavGlyph icon={item.icon} /><span className="owner-nav-item__label">{item.label}</span></button>)}
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
