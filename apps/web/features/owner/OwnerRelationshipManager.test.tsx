import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, type WebRequest } from "../../lib/api/client";
import type {
  OwnerAsset,
  OwnerOperationIntent,
  OwnerOperationPlan,
  OwnerOperationResult,
  OwnerPerson,
  OwnerSite,
} from "../../lib/types";
import { OwnerRelationshipManager, type OwnerRelationshipManagerProps } from "./OwnerRelationshipManager";

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
  asset_count: 2,
};

const siteTwo: OwnerSite = {
  ...siteOne,
  id: "site-2",
  name: "Central Yard Project",
  short_name: "Yard",
  code: "SITE-TWO",
  asset_count: 0,
};

const currentDriver: OwnerPerson = {
  user_id: "user-current",
  membership_id: "driver-current",
  phone: "+919100000001",
  display_name: "Basavaraj Koli",
  role: "DRIVER",
  status: "ACTIVE",
  sites: [],
  has_active_assignment: true,
  has_active_duty: false,
  current_asset_id: "asset-tipper",
  current_asset_code: "TIP-INTERNAL",
  current_site_id: siteOne.id,
  current_site_name: "Quarry",
};

const availableDriver: OwnerPerson = {
  ...currentDriver,
  user_id: "user-available",
  membership_id: "driver-available",
  phone: "+919100000002",
  display_name: "Asha Singh",
  status: "INVITED",
  has_active_assignment: false,
  current_asset_id: null,
  current_asset_code: null,
  current_site_id: null,
  current_site_name: null,
};

const inactiveDriver: OwnerPerson = {
  ...availableDriver,
  user_id: "user-inactive",
  membership_id: "driver-inactive",
  phone: "+919100000003",
  display_name: "Kiran Rao",
  status: "INACTIVE",
};

const supervisor: OwnerPerson = {
  ...availableDriver,
  user_id: "user-supervisor",
  membership_id: "supervisor-1",
  display_name: "Meera Shah",
  role: "SUPERVISOR",
  status: "ACTIVE",
  sites: [{ site_id: siteOne.id, site_name: "Quarry" }],
};

const tipper: OwnerAsset = {
  id: "asset-tipper",
  asset_code: "TIP-INTERNAL",
  asset_type: "TIPPER",
  ownership_type: "RENTED",
  registration_number: "MH01AM1234",
  short_name: "ABHI-BENZ",
  manufacturer: "BharatBenz",
  model: "2823C",
  chassis_number: "MA1XXXXXXXX",
  engine_number: "E4XXXXXX",
  status: "ACTIVE",
  rental_party_name: "Roadworks Hire",
  rental_owner_phone_primary: "+919876543210",
  rental_owner_phone_secondary: null,
  rental_start_date: "2026-01-01",
  rental_end_date: null,
  current_deployment: {
    id: "deployment-1",
    asset_id: "asset-tipper",
    site_id: siteOne.id,
    site_name: "Quarry",
    starts_at: "2026-01-01T00:00:00Z",
    ends_at: null,
  },
  has_active_assignment: true,
  active_assignment: {
    assignment_id: "assignment-1",
    site_id: siteOne.id,
    site_name: "Quarry",
    driver_membership_id: currentDriver.membership_id,
    driver_name: currentDriver.display_name,
    driver_phone: currentDriver.phone,
    starts_at: "2026-01-02T00:00:00Z",
    regular_duty_minutes: 600,
  },
};

const deployedExcavator: OwnerAsset = {
  ...tipper,
  id: "asset-excavator",
  asset_code: "EXC-INTERNAL",
  asset_type: "EXCAVATOR",
  ownership_type: "OWNED",
  registration_number: null,
  short_name: "North excavator",
  rental_party_name: null,
  rental_owner_phone_primary: null,
  rental_owner_phone_secondary: null,
  rental_start_date: null,
  has_active_assignment: false,
  active_assignment: null,
  current_deployment: {
    ...tipper.current_deployment!,
    id: "deployment-2",
    asset_id: "asset-excavator",
  },
};

