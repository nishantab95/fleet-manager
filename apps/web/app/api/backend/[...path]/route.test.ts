import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { proxyFleetRequest } from "./route";

const context = (path: string[]) => ({ params: Promise.resolve({ path }) });

afterEach(() => { vi.restoreAllMocks(); delete process.env.FLEET_API_UPSTREAM_URL; });

describe("Fleet API same-origin proxy", () => {
  it("forwards query, auth, cookie, content type, and request bytes", async () => {
    process.env.FLEET_API_UPSTREAM_URL = "https://fleet.test";
    const fetchMock = vi.fn(async (...args: Parameters<typeof fetch>) => { void args; return new Response(JSON.stringify({ ok: true }), { status: 201, headers: { "content-type": "application/json", "set-cookie": "fleet_web_refresh=abc; Path=/api/v1/auth; HttpOnly; Secure; SameSite=Lax" } }); });
    vi.stubGlobal("fetch", fetchMock);
    const request = new NextRequest("http://127.0.0.1:3000/api/backend/api/v1/auth/web-refresh?mode=owner", { method: "POST", headers: { authorization: "Bearer token", cookie: "fleet_web_refresh=old", "content-type": "application/json", "x-request-id": "request-1" }, body: JSON.stringify({ value: 1 }) });
    const response = await proxyFleetRequest(request, context(["api", "v1", "auth", "web-refresh"]));
    expect(response.status).toBe(201);
    const [url, options] = fetchMock.mock.calls[0]!;
    expect(options).toBeDefined();
    expect(String(url)).toBe("https://fleet.test/api/v1/auth/web-refresh?mode=owner");
    expect(options).toEqual(expect.objectContaining({ method: "POST", cache: "no-store", redirect: "manual" }));
    expect((options!.headers as Headers).get("authorization")).toBe("Bearer token");
    expect((options!.headers as Headers).get("cookie")).toBe("fleet_web_refresh=old");
    expect(new TextDecoder().decode(options!.body as ArrayBuffer)).toBe('{"value":1}');
    expect(response.headers.get("set-cookie")).toContain("Path=/api/backend/api/v1/auth");
    expect(response.headers.get("set-cookie")).not.toContain("Secure");
  });

  it("preserves multipart content and returns a controlled unavailable response", async () => {
    process.env.FLEET_API_UPSTREAM_URL = "https://fleet.test/base";
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => { void args; return Promise.reject(new Error("offline")); });
    vi.stubGlobal("fetch", fetchMock);
    const request = new NextRequest("http://localhost:3000/api/backend/api/v1/evidence", { method: "POST", headers: { "content-type": "multipart/form-data; boundary=boundary" }, body: "--boundary\r\ncontent\r\n--boundary--" });
    const response = await proxyFleetRequest(request, context(["api", "v1", "evidence"]));
    expect(response.status).toBe(502);
    expect(await response.json()).toEqual({ detail: "Fleet API upstream is unavailable" });
    expect((fetchMock.mock.calls[0]![1]!.headers as Headers).get("content-type")).toContain("multipart/form-data");
  });

  it("forwards deployment removal preview with the asset identifier and exact operation route", async () => {
    process.env.FLEET_API_UPSTREAM_URL = "https://fleet.test";
    const fetchMock = vi.fn(async (...args: Parameters<typeof fetch>) => {
      void args;
      return Response.json({ action: "REMOVE_DEPLOYMENT", can_execute: true });
    });
    vi.stubGlobal("fetch", fetchMock);
    const request = new NextRequest("http://localhost:3000/api/backend/api/v1/owner/operations/preview", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "REMOVE_DEPLOYMENT", asset_id: "asset-deployed" }),
    });

    const response = await proxyFleetRequest(
      request,
      context(["api", "v1", "owner", "operations", "preview"]),
    );

    expect(response.status).toBe(200);
    const [url, options] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("https://fleet.test/api/v1/owner/operations/preview");
    expect(new TextDecoder().decode(options!.body as ArrayBuffer)).toBe(
      '{"action":"REMOVE_DEPLOYMENT","asset_id":"asset-deployed"}',
    );
  });

  it("rejects paths outside the Fleet API allow-list", async () => {
    const response = await proxyFleetRequest(new NextRequest("http://localhost:3000/api/backend/private"), context(["private"]));
    expect(response.status).toBe(404);
  });
});
