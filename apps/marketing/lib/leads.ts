import { randomUUID } from "node:crypto";
import { realpath, stat, writeFile } from "node:fs/promises";
import path from "node:path";

export const fleetSizes = ["1-10", "11-30", "31-75", "76+"] as const;
export const fleetTypes = ["tippers", "earthmoving", "mixed", "other"] as const;

export type PublicLead = {
  name: string;
  company: string;
  phone: string;
  email: string;
  fleetSize: (typeof fleetSizes)[number];
  fleetType: (typeof fleetTypes)[number];
  message: string;
};

type ValidationResult =
  | { ok: true; value: PublicLead }
  | { ok: false; fields: Record<string, string> };

export class LeadStoreUnavailableError extends Error {}

function compact(value: unknown): string {
  return typeof value === "string" ? value.trim().replace(/\s+/g, " ") : "";
}

function messageText(value: unknown): string {
  return typeof value === "string"
    ? value.trim().replace(/\r\n/g, "\n").replace(/[\t\f\v]+/g, " ")
    : "";
}

function unsafeMarkup(value: string): boolean {
  return /[<>]/.test(value);
}

export function validateLead(input: unknown): ValidationResult {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    return { ok: false, fields: { form: "Enter the required contact details." } };
  }
  const body = input as Record<string, unknown>;
  const honeypot = compact(body.website);
  const name = compact(body.name);
  const company = compact(body.company);
  const phone = compact(body.phone);
  const email = compact(body.email).toLowerCase();
  const fleetSize = compact(body.fleetSize);
  const fleetType = compact(body.fleetType);
  const message = messageText(body.message);
  const fields: Record<string, string> = {};

  if (honeypot) fields.form = "The request could not be accepted.";
  if (name.length < 2 || name.length > 80 || unsafeMarkup(name)) {
    fields.name = "Enter a name between 2 and 80 characters.";
  }
  if (company.length < 2 || company.length > 120 || unsafeMarkup(company)) {
    fields.company = "Enter a company name between 2 and 120 characters.";
  }
  const phoneDigits = phone.replace(/\D/g, "");
  if (
    phone.length > 24 ||
    phoneDigits.length < 7 ||
    phoneDigits.length > 15 ||
    !/^\+?[0-9 ()-]+$/.test(phone)
  ) {
    fields.phone = "Enter a valid contact number.";
  }
  if (
    email.length > 254 ||
    !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ||
    unsafeMarkup(email)
  ) {
    fields.email = "Enter a valid email address.";
  }
  if (!fleetSizes.includes(fleetSize as PublicLead["fleetSize"])) {
    fields.fleetSize = "Select a fleet-size range.";
  }
  if (!fleetTypes.includes(fleetType as PublicLead["fleetType"])) {
    fields.fleetType = "Select a primary fleet type.";
  }
  if (message.length < 20 || message.length > 1000 || unsafeMarkup(message)) {
    fields.message = "Enter 20 to 1,000 characters without HTML markup.";
  }

  if (Object.keys(fields).length > 0) return { ok: false, fields };
  return {
    ok: true,
    value: {
      name,
      company,
      phone,
      email,
      fleetSize: fleetSize as PublicLead["fleetSize"],
      fleetType: fleetType as PublicLead["fleetType"],
      message,
    },
  };
}

function isInside(parent: string, child: string): boolean {
  const relative = path.relative(parent, child);
  return (
    relative === "" ||
    (!path.isAbsolute(relative) &&
      !relative.startsWith(`..${path.sep}`) &&
      relative !== "..")
  );
}

export async function persistLead(
  lead: PublicLead,
  configuredDirectory = process.env.FLEET_MARKETING_LEAD_DIR,
): Promise<{ id: string; receivedAt: string }> {
  if (!configuredDirectory?.trim() || !path.isAbsolute(configuredDirectory)) {
    throw new LeadStoreUnavailableError("Lead storage is not configured.");
  }
  const leadDirectory = await realpath(configuredDirectory.trim()).catch(() => null);
  if (!leadDirectory) {
    throw new LeadStoreUnavailableError("Lead storage is unavailable.");
  }
  const info = await stat(leadDirectory);
  if (!info.isDirectory()) {
    throw new LeadStoreUnavailableError("Lead storage is unavailable.");
  }
  const workingDirectory = await realpath(process.cwd());
  const workingDirectoryParent = path.dirname(workingDirectory);
  const repositoryRoot =
    path.basename(workingDirectory).toLowerCase() === "marketing" &&
    path.basename(workingDirectoryParent).toLowerCase() === "apps"
      ? path.dirname(workingDirectoryParent)
      : workingDirectory;
  if (isInside(repositoryRoot, leadDirectory)) {
    throw new LeadStoreUnavailableError("Lead storage must remain outside the repository.");
  }

  const id = randomUUID();
  const receivedAt = new Date().toISOString();
  const filename = `${receivedAt.replace(/[:.]/g, "-")}-${id}.json`;
  const payload = JSON.stringify({ id, receivedAt, ...lead }) + "\n";
  await writeFile(path.join(leadDirectory, filename), payload, {
    encoding: "utf8",
    flag: "wx",
    mode: 0o600,
  });
  return { id, receivedAt };
}