const undeployedGrader: OwnerAsset = {
  ...deployedExcavator,
  id: "asset-grader",
  asset_code: "GRD-INTERNAL",
  asset_type: "GRADER",
  short_name: "Road grader",
  current_deployment: null,
};

const inactiveGrader: OwnerAsset = {
  ...undeployedGrader,
  id: "asset-grader-inactive",
  asset_code: "GRD-INACTIVE",
  status: "INACTIVE",
};

function defaultPlan(intent: OwnerOperationIntent): OwnerOperationPlan {
  return {
    action: intent.action,
    state_token: `token-${intent.action}`,
    title: "Prepared relationship change",
    summary: "The authoritative current state was reviewed.",
    current_state: [{ kind: "ASSET", id: intent.asset_id ?? "person", label: "Current record", status: "ACTIVE", details: {} }],
    dependencies: [],
    warnings: [],
    allowed_resolutions: [],
    blocked_reasons: [],
    planned_changes: [`Apply ${intent.action}`],
    can_execute: true,
  };
}

function operationApi(
  planFor: (intent: OwnerOperationIntent) => OwnerOperationPlan = defaultPlan,
  executeError?: Error,
) {
  return vi.fn((path: string, options?: RequestInit) => {
    const body = options?.body ? JSON.parse(options.body as string) as OwnerOperationIntent & { state_token?: string } : null;
    if (path.endsWith("/preview") && body) return Promise.resolve(planFor(body));
    if (path.endsWith("/execute") && body) {
      if (executeError) return Promise.reject(executeError);
      const result: OwnerOperationResult = {
        action: body.action,
        completed_changes: [`Applied ${body.action}`],
        message: "Relationship updated.",
      };
      return Promise.resolve(result);
    }
    return Promise.resolve({});
  });
}

function managerProps(overrides: Partial<OwnerRelationshipManagerProps> = {}) {
  return {
    target: { kind: "asset", assetId: tipper.id } as const,
    assets: [tipper, deployedExcavator, undeployedGrader, inactiveGrader],
    people: [currentDriver, availableDriver, inactiveDriver, supervisor],
    sites: [siteOne, siteTwo],
    apiRequest: operationApi() as unknown as WebRequest,
    onClose: vi.fn(),
    onComplete: vi.fn(),
    ...overrides,
  } satisfies OwnerRelationshipManagerProps;
}

function requestBodies(apiRequest: ReturnType<typeof operationApi>, suffix: "/preview" | "/execute") {
  return apiRequest.mock.calls
    .filter(([path]) => path.endsWith(suffix))
    .map(([, options]) => JSON.parse(options?.body as string) as OwnerOperationIntent & { state_token?: string });
}

function expectNoNormalWizard(dialog: HTMLElement) {
  expect(within(dialog).queryByRole("list", { name: "Operation progress" })).not.toBeInTheDocument();
  expect(within(dialog).queryByRole("button", { name: "Continue" })).not.toBeInTheDocument();
  expect(within(dialog).queryByRole("button", { name: "Review changes" })).not.toBeInTheDocument();
  expect(within(dialog).queryByText("Current state", { exact: true })).not.toBeInTheDocument();
  expect(within(dialog).queryByText("Result", { exact: true })).not.toBeInTheDocument();
  expect(within(dialog).queryByText("Done", { exact: true })).not.toBeInTheDocument();
}

afterEach(cleanup);

