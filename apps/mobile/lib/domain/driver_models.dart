import 'dart:convert';

enum DriverEventType { tripComplete, kmReading, diesel, emergency }

extension DriverEventTypeWire on DriverEventType {
  String get wireName => switch (this) {
    DriverEventType.tripComplete => 'TRIP_COMPLETE',
    DriverEventType.kmReading => 'KM_READING',
    DriverEventType.diesel => 'DIESEL',
    DriverEventType.emergency => 'EMERGENCY',
  };
}

enum KmReadingType { startReading, endReading }

extension KmReadingTypeWire on KmReadingType {
  String get wireName => switch (this) {
    KmReadingType.startReading => 'START_READING',
    KmReadingType.endReading => 'END_READING',
  };
}

enum EmergencyCategory {
  breakdown,
  accident,
  tyreOrVehicleProblem,
  contactSupervisor,
}

extension EmergencyCategoryWire on EmergencyCategory {
  String get wireName => switch (this) {
    EmergencyCategory.breakdown => 'BREAKDOWN',
    EmergencyCategory.accident => 'ACCIDENT',
    EmergencyCategory.tyreOrVehicleProblem => 'TYRE_OR_VEHICLE_PROBLEM',
    EmergencyCategory.contactSupervisor => 'CONTACT_SUPERVISOR',
  };

  String get label => switch (this) {
    EmergencyCategory.breakdown => 'Breakdown',
    EmergencyCategory.accident => 'Accident',
    EmergencyCategory.tyreOrVehicleProblem => 'Tyre or vehicle problem',
    EmergencyCategory.contactSupervisor => 'Contact supervisor',
  };
}

enum SyncState { pending, syncing, syncFailed, synced }

class SessionTokens {
  const SessionTokens({
    required this.accessToken,
    required this.refreshToken,
    required this.expiresIn,
    required this.membershipId,
    required this.companyId,
    required this.role,
  });

  final String accessToken;
  final String refreshToken;
  final int expiresIn;
  final String membershipId;
  final String companyId;
  final String role;

  factory SessionTokens.fromJson(Map<String, dynamic> json) {
    return SessionTokens(
      accessToken: json['access_token'] as String,
      refreshToken: json['refresh_token'] as String,
      expiresIn: json['expires_in'] as int,
      membershipId: json['membership_id'] as String,
      companyId: json['company_id'] as String,
      role: json['role'] as String,
    );
  }

  Map<String, dynamic> toJson() => {
    'access_token': accessToken,
    'refresh_token': refreshToken,
    'expires_in': expiresIn,
    'membership_id': membershipId,
    'company_id': companyId,
    'role': role,
  };
}

class MembershipOption {
  const MembershipOption({
    required this.membershipId,
    required this.companyId,
    required this.companyName,
    required this.role,
  });

  final String membershipId;
  final String companyId;
  final String companyName;
  final String role;

  factory MembershipOption.fromJson(Map<String, dynamic> json) {
    return MembershipOption(
      membershipId: json['membership_id'] as String,
      companyId: json['company_id'] as String,
      companyName: json['company_name'] as String,
      role: json['role'] as String,
    );
  }
}

class DriverAssignment {
  const DriverAssignment({
    required this.assignmentId,
    required this.tipperId,
    required this.tipperRegistrationNumber,
    required this.tipperShortName,
    required this.siteId,
    required this.siteName,
    required this.supervisorName,
  });

  final String assignmentId;
  final String tipperId;
  final String tipperRegistrationNumber;
  final String? tipperShortName;
  final String siteId;
  final String siteName;
  final String supervisorName;

  factory DriverAssignment.fromJson(Map<String, dynamic> json) {
    return DriverAssignment(
      assignmentId: json['assignment_id'] as String,
      tipperId: json['tipper_id'] as String,
      tipperRegistrationNumber: json['tipper_registration_number'] as String,
      tipperShortName: json['tipper_short_name'] as String?,
      siteId: json['site_id'] as String,
      siteName: json['site_name'] as String,
      supervisorName: json['supervisor_name'] as String,
    );
  }
}

class PendingEvent {
  const PendingEvent({
    required this.clientEventUuid,
    required this.assignmentId,
    required this.tipperId,
    required this.siteId,
    required this.supervisorName,
    required this.eventType,
    required this.deviceCreatedAt,
    required this.payload,
    required this.state,
    required this.retryCount,
    required this.createdAt,
    this.evidencePath,
    this.lastSyncError,
  });

  final String clientEventUuid;
  final String assignmentId;
  final String tipperId;
  final String siteId;
  final String supervisorName;
  final DriverEventType eventType;
  final DateTime deviceCreatedAt;
  final Map<String, dynamic> payload;
  final SyncState state;
  final int retryCount;
  final DateTime createdAt;
  final String? evidencePath;
  final String? lastSyncError;

  String get payloadJson => jsonEncode(payload);
}
