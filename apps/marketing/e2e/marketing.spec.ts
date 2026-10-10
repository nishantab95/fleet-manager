import { expect, test } from "@playwright/test";

const pages = [
  ["/", /Run the field/],
  ["/features", /Purpose-built for every role/],
  ["/how-it-works", /From assignment to answer/],
  ["/solutions", /For fleets that build/],
  ["/pricing", /Scope first/],
  ["/contact", /Bring us the operation/],
] as const;

test.describe("Fleet AI Systems marketing site", () => {
  for (const [path, heading] of pages) {
    test(`${path} is a branded, indexable public route`, async ({ page }) => {
      const refreshRequests: string[] = [];
      page.on("request", (request) => {
        if (request.url().includes("/auth/web-refresh")) refreshRequests.push(request.url());
      });
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
      await expect(page.locator("header").getByRole("link", { name: "Fleet AI Systems home" })).toBeVisible();
      await expect(page).toHaveTitle(/Fleet AI Systems/);
      if (path === "/") await expect(page).toHaveTitle("Clearer construction fleet operations | Fleet AI Systems");
      await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", new RegExp(`https://fleetaisystems\\.com${path === "/" ? "/?$" : `${path}$`}`));
      expect(refreshRequests).toEqual([]);
    });
  }

  for (const [width, height] of [[390, 844], [768, 1024], [1280, 720], [1366, 768], [1440, 900], [1920, 1080]] as const) {
    test(`homepage remains usable at ${width}x${height}`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await page.goto("/");
      await expect(page.getByRole("heading", { level: 1, name: /Run the field/ })).toBeVisible();
      const dimensions = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
      expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client + 1);
      await expect(page.locator(".marketing-showcase__label", { hasText: "Owner workspace" })).toBeVisible();
      await expect(page.getByText("DRIVER / OPERATOR", { exact: true })).toBeVisible();
      await expect(page.getByText("SUPERVISOR", { exact: true })).toBeVisible();
      if (width < 1120) {
        await page.locator(".marketing-menu summary").click();
        await expect(page.locator(".marketing-menu nav").getByRole("link", { name: "Features" })).toBeVisible();
      } else {
        await expect(page.locator(".marketing-nav--desktop").getByRole("link", { name: "Features" })).toBeVisible();
      }
    });
  }

  test("contact form validates and submits only to the isolated lead route", async ({ page }) => {
    let submittedBody: Record<string, string> | undefined;
    await page.route("**/public/leads", async (route) => {
      submittedBody = route.request().postDataJSON() as Record<string, string>;
      await route.fulfill({
        contentType: "application/json",
        status: 201,
        body: JSON.stringify({ status: "received", reference: "e2e-lead" }),
      });
    });
    await page.goto("/contact");
    await page.getByRole("button", { name: /Request a demo/ }).click();
    expect(submittedBody).toBeUndefined();
    await page.getByLabel("Full name").fill("Anita Rao");
    await page.getByLabel("Company").fill("Rao Earthworks");
    await page.getByLabel("Phone").fill("+91 98765 43210");
    await page.getByLabel("Email").fill("anita@example.com");
    await page.getByLabel("Fleet size").selectOption("11-30");
    await page.getByLabel("Primary fleet type").selectOption("mixed");
    await page.getByLabel("What would you like to improve?").fill("Daily site and maintenance coordination");
    await page.getByRole("button", { name: /Request a demo/ }).click();
    await expect(page.getByRole("status")).toContainText("Request received");
    expect(submittedBody).toMatchObject({
      company: "Rao Earthworks",
      fleetSize: "11-30",
      fleetType: "mixed",
    });
  });

  test("SEO discovery files expose only the public surface", async ({ request }) => {
    const sitemap = await request.get("/sitemap.xml");
    expect(sitemap.ok()).toBe(true);
    const sitemapBody = await sitemap.text();
    expect(sitemapBody).toContain("https://fleetaisystems.com/features");
    expect(sitemapBody).not.toContain("/owner");

    const robots = await request.get("/robots.txt");
    expect(robots.ok()).toBe(true);
    const robotsBody = await robots.text();
    expect(robotsBody).toContain("Disallow: /public/");
    expect(robotsBody).toContain("Sitemap: https://fleetaisystems.com/sitemap.xml");
  });

  test("private operational routes do not exist in the marketing service", async ({ request }) => {
    for (const path of ["/owner", "/api/backend/health", "/admin", "/docs", "/openapi.json", "/evidence/private", "/internal"]) {
      const response = await request.get(path);
      expect(response.status(), path).toBe(404);
    }
  });

  test("the public lead surface is create-only", async ({ request }) => {
    const response = await request.get("/public/leads");
    expect(response.status()).toBe(405);
  });

  test("health endpoint reveals no operational diagnostics", async ({ request }) => {
    const response = await request.get("/health");
    expect(response.ok()).toBe(true);
    expect(await response.json()).toEqual({ status: "ok", service: "fleet-ai-systems-marketing" });
  });
});
