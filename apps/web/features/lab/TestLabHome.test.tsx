import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TestLabHome } from "./TestLabHome";

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("PC Test Lab home", () => {
  it("renders three navigation-only role cards and local service status", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (String(input).endsWith("/health")) return Promise.resolve(response({ service: "fleet-manager-api", status: "ok" }));
      return Promise.resolve(response({ database: "available", status: "ready" }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<TestLabHome />);

    expect(screen.getByRole("heading", { name: "PC TEST LAB" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /DRIVER.*Enter operational events/ })).toHaveAttribute("href", "/login?workspace=driver-test");
    expect(screen.getByRole("link", { name: /SUPERVISOR.*Review and verify events/ })).toHaveAttribute("href", "/login?workspace=supervisor");
    expect(screen.getByRole("link", { name: /OWNER.*Dashboard, reports and administration/ })).toHaveAttribute("href", "/login?workspace=owner");
    expect((await screen.findAllByText("READY")).length).toBe(2);
    expect(screen.getByText("LAUNCHER")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("explains that fresh testing stays in the launcher", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(response({ status: "not_ready" }, 503))));
    render(<TestLabHome />);

    fireEvent.click(screen.getByRole("button", { name: "START FRESH TEST" }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("python launch.py --fresh"));
  });
});