describe("Owner relationship manager", () => {
  it("shows off-duty identity, activity, simple selectors, and saves a Driver change with the preview token", async () => {
    const apiRequest = operationApi();
    const onEditAsset = vi.fn();
    const props = managerProps({ apiRequest: apiRequest as unknown as WebRequest, onEditAsset });
    render(<OwnerRelationshipManager {...props} />);

    const dialog = screen.getByRole("dialog", { name: "ABHI-BENZ" });
    expect(dialog).toHaveTextContent(/MH01AM1234 · TIPPER · RENTED/i);
    const activity = within(dialog).getByRole("region", { name: "Asset activity" });
    expect(activity).toHaveTextContent("Off duty");
    expect(activity).toHaveTextContent("Basavaraj Koli");
    expect(activity).toHaveTextContent("Quarry");
    const technicalDetails = within(dialog).getByRole("region", { name: "Technical details" });
    expect(technicalDetails).toHaveTextContent("MA1XXXXXXXX");
    expect(technicalDetails).toHaveTextContent("E4XXXXXX");
    fireEvent.click(within(technicalDetails).getByRole("button", { name: "Edit asset details" }));
    expect(onEditAsset).toHaveBeenCalledWith(tipper.id);
    expect(within(dialog).getByLabelText("Driver / Operator")).toHaveValue(currentDriver.membership_id);
    expect(within(dialog).getByLabelText("Site")).toHaveValue(siteOne.id);
    expectNoNormalWizard(dialog);

    fireEvent.change(within(dialog).getByLabelText("Driver / Operator"), { target: { value: availableDriver.membership_id } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    const confirmation = await screen.findByRole("dialog", { name: "Change Driver / Operator?" });
    expectNoNormalWizard(confirmation);
    fireEvent.click(within(confirmation).getByRole("button", { name: "Change Driver" }));

    await waitFor(() => expect(props.onComplete).toHaveBeenCalledWith("Relationship updated."));
    expect(requestBodies(apiRequest, "/preview")).toContainEqual(expect.objectContaining({
      action: "REASSIGN_DRIVER",
      asset_id: tipper.id,
      driver_membership_id: availableDriver.membership_id,
      activate_membership: false,
      regular_duty_minutes: 600,
    }));
    expect(requestBodies(apiRequest, "/execute")).toContainEqual(expect.objectContaining({
      action: "REASSIGN_DRIVER",
      asset_id: tipper.id,
      driver_membership_id: availableDriver.membership_id,
      state_token: "token-REASSIGN_DRIVER",
    }));
  });

  it("moves an off-duty asset while keeping its Driver through one concise confirmation", async () => {
    const apiRequest = operationApi();
    render(<OwnerRelationshipManager {...managerProps({ apiRequest: apiRequest as unknown as WebRequest })} />);

    const dialog = screen.getByRole("dialog", { name: "ABHI-BENZ" });
    fireEvent.change(within(dialog).getByLabelText("Site"), { target: { value: siteTwo.id } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    const confirmation = await screen.findByRole("dialog", { name: "Move ABHI-BENZ?" });
    expect(confirmation).toHaveTextContent("Basavaraj Koli will remain assigned at the new Site.");
    expectNoNormalWizard(confirmation);
    fireEvent.click(within(confirmation).getByRole("button", { name: "Move Asset" }));

    await waitFor(() => expect(requestBodies(apiRequest, "/execute")).toHaveLength(1));
    expect(requestBodies(apiRequest, "/preview")[0]).toEqual(expect.objectContaining({
      action: "MOVE_DEPLOYMENT",
      asset_id: tipper.id,
      target_site_id: siteTwo.id,
      assignment_action: "KEEP",
    }));
    expect(requestBodies(apiRequest, "/execute")[0]).toEqual(expect.objectContaining({
      action: "MOVE_DEPLOYMENT",
      state_token: "token-MOVE_DEPLOYMENT",
    }));
  });

  it("removes an off-duty deployment and deactivates an off-duty asset with one confirmation each", async () => {
    const removeApi = operationApi();
    render(<OwnerRelationshipManager {...managerProps({
      apiRequest: removeApi as unknown as WebRequest,
      target: { kind: "asset", assetId: tipper.id, presetSiteId: null, presetDriverId: null, initialAction: "REMOVE_DEPLOYMENT" },
    })} />);
    let dialog = screen.getByRole("dialog", { name: "ABHI-BENZ" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    let confirmation = await screen.findByRole("dialog", { name: "Remove ABHI-BENZ from Site?" });
    expect(confirmation).toHaveTextContent("ends the current deployment and any off-duty assignment together");
    fireEvent.click(within(confirmation).getByRole("button", { name: "Remove from Site" }));
    await waitFor(() => expect(requestBodies(removeApi, "/execute")[0]).toEqual(expect.objectContaining({
      action: "REMOVE_DEPLOYMENT",
      asset_id: tipper.id,
      state_token: "token-REMOVE_DEPLOYMENT",
    })));
    cleanup();

    const deactivateApi = operationApi();
    render(<OwnerRelationshipManager {...managerProps({ apiRequest: deactivateApi as unknown as WebRequest })} />);
    dialog = screen.getByRole("dialog", { name: "ABHI-BENZ" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Deactivate asset" }));
    confirmation = await screen.findByRole("dialog", { name: "Deactivate ABHI-BENZ?" });
    expect(confirmation).toHaveTextContent("off-duty assignment and Site deployment will end together");
    expectNoNormalWizard(confirmation);
    fireEvent.click(within(confirmation).getByRole("button", { name: "Deactivate" }));
    await waitFor(() => expect(requestBodies(deactivateApi, "/execute")[0]).toEqual(expect.objectContaining({
      action: "DEACTIVATE_ASSET",
      asset_id: tipper.id,
      state_token: "token-DEACTIVATE_ASSET",
    })));
  });

  it("cancels destructive deactivation without sending an execute request or reporting completion", async () => {
    const apiRequest = operationApi();
    const props = managerProps({ apiRequest: apiRequest as unknown as WebRequest });
    render(<OwnerRelationshipManager {...props} />);

    fireEvent.click(screen.getByRole("button", { name: "Deactivate asset" }));
    const confirmation = await screen.findByRole("dialog", { name: "Deactivate ABHI-BENZ?" });
    fireEvent.click(within(confirmation).getByRole("button", { name: "Cancel" }));

    expect(screen.getByRole("dialog", { name: "ABHI-BENZ" })).toBeInTheDocument();
    expect(requestBodies(apiRequest, "/preview")).toHaveLength(1);
    expect(requestBodies(apiRequest, "/execute")).toHaveLength(0);
    expect(props.onComplete).not.toHaveBeenCalled();
    expect(props.onClose).not.toHaveBeenCalled();
  });

  it("surfaces a concise stale-state message after an execute conflict without false completion", async () => {
    const apiRequest = operationApi(defaultPlan, new ApiError(409, "State token mismatch", "CONFLICT"));
    const props = managerProps({ apiRequest: apiRequest as unknown as WebRequest });
    render(<OwnerRelationshipManager {...props} />);

    fireEvent.click(screen.getByRole("button", { name: "Deactivate asset" }));
    const confirmation = await screen.findByRole("dialog", { name: "Deactivate ABHI-BENZ?" });
    fireEvent.click(within(confirmation).getByRole("button", { name: "Deactivate" }));

    const manager = await screen.findByRole("dialog", { name: "ABHI-BENZ" });
    expect(within(manager).getByRole("alert")).toHaveTextContent("State changed. Refresh and try again.");
    expect(manager).not.toHaveTextContent("State token mismatch");
    expect(requestBodies(apiRequest, "/execute")).toHaveLength(1);
    expect(props.onComplete).not.toHaveBeenCalled();
    expect(props.onClose).not.toHaveBeenCalled();
  });

  it("translates a route-level preview 404 and permits a safe retry", async () => {
    const apiRequest = operationApi();
    apiRequest.mockRejectedValueOnce(new ApiError(404, "Not Found"));
    const props = managerProps({ apiRequest: apiRequest as unknown as WebRequest });
    render(<OwnerRelationshipManager {...props} />);

    fireEvent.click(screen.getByRole("button", { name: "Deactivate asset" }));
    const manager = screen.getByRole("dialog", { name: "ABHI-BENZ" });
    expect(await within(manager).findByRole("alert")).toHaveTextContent("Fleet Manager server must be updated before this action can be used.");
    expect(manager).not.toHaveTextContent("Not Found");
    expect(within(manager).getByRole("button", { name: "Deactivate asset" })).toBeEnabled();
    expect(requestBodies(apiRequest, "/execute")).toHaveLength(0);

    fireEvent.click(within(manager).getByRole("button", { name: "Deactivate asset" }));
    const confirmation = await screen.findByRole("dialog", { name: "Deactivate ABHI-BENZ?" });
    expect(confirmation).toHaveTextContent("Relationship history will be preserved.");
    fireEvent.click(within(confirmation).getByRole("button", { name: "Cancel" }));
    expect(requestBodies(apiRequest, "/execute")).toHaveLength(0);
  });

  it("maps backend Driver and Site blockers to their affected inline fields", async () => {
    const apiRequest = operationApi((intent) => ({
      ...defaultPlan(intent),
      blocked_reasons: [
        "The selected Driver / Operator is no longer eligible.",
        "The selected Site is no longer active.",
      ],
      can_execute: false,
    }));
    render(<OwnerRelationshipManager {...managerProps({
      apiRequest: apiRequest as unknown as WebRequest,
      target: { kind: "asset", assetId: inactiveGrader.id, initialAction: "REACTIVATE_ASSET" },
    })} />);

    const dialog = screen.getByRole("dialog", { name: "Road grader" });
    const driverField = within(dialog).getByLabelText("Driver / Operator").closest("label");
    const siteField = within(dialog).getByLabelText("Site").closest("label");
    fireEvent.change(within(dialog).getByLabelText("Driver / Operator"), { target: { value: availableDriver.membership_id } });
    fireEvent.change(within(dialog).getByLabelText("Site"), { target: { value: siteTwo.id } });
    fireEvent.click(within(dialog).getByRole("button", { name: "REACTIVATE & SET UP" }));

    await waitFor(() => expect(requestBodies(apiRequest, "/preview")).toHaveLength(1));
    expect(driverField).toHaveTextContent("The selected Driver / Operator is no longer eligible.");
    expect(siteField).toHaveTextContent("The selected Site is no longer active.");
    expect(requestBodies(apiRequest, "/execute")).toHaveLength(0);
  });

  it("locks ordinary on-duty edits but provides the Owner warning, reason, and final force-close confirmation", async () => {
    const onDutyDriver = { ...currentDriver, has_active_duty: true };
    const apiRequest = operationApi((intent) => ({
      ...defaultPlan(intent),
      dependencies: intent.action === "DEACTIVATE_ASSET"
        ? [{ kind: "DUTY", id: "duty-1", label: "Active duty", status: "ACTIVE", details: { started_at: "2026-10-08T02:45:00Z" } }]
        : [],
      blocked_reasons: intent.action === "DEACTIVATE_ASSET" ? ["The active duty must be resolved first."] : [],
      can_execute: intent.action !== "DEACTIVATE_ASSET",
    }));
    const forceClose = vi.fn().mockResolvedValue("Duty force-closed and asset deactivated.");
    const viewDuty = vi.fn();
    const props = managerProps({
      apiRequest: apiRequest as unknown as WebRequest,
      people: [onDutyDriver, availableDriver, inactiveDriver, supervisor],
      onForceCloseDutyAndDeactivate: forceClose,
      onViewActiveDuty: viewDuty,
    });
    render(<OwnerRelationshipManager {...props} />);

    let dialog = screen.getByRole("dialog", { name: "ABHI-BENZ" });
    const activity = within(dialog).getByRole("region", { name: "Asset activity" });
    expect(activity).toHaveTextContent("On duty");
    expect(activity).toHaveTextContent("Basavaraj Koli");
    expect(activity).toHaveTextContent("Quarry");
    expect(within(dialog).getByLabelText("Driver / Operator")).toBeDisabled();
    expect(within(dialog).getByLabelText("Site")).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "Save changes" })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "Deactivate asset" })).toBeEnabled();
    expect(within(dialog).getByRole("button", { name: "VIEW ACTIVE DUTY" })).toBeEnabled();

    fireEvent.click(within(dialog).getByRole("button", { name: "Deactivate asset" }));
    dialog = screen.getByRole("dialog", { name: "Deactivate ABHI-BENZ" });
    expect(dialog).toHaveTextContent("This asset currently has an active duty.");
    expect(dialog).toHaveTextContent("Basavaraj Koli");
    expect(dialog).toHaveTextContent("Quarry");
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeEnabled();
    expect(within(dialog).getByRole("button", { name: "View duty" })).toBeEnabled();
    expect(within(dialog).getByRole("button", { name: "Force close duty & deactivate" })).toBeEnabled();
    expect(within(dialog).queryByLabelText("Force-close reason")).not.toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: "Force close duty & deactivate" }));
    dialog = screen.getByRole("dialog", { name: "Why must this duty be force-closed?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Continue" }));
    expect(within(dialog).getAllByRole("alert")[0]).toHaveTextContent("Enter a reason for force-closing this duty.");
    fireEvent.change(within(dialog).getByLabelText("Force-close reason"), { target: { value: "  Driver forgot to end duty  " } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Continue" }));

    dialog = screen.getByRole("dialog", { name: "Force close duty & deactivate ABHI-BENZ?" });
    expect(dialog).toHaveTextContent("Force close Basavaraj Koli's active duty");
    expect(dialog).toHaveTextContent("Mark END KM as missing");
    expect(dialog).toHaveTextContent("End the current Driver / Operator assignment");
    expect(dialog).toHaveTextContent("Remove ABHI-BENZ from Quarry");
    expect(dialog).toHaveTextContent("Deactivate ABHI-BENZ");
    expect(dialog).toHaveTextContent("Preserve all existing history and evidence");
    expect(dialog).toHaveTextContent("Driver forgot to end duty");
    fireEvent.click(within(dialog).getByRole("button", { name: "Force close & deactivate" }));

    await waitFor(() => expect(forceClose).toHaveBeenCalledWith(tipper.id, "Driver forgot to end duty"));
    expect(props.onComplete).toHaveBeenCalledWith("Duty force-closed and asset deactivated.");
    expect(props.onClose).toHaveBeenCalled();
  });

  it("routes View active duty from the locked manager without attempting a relationship mutation", () => {
    const apiRequest = operationApi();
    const viewDuty = vi.fn();
    const onClose = vi.fn();
    render(<OwnerRelationshipManager {...managerProps({
      apiRequest: apiRequest as unknown as WebRequest,
      people: [{ ...currentDriver, has_active_duty: true }, availableDriver],
      onClose,
      onViewActiveDuty: viewDuty,
    })} />);

    const dialog = screen.getByRole("dialog", { name: "ABHI-BENZ" });
    fireEvent.click(within(dialog).getByRole("button", { name: "VIEW ACTIVE DUTY" }));
    expect(onClose).toHaveBeenCalledOnce();
    expect(viewDuty).toHaveBeenCalledWith(tipper.id);
    expect(requestBodies(apiRequest, "/execute")).toHaveLength(0);
  });

  it("reactivates an Asset only, without a Site or Driver, and executes with the preview token", async () => {
    const apiRequest = operationApi();
    render(<OwnerRelationshipManager {...managerProps({
      apiRequest: apiRequest as unknown as WebRequest,
      target: { kind: "asset", assetId: inactiveGrader.id, focus: "lifecycle", initialAction: "REACTIVATE_ASSET" },
    })} />);

    const dialog = screen.getByRole("dialog", { name: "Road grader" });
    expect(within(dialog).getByRole("region", { name: "Asset activity" })).toHaveTextContent("Inactive");
    expectNoNormalWizard(dialog);
    fireEvent.click(within(dialog).getByRole("button", { name: "REACTIVATE ONLY" }));

    await waitFor(() => expect(requestBodies(apiRequest, "/execute")).toHaveLength(1));
    expect(requestBodies(apiRequest, "/preview")[0]).toEqual(expect.objectContaining({
      action: "REACTIVATE_ASSET",
      asset_id: inactiveGrader.id,
      site_id: null,
      driver_membership_id: null,
      activate_membership: false,
    }));
    expect(requestBodies(apiRequest, "/execute")[0]).toEqual(expect.objectContaining({ state_token: "token-REACTIVATE_ASSET" }));
  });

  it("supports Site-only and Site-plus-Driver reactivation without a wizard", async () => {
    const siteOnlyApi = operationApi();
    render(<OwnerRelationshipManager {...managerProps({
      apiRequest: siteOnlyApi as unknown as WebRequest,
      target: { kind: "asset", assetId: inactiveGrader.id, initialAction: "REACTIVATE_ASSET" },
    })} />);
    let dialog = screen.getByRole("dialog", { name: "Road grader" });
    fireEvent.change(within(dialog).getByLabelText("Site"), { target: { value: siteTwo.id } });
    fireEvent.click(within(dialog).getByRole("button", { name: "REACTIVATE & SET UP" }));
    await waitFor(() => expect(requestBodies(siteOnlyApi, "/execute")).toHaveLength(1));
    expect(requestBodies(siteOnlyApi, "/execute")[0]).toEqual(expect.objectContaining({
      action: "REACTIVATE_ASSET",
      site_id: siteTwo.id,
      driver_membership_id: null,
      state_token: "token-REACTIVATE_ASSET",
    }));
    cleanup();

    const setupApi = operationApi();
    render(<OwnerRelationshipManager {...managerProps({
      apiRequest: setupApi as unknown as WebRequest,
      target: { kind: "asset", assetId: inactiveGrader.id, initialAction: "REACTIVATE_ASSET" },
    })} />);
    dialog = screen.getByRole("dialog", { name: "Road grader" });
    fireEvent.change(within(dialog).getByLabelText("Site"), { target: { value: siteOne.id } });
    fireEvent.change(within(dialog).getByLabelText("Driver / Operator"), { target: { value: inactiveDriver.membership_id } });
    const roleChoice = within(dialog).getByRole("checkbox", { name: "Include Driver / Operator role reactivation" });
    expect(roleChoice).not.toBeChecked();
    fireEvent.click(roleChoice);
    fireEvent.click(within(dialog).getByRole("button", { name: "REACTIVATE & SET UP" }));
    await waitFor(() => expect(requestBodies(setupApi, "/execute")).toHaveLength(1));
    expect(requestBodies(setupApi, "/execute")[0]).toEqual(expect.objectContaining({
      action: "REACTIVATE_ASSET",
      site_id: siteOne.id,
      driver_membership_id: inactiveDriver.membership_id,
      activate_membership: true,
      state_token: "token-REACTIVATE_ASSET",
    }));
  });

  it("requires a Site before a Driver can be included in asset reactivation", () => {
    const apiRequest = operationApi();
    render(<OwnerRelationshipManager {...managerProps({
      apiRequest: apiRequest as unknown as WebRequest,
      target: { kind: "asset", assetId: inactiveGrader.id, initialAction: "REACTIVATE_ASSET" },
    })} />);

    const dialog = screen.getByRole("dialog", { name: "Road grader" });
    fireEvent.change(within(dialog).getByLabelText("Driver / Operator"), { target: { value: availableDriver.membership_id } });
    fireEvent.click(within(dialog).getByRole("button", { name: "REACTIVATE & SET UP" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Choose a Site before assigning a Driver / Operator.");
    expect(requestBodies(apiRequest, "/preview")).toHaveLength(0);
  });

  it("assigns and reactivates a Driver from the person manager using state-token execution", async () => {
    const assignApi = operationApi();
    render(<OwnerRelationshipManager {...managerProps({
      apiRequest: assignApi as unknown as WebRequest,
      target: { kind: "person", membershipId: availableDriver.membership_id },
    })} />);
    let dialog = screen.getByRole("dialog", { name: "Asha Singh" });
    fireEvent.change(within(dialog).getByLabelText("Asset"), { target: { value: deployedExcavator.id } });
    expect(dialog).toHaveTextContent("Derived from Asset");
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(requestBodies(assignApi, "/execute")).toHaveLength(1));
    expect(requestBodies(assignApi, "/execute")[0]).toEqual(expect.objectContaining({
      action: "ASSIGN_DRIVER",
      asset_id: deployedExcavator.id,
      driver_membership_id: availableDriver.membership_id,
      site_id: siteOne.id,
      state_token: "token-ASSIGN_DRIVER",
    }));
    cleanup();

    const reactivateApi = operationApi();
    render(<OwnerRelationshipManager {...managerProps({
      apiRequest: reactivateApi as unknown as WebRequest,
      target: { kind: "person", membershipId: inactiveDriver.membership_id },
    })} />);
    dialog = screen.getByRole("dialog", { name: "Kiran Rao" });
    fireEvent.change(within(dialog).getByLabelText("Asset"), { target: { value: undeployedGrader.id } });
    fireEvent.change(within(dialog).getByLabelText("Assignment Site"), { target: { value: siteTwo.id } });
    fireEvent.click(within(dialog).getByRole("button", { name: "REACTIVATE & ASSIGN" }));
    await waitFor(() => expect(requestBodies(reactivateApi, "/execute")).toHaveLength(1));
    expect(requestBodies(reactivateApi, "/execute")[0]).toEqual(expect.objectContaining({
      action: "ACTIVATE_PERSON",
      person_membership_id: inactiveDriver.membership_id,
      asset_id: undeployedGrader.id,
      site_id: siteTwo.id,
      state_token: "token-ACTIVATE_PERSON",
    }));
  });

  it("updates Supervisor Site access and deactivates an off-duty role through concise flows", async () => {
    const apiRequest = operationApi();
    render(<OwnerRelationshipManager {...managerProps({
      apiRequest: apiRequest as unknown as WebRequest,
      target: { kind: "person", membershipId: supervisor.membership_id },
    })} />);

    let dialog = screen.getByRole("dialog", { name: "Meera Shah" });
    expect(within(dialog).getByRole("group", { name: "Site access" })).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Yard" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save access" }));
    await waitFor(() => expect(requestBodies(apiRequest, "/execute")).toHaveLength(1));
    expect(requestBodies(apiRequest, "/execute")[0]).toEqual(expect.objectContaining({
      action: "SET_SUPERVISOR_SITES",
      person_membership_id: supervisor.membership_id,
      selected_site_ids: [siteOne.id, siteTwo.id],
      state_token: "token-SET_SUPERVISOR_SITES",
    }));
    cleanup();

    const deactivateApi = operationApi();
    render(<OwnerRelationshipManager {...managerProps({
      apiRequest: deactivateApi as unknown as WebRequest,
      target: { kind: "person", membershipId: supervisor.membership_id },
    })} />);
    dialog = screen.getByRole("dialog", { name: "Meera Shah" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Deactivate role" }));
    const confirmation = await screen.findByRole("dialog", { name: /Deactivate Meera Shah's Supervisor role\?/i });
    expectNoNormalWizard(confirmation);
    fireEvent.click(within(confirmation).getByRole("button", { name: "Deactivate role" }));
    await waitFor(() => expect(requestBodies(deactivateApi, "/execute")[0]).toEqual(expect.objectContaining({
      action: "DEACTIVATE_PERSON",
      person_membership_id: supervisor.membership_id,
      state_token: "token-DEACTIVATE_PERSON",
    })));
  });
});
