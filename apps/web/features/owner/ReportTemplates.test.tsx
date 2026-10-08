import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { OwnerSite, ReportTemplate } from "../../lib/types";
import type { WebRequest } from "../../lib/api/client";
import { filenameFromDisposition, ReportTemplates } from "./ReportTemplates";

const builtin: ReportTemplate = { id: "template-1", name: "Management Summary", is_builtin: true, is_default: true, builtin_key: "management_summary", included_sheets: ["management_dashboard", "exceptions"], management_dashboard_columns: ["asset", "pending_status"], tipper_daily_columns: ["asset", "status"], machinery_daily_columns: ["asset", "machine_hours", "status"], created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" };
const simple: ReportTemplate = { ...builtin, id: "simple-1", name: "Simple Site Workbook", is_default: false, builtin_key: "simple_site_workbook", included_sheets: [] };
const sites: OwnerSite[] = [{ id: "site-1", name: "ABL Railway Work", short_name: "ABL Railway", code: "ABL", location_description: null, latitude: null, longitude: null, status: "ACTIVE", supervisors: [], asset_count: 3 }];

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("Owner report templates", () => {
  it("duplicates a built-in and keeps Asset mandatory in custom column choices", async () => {
    const apiRequest = vi.fn((path: string, options?: RequestInit) => {
      if (!options) return Promise.resolve([builtin]);
      if (path.endsWith("/duplicate")) return Promise.resolve({ ...builtin, id: "copy-1", name: "Owner Copy", is_builtin: false, is_default: false });
      return Promise.resolve({});
    });
    render(<ReportTemplates accessToken="owner-token" apiRequest={apiRequest as unknown as WebRequest} setError={vi.fn()} sites={sites} />);
    expect((await screen.findAllByText("Management Summary")).length).toBeGreaterThan(0);
    const mandatory = screen.getAllByLabelText("Asset");
    expect(mandatory.length).toBe(3); expect(mandatory.every((input) => (input as HTMLInputElement).checked && (input as HTMLInputElement).disabled)).toBe(true);
    fireEvent.change(screen.getByLabelText("Duplicate template name"), { target: { value: "Owner Copy" } });
    fireEvent.click(screen.getByRole("button", { name: "Duplicate" }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("/api/v1/owner/report-templates/template-1/duplicate", expect.objectContaining({ method: "POST", body: JSON.stringify({ name: "Owner Copy" }) })));
  });

  it("downloads the built-in Simple Site Workbook for exactly one Site and date range", async () => {
    const apiRequest = vi.fn(() => Promise.resolve([builtin, simple]));
    const setError = vi.fn();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(new Blob(["xlsx"]), { status: 200, headers: { "Content-Disposition": 'attachment; filename="abl-2026-10-01-to-2026-10-31.xlsx"' } }));
    const createObjectURL = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:site-workbook");
    const revokeObjectURL = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    render(<ReportTemplates accessToken="owner-token" apiRequest={apiRequest as unknown as WebRequest} setError={setError} sites={sites} />);
    const simpleChoices = await screen.findAllByText("Simple Site Workbook");
    fireEvent.click(simpleChoices[0]);

    expect(screen.getByRole("combobox", { name: "Site" })).toBeInTheDocument();
    expect(screen.getByLabelText("From Date")).toBeInTheDocument();
    expect(screen.getByLabelText("To Date")).toBeInTheDocument();
    expect(screen.queryByLabelText("Duplicate template name")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Template name")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Set as default" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "DOWNLOAD SITE WORKBOOK" })).toBeDisabled();

    fireEvent.change(screen.getByRole("combobox", { name: "Site" }), { target: { value: "site-1" } });
    fireEvent.change(screen.getByLabelText("From Date"), { target: { value: "2026-10-01" } });
    fireEvent.change(screen.getByLabelText("To Date"), { target: { value: "2026-10-31" } });
    fireEvent.click(screen.getByRole("button", { name: "DOWNLOAD SITE WORKBOOK" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/backend/api/v1/reports/sites/site-1/simple-workbook.xlsx?from_date=2026-10-01&to_date=2026-10-31", { credentials: "include", headers: { Authorization: "Bearer owner-token" } }));
    await waitFor(() => expect(click).toHaveBeenCalledOnce());
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:site-workbook");
    expect(filenameFromDisposition('attachment; filename="abl-2026-10-01-to-2026-10-31.xlsx"', "fallback.xlsx")).toBe("abl-2026-10-01-to-2026-10-31.xlsx");
    expect(setError).toHaveBeenLastCalledWith("");
  });

  it("rejects a reversed Simple Site Workbook date range before download", async () => {
    const apiRequest = vi.fn(() => Promise.resolve([simple]));
    const setError = vi.fn();
    const fetchMock = vi.spyOn(globalThis, "fetch");
    render(<ReportTemplates accessToken="owner-token" apiRequest={apiRequest as unknown as WebRequest} setError={setError} sites={sites} />);
    await screen.findByText("One practical workbook for one Site and one date range, with Summary first and one sheet per relevant asset.");
    fireEvent.change(screen.getByRole("combobox", { name: "Site" }), { target: { value: "site-1" } });
    fireEvent.change(screen.getByLabelText("From Date"), { target: { value: "2026-11-01" } });
    fireEvent.change(screen.getByLabelText("To Date"), { target: { value: "2026-10-31" } });
    fireEvent.click(screen.getByRole("button", { name: "DOWNLOAD SITE WORKBOOK" }));
    expect(setError).toHaveBeenLastCalledWith("From Date must be on or before To Date.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("surfaces a backend Simple Site Workbook error without starting a browser download", async () => {
    const apiRequest = vi.fn(() => Promise.resolve([simple]));
    const setError = vi.fn();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: { message: "The reporting range is too large." } }), { status: 422, headers: { "Content-Type": "application/json" } }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    render(<ReportTemplates accessToken="owner-token" apiRequest={apiRequest as unknown as WebRequest} setError={setError} sites={sites} />);
    await screen.findByText("One practical workbook for one Site and one date range, with Summary first and one sheet per relevant asset.");
    fireEvent.change(screen.getByRole("combobox", { name: "Site" }), { target: { value: "site-1" } });
    fireEvent.change(screen.getByLabelText("From Date"), { target: { value: "2026-10-01" } });
    fireEvent.change(screen.getByLabelText("To Date"), { target: { value: "2026-10-31" } });
    fireEvent.click(screen.getByRole("button", { name: "DOWNLOAD SITE WORKBOOK" }));
    await waitFor(() => expect(setError).toHaveBeenLastCalledWith("The reporting range is too large."));
    expect(click).not.toHaveBeenCalled();
  });
});
