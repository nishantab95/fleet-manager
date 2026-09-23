"use client";

import type { ReactNode } from "react";

export function Metric({ label, value }: { label: string; value: number | string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}

export function Badge({ status }: { status: "ACTIVE" | "INACTIVE" }) {
  return <span className={status === "ACTIVE" ? "badge active" : "badge"}>{status}</span>;
}

export function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: string[][] }) {
  return <label>{label}<select value={value} onChange={(event) => onChange(event.target.value)} required><option value="">Choose…</option>{options.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>;
}

export function WorkspaceHeader({ eyebrow, title, onLogout }: { eyebrow: string; title: string; onLogout: () => void }) {
  return <header className="topbar"><div><p className="eyebrow">Fleet Manager · {eyebrow}</p><h1>{title}</h1></div><button className="secondary" onClick={onLogout} type="button">Log out</button></header>;
}

export function QaNotice({ children }: { children: ReactNode }) {
  return <div className="notice" role="note">{children}</div>;
}
