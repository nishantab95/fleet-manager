import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { OwnerOperations } from "./OwnerOperations";
import type { WebRequest } from "../../lib/api/client";

afterEach(cleanup);

it("shows HMR and machine hours instead of trip or kilometre metrics for machinery", async () => {
  const machine = { assignment_id: "a1", tipper_id: "m1", registration_number: null, short_name: "Excavator One", asset_type: "EXCAVATOR", site_id: "s1", site_name: "Quarry", driver_name: "Operator A", supervisor_name: "Supervisor A", assignment_starts_at: "2026-01-01T00:00:00Z", assignment_ends_at: null, approved_trip_count: null, pending_trip_count: null, disputed_trip_count: null, rejected_trip_count: null, trips_state: "NOT_APPLICABLE", start_km: null, end_km: null, distance_km: null, distance_state: "NOT_APPLICABLE", start_hmr: 100, end_hmr: 107.5, machine_hours: 7.5, machine_hours_state: "VALUE", km_per_approved_trip: null, verified_diesel_issued: 30, pending_diesel_issued: 2, diesel_issued_per_approved_trip: null, first_trip_completed_at: null, last_trip_completed_at: null, recorded_activity_span_seconds: null, avg_trip_completion_interval_seconds: null, median_trip_completion_interval_seconds: null, longest_trip_gap_seconds: null, pending_diesel_count: 1, disputed_diesel_count: 0, unresolved_emergency_count: 0, missing_start_reading: false, missing_end_reading: false, completeness_status: "COMPLETE", closure_status: "OPEN", exceptions: [], events: [] };
  const closure = { site_id: "s1", site_name: "Quarry", operational_date: "2026-01-01", reporting_timezone: "Asia/Kolkata", workday_start_minutes: 0, status: "READY_TO_CLOSE", blockers: [], history: [] };
  const site = { site_id: "s1", site_name: "Quarry", operational_date: "2026-01-01", reporting_timezone: "Asia/Kolkata", assigned_tippers_count: 1, approved_trip_count: 0, pending_trip_count: 0, disputed_trip_count: 0, total_km: null, verified_diesel_issued: 30, missing_reading_count: 0, unresolved_emergency_count: 0, closure, tippers: [machine] };
  const dashboard = { operational_date: "2026-01-01", reporting_timezone: "Asia/Kolkata", workday_start_minutes: 0, assigned_tippers_count: 1, approved_trip_count: 0, total_km: null, verified_diesel_issued: 30, pending_verification_count: 1, missing_reading_count: 0, unresolved_emergency_count: 0, sites_not_closed_count: 1, complete_tippers_count: 1, sites: [site], exceptions: [] };
  const apiRequest = vi.fn((path: string) => {
    if (path.includes("/reports/dashboard")) return Promise.resolve(dashboard);
    if (path === "/api/v1/admin/company") return Promise.resolve({ company_id: "c1", reporting_timezone: "Asia/Kolkata", operational_day_start_minutes: 0 });
    if (path.includes("/reports/duty")) return Promise.resolve([]);
    if (path.includes("report-templates")) return Promise.resolve([]);
    if (path.includes("/reports/sites/")) return Promise.resolve(site);
    if (path.includes("/reports/tippers/")) return Promise.resolve([machine]);
    return Promise.resolve({});
  });
  render(<OwnerOperations accessToken="token" apiRequest={apiRequest as unknown as WebRequest} setError={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: /Quarry/ }));
  fireEvent.click(await screen.findByRole("button", { name: /Excavator One/ }));
  expect(await screen.findByText("Start HMR")).toBeInTheDocument();
  expect(screen.getByText("Machine hours")).toBeInTheDocument();
  expect(screen.queryByText("Approved Trips")).not.toBeInTheDocument();
  expect(screen.queryByText("Distance KM")).not.toBeInTheDocument();
});
