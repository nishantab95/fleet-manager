import { expect, test } from "@playwright/test";

test.describe("PC Test Lab", () => {
  test("shows the role navigator and launcher-owned reset guidance", async ({ page }) => {
    await page.route("**/health", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ service: "fleet-manager-api", status: "ok" }),
      });
    });
    await page.route("**/ready", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ database: "available", status: "ready" }),
      });
    });

    await page.goto("/lab");

    await expect(page.getByRole("heading", { name: "PC TEST LAB" })).toBeVisible();
    await expect(page.getByText("INTERNAL / QA ONLY")).toBeVisible();
    await expect(page.getByRole("link", { name: /DRIVER.*Enter operational events/ })).toHaveAttribute("href", "/login?workspace=driver-test");
    await expect(page.getByRole("link", { name: /SUPERVISOR.*Review and verify events/ })).toHaveAttribute("href", "/login?workspace=supervisor");
    await expect(page.getByRole("link", { name: /OWNER.*Dashboard, reports and administration/ })).toHaveAttribute("href", "/login?workspace=owner");
    await expect(page.getByText("API").locator("..").getByText("READY")).toBeVisible();
    await expect(page.getByText("Database").locator("..").getByText("READY")).toBeVisible();
    await expect(page.getByText("LAUNCHER")).toBeVisible();

    await page.getByRole("button", { name: "START FRESH TEST" }).click();
    await expect(page.getByRole("status")).toContainText("python launch.py --fresh");
    await expect(page.getByRole("status")).toContainText("RESET PILOT");
  });
});
