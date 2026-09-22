import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OwnerOperations } from "./page";

const site = {
  site_id: "site-1",
  site_name: "Alpha Site",
  operational_date: "2025-01-15",
  reporting_timezone: "Asia/Kolkata",
  assigned_tippers_count: 1,
  approved_trip_count: 2,
  pending_trip_count: 1,
  disputed_trip_count: 0,
  total_km: null,
  verified_diesel_issued: 0,
  missing_reading_count: 1,
  unresolved_emergency_count: 0,
  closure: {
    site_id: "site-1",
    site_name: "Alpha Site",
    operational_date: "2025-01-15",
    reporting_timezone: "Asia/Kolkata",
    workday_start_minutes: 0,
    status: "OPEN",
    blockers: [{ code: "MISSING_END_READING", description: "No approved END reading exists", assignment_id: "assignment-1", tipper_id: "tipper-1", tipper_registration_number: "KA01", site_id: "site-1", event_id: null }],
    history: [],
  },
  tippers: [],
};

const dashboard = {
  operational_date: "2025-01-15",
  reporting_timezone: "Asia/Kolkata",
  workday_start_minutes: 0,
  assigned_tippers_count: 1,
  approved_trip_count: 2,
  pending_trip_count: 1,
  total_km: null,
  verified_diesel_issued: 0,
  pending_verification_count: 1,
  missing_reading_count: 1,
  unresolved_emergency_count: 0,
  sites_not_closed_count: 1,
  complete_tippers_count: 0,
  sites: [site],
  exceptions: site.closure.blockers,
};

const siteDetail = {
  ...site,
  tippers: [{
    assignment_id: "assignment-1",
    tipper_id: "tipper-1",
    registration_number: "KA01",
    short_name: null,
    site_id: "site-1",
    site_name: "Alpha Site",
    driver_name: "Driver A",
    supervisor_name: "Supervisor A",
    assignment_starts_at: "2025-01-14T18:00:00Z",
    assignment_ends_at: null,
    approved_trip_count: 2,
    pending_trip_count: 1,
    disputed_trip_count: 0,
    rejected_trip_count: 0,
    start_km: 100,
    end_km: null,
    distance_km: null,
    verified_diesel_issued: 0,
    pending_diesel_count: 0,
    disputed_diesel_count: 0,
    unresolved_emergency_count: 0,
    missing_start_reading: false,
    missing_end_reading: true,
    completeness_status: "INCOMPLETE",
    exceptions: site.closure.blockers,
    events: [],
  }],
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("owner operations", () => {
  it("renders approved and pending totals, unavailable KM, blockers, and site/tipper drill-down", async () => {
    const errors: string[] = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/reports/dashboard")) return Promise.resolve(response(dashboard));
      if (url.includes("/admin/company")) return Promise.resolve(response({ company_id: "company-1", reporting_timezone: "Asia/Kolkata", operational_day_start_minutes: 0 }));
      if (url.includes("/reports/sites/site-1/daily")) return Promise.resolve(response(siteDetail));
      if (url.includes("/reports/tippers/tipper-1/daily")) return Promise.resolve(response(siteDetail.tippers));
      return Promise.resolve(response({}));
    }));

    render(<OwnerOperations accessToken="token" setError={(message) => errors.push(message)} />);
    expect(await screen.findByText("Owner operations")).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
    expect(screen.getByText("Approved trips")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Alpha Site/ }));
    expect(await screen.findByText("Alpha Site · daily detail")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close day" })).toBeDisabled();
    fireEvent.click(screen.getByText("Driver A").closest("button") as HTMLElement);
    expect(await screen.findByText("KA01 · event trace")).toBeInTheDocument();
    expect(errors.filter(Boolean)).toEqual([]);
  });

  it("loads a changed date, triggers Excel export, and reports API failures", async () => {
    const errors: string[] = [];
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("daily.xlsx")) return Promise.resolve(new Response(new Blob(["xlsx"]), { status: 200 }));
      if (url.includes("/reports/dashboard")) return Promise.resolve(response({ ...dashboard, operational_date: "2025-02-01", sites: [], exceptions: [] }));
      if (url.includes("/admin/company")) return Promise.resolve(response({ company_id: "company-1", reporting_timezone: "UTC", operational_day_start_minutes: 60 }));
      return Promise.resolve(response({}, 500));
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:report"), revokeObjectURL: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    render(<OwnerOperations accessToken="token" setError={(message) => errors.push(message)} />);
    expect(await screen.findByText("Owner operations")).toBeInTheDocument();
    const dateInput = screen.getByLabelText("Operational date");
    fireEvent.change(dateInput, { target: { value: "2025-02-01" } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("operational_date=2025-02-01"), expect.anything()));
    fireEvent.click(screen.getByRole("button", { name: "Download Excel" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("daily.xlsx"), expect.anything()));
    expect(screen.getByText(/No assigned tippers/)).toBeInTheDocument();
  });

  it("enables close when a selected site is ready and posts the closure action", async () => {
    const readySite = {
      ...site,
      closure: { ...site.closure, status: "READY_TO_CLOSE", blockers: [] },
    };
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/reports/dashboard")) return Promise.resolve(response({ ...dashboard, sites: [readySite], exceptions: [] }));
      if (url.includes("/admin/company")) return Promise.resolve(response({ company_id: "company-1", reporting_timezone: "Asia/Kolkata", operational_day_start_minutes: 0 }));
      if (url.includes("/reports/sites/site-1/daily")) return Promise.resolve(response({ ...siteDetail, closure: readySite.closure }));
      if (url.includes("/closure/close")) return Promise.resolve(response({ ...readySite.closure, status: "CLOSED" }));
      return Promise.resolve(response({}, 500));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<OwnerOperations accessToken="token" setError={vi.fn()} />);
    await screen.findByText("Owner operations");
    fireEvent.click(screen.getByRole("button", { name: /Alpha Site/ }));
    const closeButton = await screen.findByRole("button", { name: "Close day" });
    expect(closeButton).toBeEnabled();
    fireEvent.click(closeButton);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("closure/close"), expect.objectContaining({ method: "POST" })));
  });

  it.each([401, 403])("reports an API authorization failure for status %s", async (status) => {
    const error = vi.fn();
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      if (String(input).includes("/reports/dashboard")) return Promise.resolve(response({ detail: { message: "Access denied" } }, status));
      return Promise.resolve(response({}, status));
    }));
    render(<OwnerOperations accessToken="token" setError={error} />);
    await waitFor(() => expect(error).toHaveBeenCalledWith("Access denied"));
  });
});
