import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { WebRequest } from "../../lib/api/client";
import type { OwnerAsset } from "../../lib/types";
import { Maintenance } from "./Maintenance";

const trackedAsset: OwnerAsset = {
  id: "tracked-1",
  asset_code: "EXC-01",
  asset_type: "EXCAVATOR",
  ownership_type: "OWNED",
  registration_number: null,
  short_name: "Tracked excavator",
  manufacturer: "CAT",
  model: "320",
  model_year: 2024,
  is_wheeled: false,
  supports_odometer_km: false,
  supports_hour_meter: true,
  chassis_number: null,
  engine_number: null,
  status: "ACTIVE",
  rental_party_name: null,
  rental_owner_phone_primary: null,
  rental_owner_phone_secondary: null,
  rental_start_date: null,
  rental_end_date: null,
  current_deployment: null,
  has_active_assignment: false,
  active_assignment: null,
};

const wheeledAsset: OwnerAsset = {
  ...trackedAsset,
  id: "wheeled-1",
  asset_code: "TIP-01",
  asset_type: "TIPPER",
  registration_number: "KA01AB1234",
  short_name: "Dual meter tipper",
  is_wheeled: true,
  supports_odometer_km: true,
};

const rentedAsset: OwnerAsset = {
  ...wheeledAsset,
  id: "rented-1",
  asset_code: "RENT-01",
  short_name: "Rented dual-meter tipper",
  ownership_type: "RENTED",
  maintenance_responsibility: "OWNER_COMPANY",
};

const wheeledItem = {
  id: "schedule-1",
  asset_id: wheeledAsset.id,
  task_code: "ENGINE_OIL",
  task_label: "Engine Oil",
  action_type: "REPLACE",
  description: null,
  enabled: true,
  state: "DUE_SOON",
  triggered_by: ["ODOMETER_KM"],
  criteria: [
    { id: "days", basis: "CALENDAR_DAYS", interval_value: "90", warning_value: "7", baseline_value: null, baseline_date: "2026-08-01", state: "NOT_DUE", current_value: null, due_value: null, current_date: "2026-10-09", due_date: "2026-10-30" },
    { id: "km", basis: "ODOMETER_KM", interval_value: "5000", warning_value: "500", baseline_value: "10000", baseline_date: null, state: "DUE_SOON", current_value: "14500", due_value: "15000", current_date: null, due_date: null },
    { id: "hours", basis: "HOUR_METER_HOURS", interval_value: "250", warning_value: "25", baseline_value: "1000", baseline_date: null, state: "NOT_DUE", current_value: "1100", due_value: "1250", current_date: null, due_date: null },
  ],
};

function maintenanceApi() {
  return vi.fn(async (path: string, _options?: RequestInit) => {
    void _options;
    if (path.endsWith("/overview")) {
      return { overdue: 1, due: 2, due_soon: 3, unknown: 0, open_work_orders: 4, items: [] };
    }
    if (path.endsWith("/work-orders") || path.endsWith("/history") || path.endsWith("/templates")) return [];
    if (path.includes("/templates/matches/")) return [];
    if (path.includes("/plans/tracked-1")) {
      return { id: null, asset_id: trackedAsset.id, asset_code: trackedAsset.asset_code, manufacturer: trackedAsset.manufacturer, model: trackedAsset.model, model_year: trackedAsset.model_year, is_wheeled: false, supports_odometer_km: false, supports_hour_meter: true, maintenance_responsibility: "OWNER_COMPANY", managed_by_current_company: true, management_message: null, source: null, source_template_id: null, source_template_version: null, items: [] };
    }
    if (path.includes("/plans/wheeled-1")) {
      return { id: "plan-1", asset_id: wheeledAsset.id, asset_code: wheeledAsset.asset_code, manufacturer: wheeledAsset.manufacturer, model: wheeledAsset.model, model_year: wheeledAsset.model_year, is_wheeled: true, supports_odometer_km: true, supports_hour_meter: true, maintenance_responsibility: "OWNER_COMPANY", managed_by_current_company: true, management_message: null, source: "CUSTOM", source_template_id: null, source_template_version: null, items: [wheeledItem] };
    }
    if (path.includes("/plans/rented-1")) {
      return { id: null, asset_id: rentedAsset.id, asset_code: rentedAsset.asset_code, manufacturer: rentedAsset.manufacturer, model: rentedAsset.model, model_year: rentedAsset.model_year, is_wheeled: true, supports_odometer_km: true, supports_hour_meter: true, maintenance_responsibility: "OWNER_COMPANY", managed_by_current_company: false, management_message: "Managed by rental owner", source: null, source_template_id: null, source_template_version: null, items: [] };
    }
    return {};
  });
}

