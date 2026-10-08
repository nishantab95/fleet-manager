import 'dart:typed_data';

import 'package:flutter/services.dart' show appFlavor;

import 'driver_models.dart';

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
    this.shortName,
    this.code,
    this.status = 'ACTIVE',
  });

  final String id;
  final String name;
  final String? shortName;
  final String? code;
  final String status;

  factory SupervisorSite.fromJson(Map<String, dynamic> json) => SupervisorSite(
    id: '${json['id']}',
    name: '${json['name'] ?? 'Site'}',
    shortName: json['short_name'] as String?,
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
    this.assetCode,
    this.assetType = 'TIPPER',
    this.dutySessionId,
    this.captureGroupUuid,
    this.driverPhone,
    this.readingType,
    this.readingValue,
    this.litres,
    this.emergencyCategory,
    this.emergencyStatus,
    this.emergencyDescription,
    this.history = const [],
    this.assetShortName,
  });

  final String id;
  final String eventType;
  final String assignmentId;
  final String? dutySessionId;
  final String? captureGroupUuid;
  final String driverName;
  final String? driverPhone;
  final String? assetCode;
  final String? assetShortName;
  final String assetType;
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
  bool get isHmr => eventType == 'HMR_READING';
  bool get isDiesel => eventType == 'DIESEL';
  bool get isOpenEmergency =>
      isEmergency && emergencyStatus != null && emergencyStatus != 'RESOLVED';
  bool get isPending => verificationStatus == 'PENDING_VERIFICATION';
  bool get needsSupervisorReview => isPending && !isEmergency;

  factory SupervisorEvent.fromJson(Map<String, dynamic> json) {
    final value = json['reading_value'];
    final litres = json['litres'];
    return SupervisorEvent(
      id: '${json['event_id']}',
      eventType: '${json['event_type'] ?? ''}',
      assignmentId: '${json['assignment_id']}',
      dutySessionId: json['duty_session_id']?.toString(),
      captureGroupUuid: json['capture_group_uuid']?.toString(),
      driverName: '${json['driver_name'] ?? 'Driver'}',
      driverPhone: json['driver_phone'] as String?,
      assetCode: json['asset_code'] as String?,
      assetShortName: json['asset_short_name'] as String?,
      assetType: '${json['asset_type'] ?? 'TIPPER'}',
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

int supervisorReviewPendingCount(Iterable<SupervisorEvent> events) =>
    events.where((event) => event.needsSupervisorReview).length;

double supervisorDieselLitres(Iterable<SupervisorEvent> events) => events
    .where(
      (event) =>
          event.isDiesel &&
          event.litres != null &&
          event.verificationStatus != 'REJECTED',
    )
    .fold(0, (total, event) => total + event.litres!);

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
    required this.assetCode,
    required this.assetType,
    required this.supportsOdometerKm,
    required this.supportsHourMeter,
    required this.tipperRegistration,
    required this.siteName,
    required this.dutyStart,
    required this.startKm,
    required this.startHmr,
    required this.regularMinutes,
    required this.regularEnds,
    required this.actualEnd,
    required this.endKm,
    required this.endHmr,
    required this.machineHours,
    required this.verifiedDieselLitres,
    required this.pendingDieselLitres,
    required this.spanSeconds,
    required this.overtimeMinutes,
    required this.status,
  });

  final String driverName;
  final String assetCode;
  final String assetType;
  final bool supportsOdometerKm;
  final bool supportsHourMeter;
  final String tipperRegistration;
  final String siteName;
  final DateTime? dutyStart;
  final double? startKm;
  final double? startHmr;
  final int regularMinutes;
  final DateTime? regularEnds;
  final DateTime? actualEnd;
  final double? endKm;
  final double? endHmr;
  final double? machineHours;
  final double verifiedDieselLitres;
  final double pendingDieselLitres;
  final double? spanSeconds;
  final int overtimeMinutes;
  final String status;

  DriverAssetCapabilities get capabilities {
    final base = DriverAssetCapabilities.forType(assetType);
    return DriverAssetCapabilities(
      supportsTripComplete: base.supportsTripComplete,
      supportsOdometer: supportsOdometerKm,
      supportsHourMeter: supportsHourMeter,
      supportsDiesel: base.supportsDiesel,
      supportsEmergency: base.supportsEmergency,
      supportsDutySession: base.supportsDutySession,
    );
  }

  double? get distanceKm =>
      startKm != null && endKm != null ? endKm! - startKm! : null;

  factory OwnerDutyReport.fromJson(Map<String, dynamic> json) =>
      OwnerDutyReport(
        driverName: '${json['driver_name'] ?? 'Driver'}',
        assetCode:
            '${json['asset_code'] ?? json['tipper_registration_number'] ?? ''}',
        assetType: '${json['asset_type'] ?? 'TIPPER'}',
        supportsOdometerKm:
            json['supports_odometer_km'] as bool? ??
            DriverAssetCapabilities.forType(
              '${json['asset_type'] ?? 'TIPPER'}',
            ).supportsOdometer,
        supportsHourMeter:
            json['supports_hour_meter'] as bool? ??
            DriverAssetCapabilities.forType(
              '${json['asset_type'] ?? 'TIPPER'}',
            ).supportsHourMeter,
        tipperRegistration: '${json['tipper_registration_number'] ?? ''}',
        siteName: '${json['site_name'] ?? 'Site'}',
        dutyStart: _date(json['duty_start']),
        startKm: _number(json['start_km']),
        startHmr: _number(json['start_hmr']),
        regularMinutes: _int(json['regular_duty_minutes']),
        regularEnds: _date(json['regular_duty_ends_at']),
        actualEnd: _date(json['actual_duty_end']),
        endKm: _number(json['end_km']),
        endHmr: _number(json['end_hmr']),
        machineHours: _number(json['machine_hours']),
        verifiedDieselLitres: _number(json['verified_diesel_issued']) ?? 0,
        pendingDieselLitres: _number(json['pending_diesel_issued']) ?? 0,
        spanSeconds: _number(json['actual_duty_span_seconds']),
        overtimeMinutes: _int(json['overtime_minutes']),
        status: '${json['status'] ?? ''}',
      );
}

