import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

const sourceAsset: OwnerAsset = {
  ...wheeledAsset,
  id: "source-1",
  asset_code: "TIP-02",
  short_name: "Source tipper",
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

const dueSoonItem = { ...wheeledItem, id: "soon", asset_code: "TIP-01", site_name: "Quarry", state: "DUE_SOON" };
const overdueItem = {
  ...wheeledItem,
  id: "late",
  asset_code: "TIP-01",
  site_name: "Quarry",
  task_label: "Brake Inspection",
  state: "OVERDUE",
  triggered_by: ["CALENDAR_DAYS"],
  criteria: [{ ...wheeledItem.criteria[0], id: "late-date", state: "OVERDUE", due_date: "2026-09-01" }],
};

const oemMatch = {
  id: "oem-1",
  name: "CAT 320 service plan",
  template_type: "OEM_VERIFIED",
  confidence: "VERIFIED",
};

function planFor(asset: OwnerAsset, items: typeof wheeledItem[] = [], id: string | null = null) {
  return {
    id,
    asset_id: asset.id,
    asset_code: asset.asset_code,
    asset_type: asset.asset_type,
    manufacturer: asset.manufacturer,
    model: asset.model,
    model_year: asset.model_year,
    is_wheeled: asset.is_wheeled,
    supports_odometer_km: asset.supports_odometer_km,
    supports_hour_meter: asset.supports_hour_meter,
    maintenance_responsibility: "OWNER_COMPANY",
    managed_by_current_company: asset.ownership_type === "OWNED",
    management_message: asset.ownership_type === "OWNED" ? null : "Maintenance managed by rental owner.",
    source: id ? "CUSTOM" : null,
    source_template_id: null,
    source_template_version: null,
    items,
  };
}

function maintenanceApi(options: {
  overviewItems?: object[];
  matches?: object[];
  history?: object[];
  sourceHasPlan?: boolean;
} = {}) {
  return vi.fn(async (path: string, requestOptions?: RequestInit) => {
    if (path.endsWith("/overview")) {
      return {
        overdue: 1,
        due: 2,
        due_soon: 3,
        unknown: 0,
        open_work_orders: 4,
        items: options.overviewItems ?? [],
      };
    }
    if (path.endsWith("/history")) return options.history ?? [];
    if (path.includes("/templates/matches/")) return options.matches ?? [];
    if (path.includes("/templates/oem-1/items")) {
      return [{ ...wheeledItem, id: "template-item", template_id: "oem-1" }];
    }
    if (path.includes("/plans/tracked-1")) return planFor(trackedAsset);
    if (path.includes("/plans/wheeled-1")) return planFor(wheeledAsset, [wheeledItem], "plan-1");
    if (path.includes("/plans/source-1")) {
      return options.sourceHasPlan
        ? planFor(sourceAsset, [{ ...wheeledItem, asset_id: sourceAsset.id }], "source-plan")
        : planFor(sourceAsset);
    }
    if (path.includes("/plans/rented-1")) return planFor(rentedAsset);
    if (requestOptions?.method) return {};
    return {};
  });
}

afterEach(cleanup);

describe("Owner maintenance", () => {
  it("shows only the three Owner tabs and compact alert totals", async () => {
    const apiRequest = maintenanceApi();
    render(<Maintenance assets={[trackedAsset, wheeledAsset]} apiRequest={apiRequest as unknown as WebRequest} />);

    await waitFor(() => expect(screen.getByLabelText("Maintenance alert totals")).toHaveTextContent("1 Overdue"));
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
      "Overview", "Asset Plans", "History",
    ]);
    expect(screen.queryByRole("tab", { name: "Due" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Work Orders" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Templates" })).not.toBeInTheDocument();
    expect(screen.queryByText("Open work orders")).not.toBeInTheDocument();
  });

  it("sorts immediate maintenance by severity and explains the triggering criterion", async () => {
    const apiRequest = maintenanceApi({ overviewItems: [dueSoonItem, overdueItem] });
    render(<Maintenance assets={[wheeledAsset]} apiRequest={apiRequest as unknown as WebRequest} />);

    await screen.findByText("Brake Inspection");
    const rows = screen.getAllByRole("row");
    expect(within(rows[1]).getByText("Brake Inspection")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Date")).toBeInTheDocument();
    expect(within(rows[1]).getByText("2026-10-09 / 2026-09-01")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Engine Oil")).toBeInTheDocument();
    fireEvent.click(within(rows[2]).getByText("Engine Oil"));
    expect(within(rows[2]).getByText(/Hours: 1100 \/ 1250 h/)).toBeInTheDocument();
  });

  it("hides KM configuration for a tracked Asset and never exposes task codes", async () => {
    const apiRequest = maintenanceApi();
    render(<Maintenance assets={[trackedAsset, wheeledAsset]} apiRequest={apiRequest as unknown as WebRequest} initialAssetId={trackedAsset.id} />);

    await screen.findByText("Asset plan");
    fireEvent.click(screen.getByRole("button", { name: "+ Custom Item" }));
    expect(screen.getByLabelText("Maintenance Item")).toBeInTheDocument();
    expect(screen.getByLabelText("Every days")).toBeInTheDocument();
    expect(screen.getByLabelText("Every hours")).toBeInTheDocument();
    expect(screen.queryByLabelText("Every KM")).not.toBeInTheDocument();
    expect(screen.queryByText("Task code")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Maintenance Item"), { target: { value: "Inspect boom pins" } });
    fireEvent.click(screen.getByRole("button", { name: "Add Item" }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/owner/maintenance/plans/tracked-1/items",
      expect.objectContaining({ method: "POST" }),
    ));
    const create = apiRequest.mock.calls.find(([path, request]) => path.endsWith("/tracked-1/items") && request?.method === "POST");
    expect(JSON.parse(String(create?.[1]?.body))).toEqual(expect.objectContaining({
      task_code: "CUSTOM",
      custom_label: "Inspect boom pins",
      criteria: [],
    }));
  });

  it("shows an exact OEM recommendation with preview and apply", async () => {
    const apiRequest = maintenanceApi({ matches: [oemMatch] });
    render(<Maintenance assets={[trackedAsset]} apiRequest={apiRequest as unknown as WebRequest} initialAssetId={trackedAsset.id} />);

    await screen.findByText("Recommended plan");
    expect(screen.getByText("Exact OEM plan")).toBeInTheDocument();
    expect(screen.queryByText("oem-1")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect(await screen.findByRole("region", { name: "Recommended plan preview" })).toHaveTextContent("Engine Oil");
    fireEvent.click(screen.getAllByRole("button", { name: "Apply Plan" })[0]);
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/owner/maintenance/plans/tracked-1/apply-template",
      expect.objectContaining({ method: "POST" }),
    ));
  });

  it("falls back to a starter recommendation when no exact OEM plan matches", async () => {
    const apiRequest = maintenanceApi({
      matches: [{
        id: "starter-1",
        name: "Tracked Excavator Starter",
        template_type: "COMPANY_STARTER",
        confidence: "SUGGESTED",
      }],
    });
    render(<Maintenance assets={[trackedAsset]} apiRequest={apiRequest as unknown as WebRequest} initialAssetId={trackedAsset.id} />);

    await screen.findByText("Recommended plan");
    expect(screen.getByText("Starter plan")).toBeInTheDocument();
    expect(screen.getByText("Tracked Excavator Starter")).toBeInTheDocument();
  });

  it("keeps the plan list compact and edits all supported triggers inline", async () => {
    const apiRequest = maintenanceApi();
    render(<Maintenance assets={[wheeledAsset]} apiRequest={apiRequest as unknown as WebRequest} initialAssetId={wheeledAsset.id} />);

    await screen.findByText("Engine Oil");
    expect(screen.getByRole("columnheader", { name: "Interval" })).toBeInTheDocument();
    expect(screen.getByText("5,000 km")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByLabelText("Every KM")).toHaveValue(5000);
    expect(screen.getByLabelText("Every hours")).toHaveValue(250);
    fireEvent.change(screen.getByLabelText("Every KM"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/api/v1/owner/maintenance/plans/wheeled-1/items/schedule-1",
      expect.objectContaining({ method: "PUT" }),
    ));
    const update = apiRequest.mock.calls.find(([path, request]) => path.includes("schedule-1") && request?.method === "PUT");
    expect(JSON.parse(String(update?.[1]?.body)).criteria).not.toEqual(
      expect.arrayContaining([expect.objectContaining({ basis: "ODOMETER_KM" })]),
    );
  });

  it("previews a copy and keeps a missing source plan error inline", async () => {
    const apiRequest = maintenanceApi({ sourceHasPlan: false });
    render(<Maintenance assets={[wheeledAsset, sourceAsset]} apiRequest={apiRequest as unknown as WebRequest} initialAssetId={wheeledAsset.id} />);

    await screen.findByText("Asset plan");
    fireEvent.click(screen.getByRole("button", { name: "Copy from another Asset" }));
    fireEvent.change(screen.getByLabelText("Copy maintenance plan from Asset"), { target: { value: sourceAsset.id } });
    expect(screen.queryByText(/does not have a maintenance plan/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect(await screen.findByText("That Asset does not have a maintenance plan to copy.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copy Plan" })).not.toBeInTheDocument();
  });

  it("keeps a directly opened rented Asset read-only", async () => {
    const apiRequest = maintenanceApi();
    render(<Maintenance assets={[rentedAsset]} apiRequest={apiRequest as unknown as WebRequest} initialAssetId={rentedAsset.id} />);

    await screen.findByText("Maintenance managed by rental owner.");
    expect(screen.queryByLabelText("Maintenance Asset")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "+ Custom Item" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copy from another Asset" })).not.toBeInTheDocument();
  });

  it("filters Owner history and expands truthful service details", async () => {
    const history = [{
      id: "record-1",
      asset_id: wheeledAsset.id,
      asset_code: "TIP-01",
      task_label: "Engine Oil",
      service_date: "2026-10-01",
      odometer_km: "15000",
      hour_meter: "1250",
      vendor: "Fleet workshop",
      total_cost: "3400.00",
      notes: "Filter replaced",
      created_at: "2026-10-01T10:30:00Z",
      site_name: "Quarry",
      submitted_by: "Driver Dev",
      approved_by: "Supervisor Sam",
      status: "COMPLETED",
      evidence: [{ evidence_id: "evidence-1", content_type: "image/jpeg", size_bytes: 100 }],
    }];
    const apiRequest = maintenanceApi({ history });
    render(<Maintenance assets={[wheeledAsset]} apiRequest={apiRequest as unknown as WebRequest} />);

    fireEvent.click(screen.getByRole("tab", { name: "History" }));
    expect(await screen.findByText("Driver Dev")).toBeInTheDocument();
    expect(screen.getByText("Supervisor Sam")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Engine Oil" }));
    expect(screen.getByText("Fleet workshop")).toBeInTheDocument();
    expect(screen.getByText("Filter replaced")).toBeInTheDocument();
    expect(screen.getByText("Audit")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Photo 1" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("History from date"), { target: { value: "2026-10-02" } });
    expect(screen.getByText("No service history matches these filters.")).toBeInTheDocument();
  });
});