afterEach(cleanup);

describe("Owner maintenance", () => {
  it("shows all module tabs and dashboard alert counts", async () => {
    const apiRequest = maintenanceApi();
    render(<Maintenance assets={[trackedAsset, wheeledAsset]} apiRequest={apiRequest as unknown as WebRequest} />);

    await waitFor(() => expect(screen.getByText("Overdue").nextSibling).toHaveTextContent("1"));
    for (const tab of ["Overview", "Due", "Asset Plans", "Work Orders", "History", "Templates"]) {
      expect(screen.getByRole("tab", { name: tab })).toBeInTheDocument();
    }
    expect(screen.getByText("Open work orders").nextSibling).toHaveTextContent("4");
  });

  it("hides KM maintenance inputs for tracked assets and offers plan-copy choices", async () => {
    const apiRequest = maintenanceApi();
    render(<Maintenance assets={[trackedAsset, wheeledAsset]} apiRequest={apiRequest as unknown as WebRequest} initialAssetId={trackedAsset.id} />);

    await screen.findByText("MAINTENANCE SETUP");
    expect(screen.getByText(/No model-specific maintenance template/)).toBeInTheDocument();
    expect(screen.getByLabelText("Copy maintenance plan from Asset")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "+ Add custom item" }));
    expect(screen.getByLabelText("Every days")).toBeInTheDocument();
    expect(screen.getByLabelText("Every hours")).toBeInTheDocument();
    expect(screen.queryByLabelText("Every KM")).not.toBeInTheDocument();
  });

  it("offers date, KM, and hours per maintenance item for wheeled dual-meter assets", async () => {
    const apiRequest = maintenanceApi();
    render(<Maintenance assets={[trackedAsset, wheeledAsset]} apiRequest={apiRequest as unknown as WebRequest} initialAssetId={wheeledAsset.id} />);

    await screen.findByText("MAINTENANCE SETUP");
    fireEvent.click(screen.getByRole("button", { name: "+ Add custom item" }));
    expect(screen.getByLabelText("Every days")).toBeInTheDocument();
    expect(screen.getByLabelText("Every KM")).toBeInTheDocument();
    expect(screen.getByLabelText("Every hours")).toBeInTheDocument();
  });

  it("keeps routine intervals inline and saves all dual-meter criteria", async () => {
    const apiRequest = maintenanceApi();
    render(<Maintenance assets={[trackedAsset, wheeledAsset]} apiRequest={apiRequest as unknown as WebRequest} initialAssetId={wheeledAsset.id} />);

    await screen.findByLabelText("Days — Engine Oil");
    expect(screen.getByLabelText("KM — Engine Oil")).toHaveValue(5000);
    expect(screen.getByLabelText("Hours — Engine Oil")).toHaveValue(250);
    fireEvent.change(screen.getByLabelText("KM — Engine Oil"), { target: { value: "6000" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/owner/maintenance/plans/wheeled-1/items/schedule-1",
      expect.objectContaining({ method: "PUT" }),
    ));
    const update = apiRequest.mock.calls.find(([path, options]) => path.includes("schedule-1") && options?.method === "PUT");
    expect(JSON.parse(String(update?.[1]?.body)).criteria).toEqual(expect.arrayContaining([
      expect.objectContaining({ basis: "CALENDAR_DAYS", interval_value: "90" }),
      expect.objectContaining({ basis: "ODOMETER_KM", interval_value: "6000" }),
      expect.objectContaining({ basis: "HOUR_METER_HOURS", interval_value: "250" }),
    ]));
  });

  it("shows rented assets as operational but externally maintained", async () => {
    const apiRequest = maintenanceApi();
    render(<Maintenance assets={[rentedAsset]} apiRequest={apiRequest as unknown as WebRequest} initialAssetId={rentedAsset.id} />);

    await screen.findByText("Managed by rental owner");
    expect(screen.getByText(/Operational KM\/HMR continues to be recorded/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "+ Add custom item" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Copy maintenance plan from Asset")).not.toBeInTheDocument();
  });
});
