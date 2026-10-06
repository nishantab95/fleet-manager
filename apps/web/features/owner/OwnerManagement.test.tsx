import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, type WebRequest } from "../../lib/api/client";
import type {
  OwnerAsset,
  OwnerOperationAction,
  OwnerOperationIntent,
  OwnerOperationPlan,
  OwnerPerson,
  OwnerSite,
} from "../../lib/types";
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

const activeOwner: OwnerPerson = {
  ...activeDriver,
  membership_id: "owner-active",
  role: "OWNER_ADMIN",
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

function operationPlan(
  action: OwnerOperationAction,
  overrides: Partial<OwnerOperationPlan> = {},
): OwnerOperationPlan {
  return {
    action,
    state_token: "a".repeat(64),
    title: action === "REMOVE_DEPLOYMENT" ? "Remove Big digger from Site" : "Review operation",
    summary: "Review the current state before making changes.",
    current_state: [{ kind: "ASSET", id: deployedMachine.id, label: "Big digger", status: "ACTIVE", details: {} }],
    dependencies: [{ kind: "DEPLOYMENT", id: "deployment-1", label: "Quarry", status: "ACTIVE", details: { site_id: siteOne.id } }],
    warnings: [],
    allowed_resolutions: [],
    blocked_reasons: [],
    planned_changes: ["Preserve operational history"],
    can_execute: true,
    ...overrides,
  };
}

function operationApi(
  preview: (intent: OwnerOperationIntent) => OwnerOperationPlan,
  executeError?: Error,
) {
  return vi.fn((path: string, options?: RequestInit) => {
    const body = options?.body ? JSON.parse(options.body as string) as OwnerOperationIntent : null;
    if (path.endsWith("/preview") && body) return Promise.resolve(preview(body));
    if (path.endsWith("/execute") && body) {
      if (executeError) return Promise.reject(executeError);
      return Promise.resolve({
        action: body.action,
        completed_changes: preview(body).planned_changes,
        message: "Operation completed successfully.",
      });
    }
    return Promise.resolve({});
  });
}

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
    fireEvent.click(screen.getByRole("button", { name: "Sort by Registration" }));
    expect(screen.getByRole("columnheader", { name: /Registration/ })).toHaveAttribute("aria-sort", "ascending");
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
    fireEvent.click(screen.getByRole("button", { name: "Sort by Deployed assets" }));
    expect(screen.getByRole("columnheader", { name: /Deployed assets/ })).toHaveAttribute("aria-sort", "ascending");
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
    const apiRequest = operationApi((intent) => operationPlan("MOVE_DEPLOYMENT", {
      title: "Move Big digger",
      summary: intent.target_site_id ? "Move the asset to Yard without rewriting history." : "Choose a destination while preserving history.",
      dependencies: [
        { kind: "DEPLOYMENT", id: "deployment-1", label: "Quarry", status: "ACTIVE", details: { site_id: siteOne.id } },
        ...(intent.target_site_id ? [{ kind: "TARGET_SITE", id: siteTwo.id, label: "Yard", status: "ACTIVE", details: {} }] : []),
      ],
      blocked_reasons: intent.target_site_id ? [] : ["Choose a destination Site."],
      planned_changes: intent.target_site_id ? ["End Big digger deployment from Quarry", "Deploy Big digger to Yard"] : [],
      can_execute: Boolean(intent.target_site_id),
    }));
    const props = common(apiRequest);
    render(<DeploymentsPanel assets={[deployedMachine, undeployedGrader]} sites={[siteOne, siteTwo]} people={[]} {...props} />);

    const deploySelect = screen.getByLabelText("Asset");
    expect(within(deploySelect).getByRole("option", { name: /Road grader/ })).toBeInTheDocument();
    expect(within(deploySelect).queryByRole("option", { name: /Big digger/ })).not.toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Current deployments" })).toHaveTextContent("Big digger");
    fireEvent.click(screen.getByRole("button", { name: "Sort by Deployment date" }));
    expect(screen.getByRole("columnheader", { name: /Deployment date/ })).toHaveAttribute("aria-sort", "ascending");

    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    const dialog = await screen.findByRole("dialog", { name: "Move Big digger" });
    expect(within(dialog).getAllByText("Current state")).toHaveLength(2);
    fireEvent.click(within(dialog).getByRole("button", { name: "Continue" }));
    const destination = within(dialog).getByLabelText("Destination Site");
    expect(within(destination).queryByRole("option", { name: "Quarry" })).not.toBeInTheDocument();
    expect(within(destination).getByRole("option", { name: "Yard" })).toBeInTheDocument();
    fireEvent.change(destination, { target: { value: "site-2" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Review changes" }));
    await within(dialog).findByText("Deploy Big digger to Yard");
    fireEvent.click(within(dialog).getByRole("button", { name: "Move asset" }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/owner/operations/execute",
      expect.objectContaining({ method: "POST" }),
    ));
    const executeCall = apiRequest.mock.calls.find(([path]) => path.endsWith("/execute"));
    expect(JSON.parse(executeCall?.[1]?.body as string)).toEqual(expect.objectContaining({
      action: "MOVE_DEPLOYMENT",
      asset_id: deployedMachine.id,
      target_site_id: siteTwo.id,
      state_token: "a".repeat(64),
    }));
  });

  it("shows a relationship-aware simple removal wizard", async () => {
    const apiRequest = operationApi(() => operationPlan("REMOVE_DEPLOYMENT", {
      planned_changes: ["Remove Big digger from Quarry", "Preserve deployment and operational history"],
    }));
    render(<DeploymentsPanel assets={[deployedMachine]} sites={[siteOne]} people={[]} {...common(apiRequest)} />);

    fireEvent.click(screen.getByRole("button", { name: "Remove deployment" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove Big digger from Site" });
    expect(dialog).toHaveTextContent("Big digger");
    expect(dialog).toHaveTextContent("Quarry");
    const progress = within(dialog).getByRole("list", { name: "Operation progress" });
    expect(progress).toHaveTextContent("Current state");
    expect(progress).toHaveTextContent("Choose changes");
    expect(progress).toHaveTextContent("Review");
    expect(progress).toHaveTextContent("Result");
    fireEvent.click(within(dialog).getByRole("button", { name: "Continue" }));
    expect(within(dialog).getByRole("button", { name: "Remove asset from Site" })).toBeEnabled();
  });

  it("shows cascading assignment and deployment changes before removal", async () => {
    const apiRequest = operationApi(() => operationPlan("REMOVE_DEPLOYMENT", {
      title: "Remove BENZ-1 from Site",
      current_state: [{ kind: "ASSET", id: assignedTipper.id, label: "BENZ-1", status: "ACTIVE", details: {} }],
      dependencies: [
        { kind: "DEPLOYMENT", id: "deployment-1", label: "Quarry", status: "ACTIVE", details: { site_id: siteOne.id } },
        { kind: "ASSIGNMENT", id: "assignment-1", label: "Operator Active", status: "OFF_DUTY", details: { asset_id: assignedTipper.id } },
      ],
      planned_changes: ["End Operator Active's assignment to BENZ-1", "Remove BENZ-1 from Quarry", "Preserve operational history"],
    }));
    render(<DeploymentsPanel assets={[assignedTipper]} sites={[siteOne]} people={[activeDriver]} {...common(apiRequest)} />);

    fireEvent.click(screen.getByRole("button", { name: "Remove deployment" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove BENZ-1 from Site" });
    expect(dialog).toHaveTextContent("Operator Active");
    expect(dialog).toHaveTextContent("OFF DUTY");
    fireEvent.click(within(dialog).getByRole("button", { name: "Continue" }));
    expect(dialog).toHaveTextContent("End Operator Active's assignment to BENZ-1");
    expect(dialog).toHaveTextContent("Remove BENZ-1 from Quarry");
  });

  it("executes removal with the reviewed state token and refreshes Owner data", async () => {
    const apiRequest = operationApi(() => operationPlan("REMOVE_DEPLOYMENT", {
      planned_changes: ["Remove Big digger from Quarry"],
    }));
    const props = common(apiRequest);
    render(<DeploymentsPanel assets={[deployedMachine]} sites={[siteOne]} people={[]} {...props} />);

    fireEvent.click(screen.getByRole("button", { name: "Remove deployment" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove Big digger from Site" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Continue" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove asset from Site" }));

    await waitFor(() => expect(props.reload).toHaveBeenCalledOnce());
    const executeCall = apiRequest.mock.calls.find(([path]) => path.endsWith("/execute"));
    expect(JSON.parse(executeCall?.[1]?.body as string)).toEqual(expect.objectContaining({
      action: "REMOVE_DEPLOYMENT",
      asset_id: deployedMachine.id,
      state_token: "a".repeat(64),
    }));
    expect(await within(dialog).findByText("Operation completed successfully.")).toBeInTheDocument();
  });

  it("blocks active-duty removal and offers the active assignment", async () => {
    const apiRequest = operationApi(() => operationPlan("REMOVE_DEPLOYMENT", {
      title: "Remove BENZ-1 from Site",
      current_state: [{ kind: "ASSET", id: assignedTipper.id, label: "BENZ-1", status: "ACTIVE", details: {} }],
      dependencies: [
        { kind: "ASSIGNMENT", id: "assignment-1", label: "Operator Active", status: "ON_DUTY", details: {} },
        { kind: "DUTY", id: "duty-1", label: "Active duty", status: "ACTIVE", details: {} },
      ],
      blocked_reasons: ["The active duty must be resolved before deployment can be removed."],
      can_execute: false,
    }));
    const onViewAssignments = vi.fn();
    render(<DeploymentsPanel assets={[assignedTipper]} sites={[siteOne]} people={[{ ...activeDriver, has_active_duty: true }]} onViewAssignments={onViewAssignments} {...common(apiRequest)} />);

    fireEvent.click(screen.getByRole("button", { name: "Remove deployment" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove BENZ-1 from Site" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Continue" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("The active duty must be resolved");
    expect(within(dialog).getByRole("button", { name: "Remove asset from Site" })).toBeDisabled();
    fireEvent.click(within(dialog).getByRole("button", { name: "View active assignment / duty" }));
    expect(onViewAssignments).toHaveBeenCalledOnce();
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });

  it("cancels deployment removal without sending a mutation", async () => {
    const apiRequest = operationApi(() => operationPlan("REMOVE_DEPLOYMENT"));
    const props = common(apiRequest);
    render(<DeploymentsPanel assets={[deployedMachine]} sites={[siteOne]} people={[]} {...props} />);

    fireEvent.click(screen.getByRole("button", { name: "Remove deployment" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove Big digger from Site" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog", { name: "Remove Big digger from Site" })).not.toBeInTheDocument();
    expect(apiRequest.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(false);
    expect(props.reload).not.toHaveBeenCalled();
  });

  it("explains a stale backend without exposing raw Not Found and can retry", async () => {
    const apiRequest = operationApi(() => operationPlan("REMOVE_DEPLOYMENT"));
    apiRequest.mockRejectedValueOnce(new ApiError(404, "Not Found"));
    render(<DeploymentsPanel assets={[deployedMachine]} sites={[siteOne]} people={[]} {...common(apiRequest)} />);

    fireEvent.click(screen.getByRole("button", { name: "Remove deployment" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove asset from Site" });
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Server update required");
    expect(dialog).toHaveTextContent("This management action is not supported by the currently running Fleet Manager server. Update the Fleet Manager server and try again.");
    expect(within(dialog).queryByText("Not Found")).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Continue" })).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Close" })).toBeEnabled();

    fireEvent.click(within(dialog).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Continue" })).toBeEnabled());
    expect(apiRequest).toHaveBeenCalledTimes(2);
  });

  it("distinguishes a missing business record from an unavailable route", async () => {
    const apiRequest = operationApi(() => operationPlan("REMOVE_DEPLOYMENT"));
    apiRequest.mockRejectedValueOnce(new ApiError(404, "Asset was not found", "NOT_FOUND"));
    render(<DeploymentsPanel assets={[deployedMachine]} sites={[siteOne]} people={[]} {...common(apiRequest)} />);

    fireEvent.click(screen.getByRole("button", { name: "Remove deployment" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove asset from Site" });
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Record unavailable");
    expect(dialog).toHaveTextContent("This record no longer exists or its state changed. Refresh and try again.");
    expect(dialog).not.toHaveTextContent("Server update required");
    expect(dialog).not.toHaveTextContent("Asset was not found");
    expect(within(dialog).queryByRole("button", { name: "Continue" })).not.toBeInTheDocument();
  });

  it("keeps the wizard safe and displays a stale-state conflict", async () => {
    const apiRequest = operationApi(
      () => operationPlan("REMOVE_DEPLOYMENT"),
      new Error("State changed. Review the operation again."),
    );
    render(<DeploymentsPanel assets={[deployedMachine]} sites={[siteOne]} people={[]} {...common(apiRequest)} />);

    fireEvent.click(screen.getByRole("button", { name: "Remove deployment" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove Big digger from Site" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Continue" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove asset from Site" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("State changed. Review the operation again.");
    expect(within(dialog).getByRole("button", { name: "Review again" })).toBeEnabled();
    expect(screen.getByRole("dialog", { name: "Remove Big digger from Site" })).toBeInTheDocument();
  });

  it("shows invited lifecycle meaning in the People table", () => {
    const props = common();
    render(<PeoplePanel people={[invitedDriver, activeDriver]} assets={[assignedTipper]} {...props} />);

    expect(screen.getByRole("table", { name: "People" })).toBeInTheDocument();
    expect(screen.getByText("Saved and assignable; first login/onboarding is not yet complete.")).toBeInTheDocument();
    expect(screen.getByText("Operator Invited")).toBeInTheDocument();
    expect(screen.getAllByText("INVITED").length).toBeGreaterThan(0);
  });

  it("groups one identity's memberships and grants another role through the normal Owner API", async () => {
    const apiRequest = vi.fn().mockResolvedValue({});
    const props = common(apiRequest);
    render(<PeoplePanel people={[activeOwner, activeDriver]} assets={[]} {...props} />);

    const table = screen.getByRole("table", { name: "People" });
    expect(within(table).getAllByRole("row")).toHaveLength(2);
    expect(within(table).getByText("Owner")).toBeInTheDocument();
    expect(within(table).getByText("DRIVER")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sort by Role(s)" }));
    expect(screen.getByRole("columnheader", { name: /Role\(s\)/ })).toHaveAttribute("aria-sort", "ascending");

    fireEvent.click(screen.getByRole("button", { name: "Manage person" }));
    const dialog = screen.getByRole("dialog", { name: "Manage Operator Active" });
    expect(within(dialog).getByText("Sole Owner protection is enforced by the server.")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Add Supervisor" }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("/api/v1/owner/people/invite", {
      method: "POST",
      body: JSON.stringify({ phone: activeDriver.phone, display_name: activeDriver.display_name, role: "SUPERVISOR" }),
    }));
  });

  it("reviews and assigns an INVITED Driver / Operator to a deployed rented machine", async () => {
    const apiRequest = operationApi(() => operationPlan("ASSIGN_DRIVER", {
      title: "Assign Operator Invited",
      dependencies: [
        { kind: "DEPLOYMENT", id: "deployment-1", label: "Quarry", status: "ACTIVE", details: { site_id: siteOne.id } },
        { kind: "DRIVER", id: invitedDriver.membership_id, label: invitedDriver.display_name, status: "INVITED", details: {} },
      ],
      planned_changes: ["Assign Operator Invited to Big digger at Quarry"],
    }));
    const props = common(apiRequest);
    render(<AssignmentsPanel assets={[deployedMachine, undeployedGrader, assignedTipper]} people={[invitedDriver, activeDriver]} sites={[siteOne]} {...props} />);

    const assetSelect = screen.getByLabelText("Assignment asset");
    expect(within(assetSelect).getByRole("option", { name: /Big digger/ })).toBeInTheDocument();
    expect(within(assetSelect).getByRole("option", { name: /Road grader.*Undeployed/ })).toBeInTheDocument();
    expect(within(assetSelect).queryByRole("option", { name: /BENZ-1/ })).not.toBeInTheDocument();

    fireEvent.change(assetSelect, { target: { value: "asset-deployed" } });
    const candidate = screen.getByRole("option", { name: "Operator Invited · +919100000001 · INVITED" });
    fireEvent.change(screen.getByLabelText("Driver / Operator"), { target: { value: candidate.getAttribute("value") } });
    fireEvent.click(screen.getByRole("button", { name: "Review assignment" }));

    const dialog = await screen.findByRole("dialog", { name: "Assign Operator Invited" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Continue" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Review changes" }));
    await within(dialog).findByText("Assign Operator Invited to Big digger at Quarry");
    fireEvent.click(within(dialog).getByRole("button", { name: "Assign Driver / Operator" }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/owner/operations/execute",
      expect.objectContaining({ method: "POST" }),
    ));
    const executeCall = apiRequest.mock.calls.find(([path]) => path.endsWith("/execute"));
    expect(JSON.parse(executeCall?.[1]?.body as string)).toEqual(expect.objectContaining({
      action: "ASSIGN_DRIVER",
      asset_id: deployedMachine.id,
      driver_membership_id: invitedDriver.membership_id,
      site_id: siteOne.id,
      regular_duty_minutes: 600,
    }));
  });

  it("renders current assignment details and reviews ending the relationship", async () => {
    const apiRequest = operationApi(() => operationPlan("END_ASSIGNMENT", {
      title: "End Operator Active assignment",
      current_state: [{ kind: "ASSET", id: assignedTipper.id, label: "BENZ-1", status: "ACTIVE", details: {} }],
      dependencies: [{ kind: "ASSIGNMENT", id: "assignment-1", label: "Operator Active", status: "OFF_DUTY", details: {} }],
      planned_changes: ["End Operator Active's assignment to BENZ-1"],
    }));
    const props = common(apiRequest);
    render(<AssignmentsPanel assets={[assignedTipper]} people={[{ ...activeDriver, current_asset_id: assignedTipper.id, current_asset_code: assignedTipper.asset_code, current_site_id: "site-1", current_site_name: "Quarry", has_active_assignment: true }]} sites={[siteOne]} {...props} />);

    const table = screen.getByRole("table", { name: "Current assignments" });
    fireEvent.click(screen.getByRole("button", { name: "Sort by Phone" }));
    expect(screen.getByRole("columnheader", { name: /Phone/ })).toHaveAttribute("aria-sort", "ascending");
    expect(table).toHaveTextContent("BENZ-1");
    expect(table).toHaveTextContent("+919100000002");
    expect(table).toHaveTextContent("10 hours");
    fireEvent.click(screen.getByRole("button", { name: "End assignment" }));
    const dialog = await screen.findByRole("dialog", { name: "End Operator Active assignment" });
    expect(dialog).toHaveTextContent("Operator Active");
    fireEvent.click(within(dialog).getByRole("button", { name: "Continue" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "End assignment" }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/owner/operations/execute",
      expect.objectContaining({ method: "POST" }),
    ));
  });

  it("changes a Driver / Operator through the shared relationship wizard", async () => {
    const apiRequest = operationApi((intent) => operationPlan("REASSIGN_DRIVER", {
      title: "Change Driver / Operator on BENZ-1",
      current_state: [{ kind: "ASSET", id: assignedTipper.id, label: "BENZ-1", status: "ACTIVE", details: {} }],
      dependencies: [
        { kind: "DEPLOYMENT", id: "deployment-1", label: "Quarry", status: "ACTIVE", details: {} },
        { kind: "ASSIGNMENT", id: "assignment-1", label: "Operator Active", status: "OFF_DUTY", details: { driver_membership_id: activeDriver.membership_id } },
        ...(intent.driver_membership_id ? [{ kind: "REPLACEMENT_DRIVER", id: invitedDriver.membership_id, label: "Operator Invited", status: "INVITED", details: {} }] : []),
      ],
      blocked_reasons: intent.driver_membership_id ? [] : ["Choose a new Driver / Operator."],
      planned_changes: intent.driver_membership_id ? ["End Operator Active's assignment to BENZ-1", "Assign Operator Invited to BENZ-1 at Quarry"] : ["End Operator Active's assignment to BENZ-1"],
      can_execute: Boolean(intent.driver_membership_id),
    }));
    render(<AssignmentsPanel assets={[assignedTipper]} people={[activeDriver, invitedDriver]} sites={[siteOne]} {...common(apiRequest)} />);

    fireEvent.click(screen.getByRole("button", { name: "Change Driver / Operator" }));
    const dialog = await screen.findByRole("dialog", { name: "Change Driver / Operator on BENZ-1" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Continue" }));
    const replacement = within(dialog).getByLabelText("Replacement Driver / Operator");
    expect(within(replacement).queryByRole("option", { name: /Operator Active/ })).not.toBeInTheDocument();
    fireEvent.change(replacement, { target: { value: invitedDriver.membership_id } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Review changes" }));
    await within(dialog).findByText("Assign Operator Invited to BENZ-1 at Quarry");
    fireEvent.click(within(dialog).getByRole("button", { name: "Change Driver / Operator" }));

    const executeCall = await waitFor(() => apiRequest.mock.calls.find(([path]) => path.endsWith("/execute")));
    expect(JSON.parse(executeCall?.[1]?.body as string)).toEqual(expect.objectContaining({
      action: "REASSIGN_DRIVER",
      asset_id: assignedTipper.id,
      driver_membership_id: invitedDriver.membership_id,
    }));
  });
});
