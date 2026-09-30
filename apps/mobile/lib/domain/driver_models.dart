import 'dart:convert';

enum DriverEventType { tripComplete, kmReading, hmrReading, diesel, emergency }

extension DriverEventTypeWire on DriverEventType {
  String get wireName => switch (this) {
    DriverEventType.tripComplete => 'TRIP_COMPLETE',
    DriverEventType.kmReading => 'KM_READING',
    DriverEventType.hmrReading => 'HMR_READING',
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

enum SyncState {
  pending,
  syncing,
  syncFailed,
  blockedPendingStartCorrection,
  synced,
}

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
    this.assetType = 'TIPPER',
    this.tipperAssetCode,
    required this.siteId,
    required this.siteName,
    required this.supervisorName,
    this.supervisorNames = const [],
  });

  final String assignmentId;
  final String tipperId;
  final String? tipperRegistrationNumber;
  final String? tipperShortName;
  final String? tipperAssetCode;
  final String assetType;
  final String siteId;
  final String siteName;
  final String supervisorName;
  final List<String> supervisorNames;

  factory DriverAssignment.fromJson(Map<String, dynamic> json) {
    final supervisorNames =
        (json['supervisor_names'] as List<dynamic>? ?? const [])
            .whereType<String>()
            .toList();
    final legacySupervisor = json['supervisor_name'] as String?;
    return DriverAssignment(
      assignmentId: json['assignment_id'] as String,
      tipperId: json['tipper_id'] as String,
      tipperRegistrationNumber: json['tipper_registration_number'] as String?,
      tipperShortName: json['tipper_short_name'] as String?,
      assetType: '${json['asset_type'] ?? 'TIPPER'}',
      tipperAssetCode:
          (json['asset_code'] ?? json['tipper_asset_code']) as String?,
      siteId: json['site_id'] as String,
      siteName: json['site_name'] as String,
      supervisorName: supervisorNames.isNotEmpty
          ? supervisorNames.join(', ')
          : legacySupervisor ?? 'Site supervisors',
      supervisorNames: supervisorNames,
    );
  }

  Map<String, dynamic> toJson() => {
    'assignment_id': assignmentId,
    'tipper_id': tipperId,
    'tipper_registration_number': tipperRegistrationNumber,
    'tipper_short_name': tipperShortName,
    'asset_type': assetType,
    if (tipperAssetCode != null) 'asset_code': tipperAssetCode,
    'site_id': siteId,
    'site_name': siteName,
    'supervisor_name': supervisorName,
    'supervisor_names': supervisorNames,
  };
}

class DriverAssetCapabilities {
  const DriverAssetCapabilities({
    required this.supportsTripComplete,
    required this.supportsOdometer,
    required this.supportsHourMeter,
    required this.supportsDiesel,
    required this.supportsEmergency,
    required this.supportsDutySession,
  });

  final bool supportsTripComplete;
  final bool supportsOdometer;
  final bool supportsHourMeter;
  final bool supportsDiesel;
  final bool supportsEmergency;
  final bool supportsDutySession;

  static const tipper = DriverAssetCapabilities(
    supportsTripComplete: true,
    supportsOdometer: true,
    supportsHourMeter: false,
    supportsDiesel: true,
    supportsEmergency: true,
    supportsDutySession: true,
  );
  static const machinery = DriverAssetCapabilities(
    supportsTripComplete: false,
    supportsOdometer: false,
    supportsHourMeter: true,
    supportsDiesel: true,
    supportsEmergency: true,
    supportsDutySession: true,
  );

  static DriverAssetCapabilities forType(String assetType) =>
      assetType == 'TIPPER' ? tipper : machinery;
}

extension DriverAssignmentCapabilities on DriverAssignment {
  DriverAssetCapabilities get capabilities =>
      DriverAssetCapabilities.forType(assetType);
}

enum DriverAssignmentAuthority {
  serverAssignment,
  serverNoAssignment,
  offlineCache,
  protectedLocalWork,
}