class OwnerAssetAssignment {
  const OwnerAssetAssignment({
    required this.assignmentId,
    required this.siteId,
    required this.siteName,
    required this.driverMembershipId,
    required this.driverName,
    required this.startsAt,
  });

  final String assignmentId;
  final String siteId;
  final String siteName;
  final String driverMembershipId;
  final String driverName;
  final DateTime? startsAt;

  factory OwnerAssetAssignment.fromJson(Map<String, dynamic> json) =>
      OwnerAssetAssignment(
        assignmentId: '${json['assignment_id']}',
        siteId: '${json['site_id']}',
        siteName: '${json['site_name'] ?? 'Site'}',
        driverMembershipId: '${json['driver_membership_id']}',
        driverName: '${json['driver_name'] ?? 'Driver'}',
        startsAt: _date(json['starts_at']),
      );
}

class DriverCandidate {
  const DriverCandidate({
    required this.membershipId,
    required this.displayName,
  });

  final String membershipId;
  final String displayName;

  factory DriverCandidate.fromJson(Map<String, dynamic> json) =>
      DriverCandidate(
        membershipId: '${json['membership_id']}',
        displayName: '${json['display_name'] ?? 'Driver / Operator'}',
      );
}

class DriverAssetAssignment {
  const DriverAssetAssignment({
    required this.assignmentId,
    required this.assetId,
    required this.assetCode,
    required this.driverMembershipId,
    required this.driverName,
    required this.deploymentId,
    required this.siteId,
    required this.siteName,
    required this.startsAt,
    required this.endsAt,
    required this.regularDutyMinutes,
  });

