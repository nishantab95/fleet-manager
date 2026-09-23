export type MembershipRole = "OWNER_ADMIN" | "SUPERVISOR" | "DRIVER";
export type Status = "ACTIVE" | "INACTIVE";
export type VerificationStatus = "PENDING_VERIFICATION" | "APPROVED" | "REJECTED" | "DISPUTED" | "AMENDED";

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
export type Assignment = { id: string; driver_membership_id: string; driver_name: string; supervisor_membership_id: string; supervisor_name: string; tipper_id: string; registration_number: string; site_id: string; site_name: string; starts_at: string; ends_at: string | null };

export type SupervisorHistory = { status: VerificationStatus; reason: string | null; actor_name: string | null; created_at: string };
export type SupervisorEvent = { event_id: string; event_type: "TRIP_COMPLETE" | "KM_READING" | "DIESEL" | "EMERGENCY"; assignment_id: string; driver_name: string; tipper_registration_number: string; site_id: string; site_name: string; device_created_at: string; server_received_at: string; verification_status: VerificationStatus; reading_type: "START_READING" | "END_READING" | null; reading_value: string | null; litres: string | null; emergency_category: string | null; emergency_status: string | null; emergency_description: string | null; evidence_id: string | null; evidence_available: boolean; verification_history: SupervisorHistory[] };
export type SiteCompleteness = { assignment_id: string; driver_name: string; tipper_registration_number: string; site_id: string; site_name: string; has_start_reading: boolean; has_end_reading: boolean; start_reading_value: string | null; end_reading_value: string | null; odometer_regression: boolean; pending_trip_verification: boolean; pending_diesel_verification: boolean; unresolved_emergency: boolean };
export type ReportException = { code: string; description: string; assignment_id: string; tipper_id: string; tipper_registration_number: string; site_id: string; event_id: string | null };
export type ReportHistory = { status: VerificationStatus; actor_name: string | null; reason: string | null; created_at: string };
export type ReportEvent = { event_id: string; event_type: "TRIP_COMPLETE" | "KM_READING" | "DIESEL" | "EMERGENCY"; assignment_id: string; tipper_id: string; tipper_registration_number: string; site_id: string; site_name: string; driver_name: string; supervisor_name: string; device_created_at: string; server_received_at: string; verification_status: VerificationStatus; reading_type: string | null; reading_value: number | null; litres: number | null; emergency_category: string | null; emergency_status: string | null; emergency_description: string | null; evidence_available: boolean; verification_history: ReportHistory[] };
export type ClosureHistory = { status: "OPEN" | "READY_TO_CLOSE" | "CLOSED" | "REOPENED"; actor_name: string | null; reason: string | null; created_at: string };
export type Closure = { site_id: string; site_name: string; operational_date: string; reporting_timezone: string; workday_start_minutes: number; status: "OPEN" | "READY_TO_CLOSE" | "CLOSED" | "REOPENED"; blockers: ReportException[]; history: ClosureHistory[] };
export type TipperDailyReport = { assignment_id: string; tipper_id: string; registration_number: string; short_name: string | null; site_id: string; site_name: string; driver_name: string; supervisor_name: string; assignment_starts_at: string; assignment_ends_at: string | null; approved_trip_count: number; pending_trip_count: number; disputed_trip_count: number; rejected_trip_count: number; start_km: number | null; end_km: number | null; distance_km: number | null; verified_diesel_issued: number; pending_diesel_count: number; disputed_diesel_count: number; unresolved_emergency_count: number; missing_start_reading: boolean; missing_end_reading: boolean; completeness_status: string; exceptions: ReportException[]; events: ReportEvent[] };
export type SiteDailyReport = { site_id: string; site_name: string; operational_date: string; reporting_timezone: string; assigned_tippers_count: number; approved_trip_count: number; pending_trip_count: number; disputed_trip_count: number; total_km: number | null; verified_diesel_issued: number; missing_reading_count: number; unresolved_emergency_count: number; closure: Closure; tippers: TipperDailyReport[] };
export type DashboardReport = { operational_date: string; reporting_timezone: string; workday_start_minutes: number; assigned_tippers_count: number; approved_trip_count: number; total_km: number | null; verified_diesel_issued: number; pending_verification_count: number; missing_reading_count: number; unresolved_emergency_count: number; sites_not_closed_count: number; complete_tippers_count: number; sites: SiteDailyReport[]; exceptions: ReportException[] };
export type CompanySettings = { company_id: string; reporting_timezone: string; operational_day_start_minutes: number };

export type DriverAssignment = { assignment_id: string; tipper_id: string; tipper_registration_number: string; tipper_short_name: string | null; site_id: string; site_name: string; supervisor_name: string };
