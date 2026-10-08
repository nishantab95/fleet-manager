"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { API_BASE, ApiError } from "../../lib/api/client";
import type { OwnerSite, ReportTemplate } from "../../lib/types";
import { machineryColumns, managementColumns, sheetCatalog, tipperColumns, title } from "./catalogs";
import { EmptyTableRow, OperationsTable, SortButton, StatusChip } from "./OwnerUi";

type WebRequest = <T>(path: string, options?: RequestInit) => Promise<T>;
type Draft = Pick<ReportTemplate, "name" | "included_sheets" | "management_dashboard_columns" | "tipper_daily_columns" | "machinery_daily_columns">;
type Props = { accessToken: string; apiRequest: WebRequest; setError: (message: string) => void; sites: OwnerSite[] };
const blank: Draft = { name: "", included_sheets: ["management_dashboard", "tipper_daily", "machinery_daily", "exceptions"], management_dashboard_columns: [...managementColumns], tipper_daily_columns: [...tipperColumns], machinery_daily_columns: [...machineryColumns] };
const simpleSiteWorkbookKey = "simple_site_workbook";

export function filenameFromDisposition(value: string | null, fallback: string) {
  const encoded = value?.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const plain = value?.match(/filename="([^"]+)"/i)?.[1] ?? value?.match(/filename=([^;]+)/i)?.[1]?.trim();
  let filename = plain;
  if (encoded) {
    try { filename = decodeURIComponent(encoded); } catch { filename = encoded; }
  }
  return (filename || fallback).replace(/[\\/:*?"<>|]/g, "-");
}

function Checklist({ legend, values, selected, onChange }: { legend: string; values: readonly string[]; selected: string[]; onChange: (next: string[]) => void }) {
  return <fieldset><legend>{legend}</legend><div className="checkbox-grid">{values.map((value) => { const mandatory = value === "asset"; return <label className="check-option" key={value}><input type="checkbox" checked={mandatory || selected.includes(value)} disabled={mandatory} onChange={(event) => onChange(event.target.checked ? [...selected, value] : selected.filter((item) => item !== value))} />{title(value)}</label>; })}</div></fieldset>;
}

export function ReportTemplates({ accessToken, apiRequest, setError, sites }: Props) {
  const [templates, setTemplates] = useState<ReportTemplate[]>([]); const [selectedId, setSelectedId] = useState(""); const [editingId, setEditingId] = useState(""); const [draft, setDraft] = useState<Draft>(blank); const [duplicateName, setDuplicateName] = useState(""); const [sortKey, setSortKey] = useState<"name" | "type" | "sheets" | "default">("name"); const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");
  const [siteId, setSiteId] = useState(""); const [fromDate, setFromDate] = useState(""); const [toDate, setToDate] = useState(""); const [downloading, setDownloading] = useState(false);
  const load = useCallback(async () => { try { const items = await apiRequest<ReportTemplate[]>("/api/v1/owner/report-templates"); setTemplates(items); setSelectedId((value) => value || items.find((item) => item.is_default)?.id || items[0]?.id || ""); } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not load report templates."); } }, [apiRequest, setError]);
  useEffect(() => { void Promise.resolve().then(load); }, [load]);
  const selected = templates.find((item) => item.id === selectedId);
  const sorted = useMemo(() => [...templates].sort((left, right) => { const value = (item: ReportTemplate) => sortKey === "name" ? item.name : sortKey === "type" ? (item.is_builtin ? "Built-in" : "Custom") : sortKey === "sheets" ? item.included_sheets.length : (item.is_default ? 1 : 0); const a = value(left); const b = value(right); const result = typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" }); return sortDirection === "asc" ? result : -result; }), [sortDirection, sortKey, templates]);
  const changeSort = (next: typeof sortKey) => { setSortDirection((current) => sortKey === next && current === "asc" ? "desc" : "asc"); setSortKey(next); };
  const run = async (action: () => Promise<unknown>) => { setError(""); try { await action(); await load(); } catch (caught) { setError(caught instanceof Error ? caught.message : "The template request failed."); } };
  const beginEdit = (item: ReportTemplate) => { setEditingId(item.id); setDraft({ name: item.name, included_sheets: [...item.included_sheets], management_dashboard_columns: [...item.management_dashboard_columns], tipper_daily_columns: [...item.tipper_daily_columns], machinery_daily_columns: [...item.machinery_daily_columns] }); };
  const submit = (event: FormEvent) => { event.preventDefault(); void run(async () => { await apiRequest(editingId ? `/api/v1/owner/report-templates/${editingId}` : "/api/v1/owner/report-templates", { method: editingId ? "PATCH" : "POST", body: JSON.stringify(draft) }); setEditingId(""); setDraft(blank); }); };
  const downloadSimpleSiteWorkbook = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    if (!siteId || !fromDate || !toDate) { setError("Choose one Site, a From Date, and a To Date."); return; }
    if (fromDate > toDate) { setError("From Date must be on or before To Date."); return; }
    setDownloading(true);
    try {
      const query = new URLSearchParams({ from_date: fromDate, to_date: toDate });
      const response = await fetch(`${API_BASE}/api/v1/reports/sites/${encodeURIComponent(siteId)}/simple-workbook.xlsx?${query}`, { credentials: "include", headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        const detail = body?.detail;
        const message = typeof detail === "string" ? detail : typeof detail?.message === "string" ? detail.message : "The Site workbook could not be downloaded.";
        throw new ApiError(response.status, message);
      }
      const fallback = `site-workbook-${fromDate}-to-${toDate}.xlsx`;
      const filename = filenameFromDisposition(response.headers.get("Content-Disposition"), fallback);
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The Site workbook could not be downloaded.");
    } finally {
      setDownloading(false);
    }
  };
  return <section><h2>Report templates</h2><p className="muted">Choose a simple Site workbook or configure the sheets and columns included in advanced Owner Excel exports.</p><div className="template-layout"><OperationsTable label="Report templates"><thead><tr>{([['name', 'Name'], ['type', 'Type'], ['sheets', 'Sheets'], ['default', 'Status']] as [typeof sortKey, string][]).map(([key, label]) => <th aria-sort={sortKey === key ? (sortDirection === "asc" ? "ascending" : "descending") : "none"} key={key} scope="col"><SortButton active={sortKey === key} direction={sortDirection} label={label} onClick={() => changeSort(key)} /></th>)}</tr></thead><tbody>{sorted.length === 0 && <EmptyTableRow colSpan={4} title="No report templates" />}{sorted.map((item) => <tr className={selectedId === item.id ? "selected-row" : ""} key={item.id} onClick={() => setSelectedId(item.id)}><td data-label="Name"><button className="owner-text-button" onClick={() => setSelectedId(item.id)} type="button"><strong>{item.name}</strong></button></td><td data-label="Type">{item.is_builtin ? "Built-in" : "Custom"}</td><td data-label="Sheets">{item.builtin_key === simpleSiteWorkbookKey ? "Summary + assets" : item.included_sheets.length}</td><td data-label="Status">{item.is_default ? <StatusChip label="Default" status="ACTIVE" /> : <span className="owner-dim">Available</span>}</td></tr>)}</tbody></OperationsTable>{selected?.builtin_key === simpleSiteWorkbookKey ? <article className="management-card"><div className="card-title"><div><h3>{selected.name}</h3><p className="muted">One practical workbook for one Site and one date range, with Summary first and one sheet per relevant asset.</p></div><span className="badge active">BUILT-IN</span></div><form className="inline-form compact" onSubmit={(event) => void downloadSimpleSiteWorkbook(event)}><label>Site<select aria-label="Site" value={siteId} onChange={(event) => setSiteId(event.target.value)} required><option value="">Choose Site</option>{[...sites].sort((left, right) => left.name.localeCompare(right.name)).map((site) => <option key={site.id} value={site.id}>{site.short_name || site.name}</option>)}</select></label><label>From Date<input aria-label="From Date" type="date" value={fromDate} onChange={(event) => setFromDate(event.target.value)} required /></label><label>To Date<input aria-label="To Date" type="date" value={toDate} onChange={(event) => setToDate(event.target.value)} required /></label><button disabled={downloading || !siteId || !fromDate || !toDate} type="submit">{downloading ? "DOWNLOADING…" : "DOWNLOAD SITE WORKBOOK"}</button></form></article> : selected ? <article className="management-card"><div className="card-title"><div><h3>{selected.name}</h3><p className="muted">{selected.included_sheets.map(title).join(", ")}</p></div>{selected.is_default && <span className="badge active">DEFAULT</span>}</div><div className="row-actions">{!selected.is_default && <button type="button" onClick={() => void run(() => apiRequest(`/api/v1/owner/report-templates/${selected.id}/default`, { method: "POST" }))}>Set as default</button>}{!selected.is_builtin && <button className="secondary" type="button" onClick={() => beginEdit(selected)}>Edit</button>}{!selected.is_builtin && <button className="secondary" type="button" onClick={() => void run(() => apiRequest(`/api/v1/owner/report-templates/${selected.id}`, { method: "DELETE" }))}>Delete</button>}</div><form className="inline-form compact" onSubmit={(event) => { event.preventDefault(); if (!duplicateName) return; void run(async () => { const copy = await apiRequest<ReportTemplate>(`/api/v1/owner/report-templates/${selected.id}/duplicate`, { method: "POST", body: JSON.stringify({ name: duplicateName }) }); setSelectedId(copy.id); setDuplicateName(""); }); }}><input aria-label="Duplicate template name" placeholder="New copy name" value={duplicateName} onChange={(event) => setDuplicateName(event.target.value)} required /><button type="submit">Duplicate</button></form></article> : null}</div>
    {selected?.builtin_key !== simpleSiteWorkbookKey && <form className="template-editor" onSubmit={submit}><h3>{editingId ? "Edit custom template" : "Create custom template"}</h3><label>Template name<input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} required /></label><Checklist legend="Workbook sheets" values={sheetCatalog.map(([id]) => id)} selected={draft.included_sheets} onChange={(included_sheets) => setDraft({ ...draft, included_sheets })} /><Checklist legend="Management dashboard columns" values={managementColumns} selected={draft.management_dashboard_columns} onChange={(management_dashboard_columns) => setDraft({ ...draft, management_dashboard_columns })} /><Checklist legend="Tipper daily columns" values={tipperColumns} selected={draft.tipper_daily_columns} onChange={(tipper_daily_columns) => setDraft({ ...draft, tipper_daily_columns })} /><Checklist legend="Machinery daily columns" values={machineryColumns} selected={draft.machinery_daily_columns} onChange={(machinery_daily_columns) => setDraft({ ...draft, machinery_daily_columns })} /><div className="row-actions"><button type="submit">{editingId ? "Save template" : "Create template"}</button>{editingId && <button className="secondary" type="button" onClick={() => { setEditingId(""); setDraft(blank); }}>Cancel</button>}</div></form>}
  </section>;
}
