import { expect, test, type Page } from "@playwright/test";

const assets = [
  {
    id: "asset-assigned",
    asset_code: "TIPPER-11111111111111111111111111111111",
    asset_type: "TIPPER",
    ownership_type: "OWNED",
    registration_number: "KA01AB1234",
    short_name: "Green Tipper",
    manufacturer: "BharatBenz",
    model: "2823C",
    chassis_number: "MA1GREEN",
    engine_number: "E4GREEN",
    status: "ACTIVE",
    rental_party_name: null,
    rental_owner_phone_primary: null,
    rental_owner_phone_secondary: null,
    rental_start_date: null,
    rental_end_date: null,
    current_deployment: { id: "deployment-1", asset_id: "asset-assigned", site_id: "site-1", site_name: "North Pit", starts_at: "2026-09-01T04:00:00Z", ends_at: null },
    has_active_assignment: true,
    active_assignment: { assignment_id: "assignment-1", site_id: "site-1", site_name: "North Pit", driver_membership_id: "driver-active", driver_name: "Ravi Kumar", driver_phone: "+919900000001", starts_at: "2026-09-02T04:00:00Z", regular_duty_minutes: 600 },
  },
  {
    id: "asset-unassigned",
    asset_code: "EXCAVATOR-22222222222222222222222222222222",
    asset_type: "EXCAVATOR",
    ownership_type: "RENTED",
    registration_number: null,
    short_name: "North Excavator",
    manufacturer: "Komatsu",
    model: "PC210",
    chassis_number: "LONG-CHASSIS-NUMBER-THAT-WRAPS-CLEANLY-1234567890",
    engine_number: "PC210-ENGINE",
    status: "ACTIVE",
    rental_party_name: "Metro Plant Hire",
    rental_owner_phone_primary: "+919876543210",
    rental_owner_phone_secondary: "+919988776655",
    rental_start_date: "2026-09-01",
    rental_end_date: "2027-03-01",
    current_deployment: { id: "deployment-2", asset_id: "asset-unassigned", site_id: "site-1", site_name: "North Pit", starts_at: "2026-09-03T04:00:00Z", ends_at: null },
    has_active_assignment: false,
    active_assignment: null,
  },
  {
    id: "asset-undeployed",
    asset_code: "ROLLER-33333333333333333333333333333333",
    asset_type: "ROLLER",
    ownership_type: "OWNED",
    registration_number: null,
    short_name: "Yard Roller",
    manufacturer: "CASE",
    model: "1107 EX",
    chassis_number: null,
    engine_number: null,
    status: "ACTIVE",
    rental_party_name: null,
    rental_owner_phone_primary: null,
    rental_owner_phone_secondary: null,
    rental_start_date: null,
    rental_end_date: null,
    current_deployment: null,
    has_active_assignment: false,
    active_assignment: null,
  },
  {
    id: "asset-inactive",
    asset_code: "GRADER-44444444444444444444444444444444",
    asset_type: "GRADER",
    ownership_type: "OWNED",
    registration_number: null,
    short_name: "Inactive Grader",
    manufacturer: "Komatsu",
    model: "GD655",
    chassis_number: null,
    engine_number: null,
    status: "INACTIVE",
    rental_party_name: null,
    rental_owner_phone_primary: null,
    rental_owner_phone_secondary: null,
    rental_start_date: null,
    rental_end_date: null,
    current_deployment: null,
    has_active_assignment: false,
    active_assignment: null,
  },
];

const people = [
  {
    user_id: "user-active",
    membership_id: "driver-active",
    phone: "+919900000001",
    display_name: "Ravi Kumar",
    role: "DRIVER",
    status: "ACTIVE",
    sites: [],
    has_active_assignment: true,
    has_active_duty: true,
    current_asset_id: "asset-assigned",
    current_asset_code: assets[0].asset_code,
    current_site_id: "site-1",
    current_site_name: "North Pit",
  },
  {
    user_id: "user-invited",
    membership_id: "driver-invited",
    phone: "+919900000002",
    display_name: "Asha Singh",
    role: "DRIVER",
    status: "INVITED",
    sites: [],
    has_active_assignment: false,
    has_active_duty: false,
    current_asset_id: null,
    current_asset_code: null,
    current_site_id: null,
    current_site_name: null,
  },
  {
    user_id: "user-supervisor",
    membership_id: "supervisor-1",
    phone: "+919900000003",
    display_name: "Meera Shah",
    role: "SUPERVISOR",
    status: "ACTIVE",
    sites: [{ site_id: "site-1", site_name: "North Pit" }],
    has_active_assignment: false,
    has_active_duty: false,
    current_asset_id: null,
    current_asset_code: null,
    current_site_id: null,
    current_site_name: null,
  },
  {
    user_id: "user-inactive",
    membership_id: "driver-inactive",
    phone: "+919900000004",
    display_name: "Kiran Rao",
    role: "DRIVER",
    status: "INACTIVE",
    sites: [],
    has_active_assignment: false,
    has_active_duty: false,
    current_asset_id: null,
    current_asset_code: null,
    current_site_id: null,
    current_site_name: null,
  },
];