class DriverStateReconciliation {
  const DriverStateReconciliation({
    required this.assignment,
    required this.duty,
    required this.authority,
    this.warning,
  });

  final DriverAssignment? assignment;
  final DriverDutyState duty;
  final DriverAssignmentAuthority authority;
  final String? warning;
}

enum DriverDutyStatus { none, active, closed }

enum LocalDutyState {
  startPendingSync,
  activeConfirmed,
  endPendingSync,
  closedConfirmed,
  needsAttention,
}

class DriverDutyState {
  const DriverDutyState({
    required this.status,
    this.localState,
    this.sessionId,
    this.assignmentId,
    this.tipperId,
    this.siteId,
    this.startedAt,
    this.startKm,
    this.endedAt,
    this.endKm,
    this.startHmr,
    this.endHmr,
    this.regularDutyMinutes,
  });

  const DriverDutyState.none() : this(status: DriverDutyStatus.none);

  final DriverDutyStatus status;
  final LocalDutyState? localState;
  final String? sessionId;
  final String? assignmentId;
  final String? tipperId;
  final String? siteId;
  final DateTime? startedAt;
  final double? startKm;
  final DateTime? endedAt;
  final double? endKm;
  final double? startHmr;
  final double? endHmr;
  final int? regularDutyMinutes;

  bool get isActive => status == DriverDutyStatus.active;
  bool get isOperationallyActive => switch (localState) {
    LocalDutyState.startPendingSync ||
    LocalDutyState.activeConfirmed ||
    LocalDutyState.needsAttention => endedAt == null,
    LocalDutyState.endPendingSync || LocalDutyState.closedConfirmed => false,
    null => isActive,
  };
  bool get canStart => switch (localState) {
    LocalDutyState.closedConfirmed => true,
    LocalDutyState.startPendingSync ||
    LocalDutyState.activeConfirmed ||
    LocalDutyState.endPendingSync ||
    LocalDutyState.needsAttention => false,
    null =>
      status == DriverDutyStatus.none || status == DriverDutyStatus.closed,
  };
  bool get canEnd => switch (localState) {
    LocalDutyState.startPendingSync ||
    LocalDutyState.activeConfirmed ||
    LocalDutyState.needsAttention => endedAt == null,
    LocalDutyState.endPendingSync || LocalDutyState.closedConfirmed => false,
    null => isActive,
  };
  bool get canCorrectStart => localState == LocalDutyState.needsAttention;
  bool get canReadKm => canStart || canEnd || canCorrectStart;

  factory DriverDutyState.fromJson(Map<String, dynamic> json) {
    final status = switch (json['status'] as String? ?? 'NONE') {
      'ACTIVE' => DriverDutyStatus.active,
      'CLOSED' => DriverDutyStatus.closed,
      _ => DriverDutyStatus.none,
    };
    return DriverDutyState(
      status: status,
      sessionId: json['session_id'] as String?,
      assignmentId: json['assignment_id'] as String?,
      tipperId: json['tipper_id'] as String?,
      siteId: json['site_id'] as String?,
      startedAt: _parseDateTime(json['started_at']),
      startKm: _parseDouble(json['start_km']),
      endedAt: _parseDateTime(json['ended_at']),
      endKm: _parseDouble(json['end_km']),
      startHmr: _parseDouble(json['start_hmr']),
      endHmr: _parseDouble(json['end_hmr']),
      regularDutyMinutes: json['regular_duty_minutes'] as int?,
    );
  }
}

DateTime? _parseDateTime(Object? value) =>
    value is String ? DateTime.tryParse(value) : null;

double? _parseDouble(Object? value) => switch (value) {
  num number => number.toDouble(),
  String text => double.tryParse(text),
  _ => null,
};

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
    this.dutySessionId,
    this.dependsOnEventUuid,
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
  final String? dutySessionId;
  final String? dependsOnEventUuid;

  String get payloadJson => jsonEncode(payload);
}
