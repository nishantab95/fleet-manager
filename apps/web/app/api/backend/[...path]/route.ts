import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const ALLOWED_ROOTS = new Set(["api", "health", "ready"]);
const REQUEST_HEADERS = [
  "accept",
  "authorization",
  "content-type",
  "cookie",
  "if-match",
  "if-none-match",
  "x-request-id",
];
const RESPONSE_HEADERS = [
  "cache-control",
  "content-disposition",
  "content-length",
  "content-type",
  "etag",
  "last-modified",
  "x-request-id",
  "x-fleet-evidence-event-type",
  "x-fleet-evidence-driver",
  "x-fleet-evidence-tipper",
  "x-fleet-evidence-timestamp",
];

type ProxyContext = { params: Promise<{ path: string[] }> };

function upstreamBase(): URL {
  const configured = process.env.FLEET_API_UPSTREAM_URL?.trim() || "http://localhost:8000";
  const url = new URL(configured);
  if (!new Set(["http:", "https:"]).has(url.protocol)) {
    throw new Error("FLEET_API_UPSTREAM_URL must use HTTP or HTTPS");
  }
  url.pathname = url.pathname.replace(/\/$/, "");
  return url;
}

function requestHeaders(request: Request): Headers {
  const headers = new Headers();
  for (const name of REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  return headers;
}

function isLoopback(hostname: string): boolean {
  return hostname === "127.0.0.1" || hostname === "localhost" || hostname === "[::1]";
}

function browserCookie(cookie: string, request: NextRequest): string {
  const rewritten = cookie.replace(/Path=\/api\/v1\/auth(?=;|$)/i, "Path=/api/backend/api/v1/auth");
  if (process.env.NODE_ENV !== "production" && request.nextUrl.protocol === "http:" && isLoopback(request.nextUrl.hostname)) {
    return rewritten.replace(/;\s*Secure(?=;|$)/i, "");
  }
  return rewritten;
}

function setCookies(headers: Headers): string[] {
  const extended = headers as Headers & { getSetCookie?: () => string[] };
  if (extended.getSetCookie) return extended.getSetCookie();
  const value = headers.get("set-cookie");
  return value ? [value] : [];
}

export async function proxyFleetRequest(request: NextRequest, context: ProxyContext): Promise<Response> {
  const { path } = await context.params;
  if (!path.length || !ALLOWED_ROOTS.has(path[0]) || path.some((segment) => segment === "..")) {
    return Response.json({ detail: "Unsupported backend path" }, { status: 404 });
  }

  let upstream: URL;
  try {
    upstream = upstreamBase();
  } catch {
    return Response.json({ detail: "Fleet API upstream is not configured correctly" }, { status: 500 });
  }
  upstream.pathname = `${upstream.pathname}/${path.map(encodeURIComponent).join("/")}`.replace(/\/+/g, "/");
  upstream.search = request.nextUrl.search;

  const method = request.method.toUpperCase();
  const body = method === "GET" || method === "HEAD" ? undefined : await request.arrayBuffer();
  let response: Response;
  try {
    response = await fetch(upstream, {
      method,
      headers: requestHeaders(request),
      body,
      cache: "no-store",
      redirect: "manual",
    });
  } catch {
    return Response.json({ detail: "Fleet API upstream is unavailable" }, { status: 502 });
  }

  const headers = new Headers();
  for (const name of RESPONSE_HEADERS) {
    const value = response.headers.get(name);
    if (value) headers.set(name, value);
  }
  for (const cookie of setCookies(response.headers)) headers.append("set-cookie", browserCookie(cookie, request));
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}

export const GET = proxyFleetRequest;
export const HEAD = proxyFleetRequest;
export const POST = proxyFleetRequest;
export const PUT = proxyFleetRequest;
export const PATCH = proxyFleetRequest;
export const DELETE = proxyFleetRequest;
export const OPTIONS = proxyFleetRequest;
