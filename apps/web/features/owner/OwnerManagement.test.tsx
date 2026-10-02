import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { OwnerAsset, OwnerSite } from "../../lib/types";
import type { WebRequest } from "../../lib/api/client";
import { AssignmentsPanel, DeploymentsPanel, FleetPanel } from "./OwnerManagement";

const machine: OwnerAsset = {
  id: "asset-1", asset_code: "EXC-01", asset_type: "EXCAVATOR", ownership_type: "RENTED", registration_number: null, short_name: "Big digger", manufacturer: "CAT", model: "320", status: "ACTIVE", rental_party_name: "Rental Co", rental_start_date: "2026-01-01", rental_end_date: null,
  current_deployment: { id: "deployment-1", asset_id: "asset-1", site_id: "site-1", site_name: "Quarry", starts_at: "2026-01-01T00:00:00Z", ends_at: null }, has_active_assignment: false, active_assignment: null,
};
const site: OwnerSite = { id: "site-1", name: "Quarry", code: "Q1", location_description: null, latitude: null, longitude: null, status: "ACTIVE", supervisors: [], asset_count: 1 };

afterEach(cleanup);

describe("Owner generic fleet workflows", () => {
  it("renders machinery capabilities and creates an owned Grader without a registration", async () => {
    const apiRequest = vi.fn().mockResolvedValue({}); const reload = vi.fn().mockResolvedValue(undefined);
    render(<FleetPanel assets={[machine]} apiRequest={apiRequest} reload={reload} setError={vi.fn()} />);
    expect(screen.getByText("HMR")).toBeInTheDocument(); expect(screen.getByText("Rented from Rental Co")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Asset type"), { target: { value: "GRADER" } });
    fireEvent.change(screen.getByLabelText("Ownership"), { target: { value: "OWNED" } });
    fireEvent.change(screen.getByLabelText("Asset code"), { target: { value: "GRD-09" } });
    fireEvent.change(screen.getByLabelText("Short name"), { target: { value: "Road grader" } });
    fireEvent.click(screen.getByRole("button", { name: "Add asset" }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("/api/v1/owner/assets", expect.objectContaining({ method: "POST" })));
    const payload = JSON.parse(apiRequest.mock.calls[0][1].body);
    expect(payload).toEqual(expect.objectContaining({ asset_type: "GRADER", ownership_type: "OWNED", registration_number: null, short_name: "Road grader" }));
    expect(payload).not.toHaveProperty("wheel_loader");
  });

  it("moves a deployed asset through the generic deployment endpoint", async () => {
    const apiRequest = vi.fn((path: string) => path.endsWith("/deployments") ? Promise.resolve([]) : Promise.resolve({})); const reload = vi.fn().mockResolvedValue(undefined);
    render(<DeploymentsPanel assets={[machine]} sites={[site]} apiRequest={apiRequest as unknown as WebRequest} reload={reload} setError={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Asset"), { target: { value: "asset-1" } });
    fireEvent.change(screen.getByLabelText("Site"), { target: { value: "site-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Move asset" }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("/api/v1/owner/assets/asset-1/deployment", expect.objectContaining({ method: "POST", body: JSON.stringify({ site_id: "site-1" }) })));
  });

  it("assigns an eligible Driver / Operator to deployed machinery", async () => {
    const apiRequest = vi.fn((path: string) => path.endsWith("eligible-drivers") ? Promise.resolve([{ membership_id: "driver-1", display_name: "Operator A" }]) : path.endsWith("assignments") ? Promise.resolve([]) : Promise.resolve({})); const reload = vi.fn().mockResolvedValue(undefined);
    render(<AssignmentsPanel assets={[machine]} apiRequest={apiRequest as unknown as WebRequest} reload={reload} setError={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Deployed asset"), { target: { value: "asset-1" } });
    await screen.findByRole("option", { name: "Operator A" });
    fireEvent.change(screen.getByLabelText("Driver / Operator"), { target: { value: "driver-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Assign" }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("/api/v1/owner/assets/asset-1/assignment", expect.objectContaining({ method: "POST", body: JSON.stringify({ driver_membership_id: "driver-1", regular_duty_minutes: 600 }) })));
  });
});
