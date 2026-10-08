import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { WebRequest } from "../../lib/api/client";
import type { OwnerAsset, OwnerPerson, OwnerSite } from "../../lib/types";
import { FleetPanel, PeoplePanel, SitesPanel } from "./OwnerManagement";

const siteOne: OwnerSite = {
  id: "site-1",
  name: "North Quarry Project",
  short_name: "Quarry",
  code: "SITE-ONE",
  location_description: "North access road",
  latitude: null,
  longitude: null,
  status: "ACTIVE",
  supervisors: [{ access_id: "access-1", membership_id: "supervisor-active", display_name: "Site Supervisor" }],
  asset_count: 1,
};

const siteTwo: OwnerSite = {
  ...siteOne,
  id: "site-2",
  name: "Central Maintenance Yard",
  short_name: "Yard",
  code: "SITE-TWO",
  supervisors: [],
  asset_count: 0,
};

const invitedDriver: OwnerPerson = {
  user_id: "user-invited",
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
  user_id: "user-active",
  membership_id: "driver-active",
  phone: "+919100000002",
  display_name: "Operator Active",
  status: "ACTIVE",
  has_active_assignment: true,
  current_asset_id: "asset-assigned",
  current_asset_code: "TIP-INTERNAL",
  current_site_id: siteOne.id,
  current_site_name: "Quarry",
};

const supervisor: OwnerPerson = {
  ...invitedDriver,
  user_id: "user-supervisor",
  membership_id: "supervisor-active",
  display_name: "Site Supervisor",
  role: "SUPERVISOR",
  status: "ACTIVE",
  sites: [{ site_id: siteOne.id, site_name: "Quarry" }],
};

