import 'dart:convert';

import 'package:drift/native.dart';
import 'package:fleet_manager_mobile/app.dart';
import 'package:fleet_manager_mobile/data/api_client.dart';
import 'package:fleet_manager_mobile/data/local_database.dart';
import 'package:fleet_manager_mobile/data/secure_session_store.dart';
import 'package:fleet_manager_mobile/data/sync_engine.dart';
import 'package:fleet_manager_mobile/domain/driver_models.dart';
import 'package:fleet_manager_mobile/domain/role_models.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('Owner authenticated call uses the current access token', () async {
    var calls = 0;
    final api = ApiClient(
      baseUrl: 'http://test',
      client: MockClient((request) async {
        calls++;
        expect(request.url.path, '/api/v1/owner/assets');
        expect(request.headers['authorization'], 'Bearer owner-access');
        return http.Response('[]', 200);
      }),
    )..setSession(_tokens(role: 'OWNER_ADMIN', access: 'owner-access'));

    expect(await api.ownerAssets(), isEmpty);
    expect(calls, 1);
  });

  test(
    'Owner refresh persists tokens and duplicate registration reaches backend',
    () async {
      var ownerCalls = 0;
      var refreshCalls = 0;
      Map<String, dynamic>? receivedAsset;
      final persisted = <SessionTokens>[];
      final api = ApiClient(
        baseUrl: 'http://test',
        persistSession: (tokens) async => persisted.add(tokens),
        client: MockClient((request) async {
          if (request.url.path == '/api/v1/auth/refresh') {
            refreshCalls++;
            expect(jsonDecode(request.body), {
              'refresh_token': 'valid-refresh',
            });
            return _tokenResponse(
              _tokens(
                role: 'OWNER_ADMIN',
                access: 'refreshed-owner-access',
                refresh: 'rotated-refresh',
              ),
            );
          }
          expect(request.url.path, '/api/v1/owner/assets');
          ownerCalls++;
          if (ownerCalls == 1) {
            expect(request.headers['authorization'], 'Bearer expired-access');
            return http.Response(
              jsonEncode({'detail': 'access token expired'}),
              401,
            );
          }
          expect(
            request.headers['authorization'],
            'Bearer refreshed-owner-access',
          );
          receivedAsset = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(
            jsonEncode({
              'detail': {
                'code': 'CONFLICT',
                'message':
                    'Registration number is already used by this company.',
              },
            }),
            409,
          );
        }),
      )..setSession(_tokens(role: 'OWNER_ADMIN'));

      final error = await _apiError(
        api.createOwnerAsset(
          const OwnerAssetInput(
            assetCode: 'newcode99',
            registrationNumber: 'testown02',
            shortName: 'owned tipper two',
            ownershipType: 'OWNED',
          ),
        ),
      );

      expect(error.statusCode, 409);
      expect(
        error.message,
        'Registration number is already used by this company.',
      );
      expect(receivedAsset?['asset_code'], 'newcode99');
      expect(receivedAsset?['registration_number'], 'testown02');
      expect(ownerCalls, 2);
      expect(refreshCalls, 1);
      expect(persisted, hasLength(1));
      expect(persisted.single.accessToken, 'refreshed-owner-access');
      expect(persisted.single.refreshToken, 'rotated-refresh');
      expect(api.session?.accessToken, 'refreshed-owner-access');
    },
  );

  test('Supervisor ordinary request refreshes and retries once', () async {
    final counts = <String, int>{};
    final api = _refreshingApi(
      role: 'SUPERVISOR',
      protectedPath: '/api/v1/supervisor/sites',
      successBody: '[]',
      counts: counts,
    );

    expect(await api.supervisorSites(), isEmpty);
    expect(counts, {'protected': 2, 'refresh': 1});
  });

  test('Owner deployment mutation uses shared refresh and retry', () async {
    final counts = <String, int>{};
    final api = _refreshingApi(
      role: 'OWNER_ADMIN',
      protectedPath: '/api/v1/owner/assets/asset-1/deployment',
      successBody: jsonEncode(_deploymentJson()),
      counts: counts,
    );

    final deployment = await api.deployOwnerAsset('asset-1', 'site-1');

    expect(deployment.assetId, 'asset-1');
    expect(deployment.siteId, 'site-1');
    expect(counts, {'protected': 2, 'refresh': 1});
  });

  test('Owner report template request uses shared refresh and retry', () async {
    final counts = <String, int>{};
    final api = _refreshingApi(
      role: 'OWNER_ADMIN',
      protectedPath: '/api/v1/owner/report-templates',
      successBody: jsonEncode([_reportTemplateJson()]),
      counts: counts,
    );

    final templates = await api.reportTemplates();

    expect(templates.single.name, 'Management Summary');
    expect(templates.single.isDefault, isTrue);
    expect(counts, {'protected': 2, 'refresh': 1});
  });

  test('Excel export sends selected template and report date', () async {
    late Uri requested;
    final api = ApiClient(
      baseUrl: 'http://test',
      client: MockClient((request) async {
        requested = request.url;
        return http.Response.bytes([1, 2, 3], 200);
      }),
    )..setSession(_tokens(role: 'OWNER_ADMIN', access: 'owner-access'));

    final bytes = await api.dailyExcel(
      date: DateTime(2026, 9, 30),
      templateId: 'template-1',
    );

    expect(bytes, [1, 2, 3]);
    expect(requested.path, '/api/v1/reports/daily.xlsx');
    expect(requested.queryParameters, {
      'operational_date': '2026-09-30',
      'template_id': 'template-1',
    });
  });

  test('Owner template mutations use scoped endpoints and payloads', () async {
    final requests = <String>[];
    final bodies = <Map<String, dynamic>>[];
    final api = ApiClient(
      baseUrl: 'http://test',
      client: MockClient((request) async {
        requests.add('${request.method} ${request.url.path}');
        if (request.body.isNotEmpty) {
          bodies.add(jsonDecode(request.body) as Map<String, dynamic>);
        }
        if (request.method == 'DELETE') return http.Response('', 204);
        return http.Response(jsonEncode(_reportTemplateJson()), 200);
      }),
    )..setSession(_tokens(role: 'OWNER_ADMIN', access: 'owner-access'));
    const input = ReportTemplateInput(
      name: 'Custom Minimal',
      includedSheets: ['management_dashboard'],
      managementDashboardColumns: ['asset', 'site'],
      tipperDailyColumns: ['asset', 'site'],
      machineryDailyColumns: ['asset', 'site'],
    );

    await api.createReportTemplate(input);
    await api.updateReportTemplate('template-1', input);
    await api.duplicateReportTemplate('template-1', 'Custom Copy');
    await api.setDefaultReportTemplate('template-1');
    await api.deleteReportTemplate('template-1');

    expect(requests, [
      'POST /api/v1/owner/report-templates',
      'PATCH /api/v1/owner/report-templates/template-1',
      'POST /api/v1/owner/report-templates/template-1/duplicate',
      'POST /api/v1/owner/report-templates/template-1/default',
      'DELETE /api/v1/owner/report-templates/template-1',
    ]);
    expect(bodies[0], input.toJson());
    expect(bodies[1], input.toJson());
    expect(bodies[2], {'name': 'Custom Copy'});
  });

  test(
    'Supervisor deployed asset request uses shared refresh and retry',
    () async {
      final counts = <String, int>{};
      final api = _refreshingApi(
        role: 'SUPERVISOR',
        protectedPath: '/api/v1/supervisor/sites/site-1/assets',
        successBody: jsonEncode([
          {
            'asset_id': 'asset-1',
            'asset_code': 'TIPPER-1',
            'asset_type': 'TIPPER',
            'ownership_type': 'OWNED',
            'registration_number': 'REG-1',
            'short_name': 'Tipper 1',
            'status': 'ACTIVE',
            'current_deployment': _deploymentJson(),
            'driver_membership_id': null,
            'driver_name': null,
            'duty_status': null,
            'pending_review_count': 0,
          },
        ]),
        counts: counts,
      );

      final assets = await api.supervisorSiteAssets('site-1');

      expect(assets.single.driverName, isNull);
      expect(counts, {'protected': 2, 'refresh': 1});
    },
  );

  test('Driver assignment calls use owner and supervisor paths', () async {
    final paths = <String>[];
    final api = ApiClient(
      baseUrl: 'http://test',
      client: MockClient((request) async {
        paths.add('${request.method} ${request.url.path}');
        if (request.url.path.endsWith('/eligible-drivers')) {
          return http.Response(
            jsonEncode([
              {'membership_id': 'driver-1', 'display_name': 'Driver One'},
            ]),
            200,
          );
        }
        expect(jsonDecode(request.body), {'driver_membership_id': 'driver-1'});
        return http.Response(jsonEncode(_assignmentJson()), 200);
      }),
    )..setSession(_tokens(role: 'OWNER_ADMIN', access: 'owner-access'));

    final candidates = await api.eligibleDrivers('asset-1');
    expect(candidates.single.displayName, 'Driver One');
    final assignment = await api.assignDriver(
      'asset-1',
      'driver-1',
      supervisorSiteId: 'site-1',
      reassign: true,
    );
    expect(assignment.driverName, 'Driver One');
    expect(paths, [
      'GET /api/v1/owner/assets/asset-1/eligible-drivers',
      'POST /api/v1/supervisor/sites/site-1/assets/asset-1/assignment/reassign',
    ]);
  });

  test('Driver ordinary request refreshes and retries once', () async {
    final counts = <String, int>{};
    final api = _refreshingApi(
      role: 'DRIVER',
      protectedPath: '/api/v1/driver/device',
      successBody: jsonEncode({
        'device_id': 'device-id',
        'membership_id': 'membership-id',
        'handed_over': false,
      }),
      counts: counts,
    );

    await api.registerDevice(installationIdentifier: 'device-1');
    expect(counts, {'protected': 2, 'refresh': 1});
  });

  test('Concurrent stale requests share one token refresh', () async {
    var protectedCalls = 0;
    var refreshCalls = 0;
    final api = ApiClient(
      baseUrl: 'http://test',
      client: MockClient((request) async {
        if (request.url.path == '/api/v1/auth/refresh') {
          refreshCalls++;
          return _tokenResponse(
            _tokens(role: 'OWNER_ADMIN', access: 'refreshed-access'),
          );
        }
        protectedCalls++;
        if (request.headers['authorization'] == 'Bearer expired-access') {
          await Future<void>.delayed(const Duration(milliseconds: 10));
          return http.Response(jsonEncode({'detail': 'expired'}), 401);
        }
        return http.Response('[]', 200);
      }),
    )..setSession(_tokens(role: 'OWNER_ADMIN'));

    await Future.wait([api.ownerAssets(), api.ownerAssets()]);

    expect(protectedCalls, 4);
    expect(refreshCalls, 1);
  });

  test('Invalid refresh expires locally without retrying forever', () async {
    var protectedCalls = 0;
    var refreshCalls = 0;
    var expiredCalls = 0;
    final api = ApiClient(
      baseUrl: 'http://test',
      client: MockClient((request) async {
        if (request.url.path == '/api/v1/auth/refresh') {
          refreshCalls++;
          return http.Response(
            jsonEncode({'detail': 'refresh token is invalid'}),
            401,
          );
        }
        protectedCalls++;
        return http.Response(
          jsonEncode({'detail': 'access token expired'}),
          401,
        );
      }),
    )..setSession(_tokens(role: 'OWNER_ADMIN'));
    api.setSessionExpiredHandler(() async => expiredCalls++);

    final error = await _apiError(api.ownerAssets());

    expect(error.statusCode, 401);
    expect(error.message, sessionExpiredMessage);
    expect(protectedCalls, 1);
    expect(refreshCalls, 1);
    expect(expiredCalls, 1);
    expect(api.session, isNull);
  });

  test('A 401 after refresh is not refreshed or retried again', () async {
    var protectedCalls = 0;
    var refreshCalls = 0;
    final api = ApiClient(
      baseUrl: 'http://test',
      client: MockClient((request) async {
        if (request.url.path == '/api/v1/auth/refresh') {
          refreshCalls++;
          return _tokenResponse(
            _tokens(role: 'SUPERVISOR', access: 'still-rejected'),
          );
        }
        protectedCalls++;
        return http.Response(jsonEncode({'detail': 'unauthorized'}), 401);
      }),
    )..setSession(_tokens(role: 'SUPERVISOR'));

    final error = await _apiError(api.supervisorSites());

    expect(error.message, sessionExpiredMessage);
    expect(protectedCalls, 2);
    expect(refreshCalls, 1);
    expect(api.session, isNull);
  });

  testWidgets('Invalid refresh returns to login with a clear message', (
    tester,
  ) async {
    FlutterSecureStorage.setMockInitialValues({});
    final sessionStore = SecureSessionStore();
    final tokens = _tokens(role: 'OWNER_ADMIN');
    await sessionStore.save(tokens);
    final api = ApiClient(
      baseUrl: 'http://test',
      persistSession: sessionStore.save,
      client: MockClient((request) async {
        return http.Response(
          jsonEncode({'detail': 'token is invalid or expired'}),
          401,
        );
      }),
    )..setSession(tokens);
    final database = LocalDatabase(NativeDatabase.memory());
    addTearDown(database.close);

    await tester.pumpWidget(
      FleetManagerApp(
        dependencies: DriverAppDependencies(
          api: api,
          sessionStore: sessionStore,
          sync: SyncEngine(
            database: database,
            remote: api,
            installationIdentifier: 'device-1',
          ),
          installationIdentifier: 'device-1',
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Sign in'), findsOneWidget);
    expect(find.text(sessionExpiredMessage), findsOneWidget);
    expect(api.session, isNull);
    expect(await sessionStore.read(), isNull);
  });
}

ApiClient _refreshingApi({
  required String role,
  required String protectedPath,
  required String successBody,
  required Map<String, int> counts,
}) {
  return ApiClient(
    baseUrl: 'http://test',
    client: MockClient((request) async {
      if (request.url.path == '/api/v1/auth/refresh') {
        counts['refresh'] = (counts['refresh'] ?? 0) + 1;
        return _tokenResponse(_tokens(role: role, access: 'refreshed-access'));
      }
      expect(request.url.path, protectedPath);
      counts['protected'] = (counts['protected'] ?? 0) + 1;
      if (counts['protected'] == 1) {
        expect(request.headers['authorization'], 'Bearer expired-access');
        return http.Response(jsonEncode({'detail': 'expired'}), 401);
      }
      expect(request.headers['authorization'], 'Bearer refreshed-access');
      return http.Response(successBody, 200);
    }),
  )..setSession(_tokens(role: role));
}

SessionTokens _tokens({
  required String role,
  String access = 'expired-access',
  String refresh = 'valid-refresh',
}) => SessionTokens(
  accessToken: access,
  refreshToken: refresh,
  expiresIn: 900,
  membershipId: 'membership-1',
  companyId: 'company-1',
  role: role,
);

http.Response _tokenResponse(SessionTokens tokens) =>
    http.Response(jsonEncode(tokens.toJson()), 200);

Map<String, dynamic> _deploymentJson() => {
  'id': 'deployment-1',
  'asset_id': 'asset-1',
  'site_id': 'site-1',
  'site_name': 'Pilot Site',
  'starts_at': '2026-09-29T08:00:00Z',
  'ends_at': null,
};

Map<String, dynamic> _assignmentJson() => {
  'assignment_id': 'assignment-1',
  'asset_id': 'asset-1',
  'asset_code': 'TIPPER-1',
  'driver_membership_id': 'driver-1',
  'driver_name': 'Driver One',
  'asset_site_deployment_id': 'deployment-1',
  'site_id': 'site-1',
  'site_name': 'Pilot Site',
  'starts_at': '2026-09-30T08:00:00Z',
  'ends_at': null,
  'regular_duty_minutes': 600,
};

Map<String, dynamic> _reportTemplateJson() => {
  'id': 'template-1',
  'name': 'Management Summary',
  'is_builtin': true,
  'is_default': true,
  'included_sheets': [
    'management_dashboard',
    'tipper_daily',
    'machinery_daily',
    'exceptions',
  ],
  'management_dashboard_columns': ['asset', 'site'],
  'tipper_daily_columns': ['asset', 'approved_trips'],
  'machinery_daily_columns': ['asset', 'machine_hours'],
};

Future<ApiException> _apiError(Future<Object?> request) async {
  try {
    await request;
  } on ApiException catch (error) {
    return error;
  }
  throw StateError('Expected ApiException');
}
