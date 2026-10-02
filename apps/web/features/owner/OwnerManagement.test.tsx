import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { WebRequest } from "../../lib/api/client";
import type { OwnerAsset, OwnerPerson, OwnerSite } from "../../lib/types";
import { AssignmentsPanel, DeploymentsPanel, FleetPanel, PeoplePanel, SitesPanel } from "./OwnerManagement";

const siteOne: OwnerSite = {
  id: "site-1",
  name: "North Quarry Project",
  short_name: "Quarry",
  code: "SITE-ONE",
  location_description: "North access road",
  latitude: null,
  longitude: null,
  status: "ACTIVE",
  supervisors: [],
  asset_count: 1,
};

const siteTwo: OwnerSite = {
  ...siteOne,
  id: "site-2",
  name: "Central Maintenance Yard",
  short_name: "Yard",
  code: "SITE-TWO",
  location_description: "Central depot",
  asset_count: 0,
};

const invitedDriver: OwnerPerson = {
  user_id: "user-1",
  membership_id: "driver-invited",
  phone: "+919100000001",
  display_name: "Operator Invited",
  role: "DRIVER",
  status: "INVITED",
  sites: [],
  has_active_assignment: false,
  has_active_duty: false,
  current_asset_id: null,
  current_asset_code: null,
  current_site_id: null,
  current_site_name: null,
};

const activeDriver: OwnerPerson = {
  ...invitedDriver,
  user_id: "user-2",
  membership_id: "driver-active",
  phone: "+919100000002",
  display_name: "Operator Active",
  status: "ACTIVE",
};

const deployedMachine: OwnerAsset = {
  id: "asset-deployed",
  asset_code: "EXC-INTERNAL",
  asset_type: "EXCAVATOR",
  ownership_type: "RENTED",
  registration_number: null,
  short_name: "Big digger",
  manufacturer: "CAT",
  model: "320",
  status: "ACTIVE",
  rental_party_name: "Rental Co",
  rental_start_date: "2026-01-01",
  rental_end_date: null,
  current_deployment: {
    id: "deployment-1",
    asset_id: "asset-deployed",
    site_id: "site-1",
    site_name: "Quarry",
    starts_at: "2026-01-01T00:00:00Z",
    ends_at: null,
  },
  has_active_assignment: false,
  active_assignment: null,
};

const undeployedGrader: OwnerAsset = {
  ...deployedMachine,
  id: "asset-undeployed",
  asset_code: "GRD-INTERNAL",
  asset_type: "GRADER",
  ownership_type: "OWNED",
  short_name: "Road grader",
  manufacturer: "Komatsu",
  model: "GD655",
  rental_party_name: null,
  rental_start_date: null,
  current_deployment: null,
};

const assignedTipper: OwnerAsset = {
  ...deployedMachine,
  id: "asset-assigned",
  asset_code: "TIP-INTERNAL",
  asset_type: "TIPPER",
  ownership_type: "OWNED",
  registration_number: "KA22AB1234",
  short_name: "BENZ-1",
  manufacturer: "BharatBenz",
  model: "2823C",
  rental_party_name: null,
  rental_start_date: null,
  has_active_assignment: true,
  active_assignment: {
    assignment_id: "assignment-1",
    site_id: "site-1",
    site_name: "Quarry",
    driver_membership_id: "driver-active",
    driver_name: "Operator Active",
    starts_at: "2026-01-02T00:00:00Z",
    regular_duty_minutes: 600,
  },
};

afterEach(cleanup);

function common(apiRequest = vi.fn().mockResolvedValue({})) {
  return {
    apiRequest: apiRequest as unknown as WebRequest,
    reload: vi.fn().mockResolvedValue(undefined),
    setError: vi.fn(),
  };
}

