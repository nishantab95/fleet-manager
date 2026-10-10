import { mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { LeadStoreUnavailableError, persistLead, validateLead } from "./leads";

const validLead = {
  name: "Anita Rao",
  company: "Rao Earthworks",
  phone: "+91 98765 43210",
  email: "ANITA@example.com",
  fleetSize: "11-30",
  fleetType: "mixed",
  message: "We need clearer multi-site duty and maintenance coordination.",
  website: "",
};

const cleanupPaths: string[] = [];
afterEach(async () => {
  await Promise.all(cleanupPaths.splice(0).map((entry) => rm(entry, { recursive: true, force: true })));
});

describe("public lead boundary", () => {
  it("normalizes the approved fields and rejects arbitrary markup", () => {
    expect(validateLead(validLead)).toEqual({
      ok: true,
      value: {
        name: "Anita Rao",
        company: "Rao Earthworks",
        phone: "+91 98765 43210",
        email: "anita@example.com",
        fleetSize: "11-30",
        fleetType: "mixed",
        message: "We need clearer multi-site duty and maintenance coordination.",
      },
    });
    const unsafe = validateLead({ ...validLead, message: "<script>alert('x')</script> and more text" });
    expect(unsafe.ok).toBe(false);
    if (!unsafe.ok) expect(unsafe.fields.message).toMatch(/without HTML/);
  });

  it("rejects bot, invalid enum, and oversized input", () => {
    const result = validateLead({
      ...validLead,
      website: "https://bot.example",
      fleetSize: "100000",
      message: "x".repeat(1001),
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.fields.form).toBeDefined();
      expect(result.fields.fleetSize).toBeDefined();
      expect(result.fields.message).toBeDefined();
    }
  });

  it("writes one private JSON record only to an external configured directory", async () => {
    const directory = await mkdtemp(path.join(tmpdir(), "fleet-marketing-leads-"));
    cleanupPaths.push(directory);
    const validated = validateLead(validLead);
    expect(validated.ok).toBe(true);
    if (!validated.ok) return;

    const receipt = await persistLead(validated.value, directory);
    const files = await readdir(directory);
    expect(files).toHaveLength(1);
    const record = JSON.parse(await readFile(path.join(directory, files[0]), "utf8"));
    expect(record.id).toBe(receipt.id);
    expect(record.email).toBe("anita@example.com");
    expect(record).not.toHaveProperty("ip");
    expect(record).not.toHaveProperty("userAgent");
  });

  it("fails closed when storage is not configured", async () => {
    const validated = validateLead(validLead);
    if (!validated.ok) throw new Error("fixture must be valid");
    await expect(persistLead(validated.value, "")).rejects.toBeInstanceOf(LeadStoreUnavailableError);
  });
});
