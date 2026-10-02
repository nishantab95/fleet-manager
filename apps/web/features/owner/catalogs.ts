import type { FleetAssetType } from "../../lib/types";

export const assetTypes: FleetAssetType[] = ["TIPPER", "EXCAVATOR", "BACKHOE_LOADER", "ROLLER", "GRADER"];

export const assetCapabilities: Record<FleetAssetType, { trips: boolean; odometer: boolean; hourMeter: boolean; diesel: boolean; emergency: boolean; duty: boolean }> = {
  TIPPER: { trips: true, odometer: true, hourMeter: false, diesel: true, emergency: true, duty: true },
  EXCAVATOR: { trips: false, odometer: false, hourMeter: true, diesel: true, emergency: true, duty: true },
  BACKHOE_LOADER: { trips: false, odometer: false, hourMeter: true, diesel: true, emergency: true, duty: true },
  ROLLER: { trips: false, odometer: false, hourMeter: true, diesel: true, emergency: true, duty: true },
  GRADER: { trips: false, odometer: false, hourMeter: true, diesel: true, emergency: true, duty: true },
};

export const sheetCatalog = [
  ["management_dashboard", "Management Dashboard"],
  ["tipper_daily", "Tipper Daily"],
  ["machinery_daily", "Machinery Daily"],
  ["trip_register", "Trip Register"],
  ["meter_readings", "Meter Readings"],
  ["diesel_register", "Diesel Register"],
  ["duty_register", "Duty Register"],
  ["exceptions", "Exceptions"],
] as const;

export const managementColumns = ["asset", "asset_type", "site", "operator", "assignment_status", "duty_status", "trips", "distance_km", "machine_hours", "verified_diesel_l", "pending_status"];
export const tipperColumns = ["asset", "site", "registration", "driver", "start_km", "end_km", "distance_km", "approved_trips", "diesel_l", "duty_start", "duty_end", "pending", "status"];
export const machineryColumns = ["asset", "asset_type", "site", "operator", "start_hmr", "end_hmr", "machine_hours", "diesel_l", "duty_start", "duty_end", "pending", "status"];

export function title(value?: string): string {
  return (value ?? "Unknown").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
