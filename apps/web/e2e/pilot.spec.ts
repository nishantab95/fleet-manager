import { expect, test } from "@playwright/test";

const ownerPhone = process.env.PLAYWRIGHT_OWNER_PHONE;
const ownerOtp = process.env.PLAYWRIGHT_OWNER_OTP;

test.describe(
  "owned-tipper pilot browser flow",
  () => {
  test.skip(!ownerPhone || !ownerOtp, "Set PLAYWRIGHT_OWNER_PHONE and PLAYWRIGHT_OWNER_OTP for a real test environment.");
  test("owner can authenticate, view operations, download Excel, and logout", async ({ page, context }) => {
    await page.goto("/login?workspace=owner");
    await page.getByLabel("Phone number").fill(ownerPhone!);
    await page.getByRole("button", { name: "Send OTP" }).click();
    await page.getByLabel("One-time code").fill(ownerOtp!);
    await page.getByRole("button", { name: "Verify and continue" }).click();
    await expect(page).toHaveURL(/\/owner$/);

    await expect(page.getByRole("heading", { name: "Administration" })).toBeVisible();
    await page.getByRole("button", { name: "Operations" }).click();
    await expect(page.getByRole("heading", { name: "Owner operations" })).toBeVisible();
    await page.getByRole("button", { name: /Pilot Site/ }).first().click();
    await expect(page.getByRole("heading", { name: /Pilot Site · daily detail/ })).toBeVisible();
    await page.locator("#owner-closure").getByRole("button", { name: /PILOT12/ }).first().click();
    await expect(page.getByText("KM / Approved Trip")).toBeVisible();
    await expect(page.getByText("Avg Trip Completion Interval")).toBeVisible();
    await expect(page.getByText("Longest Trip Gap")).toBeVisible();

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
const driverPhone = process.env.PLAYWRIGHT_DRIVER_PHONE;
const driverOtp = process.env.PLAYWRIGHT_DRIVER_OTP;

test.describe(
  "supervisor role-isolation browser flow",
  () => {
  test.skip(!supervisorPhone || !supervisorOtp, "Set supervisor OTP variables for role-isolation coverage.");
  test("role-isolated sessions do not expose owner administration", async ({ page }) => {

    await page.goto("/login?workspace=supervisor");
    await page.getByLabel("Phone number").fill(supervisorPhone!);
    await page.getByRole("button", { name: "Send OTP" }).click();
    await page.getByLabel("One-time code").fill(supervisorOtp!);
    await page.getByRole("button", { name: "Verify and continue" }).click();
    await expect(page).toHaveURL(/\/supervisor$/);

    await expect(page.getByRole("heading", { name: "Site operations verification" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Administration" })).not.toBeVisible();
  });
});

test.describe("driver role-bound browser flow", () => {
  test.skip(!driverPhone || !driverOtp, "Set driver OTP variables for driver login coverage.");
  test("driver reaches the QA workspace with the driver OTP", async ({ page }) => {
    await page.goto("/login?workspace=driver-test");
    await page.getByLabel("Phone number").fill(driverPhone!);
    await page.getByRole("button", { name: "Send OTP" }).click();
    await page.getByLabel("One-time code").fill(driverOtp!);
    await page.getByRole("button", { name: "Verify and continue" }).click();
    await expect(page).toHaveURL(/\/driver-test$/);
    await expect(page.getByRole("button", { name: "TRIP COMPLETE", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "EMERGENCY", exact: true })).toBeVisible();
  });
});

test.describe("three-role owned-tipper acceptance flow", () => {
  test.skip(!ownerPhone || !ownerOtp || !supervisorPhone || !supervisorOtp || !driverPhone || !driverOtp, "Set all pilot role phone/OTP variables for the real three-role flow.");

  test("Driver QA events reach Supervisor and Owner reporting", async ({ browser }) => {
    const authenticate = async (page: import("@playwright/test").Page, phone: string, otp: string, workspace: string) => {
      await page.goto(`/login?workspace=${workspace}`);
      await page.getByLabel("Phone number").fill(phone);
      await page.getByRole("button", { name: "Send OTP" }).click();
      await page.getByLabel("One-time code").fill(otp);
      await page.getByRole("button", { name: "Verify and continue" }).click();
    };

    const ownerContext = await browser.newContext();
    const ownerPage = await ownerContext.newPage();
    await authenticate(ownerPage, ownerPhone!, ownerOtp!, "owner");
    await expect(ownerPage).toHaveURL(/\/owner$/);
    await expect(ownerPage.getByRole("heading", { name: "Administration" })).toBeVisible();

    const driverContext = await browser.newContext();
    const driverPage = await driverContext.newPage();
    await authenticate(driverPage, driverPhone!, driverOtp!, "driver-test");
    await expect(driverPage).toHaveURL(/\/driver-test$/);
    await expect(driverPage.getByText("Pilot Site")).toBeVisible();
    await expect(driverPage.getByRole("button", { name: "TRIP COMPLETE", exact: true })).toBeVisible();
    await expect(driverPage.getByRole("button", { name: "KM READING", exact: true })).toBeVisible();
    await expect(driverPage.getByRole("button", { name: /DIESEL ISSUED/ })).toBeVisible();
    await expect(driverPage.getByRole("button", { name: "EMERGENCY", exact: true })).toBeVisible();

    const image = { name: "meter-test.png", mimeType: "image/png", buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=", "base64") };
    await driverPage.getByRole("button", { name: "KM READING", exact: true }).click();
    await driverPage.getByLabel("Reading type").selectOption("START_READING");
    await driverPage.getByLabel("KM value").fill("10000");
    await driverPage.getByLabel("Local test image").setInputFiles(image);
    await driverPage.getByRole("button", { name: "Submit KM reading" }).click();
    await expect(driverPage.getByText("KM_READING").first()).toBeVisible();

    for (let index = 0; index < 4; index += 1) {
      await driverPage.getByRole("button", { name: "TRIP COMPLETE", exact: true }).click();
      await expect(driverPage.getByText("TRIP_COMPLETE").nth(index)).toBeVisible();
    }

    await driverPage.getByRole("button", { name: /DIESEL ISSUED/ }).click();
    await driverPage.getByLabel("Litres").fill("30");
    await driverPage.getByLabel("Local test image").setInputFiles(image);
    await driverPage.getByRole("button", { name: /Submit diesel/ }).click();
    await expect(driverPage.getByText("DIESEL").first()).toBeVisible();

    await driverPage.getByRole("button", { name: "KM READING", exact: true }).click();
    await driverPage.getByLabel("Reading type").selectOption("END_READING");
    await driverPage.getByLabel("KM value").fill("10120");
    await driverPage.getByLabel("Local test image").setInputFiles(image);
    await driverPage.getByRole("button", { name: "Submit KM reading" }).click();
    await expect(driverPage.getByText("KM_READING").nth(1)).toBeVisible();

    await driverPage.getByRole("button", { name: "EMERGENCY", exact: true }).click();
    await expect(driverPage.getByText("EMERGENCY").first()).toBeVisible();

    const supervisorContext = await browser.newContext();
    const supervisorPage = await supervisorContext.newPage();
    await authenticate(supervisorPage, supervisorPhone!, supervisorOtp!, "supervisor");
    await expect(supervisorPage).toHaveURL(/\/supervisor$/);
    await expect(supervisorPage.getByRole("heading", { name: /Pilot Site · daily completeness/ })).toBeVisible();
    await expect(supervisorPage.getByText(/KM READING/).first()).toBeVisible();
    await expect(supervisorPage.getByText(/TRIP COMPLETE/).first()).toBeVisible();
    await expect(supervisorPage.getByText(/DIESEL/).first()).toBeVisible();
    await expect(supervisorPage.getByText(/EMERGENCY/).first()).toBeVisible();

    const pendingEvents = supervisorPage.locator("article").filter({ hasText: "PENDING_VERIFICATION" });
    const pendingCount = await pendingEvents.count();
    for (let index = 0; index < pendingCount; index += 1) {
      const event = pendingEvents.nth(index);
      if (!(await event.getByText(/EMERGENCY/).count())) await event.getByRole("checkbox").check();
    }
    await supervisorPage.getByRole("button", { name: /Approve selected/ }).click();
    await expect(supervisorPage.getByText(/APPROVED/).first()).toBeVisible();
    const emergency = supervisorPage.locator("article").filter({ hasText: "EMERGENCY" }).first();
    if (await emergency.getByRole("button", { name: "Acknowledge" }).count()) await emergency.getByRole("button", { name: "Acknowledge" }).click();
    await expect(emergency.getByRole("button", { name: "Resolve" })).toBeVisible();
    await emergency.getByRole("button", { name: "Resolve" }).click();

    await ownerPage.getByRole("button", { name: "Operations" }).click();
    await expect(ownerPage.getByRole("heading", { name: "Owner operations" })).toBeVisible();
    await ownerPage.getByRole("button", { name: "Refresh" }).click();
    await expect(ownerPage.getByText("Approved trips").locator(".." ).getByText("4")).toBeVisible();
    await expect(ownerPage.getByText(/120/).first()).toBeVisible();
    await expect(ownerPage.getByText(/30/).first()).toBeVisible();
    await ownerPage.getByRole("button", { name: /Pilot Site/ }).first().click();
    await expect(ownerPage.getByRole("heading", { name: /Pilot Site · daily detail/ })).toBeVisible();
    const siteDetail = ownerPage.locator("section.stack").filter({ has: ownerPage.getByRole("heading", { name: /Pilot Site · daily detail/ }) });
    await siteDetail.getByRole("button", { name: /PILOT12/ }).click();
    await expect(ownerPage.getByRole("heading", { name: /PILOT12 · event trace/ })).toBeVisible();
    await expect(ownerPage.getByText(/10000/).first()).toBeVisible();
    await expect(ownerPage.getByText(/10120/).first()).toBeVisible();
    await ownerPage.getByRole("button", { name: "Close day" }).click();
    await expect(ownerPage.getByRole("button", { name: "Reopen day" })).toBeVisible();
    const downloadPromise = ownerPage.waitForEvent("download");
    await ownerPage.getByRole("button", { name: "Download Excel" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/fleet-report-.*\.xlsx/);

    await ownerContext.close();
    await driverContext.close();
    await supervisorContext.close();
  });
});