  final String assignmentId;
  final String assetId;
  final String assetCode;
  final String driverMembershipId;
  final String driverName;
  final String deploymentId;
  final String siteId;
  final String siteName;
  final DateTime? startsAt;
  final DateTime? endsAt;
  final int regularDutyMinutes;

  factory DriverAssetAssignment.fromJson(Map<String, dynamic> json) =>
      DriverAssetAssignment(
        assignmentId: '${json['assignment_id']}',
        assetId: '${json['asset_id']}',
        assetCode: '${json['asset_code'] ?? ''}',
        driverMembershipId: '${json['driver_membership_id']}',
        driverName: '${json['driver_name'] ?? 'Driver / Operator'}',
        deploymentId: '${json['asset_site_deployment_id']}',
        siteId: '${json['site_id']}',
        siteName: '${json['site_name'] ?? 'Site'}',
        startsAt: _date(json['starts_at']),
        endsAt: _date(json['ends_at']),
        regularDutyMinutes: _int(json['regular_duty_minutes']),
      );
}

class AssetSiteDeployment {
  const AssetSiteDeployment({
    required this.id,
    required this.assetId,
    required this.siteId,
    required this.siteName,
    required this.startsAt,
    this.endsAt,
  });

  final String id;
  final String assetId;
  final String siteId;
  final String siteName;
  final DateTime? startsAt;
  final DateTime? endsAt;

  bool get isCurrent => endsAt == null;

  factory AssetSiteDeployment.fromJson(Map<String, dynamic> json) =>
      AssetSiteDeployment(
        id: '${json['id']}',
        assetId: '${json['asset_id']}',
        siteId: '${json['site_id']}',
        siteName: '${json['site_name'] ?? 'Site'}',
        startsAt: _date(json['starts_at']),
        endsAt: _date(json['ends_at']),
      );
}

class SiteDeployedAsset {
  const SiteDeployedAsset({
    required this.assetId,
    required this.assetCode,
    required this.assetType,
    required this.ownershipType,
    required this.registrationNumber,
    required this.shortName,
    required this.status,
    required this.currentDeployment,
    required this.driverMembershipId,
    required this.driverName,
    required this.dutyStatus,
    required this.pendingReviewCount,
  });

  final String assetId;
  final String assetCode;
  final String assetType;
  final String ownershipType;
  final String? registrationNumber;
  final String? shortName;
  final String status;
  final AssetSiteDeployment currentDeployment;
  final String? driverMembershipId;
  final String? driverName;
  final String? dutyStatus;
  final int pendingReviewCount;

  factory SiteDeployedAsset.fromJson(Map<String, dynamic> json) =>
      SiteDeployedAsset(
        assetId: '${json['asset_id']}',
        assetCode: '${json['asset_code'] ?? ''}',
        assetType: '${json['asset_type'] ?? ''}',
        ownershipType: '${json['ownership_type'] ?? ''}',
        registrationNumber: json['registration_number'] as String?,
        shortName: json['short_name'] as String?,
        status: '${json['status'] ?? 'ACTIVE'}',
        currentDeployment: AssetSiteDeployment.fromJson(
          json['current_deployment'] as Map<String, dynamic>,
        ),
        driverMembershipId: json['driver_membership_id'] as String?,
        driverName: json['driver_name'] as String?,
        dutyStatus: json['duty_status'] as String?,
        pendingReviewCount: _int(json['pending_review_count']),
      );
}

class OwnerAsset {
  const OwnerAsset({
    required this.id,
    required this.assetCode,
    required this.assetType,
    required this.ownershipType,
    required this.registrationNumber,
    required this.shortName,
    required this.manufacturer,
    required this.model,
    required this.status,
    required this.rentalPartyName,
    required this.rentalStartDate,
    required this.rentalEndDate,
    required this.currentDeployment,
    required this.hasActiveAssignment,
    required this.activeAssignment,
  });