const sites = [
  {
    id: "site-1",
    name: "Northern Bypass Earthworks",
    short_name: "North Pit",
    code: "SITE-11111111111111111111111111111111",
    location_description: "Chainage 14",
    latitude: null,
    longitude: null,
    status: "ACTIVE",
    supervisors: [{ access_id: "access-1", membership_id: "supervisor-1", display_name: "Meera Shah" }],
    asset_count: 2,
  },
  {
    id: "site-2",
    name: "River Bridge Approach",
    short_name: "River Yard",
    code: "SITE-22222222222222222222222222222222",
    location_description: "East bank",
    latitude: null,
    longitude: null,
    status: "ACTIVE",
    supervisors: [],
    asset_count: 0,
  },
];

async function mockOwnerApi(page: Page, options: { ownerOperationsAvailable?: boolean } = {}) {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/owner/operations/preview") && options.ownerOperationsAvailable === false) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Not Found" }),
      });
      return;
    }
    const operationBody = path.includes("/owner/operations/")
      ? route.request().postDataJSON() as { action: string; asset_id?: string; target_site_id?: string; site_id?: string; driver_membership_id?: string; activate_membership?: boolean; reason?: string; state_token?: string }
      : null;
    const intent = path.endsWith("/owner/operations/preview") ? operationBody : null;
    const selectedDriver = people.find((person) => person.membership_id === intent?.driver_membership_id);
    const reactivateBlockers = intent?.action === "REACTIVATE_ASSET" ? [
      ...(selectedDriver && !intent.site_id ? ["Choose a Site before assigning a Driver / Operator."] : []),
      ...(selectedDriver?.status === "INACTIVE" && !intent.activate_membership ? ["Explicitly reactivate the Driver / Operator role to continue."] : []),
    ] : [];
    const operationPlan = intent?.action === "REACTIVATE_ASSET" ? {
      action: intent.action,
      state_token: "a".repeat(64),
      title: "Reactivate Inactive Grader",
      summary: "Review the inactive asset and optionally set up its next Site and Driver / Operator.",
      current_state: [
        { kind: "ASSET", id: "asset-inactive", label: "Inactive Grader", status: "INACTIVE", details: { asset_type: "GRADER", ownership_type: "OWNED" } },
        { kind: "PREVIOUS_SITE", id: "old-deployment", label: "Old Yard", status: "PREVIOUS", details: {} },
      ],
      dependencies: [
        ...(intent.site_id ? [{ kind: "TARGET_SITE", id: intent.site_id, label: sites.find((site) => site.id === intent.site_id)?.short_name, status: "ACTIVE", details: {} }] : []),
        ...(selectedDriver ? [{ kind: "DRIVER", id: selectedDriver.membership_id, label: selectedDriver.display_name, status: selectedDriver.status, details: { role: "DRIVER", assignment_state: "UNASSIGNED" } }] : []),
      ],
      warnings: [],
      allowed_resolutions: ["REACTIVATE_ONLY", "REACTIVATE_AND_DEPLOY", "REACTIVATE_DEPLOY_ASSIGN"],
      blocked_reasons: reactivateBlockers,
      planned_changes: ["Reactivate Inactive Grader"],
      can_execute: reactivateBlockers.length === 0,
    } : intent?.action === "DEACTIVATE_ASSET" && intent.asset_id === "asset-assigned" ? {
      action: intent.action,
      state_token: "b".repeat(64),
      title: "Deactivate Green Tipper",
      summary: "The active duty must be resolved first.",
      current_state: [{ kind: "ASSET", id: "asset-assigned", label: "Green Tipper", status: "ACTIVE", details: {} }],
      dependencies: [
        { kind: "ASSIGNMENT", id: "assignment-1", label: "Ravi Kumar", status: "ON_DUTY", details: { driver_membership_id: "driver-active" } },
        { kind: "DUTY", id: "duty-1", label: "Active duty", status: "ACTIVE", details: { started_at: "2026-10-08T02:45:00Z" } },
      ],
      warnings: ["The active duty must be force-closed before deactivation."],
      allowed_resolutions: ["FORCE_CLOSE_DUTY_AND_DEACTIVATE_ASSET"],
      blocked_reasons: ["The active duty must be resolved first."],
      planned_changes: [],
      can_execute: false,
    } : intent?.action === "FORCE_CLOSE_DUTY_AND_DEACTIVATE_ASSET" ? {
      action: intent.action,
      state_token: "c".repeat(64),
      title: "Force close duty and deactivate Green Tipper",
      summary: "Resolve the active duty without fabricating a meter reading.",
      current_state: [{ kind: "DUTY", id: "duty-1", label: "Active duty", status: "ACTIVE", details: { started_at: "2026-10-08T02:45:00Z" } }],
      dependencies: [{ kind: "ASSET", id: "asset-assigned", label: "Green Tipper", status: "ACTIVE", details: {} }],
      warnings: ["END KM will remain missing."],
      allowed_resolutions: ["FORCE_CLOSE"],
      blocked_reasons: [],
      planned_changes: ["Force close Ravi Kumar's active duty", "Deactivate Green Tipper"],
      can_execute: Boolean(intent.reason?.trim()),
    } : intent ? {
      action: intent.action,
      state_token: "a".repeat(64),
      title: intent.action === "MOVE_DEPLOYMENT" ? "Move North Excavator" : "End Ravi Kumar's assignment",
      summary: "Review the authoritative current relationships.",
      current_state: [{ kind: "ASSET", id: intent.asset_id, label: intent.action === "MOVE_DEPLOYMENT" ? "North Excavator" : "Green Tipper", status: "ACTIVE", details: {} }],
      dependencies: intent.action === "MOVE_DEPLOYMENT"
        ? [{ kind: "DEPLOYMENT", id: "deployment-2", label: "North Pit", status: "ACTIVE", details: { site_id: "site-1" } }]
        : [{ kind: "ASSIGNMENT", id: "assignment-1", label: "Ravi Kumar", status: "OFF_DUTY", details: { driver_membership_id: "driver-active" } }],
      warnings: [],
      allowed_resolutions: intent.action === "MOVE_DEPLOYMENT" ? ["MOVE"] : ["END_ASSIGNMENT"],
      blocked_reasons: intent.action === "MOVE_DEPLOYMENT" && !intent.target_site_id ? ["Choose a destination Site."] : [],
      planned_changes: intent.action === "MOVE_DEPLOYMENT" && intent.target_site_id ? ["Move North Excavator to River Yard"] : ["End Ravi Kumar's assignment to Green Tipper"],
      can_execute: intent.action !== "MOVE_DEPLOYMENT" || Boolean(intent.target_site_id),
    } : null;
    const operationResult = path.endsWith("/owner/operations/execute") && operationBody
      ? { action: operationBody.action, completed_changes: [`Applied ${operationBody.action}`], message: "Relationship updated." }
      : null;
    const body = path.endsWith("/auth/web-refresh")
      ? { access_token: "owner-test-token", expires_in: 3600, membership_id: "owner-membership", company_id: "company-1", role: "OWNER_ADMIN" }
      : path.endsWith("/auth/me")
        ? { user_id: "owner-user", display_name: "Owner Test", membership_id: "owner-membership", company_id: "company-1", company_name: "Owner Test Company", role: "OWNER_ADMIN" }
        : path.endsWith("/owner/assets")
          ? assets
          : path.endsWith("/owner/people")
            ? people
            : path.endsWith("/owner/sites")
              ? sites
              : operationPlan
                ? operationPlan
                : operationResult
                  ? operationResult
              : path.endsWith("/owner/assets/asset-unassigned/eligible-drivers")
                ? [{ membership_id: "driver-invited", display_name: "Asha Singh", phone: "+919900000002", status: "INVITED" }]
                : [];
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
  });
}