describe("Owner operations tables", () => {
  it("uses a semantic Fleet table and creates machinery without exposing or sending Asset Code", async () => {
    const props = common();
    render(<FleetPanel assets={[deployedMachine, undeployedGrader]} people={[]} sites={[siteOne]} {...props} />);

    expect(screen.getByRole("table", { name: "Fleet assets" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /Short name/ })).toBeInTheDocument();
    expect(screen.getByText("Rental Co")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Add asset" }));
    expect(screen.queryByLabelText(/Asset code/i)).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: /^Asset type$/ }), { target: { value: "GRADER" } });
    fireEvent.change(screen.getByRole("textbox", { name: /^Short name$/ }), { target: { value: "South grader" } });
    fireEvent.click(screen.getByRole("button", { name: "Create asset" }));

    await waitFor(() => expect(props.apiRequest).toHaveBeenCalledWith("/api/v1/owner/assets", expect.objectContaining({ method: "POST" })));
    const payload = JSON.parse(vi.mocked(props.apiRequest).mock.calls[0][1]?.body as string);
    expect(payload).toEqual(expect.objectContaining({ asset_type: "GRADER", ownership_type: "OWNED", registration_number: null, short_name: "South grader" }));
    expect(payload).not.toHaveProperty("asset_code");
  });

  it("creates a site with an Owner-facing short name and no technical code field", async () => {
    const props = common();
    render(<SitesPanel sites={[siteOne]} people={[]} {...props} />);

    expect(screen.getByRole("table", { name: "Sites" })).toBeInTheDocument();
    expect(screen.getByText("Quarry")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add site" }));
    expect(screen.queryByLabelText(/Site code/i)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Site name"), { target: { value: "Railway Package 4" } });
    fireEvent.change(screen.getByLabelText("Site short name"), { target: { value: "Rail P4" } });
    fireEvent.change(screen.getByLabelText("Site location"), { target: { value: "Chainage 20" } });
    fireEvent.click(screen.getByRole("button", { name: "Create site" }));

    await waitFor(() => expect(props.apiRequest).toHaveBeenCalledWith("/api/v1/owner/sites", expect.objectContaining({ method: "POST" })));
    const payload = JSON.parse(vi.mocked(props.apiRequest).mock.calls[0][1]?.body as string);
    expect(payload).toEqual({ name: "Railway Package 4", short_name: "Rail P4", location_description: "Chainage 20" });
    expect(payload).not.toHaveProperty("code");
  });

  it("shows only undeployed assets in the deploy selector and manages deployed assets in a table", async () => {
    const apiRequest = vi.fn().mockResolvedValue({});
    const props = common(apiRequest);
    render(<DeploymentsPanel assets={[deployedMachine, undeployedGrader]} sites={[siteOne, siteTwo]} people={[]} {...props} />);

    const deploySelect = screen.getByLabelText("Asset");
    expect(within(deploySelect).getByRole("option", { name: /Road grader/ })).toBeInTheDocument();
    expect(within(deploySelect).queryByRole("option", { name: /Big digger/ })).not.toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Current deployments" })).toHaveTextContent("Big digger");

    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    const destination = screen.getByLabelText("Move destination site");
    expect(within(destination).queryByRole("option", { name: "Quarry" })).not.toBeInTheDocument();
    expect(within(destination).getByRole("option", { name: "Yard" })).toBeInTheDocument();
    fireEvent.change(destination, { target: { value: "site-2" } });
    expect(screen.getByText("Move Big digger from Quarry to Yard?")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Move asset" }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("/api/v1/owner/assets/asset-deployed/deployment", expect.objectContaining({ method: "POST", body: JSON.stringify({ site_id: "site-2" }) })));
  });

  it("shows invited lifecycle meaning in the People table", () => {
    const props = common();
    render(<PeoplePanel people={[invitedDriver, activeDriver]} assets={[assignedTipper]} {...props} />);

    expect(screen.getByRole("table", { name: "People" })).toBeInTheDocument();
    expect(screen.getByText("Saved and assignable; first login/onboarding is not yet complete.")).toBeInTheDocument();
    expect(screen.getByText("Operator Invited")).toBeInTheDocument();
    expect(screen.getAllByText("INVITED").length).toBeGreaterThan(0);
  });

  it("loads and assigns an INVITED Driver / Operator to a deployed rented machine", async () => {
    const apiRequest = vi.fn((path: string) => path.endsWith("eligible-drivers")
      ? Promise.resolve([{ membership_id: invitedDriver.membership_id, display_name: invitedDriver.display_name, phone: invitedDriver.phone, status: "INVITED" }])
      : Promise.resolve({}));
    const props = common(apiRequest);
    render(<AssignmentsPanel assets={[deployedMachine, undeployedGrader, assignedTipper]} people={[invitedDriver, activeDriver]} {...props} />);

    const assetSelect = screen.getByLabelText("Deployed asset");
    expect(within(assetSelect).getByRole("option", { name: /Big digger/ })).toBeInTheDocument();
    expect(within(assetSelect).queryByRole("option", { name: /Road grader/ })).not.toBeInTheDocument();
    expect(within(assetSelect).queryByRole("option", { name: /BENZ-1/ })).not.toBeInTheDocument();

    fireEvent.change(assetSelect, { target: { value: "asset-deployed" } });
    const candidate = await screen.findByRole("option", { name: "Operator Invited · +919100000001 · INVITED" });
    fireEvent.change(screen.getByLabelText("Driver / Operator"), { target: { value: candidate.getAttribute("value") } });
    fireEvent.click(screen.getByRole("button", { name: "Assign driver" }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("/api/v1/owner/assets/asset-deployed/assignment", expect.objectContaining({ method: "POST", body: JSON.stringify({ driver_membership_id: "driver-invited", regular_duty_minutes: 600 }) })));
  });

  it("renders current assignment details and requires confirmation before unassigning", async () => {
    const apiRequest = vi.fn().mockResolvedValue({});
    const props = common(apiRequest);
    render(<AssignmentsPanel assets={[assignedTipper]} people={[{ ...activeDriver, current_asset_id: assignedTipper.id, current_asset_code: assignedTipper.asset_code, current_site_id: "site-1", current_site_name: "Quarry", has_active_assignment: true }]} {...props} />);

    const table = screen.getByRole("table", { name: "Current assignments" });
    expect(table).toHaveTextContent("BENZ-1");
    expect(table).toHaveTextContent("+919100000002");
    expect(table).toHaveTextContent("10 hours");
    fireEvent.click(screen.getByRole("button", { name: "Unassign" }));
    expect(screen.getByRole("dialog", { name: "Unassign Driver / Operator" })).toHaveTextContent("Operator Active");
    expect(apiRequest).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole("dialog", { name: "Unassign Driver / Operator" })).getByRole("button", { name: "Unassign" }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("/api/v1/owner/assets/asset-assigned/assignment", { method: "DELETE" }));
  });
});
