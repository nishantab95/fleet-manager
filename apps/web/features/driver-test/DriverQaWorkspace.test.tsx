import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DriverDutyState } from "../../lib/types";

const makeDutyState = (status: DriverDutyState["status"]): DriverDutyState => ({
  status,
  session_id: status === "NONE" ? null : "session-1",
  assignment_id: status === "NONE" ? null : "assignment-1",
  tipper_id: status === "NONE" ? null : "tipper-1",
  site_id: status === "NONE" ? null : "site-1",
  started_at: status === "NONE" ? null : "2026-09-24T08:00:00Z",
  start_km: status === "NONE" ? null : 100,
  ended_at: status === "CLOSED" ? "2026-09-24T18:00:00Z" : null,
  end_km: status === "CLOSED" ? 120 : null,
  regular_duty_minutes: status === "NONE" ? null : 600,
});

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

const renderWorkspace = async () => {
  render(<DriverQaWorkspace />);
  await screen.findByText(/Pilot Site/);
  expect(screen.getByText("Supervisor: Pilot Supervisor")).toBeInTheDocument();
};

const expectFourButtons = () => {
  expect(screen.getAllByRole("button", { name: "TRIP COMPLETE" })).toHaveLength(1);
  expect(screen.getAllByRole("button", { name: "KM READING" })).toHaveLength(1);
  expect(screen.getAllByRole("button", { name: "DIESEL" })).toHaveLength(1);
  expect(screen.getAllByRole("button", { name: "EMERGENCY" })).toHaveLength(1);
};

afterEach(() => {
  cleanup();
  dutyState.current = makeDutyState("NONE");
  vi.clearAllMocks();
});

describe("Driver QA workspace", () => {
  it("keeps four buttons visible before duty with only KM and emergency enabled", async () => {
    await renderWorkspace();
    expectFourButtons();
    expect(screen.getByRole("button", { name: "TRIP COMPLETE" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "KM READING" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "DIESEL" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "EMERGENCY" })).toBeEnabled();
    expect(screen.getByRole("status")).toHaveTextContent("Record START KM first.");
    fireEvent.click(screen.getByRole("button", { name: "KM READING" }));
    expect(screen.getByRole("heading", { name: "START KM" })).toBeInTheDocument();
    expect(screen.getByLabelText("Required dashboard/odometer image")).toBeRequired();
  });

  it("keeps four buttons visible during active duty and maps KM to END KM", async () => {
    dutyState.current = makeDutyState("ACTIVE");
    await renderWorkspace();
    expectFourButtons();
    expect(screen.getByRole("button", { name: "TRIP COMPLETE" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "KM READING" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "DIESEL" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "EMERGENCY" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "KM READING" }));
    expect(screen.getByRole("heading", { name: "END KM" })).toBeInTheDocument();
    expect(screen.getByLabelText("Required dashboard/odometer image")).toBeRequired();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "DIESEL" }));
    expect(screen.getByLabelText("Optional fuel image")).not.toBeRequired();
  });

  it("keeps four buttons visible after duty closes with only emergency enabled", async () => {
    dutyState.current = makeDutyState("CLOSED");
    await renderWorkspace();
    expectFourButtons();
    expect(screen.getByRole("button", { name: "TRIP COMPLETE" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "KM READING" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "DIESEL" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "EMERGENCY" })).toBeEnabled();
    expect(screen.getByRole("status")).toHaveTextContent("Duty completed");
  });

  it("keeps emergency one-tap available regardless of duty state and preserves server state after remount", async () => {
    dutyState.current = makeDutyState("ACTIVE");
    await renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "EMERGENCY" }));
    await waitFor(() => expect(requestMock.mock.calls.some(([path, options]) => path === "/api/v1/driver/events" && String(options?.body).includes('"event_type":"EMERGENCY"'))).toBe(true));

    cleanup();
    await renderWorkspace();
    expect(screen.getByRole("button", { name: "TRIP COMPLETE" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "KM READING" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "DIESEL" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "EMERGENCY" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "START DUTY" })).not.toBeInTheDocument();
  });
});
