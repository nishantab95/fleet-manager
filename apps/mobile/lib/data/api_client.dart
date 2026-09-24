import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../domain/driver_models.dart';

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
    : _baseUrl =
          (baseUrl ??
                  const String.fromEnvironment(
                    'FLEET_API_BASE_URL',
                    defaultValue: 'http://10.0.2.2:8000',
                  ))
              .replaceFirst(RegExp(r'/$'), ''),
      _client = client ?? http.Client();

  final String _baseUrl;
  final http.Client _client;
  SessionTokens? _tokens;

  void setSession(SessionTokens tokens) => _tokens = tokens;

  SessionTokens? get session => _tokens;

  void clearSession() => _tokens = null;

  Future<String> requestOtp(String phone) async {
    final body = await _post('/api/v1/auth/otp/request', {'phone': phone});
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
