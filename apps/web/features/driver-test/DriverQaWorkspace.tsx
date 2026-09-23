"use client";

import { useEffect, useMemo, useState } from "react";
import { ApiError, uploadDriverEvidence } from "../../lib/api/client";
import type { DriverAssignment } from "../../lib/types";
import { QaNotice, WorkspaceHeader } from "../shared/Ui";
import { useAuth } from "../auth/AuthProvider";

type QaEventLog = { uuid: string; type: string; timestamp: string; status: string; verificationStatus: string };
type PrimaryAction = "TRIP_COMPLETE" | "KM_READING" | "DIESEL" | "EMERGENCY";
const emergencyCategories = ["BREAKDOWN", "ACCIDENT", "TYRE_OR_VEHICLE_PROBLEM", "CONTACT_SUPERVISOR"] as const;

function qaInstallationIdentifier() {
  if (typeof window !== "undefined") {
    const stored = window.sessionStorage.getItem("fleet-qa-installation-id");
    if (stored) return stored;
    const value = `qa-web-${crypto.randomUUID()}`;
    window.sessionStorage.setItem("fleet-qa-installation-id", value);
    return value;
  }
  return "qa-web-server-render";
}

export function DriverQaWorkspace() {
  const { session, request, refresh, logout } = useAuth();
  const installationIdentifier = useMemo(() => qaInstallationIdentifier(), []);
  const [assignment, setAssignment] = useState<DriverAssignment | null>(null);
  const [activeAction, setActiveAction] = useState<PrimaryAction | null>(null);
  const [readingType, setReadingType] = useState<"START_READING" | "END_READING">("START_READING");
  const [readingValue, setReadingValue] = useState("");
  const [dieselLitres, setDieselLitres] = useState("");
  const [emergencyCategory, setEmergencyCategory] = useState<(typeof emergencyCategories)[number]>("BREAKDOWN");
  const [description, setDescription] = useState("");
  const [evidenceFile, setEvidenceFile] = useState<File | null>(null);
  const [eventLog, setEventLog] = useState<QaEventLog[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const accessToken = session?.access_token ?? "";

  useEffect(() => {
    let active = true;
    void Promise.all([
      request<DriverAssignment | null>("/api/v1/driver/assignment/current"),
      request("/api/v1/driver/device", { method: "POST", body: JSON.stringify({ installation_identifier: installationIdentifier, platform: "WEB" }) }),
    ]).then(([nextAssignment]) => { if (active) setAssignment(nextAssignment); }).catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "Could not load the Driver QA assignment."); });
    return () => { active = false; };
  }, [installationIdentifier, request]);

  const submitEvent = async (eventType: PrimaryAction, fields: Record<string, unknown> = {}, file: File | null = null) => {
    if (!assignment || !session) return;
    const clientEventUuid = crypto.randomUUID();
    setBusy(true); setError("");
    try {
      let objectReference: string | undefined;
      if (file) {
        try {
          objectReference = (await uploadDriverEvidence(accessToken, clientEventUuid, file)).object_reference;
        } catch (caught) {
          if (!(caught instanceof ApiError) || caught.status !== 401) throw caught;
          const renewed = await refresh();
          if (!renewed) throw caught;
          objectReference = (await uploadDriverEvidence(renewed.access_token, clientEventUuid, file)).object_reference;
        }
      }
      const response = await request<{ client_event_uuid: string; status: string; verification_status: string }>("/api/v1/driver/events", { method: "POST", body: JSON.stringify({ client_event_uuid: clientEventUuid, event_type: eventType, device_created_at: new Date().toISOString(), installation_identifier: installationIdentifier, platform: "WEB", ...fields, ...(objectReference ? { object_reference: objectReference } : {}) }) });
      setEventLog((current) => [{ uuid: response.client_event_uuid, type: eventType, timestamp: new Date().toISOString(), status: response.status, verificationStatus: response.verification_status }, ...current]);
      setActiveAction(null); setReadingValue(""); setDieselLitres(""); setDescription(""); setEvidenceFile(null);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "The real Driver API request failed."); }
    finally { setBusy(false); }
  };

  const submitKm = async (event: React.FormEvent<HTMLFormElement>) => { event.preventDefault(); const value = Number(readingValue); if (!Number.isFinite(value) || value < 0) { setError("KM value must be a non-negative number."); return; } if (!evidenceFile) { setError("A local test image is required for a KM reading."); return; } await submitEvent("KM_READING", { reading_type: readingType, reading_value: value }, evidenceFile); };
  const submitDiesel = async (event: React.FormEvent<HTMLFormElement>) => { event.preventDefault(); const litres = Number(dieselLitres); if (!Number.isFinite(litres) || litres <= 0) { setError("Diesel litres must be greater than zero."); return; } if (!evidenceFile) { setError("A local test image is required for diesel."); return; } await submitEvent("DIESEL", { litres }, evidenceFile); };
  const submitEmergency = async (event: React.FormEvent<HTMLFormElement>) => { event.preventDefault(); await submitEvent("EMERGENCY", { category: emergencyCategory, ...(description.trim() ? { description: description.trim() } : {}) }); };

  return <main className="admin-shell">
    <WorkspaceHeader activeRole="DRIVER" eyebrow="DRIVER QA" qaNavigation title="QA Driver Simulator" onLogout={() => void logout()} />
    <div className="admin-layout single-column"><section className="content">
      <div className="notice error"><strong>QA DRIVER SIMULATOR</strong><br />NON-PRODUCTION WEB TEST CLIENT · INTERNAL / PILOT QA ONLY</div>
      <p className="muted">This browser client uses real authentication, the real DRIVER membership, the current assignment, PostgreSQL-backed APIs, and the real evidence pipeline. It is not the final Driver product.</p>
      {error && <div className="notice error">{error}</div>}
      <section className="table-card"><h2>Current assignment</h2>{assignment ? <div className="table-row"><strong>{assignment.tipper_short_name ?? assignment.tipper_registration_number}</strong><span>{assignment.tipper_registration_number}</span><span>Site: {assignment.site_name}</span><span>Supervisor: {assignment.supervisor_name}</span></div> : <div className="notice">Loading the current assignment…</div>}</section>
      <section className="stack"><h2>Driver operational actions</h2><div className="metric-grid qa-actions"><button disabled={!assignment || busy} onClick={() => void submitEvent("TRIP_COMPLETE")} type="button">TRIP COMPLETE</button><button disabled={!assignment || busy} onClick={() => { setError(""); setActiveAction("KM_READING"); }} type="button">KM READING</button><button disabled={!assignment || busy} onClick={() => { setError(""); setActiveAction("DIESEL"); }} type="button">DIESEL ISSUED / RECORDED</button><button className="danger-action" disabled={!assignment || busy} onClick={() => { setError(""); setActiveAction("EMERGENCY"); }} type="button">EMERGENCY</button></div></section>
      {activeAction === "KM_READING" && <form className="table-card stack" onSubmit={(event) => void submitKm(event)}><h3>KM reading</h3><label>Reading type<select value={readingType} onChange={(event) => setReadingType(event.target.value as typeof readingType)}><option value="START_READING">START_READING</option><option value="END_READING">END_READING</option></select></label><label>KM value<input type="number" min="0" step="0.01" value={readingValue} onChange={(event) => setReadingValue(event.target.value)} required /></label><label>Local test image<input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setEvidenceFile(event.target.files?.[0] ?? null)} required /></label><div className="inline-form"><button disabled={busy} type="submit">Submit KM reading</button><button className="secondary" type="button" onClick={() => setActiveAction(null)}>Cancel</button></div></form>}
      {activeAction === "DIESEL" && <form className="table-card stack" onSubmit={(event) => void submitDiesel(event)}><h3>DIESEL ISSUED / RECORDED</h3><label>Litres<input type="number" min="0.01" step="0.01" value={dieselLitres} onChange={(event) => setDieselLitres(event.target.value)} required /></label><label>Local test image<input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setEvidenceFile(event.target.files?.[0] ?? null)} required /></label><div className="inline-form"><button disabled={busy} type="submit">Submit diesel issued / recorded</button><button className="secondary" type="button" onClick={() => setActiveAction(null)}>Cancel</button></div></form>}
      {activeAction === "EMERGENCY" && <form className="table-card stack" onSubmit={(event) => void submitEmergency(event)}><h3>Emergency</h3><label>Category<select value={emergencyCategory} onChange={(event) => setEmergencyCategory(event.target.value as typeof emergencyCategory)}>{emergencyCategories.map((category) => <option key={category} value={category}>{category}</option>)}</select></label><label>Description (optional)<textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={500} /></label><div className="inline-form"><button disabled={busy} type="submit">Submit emergency</button><button className="secondary" type="button" onClick={() => setActiveAction(null)}>Cancel</button></div></form>}
      <QaNotice><strong>QA diagnostics</strong> · not Driver product UI. Each accepted event below has its own client UUID and server verification state.</QaNotice>
      <div className="table-card">{eventLog.length ? eventLog.map((item) => <div className="table-row" key={item.uuid}><strong>{item.type}</strong><span>{item.uuid}</span><span>{new Date(item.timestamp).toLocaleString()}</span><span>API: {item.status}</span><span>Verification: {item.verificationStatus}</span></div>) : <div className="table-row"><span>No QA events submitted in this browser session.</span></div>}</div>
      <p className="muted">Device identity: {installationIdentifier} · platform: WEB</p>
    </section></div>
  </main>;
}
