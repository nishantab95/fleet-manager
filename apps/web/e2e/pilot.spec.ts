import { expect, test } from "@playwright/test";

const ownerPhone = process.env.PLAYWRIGHT_OWNER_PHONE;
const ownerOtp = process.env.PLAYWRIGHT_OWNER_OTP;

test.describe(
  "owned-tipper pilot browser flow",
  () => {
  test.skip(!ownerPhone || !ownerOtp, "Set PLAYWRIGHT_OWNER_PHONE and PLAYWRIGHT_OWNER_OTP for a real test environment.");
  test("owner can authenticate, view operations, download Excel, and logout", async ({ page, context }) => {
    await page.goto("/");
    await page.getByLabel("Phone number").fill(ownerPhone!);
    await page.getByRole("button", { name: "Send OTP" }).click();
    await page.getByLabel("One-time code").fill(ownerOtp!);
    await page.getByRole("button", { name: "Verify and continue" }).click();
    await page.getByRole("button", { name: /OWNER_ADMIN/ }).first().click();

    await expect(page.getByRole("heading", { name: "Administration" })).toBeVisible();
    await page.getByRole("button", { name: "Operations" }).click();
    await expect(page.getByRole("heading", { name: "Owner operations" })).toBeVisible();

    const refreshCookie = (await context.cookies()).find((cookie) => cookie.name === "fleet_web_refresh");
    expect(refreshCookie?.httpOnly).toBe(true);
    expect(refreshCookie?.sameSite).toBe("Lax");
    await page.getByRole("button", { name: "Download Excel" }).click();
    await page.getByRole("button", { name: "Log out" }).click();
    await expect(page.getByRole("heading", { name: "Choose your operations workspace" })).toBeVisible();
  });

});

const supervisorPhone = process.env.PLAYWRIGHT_SUPERVISOR_PHONE;
const supervisorOtp = process.env.PLAYWRIGHT_SUPERVISOR_OTP;

test.describe(
  "supervisor role-isolation browser flow",
  () => {
  test.skip(!supervisorPhone || !supervisorOtp, "Set supervisor OTP variables for role-isolation coverage.");
  test("role-isolated sessions do not expose owner administration", async ({ page }) => {

    await page.goto("/");
    await page.getByLabel("Phone number").fill(supervisorPhone!);
    await page.getByRole("button", { name: "Send OTP" }).click();
    await page.getByLabel("One-time code").fill(supervisorOtp!);
    await page.getByRole("button", { name: "Verify and continue" }).click();
    await page.getByRole("button", { name: /SUPERVISOR/ }).first().click();

    await expect(page.getByRole("heading", { name: "Site operations verification" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Administration" })).not.toBeVisible();
  });
});
