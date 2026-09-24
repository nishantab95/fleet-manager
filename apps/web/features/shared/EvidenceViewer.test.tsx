import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EvidenceModal } from "./EvidenceViewer";

describe("EvidenceModal", () => {
  it("renders a readable private evidence view and full-size link", () => {
    render(<EvidenceModal details={{ eventId: "event-1", eventType: "DIESEL", driverName: "Driver A", tipperRegistrationNumber: "KA01AB1234", deviceCreatedAt: "2026-09-24T00:00:00Z" }} onClose={vi.fn()} url="blob:evidence" />);

    expect(screen.getByRole("dialog", { name: "Operational evidence" })).toBeInTheDocument();
    expect(screen.getByText("DIESEL")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open full size" })).toHaveAttribute("href", "blob:evidence");
  });
});
