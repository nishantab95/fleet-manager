import type { Tokens } from "../types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
  }
}

export type WebRequest = <T>(path: string, options?: RequestInit) => Promise<T>;

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
    const message = typeof detail === "object" ? detail.message : detail;
    throw new ApiError(response.status, message ?? "The request could not be completed.");
  }
  return body as T;
}

export async function refreshWebSession(): Promise<Tokens> {
  return request<Tokens>("/api/v1/auth/web-refresh", { method: "POST" });
}

export async function uploadDriverEvidence(accessToken: string, clientEventUuid: string, file: File): Promise<{ object_reference: string; content_type: string; size_bytes: number }> {
  const form = new FormData();
  form.append("file", file);
  return request(`/api/v1/driver/evidence?client_event_uuid=${encodeURIComponent(clientEventUuid)}`, { method: "POST", body: form }, accessToken);
}
