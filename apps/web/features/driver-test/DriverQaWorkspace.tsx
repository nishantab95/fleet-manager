"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError, uploadDriverEvidence } from "../../lib/api/client";
import type { DriverAssignment, DriverDutyState } from "../../lib/types";
import { QaNotice, WorkspaceHeader } from "../shared/Ui";
import { useAuth } from "../auth/AuthProvider";

type QaEventLog = { uuid: string; type: string; timestamp: string; status: string; verificationStatus: string };
type PrimaryAction = "TRIP_COMPLETE" | "KM_READING" | "DIESEL" | "EMERGENCY";

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
  const [duty, setDuty] = useState<DriverDutyState | null>(null);
  const [activeAction, setActiveAction] = useState<PrimaryAction | null>(null);
  const [readingType, setReadingType] = useState<"START_READING" | "END_READING">("START_READING");
  const [readingValue, setReadingValue] = useState("");
  const [dieselLitres, setDieselLitres] = useState("");
  const [evidenceFile, setEvidenceFile] = useState<File | null>(null);
  const [eventLog, setEventLog] = useState<QaEventLog[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const emergencySubmitLock = useRef(false);
  const accessToken = session?.access_token ?? "";

  useEffect(() => {
    let active = true;
    void Promise.all([
      request<DriverAssignment | null>("/api/v1/driver/assignment/current"),
      request<DriverDutyState>("/api/v1/driver/duty/current"),
      request("/api/v1/driver/device", { method: "POST", body: JSON.stringify({ installation_identifier: installationIdentifier, platform: "WEB" }) }),
    ]).then(([nextAssignment, nextDuty]) => { if (active) { setAssignment(nextAssignment); setDuty(nextDuty); } }).catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "Could not load the Driver QA assignment."); });
    return () => { active = false; };
  }, [installationIdentifier, request]);

  const submitEvent = async (eventType: PrimaryAction, fields: Record<string, unknown> = {}, file: File | null = null) => {
    if (!assignment || !session) return;
    if (eventType === "EMERGENCY") {
      if (emergencySubmitLock.current) return;
      emergencySubmitLock.current = true;
    }
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
      setDuty(await request<DriverDutyState>("/api/v1/driver/duty/current"));
      setActiveAction(null); setReadingValue(""); setDieselLitres(""); setEvidenceFile(null);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "The real Driver API request failed."); }
    finally { setBusy(false); if (eventType === "EMERGENCY") emergencySubmitLock.current = false; }
  };

  const submitKm = async (event: React.FormEvent<HTMLFormElement>) => { event.preventDefault(); const value = Number(readingValue); if (!Number.isFinite(value) || value < 0) { setError("KM value must be a non-negative number."); return; } if (!evidenceFile) { setError("A local test image is required for a KM reading."); return; } await submitEvent("KM_READING", { reading_type: readingType, reading_value: value }, evidenceFile); };
  const submitDiesel = async (event: React.FormEvent<HTMLFormElement>) => { event.preventDefault(); const litres = Number(dieselLitres); if (!Number.isFinite(litres) || litres <= 0) { setError("Diesel litres must be greater than zero."); return; } await submitEvent("DIESEL", { litres }, evidenceFile); };
  const dutyStatus = duty?.status ?? "LOADING";
  const openKmReading = () => {
    if (dutyStatus !== "NONE" && dutyStatus !== "ACTIVE") return;
    setError("");
    setReadingType(dutyStatus === "ACTIVE" ? "END_READING" : "START_READING");
    setActiveAction("KM_READING");
  };
  const canStartOrEndDuty = Boolean(assignment) && !busy && (dutyStatus === "NONE" || dutyStatus === "ACTIVE");
  const canOperate = Boolean(assignment) && !busy && dutyStatus === "ACTIVE";
  const disabledActionHint = dutyStatus === "CLOSED" ? "Duty is already completed." : dutyStatus === "NONE" ? "Record START KM first." : "Loading duty state…";
  return <main className="admin-shell">
    <WorkspaceHeader activeRole="DRIVER" eyebrow="DRIVER QA" qaNavigation title="QA Driver Simulator" onLogout={() => void logout()} />
    <div className="admin-layout single-column"><section className="content">
      <div className="notice error"><strong>QA DRIVER SIMULATOR</strong><br />NON-PRODUCTION WEB TEST CLIENT · INTERNAL / PILOT QA ONLY</div>
      <p className="muted">This browser client uses real authentication, the real DRIVER membership, the current assignment, PostgreSQL-backed APIs, and the real evidence pipeline. It is not the final Driver product.</p>
      {error && <div className="notice error">{error}</div>}
      <section className="table-card"><h2>Current assignment</h2>{assignment ? <div className="table-row"><strong>{assignment.tipper_short_name ?? assignment.tipper_registration_number}</strong><span>{assignment.tipper_registration_number}</span><span>Site: {assignment.site_name}</span><span>Supervisor: {assignment.supervisor_name}</span><span>Configured duty: {assignment.regular_duty_minutes / 60}h</span></div> : <div className="notice">Loading the current assignment…</div>}</section>
      <section className="table-card" aria-label="Current duty state"><strong>Duty state: {dutyStatus}</strong>{duty?.started_at && <span> · Started {new Date(duty.started_at).toLocaleString()} at START KM {duty.start_km}</span>}{duty?.ended_at && <span> · Ended {new Date(duty.ended_at).toLocaleString()} at END KM {duty.end_km}</span>}<p className="muted">This state is loaded from the server and resumes after browser restart. Overtime is not shown to drivers.</p></section>
      <section className="stack"><h2>Driver operational actions</h2><div className="metric-grid qa-actions"><button disabled={!canOperate} onClick={() => void submitEvent("TRIP_COMPLETE")} title={canOperate ? undefined : disabledActionHint} type="button">TRIP COMPLETE</button><button disabled={!canStartOrEndDuty} onClick={openKmReading} title={canStartOrEndDuty ? undefined : disabledActionHint} type="button">KM READING</button><button disabled={!canOperate} onClick={() => { setError(""); setActiveAction("DIESEL"); }} title={canOperate ? undefined : disabledActionHint} type="button">DIESEL</button><button className="danger-action" disabled={!assignment || busy} onClick={() => void submitEvent("EMERGENCY")} type="button">EMERGENCY</button></div><p className="muted" role="status">{dutyStatus === "CLOSED" ? "Duty completed" : dutyStatus === "NONE" ? "Record START KM first." : dutyStatus === "ACTIVE" ? "Duty active" : "Loading duty state…"}</p><p className="muted">Emergency sends one alert using the current driver, tipper, site, supervisor, company, and timestamp context. No category, description, or evidence is required.</p></section>
      {activeAction === "KM_READING" && <form className="table-card stack" onSubmit={(event) => void submitKm(event)}><h3>{readingType === "START_READING" ? "START KM" : "END KM"}</h3><input type="hidden" value={readingType} readOnly /><label>KM value<input aria-label="KM value" type="number" min="0" step="0.01" value={readingValue} onChange={(event) => setReadingValue(event.target.value)} required /></label><label>Required dashboard/odometer image<input aria-label="Required dashboard/odometer image" type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setEvidenceFile(event.target.files?.[0] ?? null)} required /></label><div className="inline-form"><button disabled={busy} type="submit">Submit {readingType === "START_READING" ? "START KM" : "END KM"}</button><button className="secondary" type="button" onClick={() => setActiveAction(null)}>Cancel</button></div></form>}
      {activeAction === "DIESEL" && <form className="table-card stack" onSubmit={(event) => void submitDiesel(event)}><h3>DIESEL ISSUED / RECORDED</h3><label>Litres<input type="number" min="0.01" step="0.01" value={dieselLitres} onChange={(event) => setDieselLitres(event.target.value)} required /></label><label>Optional fuel image<input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setEvidenceFile(event.target.files?.[0] ?? null)} /></label><div className="inline-form"><button disabled={busy} type="submit">Submit diesel issued / recorded</button><button className="secondary" type="button" onClick={() => setActiveAction(null)}>Cancel</button></div></form>}
      <QaNotice><strong>QA diagnostics</strong> · not Driver product UI. Each accepted event below has its own client UUID and server verification state.</QaNotice>
      <div className="table-card">{eventLog.length ? eventLog.map((item) => <div className="table-row" key={item.uuid}><strong>{item.type}</strong><span>{item.uuid}</span><span>{new Date(item.timestamp).toLocaleString()}</span><span>API: {item.status}</span><span>Verification: {item.verificationStatus}</span></div>) : <div className="table-row"><span>No QA events submitted in this browser session.</span></div>}</div>
      <p className="muted">Device identity: {installationIdentifier} · platform: WEB</p>
    </section></div>
  </main>;
}
