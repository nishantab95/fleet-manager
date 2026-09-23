"use client";

import { useEffect, useState } from "react";
import { API_BASE } from "../../lib/api/client";

type CheckState = "checking" | "ready" | "not-ready" | "launcher";

const roleCards = [
  { label: "DRIVER", description: "Enter operational events", href: "/driver-test" },
  { label: "SUPERVISOR", description: "Review and verify events", href: "/supervisor" },
  { label: "OWNER", description: "Dashboard, reports and administration", href: "/owner" },
] as const;

export function TestLabHome() {
  const [apiStatus, setApiStatus] = useState<CheckState>("checking");
  const [databaseStatus, setDatabaseStatus] = useState<CheckState>("checking");
  const [freshMessage, setFreshMessage] = useState("");

  useEffect(() => {
    let active = true;
    async function checkLocalServices() {
      try {
        const healthResponse = await fetch(`${API_BASE}/health`, { cache: "no-store" });
        const health = await healthResponse.json().catch(() => null) as { service?: string } | null;
        if (active) setApiStatus(healthResponse.ok && health?.service === "fleet-manager-api" ? "ready" : "not-ready");
      } catch {
        if (active) setApiStatus("not-ready");
      }

      try {
        const readyResponse = await fetch(`${API_BASE}/ready`, { cache: "no-store" });
        const readiness = await readyResponse.json().catch(() => null) as { database?: string } | null;
        if (active) setDatabaseStatus(readyResponse.ok && readiness?.database === "available" ? "ready" : "not-ready");
      } catch {
        if (active) setDatabaseStatus("not-ready");
      }
    }
    void checkLocalServices();
    return () => { active = false; };
  }, []);

  return <main className="lab-shell">
    <section className="lab-panel" aria-labelledby="lab-title">
      <header className="lab-header">
        <div>
          <p className="eyebrow">FLEET MANAGER</p>
          <h1 id="lab-title">PC TEST LAB</h1>
          <p className="lab-warning">INTERNAL / QA ONLY</p>
        </div>
        <div className="lab-context" aria-label="Pilot context">
          <strong>Pilot Construction</strong>
          <span>Pilot Site</span>
          <span>Tipper 12</span>
        </div>
      </header>

      <div className="lab-status" aria-label="System status">
        <StatusItem label="API" value={apiStatus} />
        <StatusItem label="Database" value={databaseStatus} />
        <StatusItem label="Object Store" value="launcher" detail="Use python launch.py --status for MinIO readiness" />
      </div>

      <section aria-labelledby="role-heading">
        <div className="lab-section-heading">
          <div>
            <p className="eyebrow">Choose a workspace</p>
            <h2 id="role-heading">Role workspaces</h2>
          </div>
          <p className="muted">Navigation only. Each workspace still performs its real role authentication and authorization.</p>
        </div>
        <div className="lab-role-grid">
          {roleCards.map((card) => <a className="lab-role-card" href={card.href} key={card.href} rel="noreferrer" target={`fleet-${card.label.toLowerCase()}-role`}>
            <strong>{card.label}</strong>
            <span>{card.description}</span>
            <small>Open authenticated workspace →</small>
          </a>)}
        </div>
      </section>

      <div className="lab-actions">
        <button onClick={() => setFreshMessage("Run python launch.py --fresh and type RESET PILOT. The browser never performs the reset.")} type="button">START FRESH TEST</button>
        <a className="secondary lab-action-link" href="#system-status">SYSTEM STATUS</a>
      </div>
      {freshMessage && <div className="notice" role="status">{freshMessage}</div>}

      <p className="lab-auth-note">Role cards open workspaces; they do not impersonate a role or grant access. Use the TEST LAB link in each QA workspace to return here.</p>
    </section>
  </main>;
}

function StatusItem({ label, value, detail }: { label: string; value: CheckState; detail?: string }) {
  const text = value === "not-ready" ? "NOT READY" : value.toUpperCase();
  return <div className="lab-status-item" id={label === "API" ? "system-status" : undefined}>
    <span>{label}</span>
    <strong data-state={value}>{text}</strong>
    {detail && <small>{detail}</small>}
  </div>;
}
