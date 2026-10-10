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

  for (const width of [390, 768, 1280, 1440, 1920]) {
    test(`homepage remains usable at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/");
      await expect(page.getByRole("heading", { level: 1, name: /Run the field/ })).toBeVisible();
      const dimensions = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
      expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client + 1);
      if (width < 1120) {
        await page.locator(".marketing-menu summary").click();
        await expect(page.locator(".marketing-menu nav").getByRole("link", { name: "Features" })).toBeVisible();
      } else {
        await expect(page.locator(".marketing-nav--desktop").getByRole("link", { name: "Features" })).toBeVisible();
      }
    });
  }

  test("contact form creates an explicit email handoff", async ({ page }) => {
    await page.goto("/contact");
    await page.getByLabel("Full name").fill("Anita Rao");
    await page.getByLabel("Company").fill("Rao Earthworks");
    await page.getByLabel("Phone").fill("+91 98765 43210");
    await page.getByLabel("Email").fill("anita@example.com");
    await page.getByLabel("Fleet size").selectOption("11–30 assets");
    await page.getByLabel("What would you like to improve?").fill("Daily site coordination");
    await page.getByRole("button", { name: /Prepare demo request/ }).click();
    await expect(page.getByRole("status")).toContainText("Your request is ready");
    await expect(page.getByRole("link", { name: /Open email draft/ })).toHaveAttribute("href", /^mailto:hello@fleetaisystems\.com/);
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
    expect(robotsBody).toContain("Disallow: /owner");
    expect(robotsBody).toContain("Sitemap: https://fleetaisystems.com/sitemap.xml");
  });
});
