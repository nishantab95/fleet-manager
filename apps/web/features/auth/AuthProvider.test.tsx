import { StrictMode } from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { requestMock, refreshWebSessionMock } = vi.hoisted(() => ({
  requestMock: vi.fn(async (path: string) => {
    if (path === "/api/v1/auth/me") {
      return { user_id: "user-1", display_name: "Pilot Owner", membership_id: "membership-1", company_id: "company-1", company_name: "Pilot Construction", role: "OWNER_ADMIN" };
    }
    return {};
  }),
  refreshWebSessionMock: vi.fn(async () => ({ access_token: "access-token", expires_in: 900, membership_id: "membership-1", company_id: "company-1", role: "OWNER_ADMIN" })),
}));

vi.mock("../../lib/api/client", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  request: requestMock,
  refreshWebSession: refreshWebSessionMock,
}));

import { AuthProvider, useAuth } from "./AuthProvider";

function StatusProbe() {
  const { status } = useAuth();
  return <span>{status}</span>;
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AuthProvider", () => {
  it("deduplicates StrictMode session restoration refreshes", async () => {
    render(
      <StrictMode>
        <AuthProvider>
          <StatusProbe />
        </AuthProvider>
      </StrictMode>,
    );

    await waitFor(() => expect(screen.getByText("authenticated")).toBeInTheDocument());
    expect(refreshWebSessionMock).toHaveBeenCalledTimes(1);
    expect(requestMock).toHaveBeenCalledTimes(1);
    expect(requestMock).toHaveBeenCalledWith("/api/v1/auth/me", {}, "access-token");
  });
});