async function openOwner(page: Page, options: { ownerOperationsAvailable?: boolean } = {}) {
  await mockOwnerApi(page, options);
  await page.goto("/owner");
  await expect(page.getByRole("heading", { name: "Fleet command centre" })).toBeVisible();
  await expect(page.getByLabel("Live fleet readiness")).toBeVisible();
}

test.describe("mocked Owner workstation", () => {
  test("consolidates fleet navigation and keeps the compact Fleet table within laptop widths", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await openOwner(page);

    await expect(page.getByLabel("Current fleet summary")).toContainText("Active assets3");
    for (const name of ["Operations", "Fleet", "People", "Sites", "Reports", "Report Templates"]) {
      await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
    }
    await expect(page.getByRole("button", { name: "Deployments", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Assignments", exact: true })).toHaveCount(0);

    await page.getByRole("button", { name: "Fleet", exact: true }).click();
    const fleetTable = page.getByRole("table", { name: "Fleet assets" });
    await expect(fleetTable).toBeVisible();
    await expect(fleetTable.getByRole("columnheader")).toHaveCount(4);
    await expect(fleetTable.getByRole("columnheader", { name: "Asset", exact: true })).toBeVisible();
    await expect(fleetTable.getByRole("columnheader", { name: "Current setup", exact: true })).toBeVisible();
    await expect(fleetTable.getByRole("columnheader", { name: "Driver / Operator", exact: true })).toBeVisible();
    await expect(fleetTable.getByRole("columnheader", { name: "Actions" })).toBeVisible();
    await expect(fleetTable.getByRole("columnheader", { name: "Registration" })).toHaveCount(0);
    await expect(fleetTable.locator("thead button")).toHaveCount(0);
    const sortBy = page.getByLabel("Sort by");
    await expect(sortBy).toHaveValue("asset-asc");
    await expect(sortBy.locator("option:checked")).toHaveText("Asset name A–Z");
    await sortBy.selectOption("asset-desc");
    await expect(fleetTable.locator("tbody tr").first()).toContainText("Yard Roller");
    await sortBy.selectOption("asset-asc");

    const rentedRow = fleetTable.getByRole("row").filter({ hasText: "North Excavator" });
    const rentedAssetCell = rentedRow.locator('td[data-label="Asset"]');
    const rentedSetupCell = rentedRow.locator('td[data-label="Current setup"]');
    await expect(rentedAssetCell).toContainText("EXCAVATOR");
    await expect(rentedAssetCell).not.toContainText("RENTED");
    await expect(rentedSetupCell).toContainText("RENTED");
    await expect(rentedRow).toContainText("Owner: Metro Plant Hire");
    await expect(rentedRow).toContainText("Primary: +91 98765 43210");
    await expect(rentedRow).toContainText("Alternate: +91 99887 76655");
    await expect(rentedRow.locator(".owner-fleet-rental")).toHaveCSS("border-top-style", "none");
    await expect(rentedRow.getByRole("button")).toHaveCount(3);
    await expect(rentedRow.getByRole("button", { name: "Manage" })).toBeVisible();
    await expect(rentedRow.getByRole("button", { name: "Maintenance" })).toBeVisible();
    await expect(rentedRow.getByRole("button", { name: "History" })).toBeVisible();

    const assignedRow = fleetTable.getByRole("row").filter({ hasText: "Green Tipper" });
    await expect(assignedRow.locator('td[data-label="Asset"]')).not.toContainText("OWNED");
    await expect(assignedRow.locator('td[data-label="Current setup"]')).toContainText("OWNED");
    await expect(assignedRow).toContainText("North Pit");
    await expect(assignedRow).toContainText("On duty");
    await expect(assignedRow).toContainText("Ravi Kumar");
    await expect(assignedRow).toContainText("+91 99000 00001");
    await rentedRow.getByRole("button", { name: "Manage" }).click();
    const manager = page.getByRole("dialog", { name: "North Excavator" });
    await expect(manager.getByRole("region", { name: "Technical details" })).toContainText("LONG-CHASSIS-NUMBER-THAT-WRAPS-CLEANLY-1234567890");
    await manager.getByRole("button", { name: "Edit asset details" }).click();
    await expect(page.getByRole("heading", { name: "Edit asset" })).toBeVisible();
    await expect(page.getByLabel("Chassis number")).toHaveValue("LONG-CHASSIS-NUMBER-THAT-WRAPS-CLEANLY-1234567890");
    await expect(page.getByLabel("Primary phone")).toHaveValue("+919876543210");
    await page.getByRole("button", { name: "Cancel" }).click();

    await page.getByLabel("Filter ownership").selectOption("RENTED");
    await page.getByLabel("Filter site").selectOption("site-1");
    await sortBy.selectOption("asset-desc");
    await expect(fleetTable.locator("tbody tr")).toHaveCount(1);
    await expect(fleetTable.locator("tbody tr").first()).toContainText("North Excavator");
    await expect(page.getByLabel("Filter ownership")).toHaveValue("RENTED");
    await expect(page.getByLabel("Filter site")).toHaveValue("site-1");
    await page.getByLabel("Filter ownership").selectOption("");
    await page.getByLabel("Filter site").selectOption("");

    for (const width of [1280, 1366, 1440, 1920]) {
      await page.setViewportSize({ width, height: 800 });
      const dimensions = await page.locator(".owner-table-shell--fleet").evaluate((element) => ({ clientWidth: element.clientWidth, scrollWidth: element.scrollWidth }));
      expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);
      const wrappedCellsFit = await rentedRow.locator(".owner-fleet-cell").evaluateAll((cells) => cells.every((cell) => cell.scrollWidth <= cell.clientWidth + 1));
      expect(wrappedCellsFit).toBe(true);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(1);
    }

    await page.getByRole("button", { name: "People", exact: true }).click();
    await expect(page.getByRole("table", { name: "People" }).getByText("Asha Singh")).toBeVisible();
    await page.getByRole("button", { name: "Sites", exact: true }).click();
    await expect(page.getByRole("table", { name: "Sites" }).getByText("North Pit", { exact: true })).toBeVisible();
  });

  test("reactivates an inactive asset with simple Site and Driver setup", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await openOwner(page);

    await page.getByRole("button", { name: "Fleet", exact: true }).click();
    const assetRow = page.getByRole("table", { name: "Fleet assets" }).getByRole("row").filter({ hasText: "Inactive Grader" });
    await assetRow.getByRole("button", { name: "Manage", exact: true }).click();

    const dialog = page.getByRole("dialog", { name: "Inactive Grader" });
    await expect(dialog.getByRole("region", { name: "Asset activity" })).toContainText("Inactive");
    await expect(dialog.getByLabel("Site")).toHaveValue("");
    await expect(dialog.getByLabel("Driver / Operator")).toHaveValue("");
    await expect(dialog.getByRole("list", { name: "Operation progress" })).toHaveCount(0);
    await expect(dialog.getByRole("button", { name: "Continue" })).toHaveCount(0);
    await expect(dialog.getByRole("button", { name: "Review changes" })).toHaveCount(0);
    await dialog.getByLabel("Site").selectOption("site-2");
    await dialog.getByLabel("Driver / Operator").selectOption("driver-inactive");
    await dialog.getByRole("checkbox", { name: "Include Driver / Operator role reactivation" }).check();

    const previewRequest = page.waitForRequest((request) => request.url().endsWith("/owner/operations/preview") && request.postDataJSON().action === "REACTIVATE_ASSET");
    const executeRequest = page.waitForRequest((request) => request.url().endsWith("/owner/operations/execute") && request.postDataJSON().action === "REACTIVATE_ASSET");
    await dialog.getByRole("button", { name: "REACTIVATE & SET UP" }).click();
    const [preview, execute] = await Promise.all([previewRequest, executeRequest]);
    expect(preview.postDataJSON()).toMatchObject({
      action: "REACTIVATE_ASSET",
      asset_id: "asset-inactive",
      site_id: "site-2",
      driver_membership_id: "driver-inactive",
      activate_membership: true,
    });
    expect(execute.postDataJSON()).toMatchObject({ action: "REACTIVATE_ASSET", state_token: "a".repeat(64) });
    await expect(page.getByRole("status")).toContainText("Relationship updated.");
  });

  test("offers an explicit Owner force-close path when an Asset is on duty", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await openOwner(page);

    await page.getByRole("button", { name: "Fleet", exact: true }).click();
    const assetRow = page.getByRole("table", { name: "Fleet assets" }).getByRole("row").filter({ hasText: "Green Tipper" });
    await assetRow.getByRole("button", { name: "Manage", exact: true }).click();

    let dialog = page.getByRole("dialog", { name: "Green Tipper" });
    await expect(dialog.getByRole("region", { name: "Asset activity" })).toContainText("On duty");
    await expect(dialog).toContainText("Ravi Kumar");
    await expect(dialog).toContainText("North Pit");
    await expect(dialog.getByLabel("Driver / Operator")).toBeDisabled();
    await expect(dialog.getByLabel("Site")).toBeDisabled();
    await expect(dialog.getByRole("button", { name: "Deactivate asset" })).toBeEnabled();
    await dialog.getByRole("button", { name: "Deactivate asset" }).click();

    dialog = page.getByRole("dialog", { name: "Deactivate Green Tipper" });
    await expect(dialog).toContainText("This asset currently has an active duty.");
    await expect(dialog.getByRole("button", { name: "Cancel" })).toBeEnabled();
    await expect(dialog.getByRole("button", { name: "View duty" })).toBeEnabled();
    await expect(dialog.getByRole("button", { name: "Force close duty & deactivate" })).toBeEnabled();
    await expect(dialog.getByLabel("Force-close reason")).toHaveCount(0);
    await dialog.getByRole("button", { name: "Force close duty & deactivate" }).click();

    dialog = page.getByRole("dialog", { name: "Why must this duty be force-closed?" });
    await dialog.getByRole("button", { name: "Continue" }).click();
    await expect(dialog.getByText("Enter a reason for force-closing this duty.").first()).toBeVisible();
    await dialog.getByLabel("Force-close reason").fill("Driver forgot to end duty");
    await dialog.getByRole("button", { name: "Continue" }).click();

    dialog = page.getByRole("dialog", { name: "Force close duty & deactivate Green Tipper?" });
    await expect(dialog).toContainText("Mark END KM as missing");
    await expect(dialog).toContainText("Preserve all existing history and evidence");
    const previewRequest = page.waitForRequest((request) => request.url().endsWith("/owner/operations/preview") && request.postDataJSON().action === "FORCE_CLOSE_DUTY_AND_DEACTIVATE_ASSET");
    const executeRequest = page.waitForRequest((request) => request.url().endsWith("/owner/operations/execute") && request.postDataJSON().action === "FORCE_CLOSE_DUTY_AND_DEACTIVATE_ASSET");
    await dialog.getByRole("button", { name: "Force close & deactivate" }).click();
    const [preview, execute] = await Promise.all([previewRequest, executeRequest]);
    expect(preview.postDataJSON()).toEqual({
      action: "FORCE_CLOSE_DUTY_AND_DEACTIVATE_ASSET",
      asset_id: "asset-assigned",
      reason: "Driver forgot to end duty",
    });
    expect(execute.postDataJSON()).toMatchObject({
      action: "FORCE_CLOSE_DUTY_AND_DEACTIVATE_ASSET",
      asset_id: "asset-assigned",
      reason: "Driver forgot to end duty",
      state_token: "c".repeat(64),
    });
    await expect(page.getByRole("status")).toContainText("Relationship updated.");
  });

  test("mobile layout keeps navigation and table cards within the page", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openOwner(page);

    await page.getByRole("button", { name: "Fleet", exact: true }).click();
    const table = page.getByRole("table", { name: "Fleet assets" });
    await expect(table).toBeVisible();
    await expect(table.locator('td[data-label="Asset"]').first()).toContainText("Green Tipper");
    const search = await page.getByLabel("Search fleet").boundingBox();
    const typeFilter = await page.getByLabel("Filter asset type").boundingBox();
    expect(search?.height).toBeLessThanOrEqual(48);
    expect(typeFilter?.height).toBeLessThanOrEqual(48);
    const sidebar = await page.locator(".owner-sidebar").boundingBox();
    expect(sidebar?.width).toBeLessThanOrEqual(390);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });

  test("explains when the configured backend lacks Owner relationship operations", async ({ page }) => {
    await openOwner(page, { ownerOperationsAvailable: false });

    await page.getByRole("button", { name: "Fleet", exact: true }).click();
    const assetRow = page.getByRole("table", { name: "Fleet assets" }).getByRole("row").filter({ hasText: "North Excavator" });
    await assetRow.getByRole("button", { name: "Manage" }).click();

    const dialog = page.getByRole("dialog", { name: "North Excavator" });
    await dialog.getByLabel("Site").selectOption("");
    await dialog.getByRole("button", { name: "Save changes" }).click();
    await expect(dialog.getByRole("alert")).toContainText("Fleet Manager server must be updated");
    await expect(dialog.getByText("Not Found", { exact: true })).toHaveCount(0);
    await expect(dialog.getByRole("button", { name: "Continue" })).toHaveCount(0);
    await expect(dialog.getByRole("button", { name: "Close management form" })).toBeEnabled();
  });
});
