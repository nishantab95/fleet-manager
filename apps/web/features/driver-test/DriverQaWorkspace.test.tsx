import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DriverDutyState } from "../../lib/types";

const { requestMock, authMock, dutyState } = vi.hoisted(() => {
  const dutyState: { current: DriverDutyState } = {
    current: {
      status: "NONE",
      session_id: null,
      assignment_id: null,
      tipper_id: null,
      site_id: null,
      started_at: null,
      start_km: null,
      ended_at: null,
      end_km: null,
      regular_duty_minutes: null,
    },
  };
  const requestMock = vi.fn(async (path: string, options?: RequestInit) => {
    if (path === "/api/v1/driver/assignment/current") return { assignment_id: "assignment-1", tipper_id: "tipper-1", tipper_registration_number: "PILOT-12", tipper_short_name: "Tipper 12", site_id: "site-1", site_name: "Pilot Site", supervisor_name: "Pilot Supervisor", regular_duty_minutes: 600 };
    if (path === "/api/v1/driver/duty/current") return dutyState.current;
    if (path === "/api/v1/driver/device") return { device_id: "device-1", installation_identifier: "qa-web-test", platform: "WEB" };
    if (path.startsWith("/api/v1/driver/events")) {
      const body = JSON.parse(String(options?.body)) as { client_event_uuid: string; event_type: string };
      return { client_event_uuid: body.client_event_uuid, status: "accepted", verification_status: "PENDING_VERIFICATION" };
    }
    return {};
  });
  const authMock = { session: { access_token: "access-token" }, request: requestMock, refresh: vi.fn(), logout: vi.fn() };
  return { requestMock, authMock, dutyState };
});

vi.mock("../auth/AuthProvider", () => ({ useAuth: () => authMock }));

import { DriverQaWorkspace } from "./DriverQaWorkspace";

afterEach(() => {
  cleanup();
  dutyState.current = {
    status: "NONE",
    session_id: null,
    assignment_id: null,
    tipper_id: null,
    site_id: null,
    started_at: null,
    start_km: null,
    ended_at: null,
    end_km: null,
    regular_duty_minutes: null,
  };
  vi.clearAllMocks();
});

describe("Driver QA workspace", () => {
  it("loads real assignment state and exposes only START DUTY plus emergency before duty", async () => {
    render(<DriverQaWorkspace />);
    expect(await screen.findByText(/Pilot Site/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "START DUTY" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "EMERGENCY" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "TRIP COMPLETE" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /DIESEL ISSUED/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/overtime/i)).toBeInTheDocument();
    await waitFor(() => expect(requestMock).toHaveBeenCalledWith("/api/v1/driver/device", expect.objectContaining({ method: "POST", body: expect.stringContaining('"platform":"WEB"') })));
  });

  it("resumes an active duty session and creates separate UUIDs for separate trips", async () => {
    dutyState.current = { ...dutyState.current, status: "ACTIVE", session_id: "session-1", assignment_id: "assignment-1", started_at: "2026-09-24T08:00:00Z", start_km: 100, regular_duty_minutes: 600 };
    render(<DriverQaWorkspace />);
    await screen.findByText(/Pilot Site/);
    const tripButton = screen.getByRole("button", { name: "TRIP COMPLETE" });
    fireEvent.click(tripButton);
    await waitFor(() => expect(screen.getAllByText("TRIP_COMPLETE")).toHaveLength(1));
    fireEvent.click(tripButton);
    await waitFor(() => expect(screen.getAllByText("TRIP_COMPLETE")).toHaveLength(2));
    const eventCalls = requestMock.mock.calls.filter(([path]) => path === "/api/v1/driver/events");
    const uuids = eventCalls.map(([, options]) => (JSON.parse(String(options?.body)) as { client_event_uuid: string }).client_event_uuid);
    expect(new Set(uuids).size).toBe(2);
    expect(screen.getAllByText(/API: accepted/)).toHaveLength(2);
  });

  it("requires KM evidence, makes diesel evidence optional, and keeps one-tap emergencies", async () => {
    render(<DriverQaWorkspace />);
    await screen.findByText(/Pilot Site/);
    fireEvent.click(screen.getByRole("button", { name: "START DUTY" }));
    expect(screen.getByRole("heading", { name: "START KM" })).toBeInTheDocument();
    expect(screen.getByLabelText("Required dashboard/odometer image")).toBeRequired();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "EMERGENCY" }));
    await waitFor(() => expect(requestMock.mock.calls.some(([path, options]) => path === "/api/v1/driver/events" && String(options?.body).includes('"event_type":"EMERGENCY"'))).toBe(true));

    cleanup();
    dutyState.current = { ...dutyState.current, status: "ACTIVE", session_id: "session-1", assignment_id: "assignment-1", regular_duty_minutes: 600 };
    render(<DriverQaWorkspace />);
    await screen.findByText(/Pilot Site/);
    fireEvent.click(screen.getByRole("button", { name: /DIESEL ISSUED/ }));
    expect(screen.getByLabelText("Optional fuel image")).not.toBeRequired();
    fireEvent.change(screen.getByLabelText("Litres"), { target: { value: "0" } });
    expect(screen.getByLabelText("Litres")).toBeInvalid();
    fireEvent.change(screen.getByLabelText("Litres"), { target: { value: "30" } });
    expect(screen.getByLabelText("Optional fuel image")).not.toBeRequired();
  });
});
