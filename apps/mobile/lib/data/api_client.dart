import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:path/path.dart' as path;

import '../domain/driver_models.dart';
import '../domain/role_models.dart';

const String _configuredApiBaseUrl = String.fromEnvironment(
  'FLEET_API_BASE_URL',
);
final String defaultApiBaseUrl = isPilotBuild
    ? (_configuredApiBaseUrl.isEmpty
          ? 'http://127.0.0.1:8000'
          : _configuredApiBaseUrl)
    : (_configuredApiBaseUrl.isEmpty
          ? 'https://api.fleetmanager.example'
          : _configuredApiBaseUrl);

const String sessionExpiredMessage =
    'Your session has expired. Please sign in again.';

typedef SessionTokensPersistor = Future<void> Function(SessionTokens tokens);
typedef SessionExpiredHandler = Future<void> Function();

abstract class DriverRemoteApi {
  Future<DeviceRegistration> registerDevice({
    required String installationIdentifier,
    bool allowHandover = false,
    bool localStateClear = false,
  });

  Future<String> uploadEvidence({
    required String clientEventUuid,
    required String evidencePath,
  });

  Future<void> submitEvent({
    required PendingEvent event,
    required String installationIdentifier,
  });
}

abstract class DriverMaintenanceRemote {
  Future<void> submitMaintenanceProof({required PendingEvent event});
}

class DeviceRegistration {
  const DeviceRegistration({
    required this.deviceId,
    required this.membershipId,
    required this.handedOver,
  });

  final String deviceId;
  final String membershipId;
  final bool handedOver;

  factory DeviceRegistration.fromJson(Map<String, dynamic> json) =>
      DeviceRegistration(
        deviceId: json['device_id'] as String,
        membershipId: json['membership_id'] as String,
        handedOver: json['handed_over'] as bool? ?? false,
      );
}

abstract class DriverDutyLookup {
  Future<DriverDutyState> currentDuty();
}

abstract class DriverStateLookup implements DriverDutyLookup {
  Future<DriverAssignment?> currentAssignment();
}

abstract class OwnerAssetApi {
  Future<List<OwnerAsset>> ownerAssets({
    String? status,
    String? ownershipType,
    String? assetType,
  });

  Future<OwnerAsset> ownerAsset(String assetId);

  Future<OwnerAsset> createOwnerAsset(OwnerAssetInput input);

  Future<OwnerAsset> updateOwnerAsset(String assetId, OwnerAssetInput input);

  Future<OwnerAsset> deactivateOwnerAsset(String assetId);

  Future<OwnerAsset> reactivateOwnerAsset(String assetId);

  Future<List<OwnerManagedSite>> ownerDeploymentSites();

  Future<List<SiteDeployedAsset>> ownerSiteAssets(String siteId);

  Future<AssetSiteDeployment> deployOwnerAsset(String assetId, String siteId);

  Future<AssetSiteDeployment> removeOwnerAssetDeployment(String assetId);
}

abstract class OwnerPeopleSiteApi {
  Future<List<OwnerPerson>> ownerPeople();
  Future<OwnerPerson> inviteOwnerPerson(OwnerPersonInput input);
  Future<OwnerPerson> updateOwnerPerson(
    String membershipId,
    OwnerPersonInput input,
  );
  Future<OwnerPerson> setOwnerPersonActive(String membershipId, bool active);
  Future<List<OwnerManagedSite>> ownerSites();
  Future<OwnerManagedSite> createOwnerSite(OwnerSiteInput input);
  Future<OwnerManagedSite> updateOwnerSite(String siteId, OwnerSiteInput input);
  Future<OwnerManagedSite> setOwnerSiteActive(String siteId, bool active);
  Future<OwnerManagedSite> grantOwnerSiteSupervisor(
    String siteId,
    String membershipId,
  );
  Future<OwnerManagedSite> revokeOwnerSiteSupervisor(
    String siteId,
    String membershipId,
  );
}

abstract class OwnerReportTemplateApi {
  Future<List<ReportTemplate>> reportTemplates();
  Future<ReportTemplate> createReportTemplate(ReportTemplateInput input);
  Future<ReportTemplate> updateReportTemplate(
    String templateId,
    ReportTemplateInput input,
  );
  Future<ReportTemplate> duplicateReportTemplate(
    String templateId,
    String name,
  );
  Future<ReportTemplate> setDefaultReportTemplate(String templateId);
  Future<void> deleteReportTemplate(String templateId);
}

