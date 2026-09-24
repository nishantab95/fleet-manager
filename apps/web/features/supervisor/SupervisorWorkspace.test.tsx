import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { WebRequest } from "../../lib/api/client";
import { SupervisorShell } from "./SupervisorWorkspace";

const site = { id: "site-1", name: "Pilot Site", code: "PILOT", status: "ACTIVE" as const };
const completeness = [{
  assignment_id: "assignment-1",
  driver_name: "Pilot Driver",
  tipper_registration_number: "PILOT12",
  site_id: "site-1",
  site_name: "Pilot Site",
  has_start_reading: true,
  has_end_reading: true,
  start_reading_value: "10000.00",
  end_reading_value: "10120.00",
  odometer_regression: false,
  pending_trip_verification: true,
  pending_diesel_verification: true,
  unresolved_emergency: true,
}];

function event(eventType: "TRIP_COMPLETE" | "KM_READING" | "DIESEL" | "EMERGENCY", index: number) {
  return {
    event_id: `event-${index}`,
    event_type: eventType,
    assignment_id: "assignment-1",
    driver_name: "Pilot Driver",
    tipper_registration_number: "PILOT12",
    site_id: "site-1",
    site_name: "Pilot Site",
    device_created_at: "2026-09-24T00:00:00Z",
    server_received_at: "2026-09-24T00:00:01Z",
    verification_status: "PENDING_VERIFICATION" as const,
    reading_type: eventType === "KM_READING" ? (index === 4 ? "START_READING" : "END_READING") : null,
    reading_value: eventType === "KM_READING" ? (index === 4 ? "10000.00" : "10120.00") : null,
    litres: eventType === "DIESEL" ? "30.000" : null,
    emergency_category: eventType === "EMERGENCY" ? "TYRE_OR_VEHICLE_PROBLEM" : null,
    emergency_status: eventType === "EMERGENCY" ? "OPEN" : null,
    emergency_description: eventType === "EMERGENCY" ? "Automated PC acceptance test" : null,
    evidence_id: null,
    evidence_available: false,
    verification_history: [],
  };
}

const events = [event("TRIP_COMPLETE", 1), event("TRIP_COMPLETE", 2), event("TRIP_COMPLETE", 3), event("TRIP_COMPLETE", 4), event("KM_READING", 5), event("KM_READING", 6), event("DIESEL", 7), event("EMERGENCY", 8)];

afterEach(cleanup);

describe("Supervisor workspace", () => {
  it("counts pending review events by category", async () => {
    const apiRequest = vi.fn(async (path: string) => path.includes("/events") ? events : completeness) as unknown as WebRequest;
    render(<SupervisorShell accessToken="token" error="" sites={[site]} setError={vi.fn()} onLogout={vi.fn()} apiRequest={apiRequest} />);

    await waitFor(() => expect(screen.getByRole("heading", { name: "Event review" })).toBeInTheDocument());
    expect(screen.getByText("Pending Trips").parentElement).toHaveTextContent("4");
    expect(screen.getByText("Pending KM").parentElement).toHaveTextContent("2");
    expect(screen.getByText("Pending Diesel").parentElement).toHaveTextContent("1");
    expect(screen.getByText("Emergencies").parentElement).toHaveTextContent("1");
    expect(screen.getAllByRole("article")).toHaveLength(8);
  });
});
