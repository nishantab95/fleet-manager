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
    status: "ACTIVE",
    rental_party_name: null,
    rental_start_date: null,
    rental_end_date: null,
    current_deployment: { id: "deployment-1", asset_id: "asset-assigned", site_id: "site-1", site_name: "North Pit", starts_at: "2026-09-01T04:00:00Z", ends_at: null },
    has_active_assignment: true,
    active_assignment: { assignment_id: "assignment-1", site_id: "site-1", site_name: "North Pit", driver_membership_id: "driver-active", driver_name: "Ravi Kumar", starts_at: "2026-09-02T04:00:00Z", regular_duty_minutes: 600 },
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
    status: "ACTIVE",
    rental_party_name: "Metro Plant Hire",
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
    status: "ACTIVE",
    rental_party_name: null,
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
    status: "INACTIVE",
    rental_party_name: null,
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
    const intent = path.endsWith("/owner/operations/preview")
      ? route.request().postDataJSON() as { action: string; asset_id?: string; target_site_id?: string; site_id?: string; driver_membership_id?: string; activate_membership?: boolean }
      : null;
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
  test("desktop tables and operational selectors expose the right records", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await openOwner(page);

    await expect(page.getByLabel("Current fleet summary")).toContainText("Active assets3");
    await expect(page.getByLabel("Current fleet summary")).toContainText("On duty1");
    for (const name of ["Operations", "Fleet", "Deployments", "Assignments", "People", "Sites", "Reports", "Report templates"]) {
      await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
    }

    await page.getByRole("button", { name: "Fleet", exact: true }).click();
    const fleetTable = page.getByRole("table", { name: "Fleet assets" });
    await expect(fleetTable).toBeVisible();
    await expect(fleetTable.getByRole("row")).toHaveCount(5);
    await expect(fleetTable.getByText("Green Tipper")).toBeVisible();
    await expect(page.getByText(assets[0].asset_code)).toBeHidden();
    await page.getByLabel("Search fleet").fill("excavator");
    await expect(fleetTable.getByText("North Excavator")).toBeVisible();
    await expect(fleetTable.getByText("Green Tipper")).toHaveCount(0);

    await page.getByRole("button", { name: "People", exact: true }).click();
    const peopleTable = page.getByRole("table", { name: "People" });
    await expect(peopleTable.getByText("Asha Singh")).toBeVisible();
    await expect(peopleTable.getByText("INVITED")).toBeVisible();

    await page.getByRole("button", { name: "Sites", exact: true }).click();
    const sitesTable = page.getByRole("table", { name: "Sites" });
    await expect(sitesTable.getByText("North Pit", { exact: true })).toBeVisible();
    await expect(sitesTable.getByText("Northern Bypass Earthworks")).toBeVisible();
    await expect(page.getByText(sites[0].code)).toHaveCount(0);

    await page.getByRole("button", { name: "Deployments", exact: true }).click();
    await expect(page.getByLabel("Asset").locator("option")).toHaveCount(2);
    await expect(page.getByLabel("Asset").locator('option[value="asset-undeployed"]')).toContainText("Yard Roller");
    const deploymentRow = page.getByRole("table", { name: "Current deployments" }).getByRole("row").filter({ hasText: "North Excavator" });
    await deploymentRow.getByRole("button", { name: "Move", exact: true }).click();
    const moveDialog = page.getByRole("dialog", { name: "Move North Excavator" });
    await expect(moveDialog).toBeVisible();
    await moveDialog.getByRole("button", { name: "Continue" }).click();
    await expect(moveDialog.getByLabel("Destination Site").locator('option[value="site-1"]')).toHaveCount(0);
    await expect(moveDialog.getByLabel("Destination Site").locator('option[value="site-2"]')).toContainText("River Yard");
    await moveDialog.getByRole("button", { name: "Close operation" }).click();

    await page.getByRole("button", { name: "Assignments", exact: true }).click();
    await page.getByLabel("Assignment asset").selectOption("asset-unassigned");
    const candidate = page.getByLabel("Driver / Operator").locator('option[value="driver-invited"]');
    await expect(candidate).toContainText("Asha Singh · +919900000002 · INVITED");
    const assignmentRow = page.getByRole("table", { name: "Current assignments" }).getByRole("row").filter({ hasText: "Green Tipper" });
    await expect(assignmentRow).toContainText("Ravi Kumar");
    await expect(assignmentRow).toContainText("+919900000001");
    await expect(assignmentRow).toContainText("10 hours");
    await assignmentRow.getByRole("button", { name: "End assignment" }).click();
    const endDialog = page.getByRole("dialog", { name: "End Ravi Kumar's assignment" });
    await expect(endDialog).toContainText("Ravi Kumar");
    await endDialog.getByRole("button", { name: "Cancel" }).click();

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });

  test("reactivates an inactive asset with optional Site and Driver setup in the shared wizard", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await openOwner(page);

    await page.getByRole("button", { name: "Fleet", exact: true }).click();
    const assetRow = page.getByRole("table", { name: "Fleet assets" }).getByRole("row").filter({ hasText: "Inactive Grader" });
    await assetRow.getByRole("button", { name: "Reactivate", exact: true }).click();

    const dialog = page.getByRole("dialog", { name: "Reactivate Inactive Grader" });
    await expect(dialog.getByRole("region", { name: "Asset current state" })).toContainText("Grader");
    await expect(dialog).toContainText("Old Yard");
    await dialog.getByRole("button", { name: "Continue" }).click();
    await expect(dialog.getByLabel("Reactivation Site")).toHaveValue("");
    await expect(dialog.getByLabel("Reactivation Driver / Operator")).toHaveValue("");
    await dialog.getByLabel("Reactivation Site").selectOption("site-2");
    await dialog.getByLabel("Reactivation Driver / Operator").selectOption("driver-inactive");
    await expect(dialog).toContainText("Currently inactive");
    await expect(dialog).not.toContainText(/before\s+assignment/i);
    await dialog.getByRole("checkbox", { name: "Reactivate role as part of this setup" }).check();
    await dialog.getByRole("button", { name: "Review changes" }).click();

    const review = dialog.getByRole("group", { name: "Final setup" });
    await expect(review).toContainText("Inactive Grader → Active");
    await expect(review).toContainText("River Yard");
    await expect(review).toContainText("Kiran Rao");
    await expect(review).toContainText("Driver / Operator → Reactivate");
    await expect(dialog.getByRole("button", { name: "REACTIVATE & SET UP" })).toBeEnabled();
  });

  test("mobile layout keeps navigation and table cards within the page", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openOwner(page);

    await page.getByRole("button", { name: "Fleet", exact: true }).click();
    const table = page.getByRole("table", { name: "Fleet assets" });
    await expect(table).toBeVisible();
    await expect(table.locator('td[data-label="Short name"]').first()).toContainText("Green Tipper");
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

    await page.getByRole("button", { name: "Deployments", exact: true }).click();
    const deploymentRow = page.getByRole("table", { name: "Current deployments" }).getByRole("row").filter({ hasText: "North Excavator" });
    await deploymentRow.getByRole("button", { name: "Remove deployment" }).click();

    const dialog = page.getByRole("dialog", { name: "Remove asset from Site" });
    await expect(dialog.getByRole("alert")).toContainText("Server update required");
    await expect(dialog).toContainText("This management action is not supported by the currently running Fleet Manager server. Update the Fleet Manager server and try again.");
    await expect(dialog.getByText("Not Found", { exact: true })).toHaveCount(0);
    await expect(dialog.getByRole("button", { name: "Continue" })).toHaveCount(0);
    await expect(dialog.getByRole("button", { name: "Retry" })).toBeEnabled();
    await expect(dialog.getByRole("button", { name: "Close", exact: true })).toBeEnabled();
  });
});
