import { createHash } from "node:crypto";

import { LeadStoreUnavailableError, persistLead, validateLead } from "../../../lib/leads";

export const dynamic = "force-dynamic";

const requestLimitBytes = 8_192;
const rateLimitWindowMs = 10 * 60 * 1_000;
const rateLimitMaximum = 5;
const rateBuckets = new Map<string, number[]>();

class RequestTooLargeError extends Error {}

function requestKey(request: Request): string {
  const forwarded = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  const address = request.headers.get("x-real-ip") || forwarded || "local";
  return createHash("sha256").update(address).digest("hex");
}

async function readJsonWithinLimit(request: Request): Promise<unknown> {
  if (!request.body) throw new SyntaxError("Missing request body.");
  const reader = request.body.getReader();
  const decoder = new TextDecoder();
  let received = 0;
  let raw = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    received += value.byteLength;
    if (received > requestLimitBytes) {
      await reader.cancel();
      throw new RequestTooLargeError();
    }
    raw += decoder.decode(value, { stream: true });
  }
  raw += decoder.decode();
  return JSON.parse(raw);
}

function rateLimited(key: string, now = Date.now()): boolean {
  const cutoff = now - rateLimitWindowMs;
  const recent = (rateBuckets.get(key) ?? []).filter((timestamp) => timestamp > cutoff);
  if (recent.length >= rateLimitMaximum) {
    rateBuckets.set(key, recent);
    return true;
  }
  recent.push(now);
  rateBuckets.set(key, recent);
  if (rateBuckets.size > 10_000) rateBuckets.clear();
  return false;
}

function json(body: object, status: number, headers: HeadersInit = {}) {
  return Response.json(body, {
    status,
    headers: { "Cache-Control": "no-store", ...headers },
  });
}

export async function POST(request: Request) {
  const contentType = request.headers.get("content-type")?.split(";", 1)[0];
  if (contentType !== "application/json") {
    return json({ error: "Content type must be application/json." }, 415);
  }
  const contentLength = Number(request.headers.get("content-length") ?? "0");
  if (!Number.isFinite(contentLength) || contentLength > requestLimitBytes) {
    return json({ error: "Request is too large." }, 413);
  }
  const origin = request.headers.get("origin");
  if (origin) {
    const allowed = new Set([
      "https://fleetaisystems.com",
      "https://www.fleetaisystems.com",
      "http://127.0.0.1:3001",
      "http://localhost:3001",
    ]);
    if (!allowed.has(origin)) return json({ error: "Origin is not allowed." }, 403);
  }
  const key = requestKey(request);
  if (rateLimited(key)) {
    return json({ error: "Too many requests. Please try again later." }, 429, {
      "Retry-After": "600",
    });
  }

  let body: unknown;
  try {
    body = await readJsonWithinLimit(request);
  } catch (error) {
    if (error instanceof RequestTooLargeError) {
      return json({ error: "Request is too large." }, 413);
    }
    return json({ error: "Request body must be valid JSON." }, 400);
  }
  const validated = validateLead(body);
  if (!validated.ok) {
    return json({ error: "Check the highlighted fields.", fields: validated.fields }, 422);
  }

  try {
    const receipt = await persistLead(validated.value);
    console.info(JSON.stringify({ event: "PUBLIC_LEAD_CREATED", leadId: receipt.id, receivedAt: receipt.receivedAt }));
    return json({ status: "received", reference: receipt.id }, 201);
  } catch (error) {
    if (error instanceof LeadStoreUnavailableError) {
      return json({ error: "Demo requests are temporarily unavailable. Please use the email link." }, 503);
    }
    console.error(JSON.stringify({ event: "PUBLIC_LEAD_WRITE_FAILED" }));
    return json({ error: "Demo requests are temporarily unavailable. Please use the email link." }, 503);
  }
}
