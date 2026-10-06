import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { WebRequest } from "../../lib/api/client";
import type { MaintenanceSchedule, OwnerAsset } from "../../lib/types";
import { MaintenanceModule, NotificationBell } from "./FutureModules";

const asset: OwnerAsset = {
  id: "asset-1",
  asset_code: "TIPPER-1",
  asset_type: "TIPPER",
  ownership_type: "OWNED",
  registration_number: "KA01AB1234",
  short_name: "BENZ-01",
  manufacturer: null,
  model: null,
  status: "ACTIVE",
  rental_party_name: null,
  rental_start_date: null,
  rental_end_date: null,
  current_deployment: null,
  has_active_assignment: false,
  active_assignment: null,
  supports_odometer_km: true,
  supports_hour_meter: false,
};

const schedule: MaintenanceSchedule = {
  id: "schedule-1",
  asset_id: asset.id,
  maintenance_type: "ENGINE_OIL",
  custom_label: null,
  description: null,
  interval_basis: "KM",
  interval_value: "10000.00",
  warning_threshold: "1000.00",
  last_service_meter: "50000.00",
  last_service_date: null,
  next_due_meter: "60000.00",
  next_due_date: null,
  current_meter: null,
  due_status: "UNKNOWN",
  status: "ACTIVE",
  notes: null,
  criteria: [],
};

afterEach(cleanup);

describe("future Owner modules", () => {
  it("keeps unknown maintenance meters visible and creates a schedule from the spreadsheet UI", async () => {
    const apiRequest = vi.fn((path: string, _options?: RequestInit) => {
      void _options;
      if (path.endsWith("/schedules")) return Promise.resolve([schedule]);
      if (path.endsWith("/work-orders") || path.endsWith("/history")) return Promise.resolve([]);
      return Promise.resolve({});
    });
    render(<MaintenanceModule accessToken="token" apiRequest={apiRequest as unknown as WebRequest} assets={[asset]} sites={[]} />);

    fireEvent.click(await screen.findByRole("tab", { name: "Schedules" }));
    const table = await screen.findByRole("table", { name: "Maintenance schedules" });
    expect(within(table).getAllByText("UNKNOWN").length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("Asset"), { target: { value: asset.id } });
    fireEvent.change(screen.getByLabelText("Interval"), { target: { value: "5000" } });
    fireEvent.change(screen.getByLabelText("Warning threshold"), { target: { value: "500" } });
    fireEvent.click(screen.getByRole("button", { name: "Create schedule" }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/owner/maintenance/schedules",
      expect.objectContaining({ method: "POST" }),
    ));
    const call = apiRequest.mock.calls.find((entry) => entry[1]?.method === "POST");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual(expect.objectContaining({
      asset_id: asset.id,
      interval_value: "5000",
      warning_threshold: "500",
      last_service_meter: null,
    }));
  });

  it("shows an unread count, marks a notification read, and deep-links to maintenance", async () => {
    const navigate = vi.fn();
    const apiRequest = vi.fn((path: string, options?: RequestInit) => {
      if (options?.method === "PATCH") return Promise.resolve({});
      return Promise.resolve([{
        id: "notification-1",
        category: "MAINTENANCE_DUE",
        title: "Maintenance overdue",
        body: "Engine oil is overdue.",
        state: "UNREAD",
        deep_link: { tab: "maintenance" },
        created_at: "2026-10-06T00:00:00Z",
      }]);
    });
    render(<NotificationBell apiRequest={apiRequest as unknown as WebRequest} onNavigate={navigate} />);

    const bell = await screen.findByRole("button", { name: "Notifications, 1 unread" });
    fireEvent.click(bell);
    fireEvent.click(screen.getByRole("button", { name: /Maintenance overdue/ }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/owner/notifications/notification-1",
      expect.objectContaining({ method: "PATCH" }),
    ));
    expect(navigate).toHaveBeenCalledWith("maintenance");
  });
});
