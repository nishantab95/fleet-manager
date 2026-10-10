import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import HomePage from "../../app/(marketing)/page";
import { ContactForm } from "./ContactForm";
import { MarketingFooter, MarketingHeader } from "./MarketingChrome";

afterEach(cleanup);

describe("Fleet AI Systems public site", () => {
  it("renders the public brand, navigation, product roles, and truthful capability copy", () => {
    render(<><MarketingHeader /><HomePage /><MarketingFooter /></>);
    expect(screen.getAllByLabelText("Fleet AI Systems").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { level: 1, name: /Run the field/ })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Book a demo/ }).length).toBeGreaterThan(0);
    expect(screen.getByText("Owner workspace")).toBeInTheDocument();
    expect(screen.getByText("Driver workflow")).toBeInTheDocument();
    expect(screen.getByText("Supervisor review", { selector: ".marketing-showcase__label" })).toBeInTheDocument();
    expect(screen.queryByText(/does not claim continuous GPS tracking/i)).not.toBeInTheDocument();
  });

  it("prepares a transparent email handoff instead of claiming to persist the lead", async () => {
    const user = userEvent.setup();
    render(<ContactForm />);
    await user.type(screen.getByLabelText("Full name"), "Anita Rao");
    await user.type(screen.getByLabelText("Company"), "Rao Earthworks");
    await user.type(screen.getByLabelText("Phone"), "+91 98765 43210");
    await user.type(screen.getByLabelText("Email"), "anita@example.com");
    fireEvent.change(screen.getByLabelText("Fleet size"), { target: { value: "11–30 assets" } });
    await user.type(screen.getByLabelText("What would you like to improve?"), "Daily site coordination");
    await user.click(screen.getByRole("button", { name: /Prepare demo request/ }));
    expect(screen.getByRole("status")).toHaveTextContent("Your request is ready");
    const link = screen.getByRole("link", { name: /Open email draft/ });
    expect(link).toHaveAttribute("href", expect.stringContaining("mailto:hello@fleetaisystems.com"));
    expect(link).toHaveAttribute("href", expect.stringContaining("Rao%20Earthworks"));
    expect(screen.getByText(/No third-party form processor is connected/)).toBeInTheDocument();
  });
});
