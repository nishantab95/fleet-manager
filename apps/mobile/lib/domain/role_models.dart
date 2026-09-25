import 'dart:typed_data';

import 'package:flutter/services.dart' show appFlavor;

const bool _explicitPilotDefine = bool.fromEnvironment(
  'FLEET_PILOT',
  defaultValue: false,
);

// Flutter exposes the selected Android product flavor through appFlavor.
// Keep the explicit define for tests and scripted builds, but never let it
// turn a production flavor into a Pilot build.
const bool isPilotBuild =
    appFlavor == 'pilot' || (appFlavor != 'production' && _explicitPilotDefine);

class SupervisorSite {
  const SupervisorSite({
    required this.id,
    required this.name,
    this.code,
    this.status = 'ACTIVE',
  });

  final String id;
  final String name;
  final String? code;
  final String status;

  factory SupervisorSite.fromJson(Map<String, dynamic> json) => SupervisorSite(
    id: '${json['id']}',
    name: '${json['name'] ?? 'Site'}',
    code: json['code'] as String?,
    status: '${json['status'] ?? 'ACTIVE'}',
  );
}

class SupervisorHistoryItem {
  const SupervisorHistoryItem({
    required this.status,
    this.reason,
    this.actorName,
    this.createdAt,
  });

  final String status;
  final String? reason;
  final String? actorName;
  final DateTime? createdAt;

  factory SupervisorHistoryItem.fromJson(Map<String, dynamic> json) =>
      SupervisorHistoryItem(
        status: '${json['status'] ?? ''}',
        reason: json['reason'] as String?,
        actorName: json['actor_name'] as String?,
        createdAt: _date(json['created_at']),
      );
}

class SupervisorEvent {
  const SupervisorEvent({
    required this.id,
    required this.eventType,
    required this.assignmentId,
    required this.driverName,
    required this.tipperRegistration,
    required this.siteId,
    required this.siteName,
    required this.deviceCreatedAt,
    required this.verificationStatus,
    required this.evidenceAvailable,
    this.dutySessionId,
    this.driverPhone,
    this.readingType,
    this.readingValue,
    this.litres,
    this.emergencyCategory,
    this.emergencyStatus,
    this.emergencyDescription,
    this.history = const [],
  });

  final String id;
  final String eventType;
  final String assignmentId;
  final String? dutySessionId;
  final String driverName;
  final String? driverPhone;
  final String tipperRegistration;
  final String siteId;
  final String siteName;
  final DateTime? deviceCreatedAt;
  final String verificationStatus;
  final String? readingType;
  final double? readingValue;
  final double? litres;
  final String? emergencyCategory;
  final String? emergencyStatus;
  final String? emergencyDescription;
  final bool evidenceAvailable;
  final List<SupervisorHistoryItem> history;

  bool get isEmergency => eventType == 'EMERGENCY';
  bool get isTrip => eventType == 'TRIP_COMPLETE';
  bool get isKm => eventType == 'KM_READING';
  bool get isDiesel => eventType == 'DIESEL';
  bool get isOpenEmergency => isEmergency && emergencyStatus == 'OPEN';
  bool get isPending => verificationStatus == 'PENDING_VERIFICATION';

