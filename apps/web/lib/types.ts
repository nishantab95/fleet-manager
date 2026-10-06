export type MembershipRole = "OWNER_ADMIN" | "SUPERVISOR" | "DRIVER";
export type Status = "ACTIVE" | "INACTIVE";
export type MembershipStatus = "INVITED" | "ACTIVE" | "INACTIVE";
export type VerificationStatus = "PENDING_VERIFICATION" | "APPROVED" | "REJECTED" | "DISPUTED" | "AMENDED";
export type FleetAssetType = "TIPPER" | "EXCAVATOR" | "BACKHOE_LOADER" | "ROLLER" | "GRADER";
export type AssetOwnershipType = "OWNED" | "RENTED";

export type Tokens = {
  access_token: string;
  expires_in: number;
  membership_id: string;
  company_id: string;
  role: MembershipRole;
};

export type Membership = {
  membership_id: string;
  company_id: string;
  company_name: string;
  role: MembershipRole;
};

export type Me = {
  user_id: string;
  display_name: string;
  membership_id: string;
  company_id: string;
  company_name: string;
  role: MembershipRole;
};

export type Site = { id: string; name: string; code: string | null; status: Status };
export type Tipper = { id: string; registration_number: string; short_name: string | null; status: Status };
export type Person = { user_id: string; membership_id: string; phone: string; display_name: string; role: MembershipRole; status: Status; user_status: string };
export type SupervisorAccess = { id: string; supervisor_membership_id: string; supervisor_name: string; site_id: string; site_name: string };
export type Assignment = { id: string; driver_membership_id: string; driver_name: string; supervisor_membership_id: string; supervisor_name: string; tipper_id: string; registration_number: string; site_id: string; site_name: string; starts_at: string; ends_at: string | null; regular_duty_minutes: number };

export type AssetSiteDeployment = { id: string; asset_id: string; site_id: string; site_name: string; starts_at: string; ends_at: string | null };
export type OwnerAssetAssignment = {
  assignment_id: string;
  site_id: string;
  site_name: string;
  driver_membership_id: string;
  driver_name: string;
  starts_at: string;
  regular_duty_minutes?: number;
};
export type OwnerAsset = {
  id: string;
  asset_code: string;
  asset_type: FleetAssetType;
  ownership_type: AssetOwnershipType;
  registration_number: string | null;
  short_name: string | null;
  manufacturer: string | null;
  model: string | null;
  status: Status;
  rental_party_name: string | null;
  rental_start_date: string | null;
  rental_end_date: string | null;
  supports_odometer_km: boolean;
  supports_hour_meter: boolean;
  current_deployment: AssetSiteDeployment | null;
  has_active_assignment: boolean;
  active_assignment: OwnerAssetAssignment | null;
};
export type OwnerPerson = {
  user_id: string;
  membership_id: string;
  phone: string;
  display_name: string;
  role: MembershipRole;
  status: MembershipStatus;
  sites: { site_id: string; site_name: string }[];
  has_active_assignment: boolean;
  has_active_duty: boolean;
  current_asset_id: string | null;
  current_asset_code: string | null;
  current_site_id: string | null;
  current_site_name: string | null;
};
export type OwnerSite = {
  id: string;
  name: string;
  short_name?: string | null;
  code: string | null;
  location_description: string | null;
  latitude: number | null;
  longitude: number | null;
  status: Status;
  supervisors: { access_id: string; membership_id: string; display_name: string }[];
  asset_count: number;
};

export type FutureFeatures = {
  maintenance: boolean;
  asset_documents: boolean;
  notifications: boolean;
  telematics: boolean;
  fuel_integrations: boolean;
  toll_expenses: boolean;
  multi_meter: boolean;
  payroll: boolean;
  attendance_location: boolean;
};

export type MaintenanceCriterion = {
  id: string;
  basis: "ODOMETER_KM" | "HOUR_METER_HOURS" | "CALENDAR_TIME";
  interval_value: string;
  warning_threshold: string;
  last_baseline_value: string | null;
  last_baseline_date: string | null;
  next_due_value: string | null;
  next_due_date: string | null;
  current_value: string | null;
  due_status: "UNKNOWN" | "NOT_DUE" | "DUE_SOON" | "DUE" | "OVERDUE";
};

