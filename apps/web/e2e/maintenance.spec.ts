import { expect, test, type Page } from "@playwright/test";

const ownedTipper = {
  id: "asset-owned",
  asset_code: "TIPPER-OWNED-01",
  asset_type: "TIPPER",
  ownership_type: "OWNED",
  registration_number: "KA01AB1234",
  short_name: "Owned Tipper",
  manufacturer: "Tata Motors",
  model: "Prima 2825.K",
  model_year: 2025,
  chassis_number: null,
  engine_number: null,
  status: "ACTIVE",
  maintenance_responsibility: "OWNER_COMPANY",
  supports_odometer_km: true,
  supports_hour_meter: true,
  rental_party_name: null,
  rental_owner_phone_primary: null,
  rental_owner_phone_secondary: null,
  rental_start_date: null,
  rental_end_date: null,
  current_deployment: null,
  has_active_assignment: false,
  active_assignment: null,
};

const rentedExcavator = {
  ...ownedTipper,
  id: "asset-rented",
  asset_code: "EXCAVATOR-RENTED-01",
  asset_type: "EXCAVATOR",
  ownership_type: "RENTED",
  registration_number: null,
  short_name: "Rented Excavator",
  manufacturer: "JCB",
  model: "NXT 205",
  maintenance_responsibility: "RENTER_COMPANY",
  supports_odometer_km: false,
  rental_party_name: "Rental Owner Ltd",
};

const planItem = {
  id: "schedule-1",
  asset_id: ownedTipper.id,
  task_code: "ENGINE_OIL",
  task_label: "Engine oil and filter",
  action_type: "REPLACE",
  description: null,
  enabled: true,
  state: "DUE_SOON",
  triggered_by: ["HOUR_METER_HOURS"],
  criteria: [
    {
      id: "criterion-days",
      basis: "CALENDAR_DAYS",
      interval_value: "180",
      warning_value: "14",
      baseline_value: null,
      baseline_date: "2026-05-01",
      state: "NOT_DUE",
      current_value: null,
      due_value: null,
      current_date: "2026-10-09",
      due_date: "2026-10-28",
    },
    {
      id: "criterion-hours",
      basis: "HOUR_METER_HOURS",
      interval_value: "500",
      warning_value: "50",
      baseline_value: "1000",
      baseline_date: null,
      state: "DUE_SOON",
      current_value: "1460",
      due_value: "1500",
      current_date: null,
      due_date: null,
    },
  ],
};

function planFor(assetId: string) {
  const rented = assetId === rentedExcavator.id;
  const asset = rented ? rentedExcavator : ownedTipper;
  return {
    id: rented ? null : "plan-1",
    asset_id: asset.id,
    asset_code: asset.asset_code,
    asset_type: asset.asset_type,
    manufacturer: asset.manufacturer,
    model: asset.model,
    model_year: asset.model_year,
    is_wheeled: !rented,
    supports_odometer_km: asset.supports_odometer_km,
    supports_hour_meter: asset.supports_hour_meter,
    maintenance_responsibility: asset.maintenance_responsibility,
    managed_by_current_company: !rented,
    management_message: rented ? "Maintenance managed by rental owner." : null,
    source: rented ? null : "CUSTOM",
    source_template_id: null,
    source_template_version: null,
    items: rented ? [] : [planItem],
  };
}

async function mockOwnerApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = [];
    if (path.endsWith("/auth/web-refresh")) {
      body = { access_token: "maintenance-test-token", expires_in: 3600, membership_id: "owner-1", company_id: "company-1", role: "OWNER_ADMIN" };
    } else if (path.endsWith("/auth/me")) {
      body = { user_id: "user-1", display_name: "Owner", membership_id: "owner-1", company_id: "company-1", company_name: "Maintenance Test", role: "OWNER_ADMIN" };
    } else if (path.endsWith("/owner/assets")) {
      body = [ownedTipper, rentedExcavator];
    } else if (path.endsWith("/owner/maintenance/overview")) {
      body = { overdue: 0, due: 0, due_soon: 1, unknown: 0, open_work_orders: 0, items: [] };
    } else if (path.endsWith("/reports/dashboard")) {
      body = {
        operational_date: "2026-10-09",
        reporting_timezone: "Asia/Kolkata",
        workday_start_minutes: 0,
        assigned_tippers_count: 0,
        approved_trip_count: 0,
        total_km: null,
        verified_diesel_issued: 0,
        drivers_on_duty: 0,
        drivers_past_regular_duty: 0,
        pending_verification_count: 0,
        missing_reading_count: 0,
        unresolved_emergency_count: 0,
        sites_not_closed_count: 0,
        complete_tippers_count: 0,
        sites: [],
        exceptions: [],
      };
    } else if (path.endsWith("/admin/company")) {
      body = {
        company_id: "company-1",
        reporting_timezone: "Asia/Kolkata",
        operational_day_start_minutes: 0,
      };
    } else if (path.match(/\/owner\/maintenance\/plans\/[^/]+$/)) {
      body = planFor(path.split("/").at(-1) ?? "");
    } else if (path.includes("/owner/maintenance/templates/matches/")) {
      body = [];
    }
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
  });
}