abstract class DriverAssignmentApi {
  Future<List<DriverCandidate>> eligibleDrivers(
    String assetId, {
    String? supervisorSiteId,
  });
  Future<DriverAssetAssignment> assignDriver(
    String assetId,
    String driverMembershipId, {
    String? supervisorSiteId,
    bool reassign = false,
  });
  Future<DriverAssetAssignment> unassignDriver(
    String assetId, {
    String? supervisorSiteId,
  });
}

class ApiException implements Exception {
  const ApiException(this.statusCode, this.message, {this.code, this.context});

  final int statusCode;
  final String message;
  final String? code;
  final Map<String, dynamic>? context;

  bool get isUnauthorized => statusCode == 401;
  bool get isRetryable =>
      statusCode == 408 || statusCode == 429 || statusCode >= 500;

  ApiException atSyncStage(String stage) => ApiException(
    statusCode,
    message,
    code: code,
    context: <String, dynamic>{...?context, 'sync_stage': stage},
  );

  @override
  String toString() => 'ApiException($statusCode): $message';
}

class ApiClient
    implements
        DriverRemoteApi,
        DriverMaintenanceRemote,
        DriverStateLookup,
        OwnerAssetApi,
        OwnerPeopleSiteApi,
        OwnerReportTemplateApi,
        DriverAssignmentApi {
  ApiClient({
    String? baseUrl,
    http.Client? client,
    SessionTokensPersistor? persistSession,
  }) : _baseUrl = (baseUrl ?? defaultApiBaseUrl).replaceFirst(
         RegExp(r'/$'),
         '',
       ),
       _client = client ?? http.Client(),
       _persistSession = persistSession;

  String _baseUrl;
  final http.Client _client;
  final SessionTokensPersistor? _persistSession;
  SessionTokens? _tokens;
  Future<SessionTokens>? _refreshInFlight;
  Future<void>? _expirationInFlight;
  SessionExpiredHandler? _sessionExpiredHandler;

  void setSession(SessionTokens tokens) => _tokens = tokens;

  SessionTokens? get session => _tokens;

  void setSessionExpiredHandler(SessionExpiredHandler? handler) {
    _sessionExpiredHandler = handler;
  }

  String get baseUrl => _baseUrl;

  void setBaseUrl(String value) {
    final normalized = value.trim().replaceFirst(RegExp(r'/$'), '');
    if (normalized.isEmpty) throw const FormatException('Server URL is empty');
    final parsed = Uri.tryParse(normalized);
    if (parsed == null || !parsed.hasScheme || parsed.host.isEmpty) {
      throw const FormatException(
        'Enter a full server URL, for example http://192.168.1.20:8000',
      );
    }
    _baseUrl = normalized;
  }

  Future<bool> testConnection() async {
    try {
      final response = await _client.get(_uri('/health'));
      return response.statusCode >= 200 && response.statusCode < 300;
    } on SocketException {
      return false;
    } on Object {
      return false;
    }
  }

  void clearSession() => _tokens = null;

  Future<String> requestOtp(String phone, {String? requestedRole}) async {
    final body = await _post('/api/v1/auth/otp/request', {
      'phone': phone,
      if (requestedRole != null) 'requested_role': requestedRole,
    });
    return body['challenge_id'] as String;
  }

  Future<String> verifyOtp({
    required String challengeId,
    required String otp,
  }) async {
    final body = await _post('/api/v1/auth/otp/verify', {
      'challenge_id': challengeId,
      'otp': otp,
    });
    return body['pre_session_token'] as String;
  }

  Future<List<MembershipOption>> memberships(String preSessionToken) async {
    final body = await _post('/api/v1/auth/memberships', {
      'pre_session_token': preSessionToken,
    });
    return (body['memberships'] as List<dynamic>)
        .map((item) => MembershipOption.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<SessionTokens> createSession({
    required String preSessionToken,
    required String membershipId,
  }) async {
    final body = await _post('/api/v1/auth/session', {
      'pre_session_token': preSessionToken,
      'membership_id': membershipId,
    });
    final tokens = SessionTokens.fromJson(body);
    setSession(tokens);
    return tokens;
  }

  Future<SessionTokens> refreshSession() async {
    final activeRefresh = _refreshInFlight;
    if (activeRefresh != null) return activeRefresh;

    final refresh = _performSessionRefresh();
    _refreshInFlight = refresh;
    try {
      return await refresh;
    } finally {
      if (identical(_refreshInFlight, refresh)) _refreshInFlight = null;
    }
  }

  Future<SessionTokens> _performSessionRefresh() async {
    final refreshToken = _tokens?.refreshToken;
    if (refreshToken == null) {
      await _expireSession();
      throw const ApiException(401, sessionExpiredMessage);
    }
    late final Map<String, dynamic> body;
    try {
      body = await _post('/api/v1/auth/refresh', {
        'refresh_token': refreshToken,
      });
    } on ApiException catch (error) {
      if (!error.isUnauthorized) rethrow;
      await _expireSession();
      throw const ApiException(401, sessionExpiredMessage);
    }
    final tokens = SessionTokens.fromJson(body);
    setSession(tokens);
    await _persistSession?.call(tokens);
    return tokens;
  }

  Future<void> logout() async {
    if (_tokens == null) return;
    await _request('POST', '/api/v1/auth/logout', authenticated: true);
    clearSession();
  }

  Future<void> validateSession() async {
    await _request('GET', '/api/v1/auth/me', authenticated: true);
  }

  Future<String> currentDisplayName() async {
    final response = await _request(
      'GET',
      '/api/v1/auth/me',
      authenticated: true,
    );
    return '${_json(response)['display_name'] ?? 'Supervisor'}';
  }

  @override
  Future<DriverAssignment?> currentAssignment() async {
    final response = await _request(
      'GET',
      '/api/v1/driver/assignment/current',
      authenticated: true,
    );
    if (response.statusCode == 204 || response.body == 'null') return null;
    return DriverAssignment.fromJson(_json(response));
  }

  @override
  Future<DriverDutyState> currentDuty() async {
    final response = await _request(
      'GET',
      '/api/v1/driver/duty/current',
      authenticated: true,
    );
    return DriverDutyState.fromJson(_json(response));
  }

  Future<List<DriverMaintenanceItem>> driverDueMaintenance() async {
    final response = await _request(
      'GET',
      '/api/v1/driver/maintenance/due',
      authenticated: true,
    );
    return _jsonList(response).map(DriverMaintenanceItem.fromJson).toList();
  }

  Future<List<SupervisorSite>> supervisorSites() async {
    final response = await _request(
      'GET',
      '/api/v1/supervisor/sites',
      authenticated: true,
    );
    return (_jsonList(response)).map(SupervisorSite.fromJson).toList();
  }

  Future<List<SupervisorEvent>> supervisorEvents(
    String siteId, {
    String? verificationStatus,
    DateTime? reviewDate,
  }) async {
    final query = <String, String>{
      if (verificationStatus != null) 'verification_status': verificationStatus,
      if (reviewDate != null) 'review_date': _dateParam(reviewDate),
      'limit': '200',
    };
    final suffix = query.isEmpty
        ? ''
        : '?${query.entries.map((e) => '${Uri.encodeQueryComponent(e.key)}=${Uri.encodeQueryComponent(e.value)}').join('&')}';
    final response = await _request(
      'GET',
      '/api/v1/supervisor/sites/$siteId/events$suffix',
      authenticated: true,
    );
    return _jsonList(response).map(SupervisorEvent.fromJson).toList();
  }

  Future<List<MaintenanceProof>> supervisorMaintenanceProofs({
    String? siteId,
  }) async {
    final suffix = siteId == null
        ? ''
        : '?site_id=${Uri.encodeQueryComponent(siteId)}';
    final response = await _request(
      'GET',
      '/api/v1/supervisor/maintenance/proofs$suffix',
      authenticated: true,
    );
    return _jsonList(response).map(MaintenanceProof.fromJson).toList();
  }

  Future<MaintenanceProof> reviewMaintenanceProof(
    String submissionId, {
    required String decision,
    String? reason,
  }) async {
    final response = await _request(
      'POST',
      '/api/v1/supervisor/maintenance/proofs/$submissionId/review',
      authenticated: true,
      body: {'decision': decision, if (reason != null) 'reason': reason},
    );
    return MaintenanceProof.fromJson(_json(response));
  }

  Future<Uint8List> maintenanceProofEvidenceBytes(
    String submissionId,
    String evidenceId,
  ) async {
    final response = await _request(
      'GET',
      '/api/v1/supervisor/maintenance/proofs/$submissionId/evidence/$evidenceId',
      authenticated: true,
    );
    return response.bodyBytes;
  }

  Future<List<CompletenessItem>> supervisorCompleteness(
    String siteId, {
    DateTime? reviewDate,
  }) async {
    final date = _dateParam(reviewDate ?? DateTime.now());
    final response = await _request(
      'GET',
      '/api/v1/supervisor/sites/$siteId/completeness?review_date=$date',
      authenticated: true,
    );
    return _jsonList(response).map(CompletenessItem.fromJson).toList();
  }

  Future<SupervisorEvent> verifySupervisorEvent(
    String eventId, {
    required String decision,
    String? reason,
  }) async {
    final response = await _request(
      'POST',
      '/api/v1/supervisor/events/$eventId/verify',
      authenticated: true,
      body: {
        'decision': decision,
        if (reason != null && reason.trim().isNotEmpty) 'reason': reason.trim(),
        'expected_status': 'PENDING_VERIFICATION',
      },
    );
    return SupervisorEvent.fromJson(_json(response));
  }

  Future<SupervisorEvent> acknowledgeEmergency(String eventId) async =>
      _supervisorEmergencyAction(eventId, 'acknowledge');

  Future<SupervisorEvent> resolveEmergency(String eventId) async =>
      _supervisorEmergencyAction(eventId, 'resolve');

  Future<SupervisorEvent> _supervisorEmergencyAction(
    String eventId,
    String action,
  ) async {
    final response = await _request(
      'POST',
      '/api/v1/supervisor/events/$eventId/emergency/$action',
      authenticated: true,
    );
    return SupervisorEvent.fromJson(_json(response));
  }

  Future<OwnerDashboard> ownerDashboard({DateTime? date}) async {
    final suffix = date == null ? '' : '?operational_date=${_dateParam(date)}';
    final response = await _request(
      'GET',
      '/api/v1/reports/dashboard$suffix',
      authenticated: true,
    );
    return OwnerDashboard.fromJson(_json(response));
  }

  Future<List<OwnerDutyReport>> ownerDuty({DateTime? date}) async {
    final suffix = date == null ? '' : '?operational_date=${_dateParam(date)}';
    final response = await _request(
      'GET',
      '/api/v1/reports/duty$suffix',
      authenticated: true,
    );
    return _jsonList(response).map(OwnerDutyReport.fromJson).toList();
  }

  Future<List<OwnerTipperReport>> ownerTipperDaily(
    String tipperId, {
    DateTime? date,
  }) async {
    final suffix = date == null ? '' : '?operational_date=${_dateParam(date)}';
    final response = await _request(
      'GET',
      '/api/v1/reports/tippers/$tipperId/daily$suffix',
      authenticated: true,
    );
    return _jsonList(response).map(OwnerTipperReport.fromJson).toList();
  }

  Future<List<OwnerTipperReport>> ownerSiteDaily(
    String siteId, {
    DateTime? date,
  }) async {
    final suffix = date == null ? '' : '?operational_date=${_dateParam(date)}';
    final response = await _request(
      'GET',
      '/api/v1/reports/sites/$siteId/daily$suffix',
      authenticated: true,
    );
    final body = _json(response);
    final tippers = body['tippers'];
    if (tippers is! List) return const [];
    return tippers
        .whereType<Map<String, dynamic>>()
        .map(OwnerTipperReport.fromJson)
        .toList();
  }

  @override
  Future<List<OwnerAsset>> ownerAssets({
    String? status,
    String? ownershipType,
    String? assetType,
  }) async {
    final query = <String, String>{
      if (assetType != null) 'asset_type': assetType,
      if (status != null) 'status': status,
      if (ownershipType != null) 'ownership_type': ownershipType,
    };
    final suffix =
        '?${query.entries.map((entry) => '${Uri.encodeQueryComponent(entry.key)}=${Uri.encodeQueryComponent(entry.value)}').join('&')}';
    final response = await _request(
      'GET',
      '/api/v1/owner/assets$suffix',
      authenticated: true,
    );
    return _jsonList(response).map(OwnerAsset.fromJson).toList();
  }

  @override
  Future<OwnerAsset> ownerAsset(String assetId) async {
    final response = await _request(
      'GET',
      '/api/v1/owner/assets/$assetId',
      authenticated: true,
    );
    return OwnerAsset.fromJson(_json(response));
  }

  @override
  Future<OwnerAsset> createOwnerAsset(OwnerAssetInput input) async {
    final response = await _request(
      'POST',
      '/api/v1/owner/assets',
      authenticated: true,
      body: input.toJson(includeAssetType: true),
    );
    return OwnerAsset.fromJson(_json(response));
  }

  @override
  Future<OwnerAsset> updateOwnerAsset(
    String assetId,
    OwnerAssetInput input,
  ) async {
    final response = await _request(
      'PATCH',
      '/api/v1/owner/assets/$assetId',
      authenticated: true,
      body: input.toJson(),
    );
    return OwnerAsset.fromJson(_json(response));
  }

  @override
  Future<OwnerAsset> deactivateOwnerAsset(String assetId) async {
    final response = await _request(
      'POST',
      '/api/v1/owner/assets/$assetId/deactivate',
      authenticated: true,
    );
    return OwnerAsset.fromJson(_json(response));
  }

  @override
  Future<OwnerAsset> reactivateOwnerAsset(String assetId) async {
    final response = await _request(
      'POST',
      '/api/v1/owner/assets/$assetId/reactivate',
      authenticated: true,
    );
    return OwnerAsset.fromJson(_json(response));
  }

  @override
  Future<List<OwnerManagedSite>> ownerDeploymentSites() => ownerSites();

  @override
  Future<List<SiteDeployedAsset>> ownerSiteAssets(String siteId) async {
    final response = await _request(
      'GET',
      '/api/v1/owner/sites/$siteId/assets',
      authenticated: true,
    );
    return _jsonList(response).map(SiteDeployedAsset.fromJson).toList();
  }

  @override
  Future<AssetSiteDeployment> deployOwnerAsset(
    String assetId,
    String siteId,
  ) async {
    final response = await _request(
      'POST',
      '/api/v1/owner/assets/$assetId/deployment',
      authenticated: true,
      body: {'site_id': siteId},
    );
    return AssetSiteDeployment.fromJson(_json(response));
  }

  @override
  Future<AssetSiteDeployment> removeOwnerAssetDeployment(String assetId) async {
    final response = await _request(
      'DELETE',
      '/api/v1/owner/assets/$assetId/deployment',
      authenticated: true,
    );
    return AssetSiteDeployment.fromJson(_json(response));
  }

  Future<List<SiteDeployedAsset>> supervisorSiteAssets(String siteId) async {
    final response = await _request(
      'GET',
      '/api/v1/supervisor/sites/$siteId/assets',
      authenticated: true,
    );
    return _jsonList(response).map(SiteDeployedAsset.fromJson).toList();
  }

  @override
  Future<List<DriverCandidate>> eligibleDrivers(
    String assetId, {
    String? supervisorSiteId,
  }) async {
    final prefix = supervisorSiteId == null
        ? '/api/v1/owner/assets/$assetId'
        : '/api/v1/supervisor/sites/$supervisorSiteId/assets/$assetId';
    final response = await _request(
      'GET',
      '$prefix/eligible-drivers',
      authenticated: true,
    );
    return _jsonList(response).map(DriverCandidate.fromJson).toList();
  }

  @override
  Future<DriverAssetAssignment> assignDriver(
    String assetId,
    String driverMembershipId, {
    String? supervisorSiteId,
    bool reassign = false,
  }) async {
    final prefix = supervisorSiteId == null
        ? '/api/v1/owner/assets/$assetId'
        : '/api/v1/supervisor/sites/$supervisorSiteId/assets/$assetId';
    final response = await _request(
      'POST',
      '$prefix/assignment${reassign ? '/reassign' : ''}',
      authenticated: true,
      body: {'driver_membership_id': driverMembershipId},
    );
    return DriverAssetAssignment.fromJson(_json(response));
  }

  @override
  Future<DriverAssetAssignment> unassignDriver(
    String assetId, {
    String? supervisorSiteId,
  }) async {
    final prefix = supervisorSiteId == null
        ? '/api/v1/owner/assets/$assetId'
        : '/api/v1/supervisor/sites/$supervisorSiteId/assets/$assetId';
    final response = await _request(
      'DELETE',
      '$prefix/assignment',
      authenticated: true,
    );
    return DriverAssetAssignment.fromJson(_json(response));
  }

  @override
  Future<List<OwnerPerson>> ownerPeople() async {
    final response = await _request(
      'GET',
      '/api/v1/owner/people',
      authenticated: true,
    );
    return _jsonList(response).map(OwnerPerson.fromJson).toList();
  }

  @override
  Future<OwnerPerson> inviteOwnerPerson(OwnerPersonInput input) async {
    final response = await _request(
      'POST',
      '/api/v1/owner/people/invite',
      authenticated: true,
      body: input.toJson(includePhone: true),
    );
    return OwnerPerson.fromJson(_json(response));
  }

  @override
  Future<OwnerPerson> updateOwnerPerson(
    String membershipId,
    OwnerPersonInput input,
  ) async {
    final response = await _request(
      'PATCH',
      '/api/v1/owner/people/$membershipId',
      authenticated: true,
      body: input.toJson(),
    );
    return OwnerPerson.fromJson(_json(response));
  }

  @override
  Future<OwnerPerson> setOwnerPersonActive(
    String membershipId,
    bool active,
  ) async {
    final action = active ? 'reactivate' : 'deactivate';
    final response = await _request(
      'POST',
      '/api/v1/owner/people/$membershipId/$action',
      authenticated: true,
    );
    return OwnerPerson.fromJson(_json(response));
  }

  @override
  Future<List<OwnerManagedSite>> ownerSites() async {
    final response = await _request(
      'GET',
      '/api/v1/owner/sites',
      authenticated: true,
    );
    return _jsonList(response).map(OwnerManagedSite.fromJson).toList();
  }

  @override
  Future<OwnerManagedSite> createOwnerSite(OwnerSiteInput input) async {
    final response = await _request(
      'POST',
      '/api/v1/owner/sites',
      authenticated: true,
      body: input.toJson(),
    );
    return OwnerManagedSite.fromJson(_json(response));
  }

  @override
  Future<OwnerManagedSite> updateOwnerSite(
    String siteId,
    OwnerSiteInput input,
  ) async {
    final response = await _request(
      'PATCH',
      '/api/v1/owner/sites/$siteId',
      authenticated: true,
      body: input.toJson(),
    );
    return OwnerManagedSite.fromJson(_json(response));
  }

  @override
  Future<OwnerManagedSite> setOwnerSiteActive(
    String siteId,
    bool active,
  ) async {
    final action = active ? 'reactivate' : 'deactivate';
    final response = await _request(
      'POST',
      '/api/v1/owner/sites/$siteId/$action',
      authenticated: true,
    );
    return OwnerManagedSite.fromJson(_json(response));
  }

  @override
  Future<OwnerManagedSite> grantOwnerSiteSupervisor(
    String siteId,
    String membershipId,
  ) async {
    final response = await _request(
      'POST',
      '/api/v1/owner/sites/$siteId/supervisors',
      authenticated: true,
      body: {'supervisor_membership_id': membershipId},
    );
    return OwnerManagedSite.fromJson(_json(response));
  }

  @override
  Future<OwnerManagedSite> revokeOwnerSiteSupervisor(
    String siteId,
    String membershipId,
  ) async {
    final response = await _request(
      'DELETE',
      '/api/v1/owner/sites/$siteId/supervisors/$membershipId',
      authenticated: true,
    );
    return OwnerManagedSite.fromJson(_json(response));
  }

  @override
  Future<List<ReportTemplate>> reportTemplates() async {
    final response = await _request(
      'GET',
      '/api/v1/owner/report-templates',
      authenticated: true,
    );
    return _jsonList(response).map(ReportTemplate.fromJson).toList();
  }

  @override
  Future<ReportTemplate> createReportTemplate(ReportTemplateInput input) async {
    final response = await _request(
      'POST',
      '/api/v1/owner/report-templates',
      authenticated: true,
      body: input.toJson(),
    );
    return ReportTemplate.fromJson(_json(response));
  }

  @override
  Future<ReportTemplate> updateReportTemplate(
    String templateId,
    ReportTemplateInput input,
  ) async {
    final response = await _request(
      'PATCH',
      '/api/v1/owner/report-templates/$templateId',
      authenticated: true,
      body: input.toJson(),
    );
    return ReportTemplate.fromJson(_json(response));
  }

  @override
  Future<ReportTemplate> duplicateReportTemplate(
    String templateId,
    String name,
  ) async {
    final response = await _request(
      'POST',
      '/api/v1/owner/report-templates/$templateId/duplicate',
      authenticated: true,
      body: {'name': name},
    );
    return ReportTemplate.fromJson(_json(response));
  }

  @override
  Future<ReportTemplate> setDefaultReportTemplate(String templateId) async {
    final response = await _request(
      'POST',
      '/api/v1/owner/report-templates/$templateId/default',
      authenticated: true,
    );
    return ReportTemplate.fromJson(_json(response));
  }

  @override
  Future<void> deleteReportTemplate(String templateId) async {
    await _request(
      'DELETE',
      '/api/v1/owner/report-templates/$templateId',
      authenticated: true,
    );
  }

  Future<Uint8List> evidenceBytes(
    String eventId, {
    required String role,
  }) async {
    final path = role == 'SUPERVISOR'
        ? '/api/v1/supervisor/events/$eventId/evidence'
        : '/api/v1/reports/events/$eventId/evidence';
    final response = await _request('GET', path, authenticated: true);
    return response.bodyBytes;
  }

  Future<Uint8List> dailyExcel({DateTime? date, String? templateId}) async {
    final query = <String, String>{
      if (date != null) 'operational_date': _dateParam(date),
      if (templateId != null) 'template_id': templateId,
    };
    final suffix = query.isEmpty
        ? ''
        : '?${query.entries.map((entry) => '${Uri.encodeQueryComponent(entry.key)}=${Uri.encodeQueryComponent(entry.value)}').join('&')}';
    final response = await _request(
      'GET',
      '/api/v1/reports/daily.xlsx$suffix',
      authenticated: true,
    );
    return response.bodyBytes;
  }

  @override
  Future<DeviceRegistration> registerDevice({
    required String installationIdentifier,
    bool allowHandover = false,
    bool localStateClear = false,
  }) async {
    final response = await _request(
      'POST',
      '/api/v1/driver/device',
      authenticated: true,
      body: {
        'installation_identifier': installationIdentifier,
        'platform': 'ANDROID',
        'allow_handover': allowHandover,
        'local_state_clear': localStateClear,
      },
    );
    return DeviceRegistration.fromJson(_json(response));
  }

  @override
  Future<String> uploadEvidence({
    required String clientEventUuid,
    required String evidencePath,
  }) => _uploadEvidence(
    clientEventUuid: clientEventUuid,
    evidencePath: evidencePath,
    retryAfterRefresh: true,
  );

  Future<String> _uploadEvidence({
    required String clientEventUuid,
    required String evidencePath,
    required bool retryAfterRefresh,
  }) async {
    final token = _tokens?.accessToken;
    if (token == null) {
      await _expireSession();
      throw const ApiException(401, sessionExpiredMessage);
    }
    final mimeType = await evidenceMimeTypeForPath(evidencePath);
    final request =
        http.MultipartRequest(
            'POST',
            _uri('/api/v1/driver/evidence?client_event_uuid=$clientEventUuid'),
          )
          ..headers['Authorization'] = 'Bearer $token'
          ..files.add(
            await http.MultipartFile.fromPath(
              'file',
              evidencePath,
              contentType: MediaType.parse(mimeType),
            ),
          );
    late final http.Response materialized;
    try {
      final response = await _client.send(request);
      materialized = await http.Response.fromStream(response);
    } on SocketException catch (error) {
      throw ApiException(503, error.message);
    }
    if (materialized.statusCode == 401) {
      if (retryAfterRefresh) {
        if (_tokens?.accessToken == token) await refreshSession();
        return _uploadEvidence(
          clientEventUuid: clientEventUuid,
          evidencePath: evidencePath,
          retryAfterRefresh: false,
        );
      }
      await _expireSession();
      throw const ApiException(401, sessionExpiredMessage);
    }
    _check(materialized);
    return (_json(materialized))['object_reference'] as String;
  }

  @override
  Future<void> submitEvent({
    required PendingEvent event,
    required String installationIdentifier,
  }) async {
    final meterCapture = event.eventType == DriverEventType.meterCapture;
    final payload = <String, dynamic>{
      if (meterCapture)
        'capture_group_uuid': event.clientEventUuid
      else ...{
        'client_event_uuid': event.clientEventUuid,
        'event_type': event.eventType.wireName,
      },
      'device_created_at': event.deviceCreatedAt.toUtc().toIso8601String(),
      'installation_identifier': installationIdentifier,
      'platform': 'ANDROID',
      ...event.payload,
    };
    await _request(
      'POST',
      meterCapture ? '/api/v1/driver/meter-captures' : '/api/v1/driver/events',
      authenticated: true,
      body: payload,
    );
  }

  @override
  Future<void> submitMaintenanceProof({required PendingEvent event}) async {
    await _request(
      'POST',
      '/api/v1/driver/maintenance/proofs',
      authenticated: true,
      body: {
        'client_submission_uuid': event.clientEventUuid,
        'schedule_id': event.payload['schedule_id'],
        'evidence_object_references': [event.payload['object_reference']],
        if (event.payload['note'] != null) 'note': event.payload['note'],
      },
    );
  }

  Future<Map<String, dynamic>> _post(
    String path,
    Map<String, dynamic> body,
  ) async {
    final response = await _request('POST', path, body: body);
    return _json(response);
  }

  Future<http.Response> _request(
    String method,
    String path, {
    Map<String, dynamic>? body,
    bool authenticated = false,
    bool retryAfterRefresh = true,
  }) async {
    final headers = <String, String>{'Content-Type': 'application/json'};
    String? requestAccessToken;
    if (authenticated) {
      final token = _tokens?.accessToken;
      if (token == null) {
        await _expireSession();
        throw const ApiException(401, sessionExpiredMessage);
      }
      requestAccessToken = token;
      headers['Authorization'] = 'Bearer $token';
    }
    final encoded = body == null ? null : jsonEncode(body);
    try {
      final request = http.Request(method, _uri(path))
        ..headers.addAll(headers)
        ..body = encoded ?? '';
      final streamed = await _client.send(request);
      final response = await http.Response.fromStream(streamed);
      if (authenticated && response.statusCode == 401) {
        if (retryAfterRefresh) {
          if (_tokens?.accessToken == requestAccessToken) {
            await refreshSession();
          }
          return await _request(
            method,
            path,
            body: body,
            authenticated: true,
            retryAfterRefresh: false,
          );
        }
        await _expireSession();
        throw const ApiException(401, sessionExpiredMessage);
      }
      _check(response);
      return response;
    } on SocketException catch (error) {
      throw ApiException(503, error.message);
    }
  }

  Future<void> _expireSession() async {
    clearSession();
    final activeExpiration = _expirationInFlight;
    if (activeExpiration != null) return activeExpiration;

    final expiration = _notifySessionExpired();
    _expirationInFlight = expiration;
    try {
      await expiration;
    } finally {
      if (identical(_expirationInFlight, expiration)) {
        _expirationInFlight = null;
      }
    }
  }

  Future<void> _notifySessionExpired() async {
    await _sessionExpiredHandler?.call();
  }

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  static Map<String, dynamic> _json(http.Response response) {
    if (response.body.isEmpty) return <String, dynamic>{};
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  static List<Map<String, dynamic>> _jsonList(http.Response response) {
    if (response.body.isEmpty) return const [];
    final decoded = jsonDecode(response.body);
    if (decoded is! List) return const [];
    return decoded.whereType<Map<String, dynamic>>().toList();
  }

  static String _dateParam(DateTime date) =>
      date.toIso8601String().substring(0, 10);

  static void _check(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) return;
    var message = 'Request failed';
    Map<String, dynamic>? structured;
    try {
      final body = _json(response);
      final detail = body['detail'];
      if (detail is Map<String, dynamic> && detail['message'] is String) {
        structured = detail;
        message = detail['message'] as String;
      } else if (detail is String) {
        message = detail;
      }
    } on Object {
      message = 'Request failed';
    }
    throw ApiException(
      response.statusCode,
      message,
      code: structured?['code'] as String?,
      context: structured,
    );
  }
}

Future<String> evidenceMimeTypeForPath(String evidencePath) async {
  final file = File(evidencePath);
  RandomAccessFile? handle;
  late final Uint8List header;
  try {
    handle = await file.open();
    header = await handle.read(12);
  } on FileSystemException catch (error) {
    throw ApiException(
      422,
      'Evidence file could not be read: ${error.message}',
      code: 'EVIDENCE_FILE_UNREADABLE',
    );
  } finally {
    await handle?.close();
  }

  final detected = _imageMimeFromSignature(header);
  if (detected == null) {
    throw const ApiException(
      422,
      'Evidence must be a JPEG, PNG, or WEBP image.',
      code: 'EVIDENCE_FORMAT_UNSUPPORTED',
    );
  }

  final extensionMime = switch (path.extension(evidencePath).toLowerCase()) {
    '.jpg' || '.jpeg' => 'image/jpeg',
    '.png' => 'image/png',
    '.webp' => 'image/webp',
    _ => null,
  };
  if (extensionMime != null && extensionMime != detected) {
    throw const ApiException(
      422,
      'Evidence file extension does not match the image content.',
      code: 'EVIDENCE_FORMAT_MISMATCH',
    );
  }
  return detected;
}

String? _imageMimeFromSignature(Uint8List bytes) {
  if (bytes.length >= 3 &&
      bytes[0] == 0xff &&
      bytes[1] == 0xd8 &&
      bytes[2] == 0xff) {
    return 'image/jpeg';
  }
  const png = <int>[0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
  if (bytes.length >= png.length) {
    var matches = true;
    for (var index = 0; index < png.length; index++) {
      if (bytes[index] != png[index]) matches = false;
    }
    if (matches) return 'image/png';
  }
  if (bytes.length >= 12 &&
      String.fromCharCodes(bytes.sublist(0, 4)) == 'RIFF' &&
      String.fromCharCodes(bytes.sublist(8, 12)) == 'WEBP') {
    return 'image/webp';
  }
  return null;
}