export type MaintenanceSchedule = {
  id: string;
  asset_id: string;
  maintenance_type: string;
  custom_label: string | null;
  description: string | null;
  interval_basis: "KM" | "HMR" | "DATE";
  interval_value: string;
  warning_threshold: string;
  last_service_meter: string | null;
  last_service_date: string | null;
  next_due_meter: string | null;
  next_due_date: string | null;
  current_meter: string | null;
  due_status: "UNKNOWN" | "NOT_DUE" | "DUE_SOON" | "DUE" | "OVERDUE";
  status: Status;
  notes: string | null;
  criteria: MaintenanceCriterion[];
};

export type MaintenanceWorkOrder = {
  id: string;
  asset_id: string;
  schedule_id: string | null;
  title: string;
  description: string | null;
  status: "DRAFT" | "SCHEDULED" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED";
  vendor_name: string | null;
  scheduled_for: string | null;
  completed_at: string | null;
  completion_meter: string | null;
  completion_odometer_km: string | null;
  completion_hour_meter: string | null;
  labor_cost: string;
  parts_cost: string;
  other_cost: string;
  notes: string | null;
};

export type MaintenanceRecord = {
  id: string;
  schedule_id: string;
  work_order_id: string | null;
  asset_id: string;
  performed_on: string;
  meter_value: string | null;
  completion_odometer_km: string | null;
  completion_hour_meter: string | null;
  notes: string | null;
  vendor_name: string | null;
  labor_cost: string;
  parts_cost: string;
  other_cost: string;
};

export type AssetDocumentPolicy = {
  id: string;
  asset_type: FleetAssetType;
  ownership_type: AssetOwnershipType | null;
  document_type: string;
  required: boolean;
  expiry_warning_days: number;
};

export type AssetCompliance = {
  asset_id: string;
  asset_code: string;
  asset_type: FleetAssetType;
  ownership_type: AssetOwnershipType;
  policy_id: string;
  document_type: string;
  required: boolean;
  status: "VALID" | "EXPIRING_SOON" | "EXPIRED" | "MISSING" | "NOT_REQUIRED" | "UNKNOWN";
  document_id: string | null;
  revision_number: number | null;
  expiry_date: string | null;
};

export type AssetDocument = {
  id: string;
  asset_id: string;
  document_type: string;
  expiry_warning_days: number;
  revision_number: number;
  document_number: string | null;
  issue_date: string | null;
  expiry_date: string | null;
  issuer: string | null;
  notes: string | null;
  expiry_status: string;
};

export type InAppNotification = {
  id: string;
  category: string;
  title: string;
  body: string;
  state: "UNREAD" | "READ" | "ACKNOWLEDGED";
  deep_link: Record<string, string> | null;
  created_at: string;
};

export type TelematicsMapping = {
  id: string;
  asset_id: string;
  provider: string;
  provider_vehicle_id: string;
  active: boolean;
};

export type TelematicsPosition = {
  id: string;
  asset_id: string;
  mapping_id: string;
  provider_event_id: string;
  recorded_at: string;
  latitude: string;
  longitude: string;
  speed_kph: string | null;
  heading: string | null;
  ignition_state: boolean | null;
  odometer_km: string | null;
  engine_hours: string | null;
  battery_voltage: string | null;
};

export type TelematicsMeterDiscrepancy = {
  id: string;
  asset_id: string;
  position_id: string;
  manual_event_id: string | null;
  meter_type: string;
  telemetry_value: string;
  manual_value: string | null;
  tolerance: string;
  difference: string | null;
  status: "WITHIN_TOLERANCE" | "MISMATCH" | "INSUFFICIENT_DATA";
  created_at: string;
};

export type CompensationProfile = {
  id: string;
  membership_id: string;
  pay_basis: "MONTHLY" | "DAILY" | "HOURLY";
  base_amount: string;
  effective_from: string;
  effective_to: string | null;
  standard_duty_minutes: number;
  overtime_rate_per_hour: string;
  notes: string | null;
};

export type AttendanceDay = {
  membership_id: string;
  display_name: string;
  operational_date: string;
  duty_minutes: number;
  overtime_minutes: number;
  state: "COMPLETE" | "OPEN_SESSION" | "OVERLAP_EXCEPTION" | "MISSING_DATA";
  location_confidence: string;
};

export type PayrollPeriod = {
  id: string;
  starts_on: string;
  ends_on: string;
  status: "DRAFT" | "REVIEWED" | "FINALIZED";
  reviewed_at: string | null;
  finalized_at: string | null;
};

