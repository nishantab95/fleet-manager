import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ReportTemplate } from "../../lib/types";
import type { WebRequest } from "../../lib/api/client";
import { ReportTemplates } from "./ReportTemplates";

const builtin: ReportTemplate = { id: "template-1", name: "Management Summary", is_builtin: true, is_default: true, included_sheets: ["management_dashboard", "exceptions"], management_dashboard_columns: ["asset", "pending_status"], tipper_daily_columns: ["asset", "status"], machinery_daily_columns: ["asset", "machine_hours", "status"], created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" };

afterEach(cleanup);

describe("Owner report templates", () => {
  it("duplicates a built-in and keeps Asset mandatory in custom column choices", async () => {
    const apiRequest = vi.fn((path: string, options?: RequestInit) => {
      if (!options) return Promise.resolve([builtin]);
      if (path.endsWith("/duplicate")) return Promise.resolve({ ...builtin, id: "copy-1", name: "Owner Copy", is_builtin: false, is_default: false });
      return Promise.resolve({});
    });
    render(<ReportTemplates apiRequest={apiRequest as unknown as WebRequest} setError={vi.fn()} />);
    expect((await screen.findAllByText("Management Summary")).length).toBeGreaterThan(0);
    const mandatory = screen.getAllByLabelText("Asset");
    expect(mandatory.length).toBe(3); expect(mandatory.every((input) => (input as HTMLInputElement).checked && (input as HTMLInputElement).disabled)).toBe(true);
    fireEvent.change(screen.getByLabelText("Duplicate template name"), { target: { value: "Owner Copy" } });
    fireEvent.click(screen.getByRole("button", { name: "Duplicate" }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("/api/v1/owner/report-templates/template-1/duplicate", expect.objectContaining({ method: "POST", body: JSON.stringify({ name: "Owner Copy" }) })));
  });
});