  final String id;
  final String assetCode;
  final String assetType;
  final String ownershipType;
  final String? registrationNumber;
  final String? shortName;
  final String? manufacturer;
  final String? model;
  final String status;
  final String? rentalPartyName;
  final DateTime? rentalStartDate;
  final DateTime? rentalEndDate;
  final AssetSiteDeployment? currentDeployment;
  final bool hasActiveAssignment;
  final OwnerAssetAssignment? activeAssignment;

  bool get isOwned => ownershipType == 'OWNED';
  bool get isRented => ownershipType == 'RENTED';
  bool get isActive => status == 'ACTIVE';

  factory OwnerAsset.fromJson(Map<String, dynamic> json) {
    final assignment = json['active_assignment'];
    final deployment = json['current_deployment'];
    return OwnerAsset(
      id: '${json['id']}',
      assetCode: '${json['asset_code'] ?? ''}',
      assetType: '${json['asset_type'] ?? 'TIPPER'}',
      ownershipType: '${json['ownership_type'] ?? 'OWNED'}',
      registrationNumber: json['registration_number'] as String?,
      shortName: json['short_name'] as String?,
      manufacturer: json['manufacturer'] as String?,
      model: json['model'] as String?,
      status: '${json['status'] ?? 'ACTIVE'}',
      rentalPartyName: json['rental_party_name'] as String?,
      rentalStartDate: _date(json['rental_start_date']),
      rentalEndDate: _date(json['rental_end_date']),
      currentDeployment: deployment is Map<String, dynamic>
          ? AssetSiteDeployment.fromJson(deployment)
          : null,
      hasActiveAssignment: json['has_active_assignment'] == true,
      activeAssignment: assignment is Map<String, dynamic>
          ? OwnerAssetAssignment.fromJson(assignment)
          : null,
    );
  }
}

class OwnerAssetInput {
  const OwnerAssetInput({
    required this.assetCode,
    required this.registrationNumber,
    required this.shortName,
    required this.ownershipType,
    this.assetType = 'TIPPER',
    this.manufacturer,
    this.model,
    this.rentalPartyName,
    this.rentalStartDate,
    this.rentalEndDate,
  });

  final String assetCode;
  final String? registrationNumber;
  final String? shortName;
  final String ownershipType;
  final String assetType;
  final String? manufacturer;
  final String? model;
  final String? rentalPartyName;
  final DateTime? rentalStartDate;
  final DateTime? rentalEndDate;

  Map<String, dynamic> toJson({bool includeAssetType = false}) =>
      <String, dynamic>{
        if (includeAssetType) 'asset_type': assetType,
        'asset_code': assetCode,
        'registration_number': registrationNumber,
        'short_name': shortName,
        'ownership_type': ownershipType,
        'manufacturer': manufacturer,
        'model': model,
        'rental_party_name': ownershipType == 'RENTED' ? rentalPartyName : null,
        'rental_start_date': ownershipType == 'RENTED'
            ? _wireDate(rentalStartDate)
            : null,
        'rental_end_date': ownershipType == 'RENTED'
            ? _wireDate(rentalEndDate)
            : null,
      };
}

class OwnerPersonSite {
  const OwnerPersonSite({required this.id, required this.name});

  final String id;
  final String name;

  factory OwnerPersonSite.fromJson(Map<String, dynamic> json) =>
      OwnerPersonSite(id: '${json['site_id']}', name: '${json['site_name']}');
}

class OwnerPerson {
  const OwnerPerson({
    required this.userId,
    required this.membershipId,
    required this.phone,
    required this.displayName,
    required this.role,
    required this.status,
    required this.sites,
    required this.hasActiveAssignment,
    required this.hasActiveDuty,
    required this.currentAssetId,
    required this.currentAssetCode,
    required this.currentSiteId,
    required this.currentSiteName,
  });

