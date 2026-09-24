import { expect, test, type Page } from "@playwright/test";

const ownerPhone = process.env.PLAYWRIGHT_OWNER_PHONE;
const supervisorPhone = process.env.PLAYWRIGHT_SUPERVISOR_PHONE;
const pilotOtp = process.env.PLAYWRIGHT_OWNER_OTP ?? process.env.PLAYWRIGHT_SUPERVISOR_OTP;
const evidenceEventId = process.env.PLAYWRIGHT_EVIDENCE_EVENT_ID;

async function authenticate(page: Page, phone: string, role: string) {
  await page.goto("/");
  await page.getByLabel("Phone number").fill(phone);
  await page.getByRole("button", { name: "Send OTP" }).click();
  await page.getByLabel("One-time code").fill(pilotOtp!);
  await page.getByRole("button", { name: "Verify and continue" }).click();
  await page.getByRole("button", { name: new RegExp(role) }).first().click();
}

async function inspectEvidenceButtons(page: Page) {
  const buttons = page.getByRole("button", { name: "View evidence" });
  await expect(buttons.first()).toBeVisible();
  const count = await buttons.count();
  for (let index = 0; index < Math.min(count, 3); index += 1) {
    await buttons.nth(index).click();
    const dialog = page.getByRole("dialog", { name: "Operational evidence" });
    await expect(dialog).toBeVisible();
    await expect(dialog.locator("img")).toBeVisible();
    await dialog.getByRole("button", { name: "Close evidence" }).click();
  }
}

test.describe("private evidence browser acceptance", () => {
  test.skip(!ownerPhone || !supervisorPhone || !pilotOtp, "Set pilot Owner/Supervisor phone and OTP variables for the real evidence flow.");

  test("Supervisor, Owner, and stable evidence route display private photos", async ({ browser }) => {
    const supervisorContext = await browser.newContext();
    const supervisorPage = await supervisorContext.newPage();
    await authenticate(supervisorPage, supervisorPhone!, "SUPERVISOR");
    await expect(supervisorPage.getByRole("heading", { name: "Site operations verification" })).toBeVisible();
    await inspectEvidenceButtons(supervisorPage);

    if (evidenceEventId) {
      await supervisorPage.goto(`/evidence/${evidenceEventId}`);
      await expect(supervisorPage.getByRole("dialog", { name: "Operational evidence" })).toBeVisible();
      await expect(supervisorPage.getByRole("dialog").locator("img")).toBeVisible();
    }

    const ownerContext = await browser.newContext();
    const ownerPage = await ownerContext.newPage();
    await authenticate(ownerPage, ownerPhone!, "OWNER_ADMIN");
    await ownerPage.getByRole("button", { name: "Operations" }).click();
    await expect(ownerPage.getByRole("heading", { name: "Owner operations" })).toBeVisible();
    await ownerPage.getByRole("button", { name: /Pilot Site/ }).first().click();
    await expect(ownerPage.getByRole("heading", { name: /Pilot Site · daily detail/ })).toBeVisible();
    await ownerPage.locator("#owner-closure").getByRole("button", { name: /PILOT12/ }).first().click();
    await expect(ownerPage.getByRole("heading", { name: /PILOT12 · event trace/ })).toBeVisible();
    await inspectEvidenceButtons(ownerPage);

    await supervisorContext.close();
    await ownerContext.close();
  });
});
