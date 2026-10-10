import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import HomePage from "../app/page";
import { ContactForm } from "./ContactForm";
import { MarketingFooter, MarketingHeader } from "./MarketingChrome";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Fleet AI Systems public site", () => {
  it("renders the public brand, navigation, product roles, and truthful capability copy", () => {
    render(<><MarketingHeader /><HomePage /><MarketingFooter /></>);
    expect(screen.getAllByLabelText("Fleet AI Systems").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { level: 1, name: /Run the field/ })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Book a demo/ }).length).toBeGreaterThan(0);
    expect(screen.getByText("Owner workspace")).toBeInTheDocument();
    expect(screen.getByText("DRIVER / OPERATOR")).toBeInTheDocument();
    expect(screen.getByText("SUPERVISOR")).toBeInTheDocument();
    expect(screen.getByText("MAINTENANCE")).toBeInTheDocument();
    expect(screen.getByText("REPORTING & EXPORTS")).toBeInTheDocument();
    expect(screen.queryByText(/does not claim continuous GPS tracking/i)).not.toBeInTheDocument();
  });

  it("submits a validated lead only to the marketing endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "received", reference: "lead-reference" }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<ContactForm />);
    await user.type(screen.getByLabelText("Full name"), "Anita Rao");
    await user.type(screen.getByLabelText("Company"), "Rao Earthworks");
    await user.type(screen.getByLabelText("Phone"), "+91 98765 43210");
    await user.type(screen.getByLabelText("Email"), "anita@example.com");
    fireEvent.change(screen.getByLabelText("Fleet size"), { target: { value: "11-30" } });
    fireEvent.change(screen.getByLabelText("Primary fleet type"), { target: { value: "mixed" } });
    await user.type(screen.getByLabelText("What would you like to improve?"), "Daily site and maintenance coordination");
    await user.click(screen.getByRole("button", { name: /Request a demo/ }));
    expect(await screen.findByRole("status")).toHaveTextContent("Request received");
    expect(fetchMock).toHaveBeenCalledWith(
      "/public/leads",
      expect.objectContaining({ method: "POST" }),
    );
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toMatchObject({
      company: "Rao Earthworks",
      fleetSize: "11-30",
      fleetType: "mixed",
    });
  });
});
