import type { Tokens } from "../types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly code?: string,
    public readonly context?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type WebRequest = <T>(path: string, options?: RequestInit) => Promise<T>;

export type EvidenceMetadata = {
  eventType: string;
  driverName: string;
  tipperRegistrationNumber: string;
  deviceCreatedAt: string;
};

export async function request<T>(path: string, options: RequestInit = {}, accessToken?: string): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, credentials: "include", headers });
  } catch {
    throw new ApiError(0, "The API is unavailable. Start the backend and try again.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body?.detail;
    const structured = detail && typeof detail === "object" ? detail as Record<string, unknown> : undefined;
    const message = structured ? structured.message : detail;
    throw new ApiError(
      response.status,
      typeof message === "string" ? message : "The request could not be completed.",
      typeof structured?.code === "string" ? structured.code : undefined,
      structured,
    );
  }
  return body as T;
}

export async function refreshWebSession(): Promise<Tokens> {
  return request<Tokens>("/api/v1/auth/web-refresh", { method: "POST" });
}

export async function fetchPrivateEvidence(path: string, accessToken: string): Promise<{ url: string; metadata: EvidenceMetadata }> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      credentials: "include",
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
    });
  } catch {
    throw new ApiError(0, "Evidence could not be loaded because the API is unavailable.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    const structured = detail && typeof detail === "object" ? detail as Record<string, unknown> : undefined;
    const message = structured ? structured.message : detail;
    throw new ApiError(
      response.status,
      typeof message === "string" ? message : "Evidence could not be loaded.",
      typeof structured?.code === "string" ? structured.code : undefined,
      structured,
    );
  }
  return {
    url: URL.createObjectURL(await response.blob()),
    metadata: {
      eventType: response.headers.get("X-Fleet-Evidence-Event-Type") ?? "Evidence",
      driverName: response.headers.get("X-Fleet-Evidence-Driver") ?? "Unknown driver",
      tipperRegistrationNumber: response.headers.get("X-Fleet-Evidence-Tipper") ?? "Unknown tipper",
      deviceCreatedAt: response.headers.get("X-Fleet-Evidence-Timestamp") ?? "",
    },
  };
}

export async function uploadDriverEvidence(accessToken: string, clientEventUuid: string, file: File): Promise<{ object_reference: string; content_type: string; size_bytes: number }> {
  const form = new FormData();
  form.append("file", file);
  return request(`/api/v1/driver/evidence?client_event_uuid=${encodeURIComponent(clientEventUuid)}`, { method: "POST", body: form }, accessToken);
}
