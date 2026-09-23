import { expect, test, type Page } from "@playwright/test";

const viewports = [1366, 1440, 1536, 1920];
const roles = [
  { name: "driver", path: "/driver-test", apiRole: "DRIVER" },
  { name: "owner", path: "/owner", apiRole: "OWNER_ADMIN" },
  { name: "supervisor", path: "/supervisor", apiRole: "SUPERVISOR" },
] as const;

async function mockApi(page: Page, role: (typeof roles)[number]["apiRole"]) {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const body = path.endsWith("/auth/web-refresh")
      ? { access_token: "layout-test-token", expires_in: 3600, membership_id: "membership-1", company_id: "company-1", role }
      : path.endsWith("/auth/me")
        ? { user_id: "user-1", display_name: "Layout test user", membership_id: "membership-1", company_id: "company-1", company_name: "Layout Test Company", role }
        : path.endsWith("/driver/assignment/current")
          ? { assignment_id: "assignment-1", tipper_id: "tipper-1", tipper_registration_number: "PILOT-12", tipper_short_name: "Tipper 12", site_id: "site-1", site_name: "Pilot Site", supervisor_name: "Pilot Supervisor" }
          : path.endsWith("/supervisor/sites")
            ? [{ id: "site-1", name: "Pilot Site", code: "PILOT", status: "ACTIVE" }]
            : path.includes("/supervisor/sites/") && path.includes("/events")
              ? []
              : path.includes("/supervisor/sites/") && path.includes("/completeness")
                ? []
                : path.endsWith("/reports/dashboard")
                  ? { operational_date: "2026-09-23", reporting_timezone: "Asia/Kolkata", workday_start_minutes: 0, assigned_tippers_count: 1, approved_trip_count: 0, total_km: null, verified_diesel_issued: 0, pending_verification_count: 0, missing_reading_count: 0, unresolved_emergency_count: 0, sites_not_closed_count: 0, complete_tippers_count: 0, sites: [], exceptions: [] }
                  : path.endsWith("/admin/company")
                    ? { company_id: "company-1", reporting_timezone: "Asia/Kolkata", operational_day_start_minutes: 0 }
                    : path.includes("/admin/")
                      ? []
                      : {};
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
  });
}

for (const role of roles) {
  test.describe(`${role.name} desktop layout`, () => {
    for (const viewport of viewports) {
      test(`${viewport}px keeps the workspace readable`, async ({ page }) => {
        await page.setViewportSize({ width: viewport, height: 900 });
        await mockApi(page, role.apiRole);
        await page.goto(role.path);
        await expect(page.locator(".admin-layout")).toBeVisible();

        const content = await page.locator(".content").boundingBox();
        expect(content?.width).toBeGreaterThanOrEqual(role.name === "owner" ? 1000 : 1200);

        if (role.name === "driver") {
          const buttons = page.locator(".qa-actions button");
          await expect(buttons).toHaveCount(4);
          const boxes = await buttons.evaluateAll((elements) => elements.map((element) => {
            const box = element.getBoundingClientRect();
            return { width: box.width, height: box.height, top: box.top };
          }));
          expect(boxes.every((box) => box.width >= 220 && box.height >= 80)).toBe(true);
          expect(boxes[0].top).toBe(boxes[1].top);
          expect(boxes[2].top).toBe(boxes[3].top);
          expect(boxes[2].top).toBeGreaterThan(boxes[0].top);
        }

        if (role.name === "owner") {
          const sidebar = await page.locator(".sidebar").boundingBox();
          expect(sidebar?.width).toBeGreaterThanOrEqual(220);
          expect(sidebar?.width).toBeLessThanOrEqual(260);
          await expect(page.getByRole("heading", { name: "Owner operations" })).toBeVisible();
        }

        if (role.name === "supervisor") {
          await expect(page.getByLabel("Assigned site")).toBeVisible();
          await expect(page.getByRole("heading", { name: /Pilot Site · daily completeness/ })).toBeVisible();
        }
      });
    }
  });
}