export type PayrollLine = {
  id: string;
  period_id: string;
  membership_id: string;
  display_name_snapshot: string;
  pay_basis_snapshot: "MONTHLY" | "DAILY" | "HOURLY";
  base_pay: string;
  duty_minutes: number;
  overtime_minutes: number;
  overtime_rate_per_hour: string;
  overtime_amount: string;
  adjustment_amount: string;
  calculated_gross_pay: string;
  calculation_state: string;
  calculation_snapshot: Record<string, unknown>;
};

export type AttendanceLocationSnapshot = {
  id: string;
  membership_id: string;
  asset_id: string;
  site_id: string;
  captured_at_device: string;
  source: string;
  status: string;
  confidence: string;
  site_distance_m: string | null;
  asset_distance_m: string | null;
};

export type LatestTelematics = {
  mapping: TelematicsMapping;
  position: TelematicsPosition | null;
  stale: boolean;
};

export type GeofenceTransition = {
  id: string;
  asset_id: string;
  site_id: string;
  position_id: string;
  transition_type: "ENTER" | "EXIT";
  occurred_at: string;
  distance_m: string;
};

export type FuelImportBatch = {
  id: string;
  file_name: string;
  source_name: string;
  status: string;
  total_rows: number;
  imported_rows: number;
  rejected_rows: number;
  created_at: string;
};

export type FuelTransaction = {
  id: string;
  batch_id: string;
  row_number: number;
  row_status: "IMPORTED" | "DUPLICATE" | "INVALID" | "UNMAPPED";
  error_message: string | null;
  asset_id: string | null;
  asset_identifier: string;
  source_type: string;
  source_name: string;
  external_transaction_id: string;
  occurred_at: string | null;
  litres: string | null;
};

export type FuelReconciliation = {
  id: string;
  external_transaction_id: string;
  operational_event_id: string | null;
  status: string;
  tolerance_litres: string;
  difference_litres: string | null;
  manually_resolved: boolean;
  resolution_reason: string | null;
};
export type DriverAssetAssignment = {
  assignment_id: string;
  asset_id: string;
  asset_code: string;
  registration_number: string | null;
  driver_membership_id: string;
  driver_name: string;
  asset_site_deployment_id: string;
  site_id: string;
  site_name: string;
  starts_at: string;
  ends_at: string | null;
  regular_duty_minutes: number;
};
export type DriverCandidate = {
  membership_id: string;
  display_name: string;
  phone?: string;
  status?: MembershipStatus;
};
export type ReportTemplate = {
  id: string;
  name: string;
  is_builtin: boolean;
  is_default: boolean;
  included_sheets: string[];
  management_dashboard_columns: string[];
  tipper_daily_columns: string[];
  machinery_daily_columns: string[];
  created_at: string;
  updated_at: string;
};