async function openMaintenance(page: Page) {
  await mockOwnerApi(page);
  await page.goto("/owner");
  await expect(page.getByRole("heading", { name: "Fleet command centre" })).toBeVisible();
  await page.getByRole("button", { name: "Maintenance", exact: true }).click();
  await page.getByRole("tab", { name: "Asset Plans" }).click();
  await expect(page.getByRole("table", { name: "Maintenance plan items" })).toBeVisible();
}

test.describe("Owner maintenance desktop workflow", () => {
  test("keeps the list-first plan compact and free of horizontal scrolling", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await openMaintenance(page);

    const table = page.getByRole("table", { name: "Maintenance plan items" });
    await expect(table.getByRole("columnheader")).toHaveCount(8);
    await expect(table.getByRole("columnheader", { name: "Triggers" })).toBeVisible();
    await expect(table).toContainText("180 days");
    await expect(table).toContainText("500 h");
    await expect(page.getByLabel("Maintenance Asset").locator("option")).toHaveCount(1);

    for (const width of [1280, 1366, 1440, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      const dimensions = await table.evaluate((element) => ({
        clientWidth: element.clientWidth,
        scrollWidth: element.scrollWidth,
      }));
      expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);
      const pageOverflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(pageOverflow).toBeLessThanOrEqual(1);
    }

    const sectionGap = await page.locator(".maintenance-section").evaluate(
      (element) => Number.parseFloat(getComputedStyle(element).rowGap),
    );
    expect(sectionGap).toBeLessThanOrEqual(24);

    await table.getByRole("button", { name: "Edit" }).click();
    await expect(page.getByLabel("Every days")).toHaveValue("180");
    await expect(page.getByLabel("Every hours")).toHaveValue("500");
  });

  test("shows only the rental-owner message from direct rented context", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockOwnerApi(page);
    await page.goto("/owner");
    await page.getByRole("button", { name: "Fleet", exact: true }).click();
    const rentedRow = page.getByRole("row").filter({ hasText: "Rented Excavator" });
    await rentedRow.getByRole("button", { name: "Maintenance plan" }).click();

    await expect(page.getByText("Maintenance managed by rental owner.", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Maintenance Asset")).toHaveCount(0);
    await expect(page.getByRole("table", { name: "Maintenance plan items" })).toHaveCount(0);
  });

  test("uses the shared compact spacing rhythm across representative Owner pages", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockOwnerApi(page);
    await page.goto("/owner");
    await expect(page.getByRole("heading", { name: "Fleet command centre" })).toBeVisible();

    const tokens = await page.locator(".owner-shell").evaluate((element) => {
      const style = getComputedStyle(element);
      return ["micro", "small", "compact", "standard", "section", "major"].map(
        (name) => style.getPropertyValue(`--owner-space-${name}`).trim(),
      );
    });
    expect(tokens).toEqual(["4px", "8px", "12px", "16px", "24px", "32px"]);

    for (const [navigation, headingName] of [
      ["Fleet", "Fleet"],
      ["People", "People"],
      ["Sites", "Sites"],
      ["Reports", "Owner operations"],
      ["Report Templates", "Report templates"],
    ] as const) {
      await page.getByRole("button", { name: navigation, exact: true }).click();
      const heading = page.getByRole("heading", { name: headingName, exact: true });
      await expect(heading).toBeVisible();
      const description = heading.locator("xpath=following-sibling::p[1]");
      await expect(description).toBeVisible();
      const [headingBox, descriptionBox] = await Promise.all([
        heading.boundingBox(),
        description.boundingBox(),
      ]);
      expect((descriptionBox?.y ?? 0) - ((headingBox?.y ?? 0) + (headingBox?.height ?? 0))).toBeLessThanOrEqual(16);
      const panelGaps = await page.locator(".owner-content .owner-panel").evaluateAll(
        (elements) => elements
          .filter((element) => (element as HTMLElement).offsetParent !== null)
          .map((element) => Number.parseFloat(getComputedStyle(element).rowGap)),
      );
      expect(panelGaps.every((gap) => gap <= 16)).toBe(true);
    }
  });
});
