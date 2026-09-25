import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

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

abstract class DriverRemoteApi {
  Future<void> registerDevice({required String installationIdentifier});

  Future<String> uploadEvidence({
    required String clientEventUuid,
    required String evidencePath,
  });

  Future<void> submitEvent({
    required PendingEvent event,
    required String installationIdentifier,
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

  @override
  String toString() => 'ApiException($statusCode): $message';
}

class ApiClient implements DriverRemoteApi {
  ApiClient({String? baseUrl, http.Client? client})
    : _baseUrl = (baseUrl ?? defaultApiBaseUrl).replaceFirst(RegExp(r'/$'), ''),
      _client = client ?? http.Client();

  String _baseUrl;
  final http.Client _client;
  SessionTokens? _tokens;

  void setSession(SessionTokens tokens) => _tokens = tokens;

  SessionTokens? get session => _tokens;

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
    final refreshToken = _tokens?.refreshToken;
    if (refreshToken == null) {
      throw const ApiException(401, 'session is missing');
    }
    final body = await _post('/api/v1/auth/refresh', {
      'refresh_token': refreshToken,
    });
    final tokens = SessionTokens.fromJson(body);
    setSession(tokens);
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

  Future<DriverAssignment?> currentAssignment() async {
    final response = await _request(
      'GET',
      '/api/v1/driver/assignment/current',
      authenticated: true,
    );
    if (response.statusCode == 204 || response.body == 'null') return null;
    return DriverAssignment.fromJson(_json(response));
  }

  Future<DriverDutyState> currentDuty() async {
    final response = await _request(
      'GET',
      '/api/v1/driver/duty/current',
      authenticated: true,
    );
    return DriverDutyState.fromJson(_json(response));
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

  Future<Uint8List> dailyExcel({DateTime? date}) async {
    final suffix = date == null ? '' : '?operational_date=${_dateParam(date)}';
    final response = await _request(
      'GET',
      '/api/v1/reports/daily.xlsx$suffix',
      authenticated: true,
    );
    return response.bodyBytes;
  }

  @override
  Future<void> registerDevice({required String installationIdentifier}) async {
    await _request(
      'POST',
      '/api/v1/driver/device',
      authenticated: true,
      body: {
        'installation_identifier': installationIdentifier,
        'platform': 'ANDROID',
      },
    );
  }

  @override
  Future<String> uploadEvidence({
    required String clientEventUuid,
    required String evidencePath,
  }) async {
    final token = _tokens?.accessToken;
    if (token == null) throw const ApiException(401, 'session is missing');
    final request =
        http.MultipartRequest(
            'POST',
            _uri('/api/v1/driver/evidence?client_event_uuid=$clientEventUuid'),
          )
          ..headers['Authorization'] = 'Bearer $token'
          ..files.add(await http.MultipartFile.fromPath('file', evidencePath));
    late final http.Response materialized;
    try {
      final response = await _client.send(request);
      materialized = await http.Response.fromStream(response);
    } on SocketException catch (error) {
      throw ApiException(503, error.message);
    }
    _check(materialized);
    return (_json(materialized))['object_reference'] as String;
  }

  @override
  Future<void> submitEvent({
    required PendingEvent event,
    required String installationIdentifier,
  }) async {
    final payload = <String, dynamic>{
      'client_event_uuid': event.clientEventUuid,
      'event_type': event.eventType.wireName,
      'device_created_at': event.deviceCreatedAt.toUtc().toIso8601String(),
      'installation_identifier': installationIdentifier,
      'platform': 'ANDROID',
      ...event.payload,
    };
    await _request(
      'POST',
      '/api/v1/driver/events',
      authenticated: true,
      body: payload,
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
  }) async {
    final headers = <String, String>{'Content-Type': 'application/json'};
    if (authenticated) {
      final token = _tokens?.accessToken;
      if (token == null) throw const ApiException(401, 'session is missing');
      headers['Authorization'] = 'Bearer $token';
    }
    final encoded = body == null ? null : jsonEncode(body);
    try {
      final request = http.Request(method, _uri(path))
        ..headers.addAll(headers)
        ..body = encoded ?? '';
      final streamed = await _client.send(request);
      final response = await http.Response.fromStream(streamed);
      _check(response);
      return response;
    } on SocketException catch (error) {
      throw ApiException(503, error.message);
    }
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