  final String userId;
  final String membershipId;
  final String phone;
  final String displayName;
  final String role;
  final String status;
  final List<OwnerPersonSite> sites;
  final bool hasActiveAssignment;
  final bool hasActiveDuty;
  final String? currentAssetId;
  final String? currentAssetCode;
  final String? currentSiteId;
  final String? currentSiteName;

  bool get isActive => status == 'ACTIVE';
  bool get isInvited => status == 'INVITED';
  bool get isSupervisor => role == 'SUPERVISOR';

  factory OwnerPerson.fromJson(Map<String, dynamic> json) => OwnerPerson(
    userId: '${json['user_id']}',
    membershipId: '${json['membership_id']}',
    phone: '${json['phone']}',
    displayName: '${json['display_name']}',
    role: '${json['role']}',
    status: '${json['status']}',
    sites: (json['sites'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(OwnerPersonSite.fromJson)
        .toList(),
    hasActiveAssignment: json['has_active_assignment'] == true,
    hasActiveDuty: json['has_active_duty'] == true,
    currentAssetId: json['current_asset_id'] as String?,
    currentAssetCode: json['current_asset_code'] as String?,
    currentSiteId: json['current_site_id'] as String?,
    currentSiteName: json['current_site_name'] as String?,
  );
}

class OwnerPersonInput {
  const OwnerPersonInput({
    required this.displayName,
    required this.role,
    this.phone,
  });

  final String displayName;
  final String role;
  final String? phone;

  Map<String, dynamic> toJson({bool includePhone = false}) => {
    'display_name': displayName,
    'role': role,
    if (includePhone) 'phone': phone,
  };
}

class OwnerSiteSupervisor {
  const OwnerSiteSupervisor({
    required this.accessId,
    required this.membershipId,
    required this.displayName,
  });

  final String accessId;
  final String membershipId;
  final String displayName;

  factory OwnerSiteSupervisor.fromJson(Map<String, dynamic> json) =>
      OwnerSiteSupervisor(
        accessId: '${json['access_id']}',
        membershipId: '${json['membership_id']}',
        displayName: '${json['display_name']}',
      );
}

class OwnerManagedSite {
  const OwnerManagedSite({
    required this.id,
    required this.name,
    required this.code,
    required this.locationDescription,
    required this.latitude,
    required this.longitude,
    required this.status,
    required this.supervisors,
    required this.assetCount,
  });

  final String id;
  final String name;
  final String? code;
  final String? locationDescription;
  final double? latitude;
  final double? longitude;
  final String status;
  final List<OwnerSiteSupervisor> supervisors;
  final int assetCount;

  bool get isActive => status == 'ACTIVE';

  factory OwnerManagedSite.fromJson(Map<String, dynamic> json) =>
      OwnerManagedSite(
        id: '${json['id']}',
        name: '${json['name']}',
        code: json['code'] as String?,
        locationDescription: json['location_description'] as String?,
        latitude: _number(json['latitude']),
        longitude: _number(json['longitude']),
        status: '${json['status']}',
        supervisors: (json['supervisors'] as List<dynamic>? ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(OwnerSiteSupervisor.fromJson)
            .toList(),
        assetCount: _int(json['asset_count']),
      );
}

class OwnerSiteInput {
  const OwnerSiteInput({
    required this.name,
    this.code,
    this.locationDescription,
    this.latitude,
    this.longitude,
  });

  final String name;
  final String? code;
  final String? locationDescription;
  final double? latitude;
  final double? longitude;

  Map<String, dynamic> toJson() => {
    'name': name,
    'code': code,
    'location_description': locationDescription,
    'latitude': latitude,
    'longitude': longitude,
  };
}

const reportSheetLabels = <String, String>{
  'management_dashboard': 'Management Dashboard',
  'tipper_daily': 'Tipper Daily',
  'machinery_daily': 'Machinery Daily',
  'trip_register': 'Trip Register',
  'meter_readings': 'Meter Readings',
  'diesel_register': 'Diesel Register',
  'duty_register': 'Duty Register',
  'exceptions': 'Exceptions',
};

const managementReportColumnLabels = <String, String>{
  'asset': 'Asset',
  'asset_type': 'Type',
  'site': 'Site',
  'operator': 'Driver / Operator',
  'assignment_status': 'Assignment Status',
  'duty_status': 'Duty Status',
  'trips': 'Trips',
  'distance_km': 'Distance KM',
  'machine_hours': 'Machine Hours',
  'verified_diesel_l': 'Verified Diesel L',
  'pending_status': 'Pending / Status',
};

const tipperReportColumnLabels = <String, String>{
  'asset': 'Asset',
  'site': 'Site',
  'registration': 'Registration',
  'driver': 'Driver',
  'start_km': 'Start KM',
  'end_km': 'End KM',
  'distance_km': 'Distance KM',
  'approved_trips': 'Approved Trips',
  'diesel_l': 'Diesel L',
  'duty_start': 'Duty Start',
  'duty_end': 'Duty End',
  'pending': 'Pending',
  'status': 'Status',
};

const machineryReportColumnLabels = <String, String>{
  'asset': 'Asset',
  'asset_type': 'Asset Type',
  'site': 'Site',
  'operator': 'Operator',
  'start_hmr': 'Start HMR',
  'end_hmr': 'End HMR',
  'machine_hours': 'Machine Hours',
  'diesel_l': 'Diesel L',
  'duty_start': 'Duty Start',
  'duty_end': 'Duty End',
  'pending': 'Pending',
  'status': 'Status',
};

class ReportTemplate {
  const ReportTemplate({
    required this.id,
    required this.name,
    required this.isBuiltin,
    required this.isDefault,
    required this.includedSheets,
    required this.managementDashboardColumns,
    required this.tipperDailyColumns,
    required this.machineryDailyColumns,
  });

  final String id;
  final String name;
  final bool isBuiltin;
  final bool isDefault;
  final List<String> includedSheets;
  final List<String> managementDashboardColumns;
  final List<String> tipperDailyColumns;
  final List<String> machineryDailyColumns;

  factory ReportTemplate.fromJson(Map<String, dynamic> json) => ReportTemplate(
    id: '${json['id']}',
    name: '${json['name']}',
    isBuiltin: json['is_builtin'] == true,
    isDefault: json['is_default'] == true,
    includedSheets: _strings(json['included_sheets']),
    managementDashboardColumns: _strings(json['management_dashboard_columns']),
    tipperDailyColumns: _strings(json['tipper_daily_columns']),
    machineryDailyColumns: _strings(json['machinery_daily_columns']),
  );
}

class ReportTemplateInput {
  const ReportTemplateInput({
    required this.name,
    required this.includedSheets,
    required this.managementDashboardColumns,
    required this.tipperDailyColumns,
    required this.machineryDailyColumns,
  });

  final String name;
  final List<String> includedSheets;
  final List<String> managementDashboardColumns;
  final List<String> tipperDailyColumns;
  final List<String> machineryDailyColumns;

  Map<String, dynamic> toJson() => {
    'name': name,
    'included_sheets': includedSheets,
    'management_dashboard_columns': managementDashboardColumns,
    'tipper_daily_columns': tipperDailyColumns,
    'machinery_daily_columns': machineryDailyColumns,
  };
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

List<String> _strings(Object? value) =>
    (value as List<dynamic>? ?? const []).map((item) => '$item').toList();

String? _wireDate(DateTime? value) => value?.toIso8601String().substring(0, 10);

// Kept as a named type so the evidence viewer can expose its authenticated bytes
// without ever exposing object-storage URLs to the UI.
typedef EvidenceBytes = Uint8List;
