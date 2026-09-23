import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { requestMock, authMock } = vi.hoisted(() => {
  const requestMock = vi.fn(async (path: string, options?: RequestInit) => {
    if (path === "/api/v1/driver/assignment/current") return { assignment_id: "assignment-1", tipper_id: "tipper-1", tipper_registration_number: "PILOT-12", tipper_short_name: "Tipper 12", site_id: "site-1", site_name: "Pilot Site", supervisor_name: "Pilot Supervisor" };
    if (path === "/api/v1/driver/device") return { device_id: "device-1", installation_identifier: "qa-web-test", platform: "WEB" };
    if (path.startsWith("/api/v1/driver/events")) {
      const body = JSON.parse(String(options?.body)) as { client_event_uuid: string; event_type: string };
      return { client_event_uuid: body.client_event_uuid, status: "accepted", verification_status: "PENDING_VERIFICATION" };
    }
    return {};
  });
  const authMock = { session: { access_token: "access-token" }, request: requestMock, refresh: vi.fn(), logout: vi.fn() };
  return { requestMock, authMock };
});

vi.mock("../auth/AuthProvider", () => ({ useAuth: () => authMock }));

import { DriverQaWorkspace } from "./DriverQaWorkspace";

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("Driver QA workspace", () => {
  it("loads the real assignment, registers WEB, and exposes exactly four primary actions without totals", async () => {
    render(<DriverQaWorkspace />);
    expect(await screen.findByText(/Pilot Site/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "TRIP COMPLETE" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "KM READING" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /DIESEL ISSUED/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "EMERGENCY" })).toBeInTheDocument();
    expect(screen.queryByText(/total km|fuel consumed|km\/l/i)).not.toBeInTheDocument();
    await waitFor(() => expect(requestMock).toHaveBeenCalledWith("/api/v1/driver/device", expect.objectContaining({ method: "POST", body: expect.stringContaining('"platform":"WEB"') })));
  });

  it("creates separate UUIDs for separate trips and reports server acknowledgement", async () => {
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

  it("requires KM evidence and validates diesel and emergency contracts", async () => {
    render(<DriverQaWorkspace />);
    await screen.findByText(/Pilot Site/);
    fireEvent.click(screen.getByRole("button", { name: "KM READING" }));
    fireEvent.change(screen.getByLabelText("KM value"), { target: { value: "-1" } });
    expect(screen.getByLabelText("KM value")).toBeInvalid();
    fireEvent.change(screen.getByLabelText("KM value"), { target: { value: "100" } });
    expect(screen.getByLabelText("Local test image")).toBeRequired();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: /DIESEL ISSUED/ }));
    fireEvent.change(screen.getByLabelText("Litres"), { target: { value: "0" } });
    expect(screen.getByLabelText("Litres")).toBeInvalid();
    fireEvent.change(screen.getByLabelText("Litres"), { target: { value: "30" } });
    expect(screen.getByLabelText("Local test image")).toBeRequired();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "EMERGENCY" }));
    fireEvent.change(screen.getByLabelText("Category"), { target: { value: "CONTACT_SUPERVISOR" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit emergency" }));
    await waitFor(() => expect(requestMock.mock.calls.some(([path, options]) => path === "/api/v1/driver/events" && String(options?.body).includes('"category":"CONTACT_SUPERVISOR"'))).toBe(true));
  });
});