export type SupervisorHistory = { status: VerificationStatus; reason: string | null; actor_name: string | null; created_at: string };
export type SupervisorEvent = { event_id: string; event_type: "TRIP_COMPLETE" | "KM_READING" | "DIESEL" | "EMERGENCY"; assignment_id: string; duty_session_id: string | null; driver_name: string; driver_phone: string | null; tipper_registration_number: string; site_id: string; site_name: string; device_created_at: string; server_received_at: string; verification_status: VerificationStatus; reading_type: "START_READING" | "END_READING" | null; reading_value: string | null; litres: string | null; emergency_category: string | null; emergency_status: string | null; emergency_description: string | null; evidence_id: string | null; evidence_available: boolean; verification_history: SupervisorHistory[] };
export type SiteCompleteness = { assignment_id: string; driver_name: string; tipper_registration_number: string; site_id: string; site_name: string; has_start_reading: boolean; has_end_reading: boolean; start_reading_value: string | null; end_reading_value: string | null; odometer_regression: boolean; pending_trip_verification: boolean; pending_diesel_verification: boolean; unresolved_emergency: boolean };
export type ReportException = { code: string; description: string; assignment_id: string; tipper_id: string; tipper_registration_number: string; site_id: string; event_id: string | null };
export type ReportHistory = { status: VerificationStatus; actor_name: string | null; reason: string | null; created_at: string };
export type ReportEvent = { event_id: string; event_type: "TRIP_COMPLETE" | "KM_READING" | "HMR_READING" | "DIESEL" | "EMERGENCY"; assignment_id: string; duty_session_id: string | null; tipper_id: string; tipper_registration_number: string; asset_code: string; asset_type: FleetAssetType; site_id: string; site_name: string; driver_name: string; driver_phone: string | null; supervisor_name: string; device_created_at: string; server_received_at: string; verification_status: VerificationStatus; reading_type: string | null; reading_value: number | null; litres: number | null; emergency_category: string | null; emergency_status: string | null; emergency_description: string | null; evidence_available: boolean; verification_history: ReportHistory[] };
export type ClosureHistory = { status: "OPEN" | "READY_TO_CLOSE" | "CLOSED" | "REOPENED"; actor_name: string | null; reason: string | null; created_at: string };
export type Closure = { site_id: string; site_name: string; operational_date: string; reporting_timezone: string; workday_start_minutes: number; status: "OPEN" | "READY_TO_CLOSE" | "CLOSED" | "REOPENED"; blockers: ReportException[]; history: ClosureHistory[] };
export type TipperDailyReport = { assignment_id: string; tipper_id: string; registration_number: string; short_name: string | null; asset_type: FleetAssetType; site_id: string; site_name: string; driver_name: string; supervisor_name: string; assignment_starts_at: string; assignment_ends_at: string | null; approved_trip_count: number | null; pending_trip_count: number | null; disputed_trip_count: number | null; rejected_trip_count: number | null; trips_state: "NOT_APPLICABLE" | "MISSING" | "ZERO" | "VALUE"; start_km: number | null; end_km: number | null; start_hmr: number | null; end_hmr: number | null; machine_hours: number | null; distance_state: "NOT_APPLICABLE" | "MISSING" | "ZERO" | "VALUE"; machine_hours_state: "NOT_APPLICABLE" | "MISSING" | "ZERO" | "VALUE"; distance_km: number | null; km_per_approved_trip: number | null; verified_diesel_issued: number; pending_diesel_issued: number; diesel_issued_per_approved_trip: number | null; first_trip_completed_at: string | null; last_trip_completed_at: string | null; recorded_activity_span_seconds: number | null; avg_trip_completion_interval_seconds: number | null; median_trip_completion_interval_seconds: number | null; longest_trip_gap_seconds: number | null; pending_diesel_count: number; disputed_diesel_count: number; unresolved_emergency_count: number; missing_start_reading: boolean; missing_end_reading: boolean; completeness_status: string; closure_status: "OPEN" | "READY_TO_CLOSE" | "CLOSED" | "REOPENED"; exceptions: ReportException[]; events: ReportEvent[] };
export type SiteDailyReport = { site_id: string; site_name: string; operational_date: string; reporting_timezone: string; assigned_tippers_count: number; approved_trip_count: number; pending_trip_count: number; disputed_trip_count: number; total_km: number | null; verified_diesel_issued: number; missing_reading_count: number; unresolved_emergency_count: number; closure: Closure; tippers: TipperDailyReport[] };
export type DashboardReport = { operational_date: string; reporting_timezone: string; workday_start_minutes: number; assigned_tippers_count: number; approved_trip_count: number; total_km: number | null; verified_diesel_issued: number; pending_verification_count: number; missing_reading_count: number; unresolved_emergency_count: number; sites_not_closed_count: number; complete_tippers_count: number; drivers_on_duty?: number; drivers_past_regular_duty?: number; closed_duties_count?: number; sites: SiteDailyReport[]; exceptions: ReportException[] };
export type CompanySettings = { company_id: string; reporting_timezone: string; operational_day_start_minutes: number };

export type DriverAssignment = { assignment_id: string; tipper_id: string; tipper_registration_number: string; tipper_short_name: string | null; site_id: string; site_name: string; supervisor_name: string; regular_duty_minutes: number };
export type DriverDutyState = { status: "NONE" | "ACTIVE" | "CLOSED"; session_id: string | null; assignment_id: string | null; tipper_id: string | null; site_id: string | null; started_at: string | null; start_km: number | null; ended_at: string | null; end_km: number | null; regular_duty_minutes: number | null };
export type DriverDutyReport = { operational_date: string; session_id: string; assignment_id: string; driver_name: string; asset_code: string; tipper_registration_number: string; asset_type: FleetAssetType; site_name: string; duty_start: string; start_km: number | null; start_hmr: number | null; regular_duty_minutes: number; regular_duty_ends_at: string; actual_duty_end: string | null; end_km: number | null; end_hmr: number | null; machine_hours: number | null; verified_diesel_issued: number; pending_diesel_issued: number; actual_duty_span_seconds: number | null; overtime_minutes: number; status: "ACTIVE" | "CLOSED" };