const availableSupervisor: OwnerPerson = {
  ...supervisor,
  user_id: "user-supervisor-2",
  membership_id: "supervisor-available",
  display_name: "Relief Supervisor",
  sites: [],
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
  chassis_number: "CAT-CHASSIS-320",
  engine_number: "CAT-ENGINE-320",
  status: "ACTIVE",
  rental_party_name: "Rental Co",
  rental_owner_phone_primary: "+919876543210",
  rental_owner_phone_secondary: "+919988776655",
  rental_start_date: "2026-01-01",
  rental_end_date: null,
  current_deployment: {
    id: "deployment-1",
    asset_id: "asset-deployed",
    site_id: siteOne.id,
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
  rental_party_name: null,
  rental_owner_phone_primary: null,
  rental_owner_phone_secondary: null,
  rental_start_date: null,
  current_deployment: null,
};

const inactiveGrader: OwnerAsset = { ...undeployedGrader, status: "INACTIVE" };

const assignedTipper: OwnerAsset = {
  ...deployedMachine,
  id: "asset-assigned",
  asset_code: "TIP-INTERNAL",
  asset_type: "TIPPER",
  ownership_type: "OWNED",
  registration_number: "KA22AB1234",
  short_name: "BENZ-1",
  rental_party_name: null,
  rental_start_date: null,
  has_active_assignment: true,
  active_assignment: {
    assignment_id: "assignment-1",
    site_id: siteOne.id,
    site_name: "Quarry",
    driver_membership_id: activeDriver.membership_id,
    driver_name: activeDriver.display_name,
    driver_phone: activeDriver.phone,
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
    openRelationshipManager: vi.fn(),
  };
}

describe("Owner management panels", () => {
  it("creates machinery without exposing or sending an Asset Code", async () => {
    const props = common();
    render(<FleetPanel assets={[deployedMachine, undeployedGrader]} people={[]} sites={[siteOne]} {...props} />);

    expect(screen.getByRole("table", { name: "Fleet assets" })).toBeInTheDocument();
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

  it("creates a Site with an Owner-facing short name and no technical code field", async () => {
    const props = common();
    render(<SitesPanel assets={[]} people={[]} sites={[siteOne]} {...props} />);

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

  it("routes every Fleet Manage action to the same relationship manager", () => {
    const props = common();
    render(<FleetPanel assets={[deployedMachine, inactiveGrader]} people={[]} sites={[siteOne]} {...props} />);

    const fleet = screen.getByRole("table", { name: "Fleet assets" });
    const activeRow = within(fleet).getByRole("row", { name: /Big digger/ });
    fireEvent.click(within(activeRow).getByRole("button", { name: "Manage" }));
    expect(props.openRelationshipManager).toHaveBeenLastCalledWith({ kind: "asset", assetId: deployedMachine.id, focus: undefined, initialAction: undefined });

    const inactiveRow = within(fleet).getByRole("row", { name: /Road grader/ });
    fireEvent.click(within(inactiveRow).getByRole("button", { name: "Manage" }));
    expect(props.openRelationshipManager).toHaveBeenLastCalledWith({ kind: "asset", assetId: inactiveGrader.id, focus: "lifecycle", initialAction: "REACTIVATE_ASSET" });
  });

  it("renders the four composite Fleet columns with contacts, setup, Driver phone, and minimal actions", () => {
    const props = common();
    render(<FleetPanel assets={[deployedMachine, assignedTipper]} people={[activeDriver]} sites={[siteOne, siteTwo]} {...props} />);

    const fleet = screen.getByRole("table", { name: "Fleet assets" });
    expect(within(fleet).getAllByRole("columnheader").map((header) => header.textContent?.replace(/[↕↑↓]/g, "").trim())).toEqual([
      "Asset",
      "Current setup",
      "Driver / Operator",
      "Actions",
    ]);
    expect(within(fleet).queryByRole("columnheader", { name: "Registration" })).not.toBeInTheDocument();
    const rentedRow = within(fleet).getByRole("row", { name: /Big digger/ });
    expect(rentedRow).toHaveTextContent("EXCAVATOR · RENTED");
    expect(rentedRow).toHaveTextContent("Owner: Rental Co");
    expect(rentedRow).toHaveTextContent("+91 98765 43210");
    expect(rentedRow).toHaveTextContent("+91 99887 76655");
    expect(within(rentedRow).getAllByRole("button").map((button) => button.textContent)).toEqual(["Manage", "History"]);
    const assignedRow = within(fleet).getByRole("row", { name: /BENZ-1/ });
    expect(assignedRow).toHaveTextContent("Quarry");
    expect(assignedRow).toHaveTextContent("Off duty");
    expect(assignedRow).toHaveTextContent("Operator Active");
    expect(assignedRow).toHaveTextContent("+91 91000 00002");
    expect(assignedRow).not.toHaveTextContent("Owner:");
  });

  it("shows and submits rented contacts plus optional technical identifiers", async () => {
    const props = common();
    render(<FleetPanel assets={[]} people={[]} sites={[]} {...props} />);

    fireEvent.click(screen.getByRole("button", { name: "Add asset" }));
    expect(screen.getByLabelText("Chassis number")).not.toBeRequired();
    expect(screen.getByLabelText("Engine number")).not.toBeRequired();
    expect(screen.queryByLabelText("Primary phone")).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: /^Ownership$/ }), { target: { value: "RENTED" } });
    fireEvent.change(screen.getByLabelText("Registration"), { target: { value: "MH01AM5678" } });
    fireEvent.change(screen.getByLabelText("Short name"), { target: { value: "SUBI-BENZ" } });
    fireEvent.change(screen.getByLabelText("Chassis number"), { target: { value: "MA1XXXXXXXX" } });
    fireEvent.change(screen.getByLabelText("Engine number"), { target: { value: "E4XXXXXX" } });
    fireEvent.change(screen.getByLabelText("Rental Owner / Supplier name"), { target: { value: "Suresh Transport" } });
    fireEvent.change(screen.getByLabelText("Primary phone"), { target: { value: "98765 43210" } });
    fireEvent.change(screen.getByLabelText("Alternate phone"), { target: { value: "99887 76655" } });
    fireEvent.click(screen.getByRole("button", { name: "Create asset" }));

    await waitFor(() => expect(props.apiRequest).toHaveBeenCalled());
    const payload = JSON.parse(vi.mocked(props.apiRequest).mock.calls[0][1]?.body as string);
    expect(payload).toEqual(expect.objectContaining({
      chassis_number: "MA1XXXXXXXX",
      engine_number: "E4XXXXXX",
      rental_party_name: "Suresh Transport",
      rental_owner_phone_primary: "98765 43210",
      rental_owner_phone_secondary: "99887 76655",
    }));
  });

  it("groups one identity's memberships and preserves the invited lifecycle explanation", () => {
    const ownerMembership: OwnerPerson = {
      ...activeDriver,
      membership_id: "owner-active",
      role: "OWNER_ADMIN",
      has_active_assignment: false,
      current_asset_id: null,
      current_asset_code: null,
      current_site_id: null,
      current_site_name: null,
    };
    const props = common();
    render(<PeoplePanel assets={[assignedTipper]} people={[ownerMembership, activeDriver, invitedDriver]} sites={[siteOne]} {...props} />);

    expect(screen.getByText("Saved and assignable; first login/onboarding is not yet complete.")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "People" });
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    const groupedRow = within(table).getByRole("row", { name: /Operator Active/ });
    expect(groupedRow).toHaveTextContent("Owner");
    expect(groupedRow).toHaveTextContent(/Driver/i);
    expect(groupedRow).toHaveTextContent("BENZ-1");
    const invitedRow = within(table).getByRole("row", { name: /Operator Invited/ });
    expect(invitedRow).toHaveTextContent("INVITED");
  });

  it("routes People and Site Details entry points to the same person or asset manager", () => {
    const props = common();
    render(<PeoplePanel assets={[assignedTipper]} people={[activeDriver]} sites={[siteOne]} {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Manage person" }));
    fireEvent.click(screen.getByRole("button", { name: "Manage assignment" }));
    expect(props.openRelationshipManager).toHaveBeenLastCalledWith({ kind: "person", membershipId: activeDriver.membership_id });
    cleanup();

    render(<SitesPanel assets={[assignedTipper]} people={[activeDriver, supervisor, availableSupervisor]} sites={[siteOne]} {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    fireEvent.click(screen.getByRole("button", { name: "Manage asset" }));
    expect(props.openRelationshipManager).toHaveBeenLastCalledWith({ kind: "asset", assetId: assignedTipper.id });

    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    fireEvent.click(screen.getByRole("button", { name: "Site Supervisor · Manage" }));
    expect(props.openRelationshipManager).toHaveBeenLastCalledWith({ kind: "person", membershipId: supervisor.membership_id });

    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    fireEvent.change(screen.getByLabelText("Supervisor for Quarry"), { target: { value: availableSupervisor.membership_id } });
    fireEvent.click(screen.getByRole("button", { name: "Manage access" }));
    expect(props.openRelationshipManager).toHaveBeenLastCalledWith({ kind: "person", membershipId: availableSupervisor.membership_id, presetSiteId: siteOne.id });
  });
});
