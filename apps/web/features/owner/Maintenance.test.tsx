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

function maintenanceApi() {
  return vi.fn(async (path: string) => {
    if (path.endsWith("/overview")) {
      return { overdue: 1, due: 2, due_soon: 3, unknown: 0, open_work_orders: 4, items: [] };
    }
    if (path.endsWith("/work-orders") || path.endsWith("/history") || path.endsWith("/templates")) return [];
    if (path.includes("/templates/matches/")) return [];
    if (path.includes("/plans/tracked-1")) {
      return { id: null, asset_id: trackedAsset.id, asset_code: trackedAsset.asset_code, manufacturer: trackedAsset.manufacturer, model: trackedAsset.model, model_year: trackedAsset.model_year, is_wheeled: false, supports_odometer_km: false, supports_hour_meter: true, source: null, source_template_id: null, source_template_version: null, items: [] };
    }
    if (path.includes("/plans/wheeled-1")) {
      return { id: null, asset_id: wheeledAsset.id, asset_code: wheeledAsset.asset_code, manufacturer: wheeledAsset.manufacturer, model: wheeledAsset.model, model_year: wheeledAsset.model_year, is_wheeled: true, supports_odometer_km: true, supports_hour_meter: true, source: null, source_template_id: null, source_template_version: null, items: [] };
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

    await screen.findByText("EXC-01 MAINTENANCE PLAN");
    expect(screen.getByText(/No model-specific maintenance template/)).toBeInTheDocument();
    expect(screen.getByLabelText("Copy maintenance plan from Asset")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add maintenance item / start blank" }));
    expect(screen.getByLabelText("Every days")).toBeInTheDocument();
    expect(screen.getByLabelText("Every hours")).toBeInTheDocument();
    expect(screen.queryByLabelText("Every KM")).not.toBeInTheDocument();
  });

  it("offers date, KM, and hours per maintenance item for wheeled dual-meter assets", async () => {
    const apiRequest = maintenanceApi();
    render(<Maintenance assets={[trackedAsset, wheeledAsset]} apiRequest={apiRequest as unknown as WebRequest} initialAssetId={wheeledAsset.id} />);

    await screen.findByText("TIP-01 MAINTENANCE PLAN");
    fireEvent.click(screen.getByRole("button", { name: "Add maintenance item / start blank" }));
    expect(screen.getByLabelText("Every days")).toBeInTheDocument();
    expect(screen.getByLabelText("Every KM")).toBeInTheDocument();
    expect(screen.getByLabelText("Every hours")).toBeInTheDocument();
  });
});
