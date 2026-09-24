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
    driver_phone: "+919876543210",
    tipper_registration_number: "PILOT12",
    site_id: "site-1",
    site_name: "Pilot Site",
    device_created_at: "2026-09-24T00:00:00Z",
    server_received_at: "2026-09-24T00:00:01Z",
    verification_status: "PENDING_VERIFICATION" as const,
    reading_type: eventType === "KM_READING" ? (index === 5 ? "START_READING" : "END_READING") : null,
    reading_value: eventType === "KM_READING" ? (index === 5 ? "10000.00" : "10120.00") : null,
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

    await waitFor(() => expect(screen.getByRole("heading", { name: "Operations by tipper" })).toBeInTheDocument());
    expect(screen.getByText("Pending Trips").parentElement).toHaveTextContent("4");
    expect(screen.getByText("Pending KM").parentElement).toHaveTextContent("2");
    expect(screen.getByText("Pending Diesel").parentElement).toHaveTextContent("1");
    expect(screen.getByText("Open Emergencies").parentElement).toHaveTextContent("1");
    expect(screen.getAllByRole("article")).toHaveLength(7);
    expect(screen.getByRole("alert")).toHaveTextContent("Pilot Driver");
  });

  it("opens private evidence in a modal with event context", async () => {
    const evidenceEvents = events.map((item, index) => index === 4 ? { ...item, evidence_available: true } : item);
    const apiRequest = vi.fn(async (path: string) => path.includes("/events") ? evidenceEvents : completeness) as unknown as WebRequest;
    const responseBytes = new Uint8Array([0xff, 0xd8, 0xff, 0x00, 0x01, 0xff, 0xd9]);
    const fetchMock = vi.fn(async () => new Response(responseBytes, {
      status: 200,
      headers: {
        "Content-Type": "image/jpeg",
        "X-Fleet-Evidence-Event-Type": "KM_READING",
        "X-Fleet-Evidence-Driver": "Pilot Driver",
        "X-Fleet-Evidence-Tipper": "PILOT12",
        "X-Fleet-Evidence-Timestamp": "2026-09-24T00:00:00Z",
      },
    }));
    vi.stubGlobal("fetch", fetchMock);
    const createObjectUrlMock = vi.fn(() => "blob:evidence");
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectUrlMock });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });

    render(<SupervisorShell accessToken="token" error="" sites={[site]} setError={vi.fn()} onLogout={vi.fn()} apiRequest={apiRequest} />);

    await waitFor(() => expect(screen.getByRole("button", { name: "View Photo" })).toBeInTheDocument());
    screen.getByRole("button", { name: "View Photo" }).click();
    await waitFor(() => expect(screen.getByRole("dialog", { name: "Operational evidence" })).toBeInTheDocument());
    const dialog = screen.getByRole("dialog", { name: "Operational evidence" });
    expect(dialog).toHaveTextContent("Pilot Driver");
    expect(dialog).toHaveTextContent("PILOT12");
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/v1/supervisor/events/event-5/evidence"), expect.any(Object));
    const [blob] = createObjectUrlMock.mock.calls[0] as Blob[];
    expect(blob.type).toBe("image/jpeg");
    expect(blob.size).toBe(responseBytes.byteLength);
    expect(Object.prototype.toString.call(blob)).toBe("[object Blob]");
  });

  it("keeps tipper groups separate and labels operational subsections explicitly", async () => {
    const secondTipperCompleteness = {
      ...completeness[0],
      assignment_id: "assignment-2",
      driver_name: "Second Driver",
      tipper_registration_number: "PILOT13",
    };
    const secondTipperTrip = { ...events[0], event_id: "event-9", assignment_id: "assignment-2", driver_name: "Second Driver", tipper_registration_number: "PILOT13" };
    const apiRequest = vi.fn(async (path: string) => path.includes("/events") ? [...events.filter((item) => item.event_type !== "EMERGENCY"), secondTipperTrip] : [...completeness, secondTipperCompleteness]) as unknown as WebRequest;
    render(<SupervisorShell accessToken="token" error="" sites={[site]} setError={vi.fn()} onLogout={vi.fn()} apiRequest={apiRequest} />);

    await waitFor(() => expect(screen.getAllByText("PILOT13").length).toBeGreaterThan(1));
    expect(screen.getByText("START KM")).toBeInTheDocument();
    expect(screen.getByText("END KM")).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: "DIESEL" })).toHaveLength(2);
    const secondTipperGroup = screen.getAllByText("PILOT13").at(-1)?.closest("details");
    expect(secondTipperGroup).not.toBeNull();
    expect(secondTipperGroup).toHaveTextContent("Trip 1");
    expect(secondTipperGroup).not.toHaveTextContent("PILOT12");
  });
});