  factory SupervisorEvent.fromJson(Map<String, dynamic> json) {
    final value = json['reading_value'];
    final litres = json['litres'];
    return SupervisorEvent(
      id: '${json['event_id']}',
      eventType: '${json['event_type'] ?? ''}',
      assignmentId: '${json['assignment_id']}',
      dutySessionId: json['duty_session_id']?.toString(),
      driverName: '${json['driver_name'] ?? 'Driver'}',
      driverPhone: json['driver_phone'] as String?,
      tipperRegistration: '${json['tipper_registration_number'] ?? ''}',
      siteId: '${json['site_id']}',
      siteName: '${json['site_name'] ?? 'Site'}',
      deviceCreatedAt: _date(json['device_created_at']),
      verificationStatus: '${json['verification_status'] ?? ''}',
      readingType: json['reading_type'] as String?,
      readingValue: _number(value),
      litres: _number(litres),
      emergencyCategory: json['emergency_category'] as String?,
      emergencyStatus: json['emergency_status'] as String?,
      emergencyDescription: json['emergency_description'] as String?,
      evidenceAvailable: json['evidence_available'] == true,
      history: (json['verification_history'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(SupervisorHistoryItem.fromJson)
          .toList(),
    );
  }
}

class CompletenessItem {
  const CompletenessItem({
    required this.driverName,
    required this.tipperRegistration,
    required this.hasStart,
    required this.hasEnd,
    required this.pendingTrips,
    required this.pendingDiesel,
    required this.unresolvedEmergency,
  });

  final String driverName;
  final String tipperRegistration;
  final bool hasStart;
  final bool hasEnd;
  final bool pendingTrips;
  final bool pendingDiesel;
  final bool unresolvedEmergency;

  factory CompletenessItem.fromJson(Map<String, dynamic> json) =>
      CompletenessItem(
        driverName: '${json['driver_name'] ?? 'Driver'}',
        tipperRegistration: '${json['tipper_registration_number'] ?? ''}',
        hasStart: json['has_start_reading'] == true,
        hasEnd: json['has_end_reading'] == true,
        pendingTrips: json['pending_trip_verification'] == true,
        pendingDiesel: json['pending_diesel_verification'] == true,
        unresolvedEmergency: json['unresolved_emergency'] == true,
      );
}

class OwnerDashboard {
  const OwnerDashboard({
    required this.date,
    required this.activeTippers,
    required this.approvedTrips,
    required this.pending,
    required this.distanceKm,
    required this.dieselIssued,
    required this.missingReadings,
    required this.openEmergencies,
    required this.driversOnDuty,
    required this.driversPastDuty,
    required this.sites,
  });

  final String date;
  final int activeTippers;
  final int approvedTrips;
  final int pending;
  final double? distanceKm;
  final double dieselIssued;
  final int missingReadings;
  final int openEmergencies;
  final int driversOnDuty;
  final int driversPastDuty;
  final List<OwnerSiteSummary> sites;

  factory OwnerDashboard.fromJson(Map<String, dynamic> json) => OwnerDashboard(
    date: '${json['operational_date'] ?? ''}',
    activeTippers: _int(json['assigned_tippers_count']),
    approvedTrips: _int(json['approved_trip_count']),
    pending: _int(json['pending_verification_count']),
    distanceKm: _number(json['total_km']),
    dieselIssued: _number(json['verified_diesel_issued']) ?? 0,
    missingReadings: _int(json['missing_reading_count']),
    openEmergencies: _int(json['unresolved_emergency_count']),
    driversOnDuty: _int(json['drivers_on_duty']),
    driversPastDuty: _int(json['drivers_past_regular_duty']),
    sites: (json['sites'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(OwnerSiteSummary.fromJson)
        .toList(),
  );
}

class OwnerSiteSummary {
  const OwnerSiteSummary({
    required this.id,
    required this.name,
    required this.tippers,
    required this.approvedTrips,
    required this.distanceKm,
    required this.diesel,
    required this.pending,
    required this.missing,
    required this.emergencies,
    required this.closureStatus,
  });

  final String id;
  final String name;
  final int tippers;
  final int approvedTrips;
  final double? distanceKm;
  final double diesel;
  final int pending;
  final int missing;
  final int emergencies;
  final String closureStatus;

  factory OwnerSiteSummary.fromJson(Map<String, dynamic> json) =>
      OwnerSiteSummary(
        id: '${json['site_id']}',
        name: '${json['site_name'] ?? 'Site'}',
        tippers: _int(json['assigned_tippers_count']),
        approvedTrips: _int(json['approved_trip_count']),
        distanceKm: _number(json['total_km']),
        diesel: _number(json['verified_diesel_issued']) ?? 0,
        pending: _int(json['pending_trip_count']),
        missing: _int(json['missing_reading_count']),
        emergencies: _int(json['unresolved_emergency_count']),
        closureStatus: '${json['closure']?['status'] ?? 'OPEN'}',
      );
}

class OwnerTipperReport {
  const OwnerTipperReport({
    required this.registration,
    required this.shortName,
    required this.siteName,
    required this.driverName,
    required this.approvedTrips,
    required this.distanceKm,
    required this.diesel,
    required this.pending,
    required this.missingStart,
    required this.missingEnd,
    required this.events,
  });

  final String registration;
  final String? shortName;
  final String siteName;
  final String driverName;
  final int approvedTrips;
  final double? distanceKm;
  final double diesel;
  final int pending;
  final bool missingStart;
  final bool missingEnd;
  final List<SupervisorEvent> events;

  factory OwnerTipperReport.fromJson(Map<String, dynamic> json) =>
      OwnerTipperReport(
        registration: '${json['registration'] ?? ''}',
        shortName: json['short_name'] as String?,
        siteName: '${json['site_name'] ?? 'Site'}',
        driverName: '${json['driver_name'] ?? 'Unassigned'}',
        approvedTrips: _int(json['approved_trip_count']),
        distanceKm: _number(json['distance_km']),
        diesel: _number(json['verified_diesel_issued']) ?? 0,
        pending:
            _int(json['pending_trip_count']) +
            _int(json['pending_diesel_count']),
        missingStart: json['missing_start_reading'] == true,
        missingEnd: json['missing_end_reading'] == true,
        events: (json['events'] as List<dynamic>? ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(SupervisorEvent.fromJson)
            .toList(),
      );
}

class OwnerDutyReport {
  const OwnerDutyReport({
    required this.driverName,
    required this.tipperRegistration,
    required this.siteName,
    required this.dutyStart,
    required this.startKm,
    required this.regularMinutes,
    required this.regularEnds,
    required this.actualEnd,
    required this.endKm,
    required this.spanSeconds,
    required this.overtimeMinutes,
    required this.status,
  });

  final String driverName;
  final String tipperRegistration;
  final String siteName;
  final DateTime? dutyStart;
  final double? startKm;
  final int regularMinutes;
  final DateTime? regularEnds;
  final DateTime? actualEnd;
  final double? endKm;
  final double? spanSeconds;
  final int overtimeMinutes;
  final String status;

  factory OwnerDutyReport.fromJson(Map<String, dynamic> json) =>
      OwnerDutyReport(
        driverName: '${json['driver_name'] ?? 'Driver'}',
        tipperRegistration: '${json['tipper_registration_number'] ?? ''}',
        siteName: '${json['site_name'] ?? 'Site'}',
        dutyStart: _date(json['duty_start']),
        startKm: _number(json['start_km']),
        regularMinutes: _int(json['regular_duty_minutes']),
        regularEnds: _date(json['regular_duty_ends_at']),
        actualEnd: _date(json['actual_duty_end']),
        endKm: _number(json['end_km']),
        spanSeconds: _number(json['actual_duty_span_seconds']),
        overtimeMinutes: _int(json['overtime_minutes']),
        status: '${json['status'] ?? ''}',
      );
}

DateTime? _date(Object? value) =>
    value is String ? DateTime.tryParse(value) : null;
double? _number(Object? value) => switch (value) {
  num v => v.toDouble(),
  String v => double.tryParse(v),
  _ => null,
};
int _int(Object? value) => switch (value) {
  int v => v,
  num v => v.toInt(),
  String v => int.tryParse(v) ?? 0,
  _ => 0,
};

// Kept as a named type so the evidence viewer can expose its authenticated bytes
// without ever exposing object-storage URLs to the UI.
typedef EvidenceBytes = Uint8List;
