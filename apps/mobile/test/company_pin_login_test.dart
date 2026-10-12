import 'dart:convert';

import 'package:drift/native.dart';
import 'package:fleet_manager_mobile/app.dart';
import 'package:fleet_manager_mobile/auth/device_authenticator.dart';
import 'package:fleet_manager_mobile/auth/login_auth_provider.dart';
import 'package:fleet_manager_mobile/data/api_client.dart';
import 'package:fleet_manager_mobile/data/local_database.dart';
import 'package:fleet_manager_mobile/data/secure_session_store.dart';
import 'package:fleet_manager_mobile/data/sync_engine.dart';
import 'package:fleet_manager_mobile/domain/driver_models.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  setUp(() => FlutterSecureStorage.setMockInitialValues({}));

  test('company PIN build retains private updates without Firebase', () {
    final mode = resolveFleetAuthMode(
      configured: 'company_pin',
      pilotBuild: true,
      productionBuild: false,
    );
    expect(mode, FleetAuthMode.companyPin);
    expect(
      resolveFirebaseBuildProfile(
        configured: 'company-pin',
        pilotBuild: true,
        authMode: mode,
      ),
      'company-pin',
    );
    expect(
      privateApkUpdatesEnabled(
        pilotBuild: true,
        authMode: mode,
        firebaseCompanyBuild: false,
        companyPinBuild: true,
      ),
      isTrue,
    );
  });

  testWidgets(
    'first use activates device, confirms six digit fallback PIN, and enters sole role',
    (tester) async {
      final harness = _Harness();
      addTearDown(harness.close);
      SessionTokens? signedIn;
      await tester.pumpWidget(
        MaterialApp(
          home: LoginScreen(
            dependencies: harness.dependencies,
            onSignedIn: (tokens) async => signedIn = tokens,
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.enterText(
        find.byKey(const Key('company-phone')),
        '9876543210',
      );
      await tester.enterText(
        find.byKey(const Key('activation-code')),
        '123456',
      );
      await tester.tap(find.byKey(const Key('activate-device')));
      await tester.pumpAndSettle();
      expect(harness.activationPhone, '+919876543210');
      expect(harness.activationCode, '123456');

      await tester.enterText(find.byKey(const Key('company-pin')), '246810');
      await tester.enterText(
        find.byKey(const Key('confirm-company-pin')),
        '246811',
      );
      await tester.tap(find.byKey(const Key('create-pin')));
      await tester.pumpAndSettle();
      expect(find.text('PIN confirmation does not match.'), findsOneWidget);

      await tester.enterText(
        find.byKey(const Key('confirm-company-pin')),
        '246810',
      );
      await tester.tap(find.byKey(const Key('create-pin')));
      await tester.pumpAndSettle();
      expect(harness.createdPin, '246810');
      expect(signedIn?.role, 'OWNER_ADMIN');
      expect(
        await harness.sessionStore.readCompanyDeviceCredential(),
        'device-credential',
      );
    },
  );

  testWidgets(
    'OS authentication success unlocks Fleet without sending OS secrets',
    (tester) async {
      final harness = _Harness(
        deviceResult: DeviceAuthenticationResult.authenticated,
      );
      addTearDown(harness.close);
      await harness.sessionStore.saveCompanyDeviceCredential(
        'device-credential',
      );
      SessionTokens? signedIn;
      await tester.pumpWidget(
        MaterialApp(
          home: LoginScreen(
            dependencies: harness.dependencies,
            onSignedIn: (tokens) async => signedIn = tokens,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(harness.deviceAuthenticator.calls, 1);
      expect(signedIn?.role, 'OWNER_ADMIN');
      expect(harness.deviceAuthPayload, {
        'device_credential': 'device-credential',
        'installation_identifier': 'company-pin-test',
      });
      expect(harness.deviceAuthPayload, isNot(contains('pin')));
      expect(harness.deviceAuthPayload, isNot(contains('biometric')));
    },
  );

  testWidgets('OS authentication cancellation leaves Fleet locked', (
    tester,
  ) async {
    final harness = _Harness(
      deviceResult: DeviceAuthenticationResult.cancelled,
    );
    addTearDown(harness.close);
    await harness.sessionStore.saveCompanyDeviceCredential('device-credential');
    SessionTokens? signedIn;
    await tester.pumpWidget(
      MaterialApp(
        home: LoginScreen(
          dependencies: harness.dependencies,
          onSignedIn: (tokens) async => signedIn = tokens,
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(signedIn, isNull);
    expect(
      find.text('Device authentication was cancelled. Fleet remains locked.'),
      findsOneWidget,
    );
    expect(find.byKey(const Key('device-auth')), findsOneWidget);
    expect(find.byKey(const Key('company-pin')), findsNothing);
    expect(harness.deviceAuthPayload, isNull);
  });

  testWidgets(
    'unavailable OS authentication retains exactly six digit Fleet PIN fallback',
    (tester) async {
      final harness = _Harness(
        deviceResult: DeviceAuthenticationResult.unavailable,
      );
      addTearDown(harness.close);
      await harness.sessionStore.saveCompanyDeviceCredential(
        'device-credential',
      );
      SessionTokens? signedIn;
      await tester.pumpWidget(
        MaterialApp(
          home: LoginScreen(
            dependencies: harness.dependencies,
            onSignedIn: (tokens) async => signedIn = tokens,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('company-pin')), findsOneWidget);
      await tester.enterText(find.byKey(const Key('company-pin')), '2468');
      await tester.tap(find.byKey(const Key('pin-login')));
      await tester.pumpAndSettle();
      expect(find.text('Enter your 6-digit PIN.'), findsOneWidget);
      await tester.enterText(find.byKey(const Key('company-pin')), '246810');
      await tester.tap(find.byKey(const Key('pin-login')));
      await tester.pumpAndSettle();

      expect(harness.fallbackPin, '246810');
      expect(signedIn?.role, 'OWNER_ADMIN');
    },
  );

  testWidgets('driver and supervisor account shows exactly two workspaces', (
    tester,
  ) async {
    final harness = _Harness(
      deviceResult: DeviceAuthenticationResult.authenticated,
      roles: const ['DRIVER', 'SUPERVISOR'],
    );
    addTearDown(harness.close);
    await harness.sessionStore.saveCompanyDeviceCredential('device-credential');
    await tester.pumpWidget(
      MaterialApp(
        home: LoginScreen(
          dependencies: harness.dependencies,
          onSignedIn: (_) async {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('choose-DRIVER')), findsOneWidget);
    expect(find.byKey(const Key('choose-SUPERVISOR')), findsOneWidget);
    expect(find.byKey(const Key('choose-OWNER_ADMIN')), findsNothing);
  });

  testWidgets(
    'multi-role authentication shows only server workspaces and selects exact role',
    (tester) async {
      final harness = _Harness(
        deviceResult: DeviceAuthenticationResult.authenticated,
        roles: const ['DRIVER', 'SUPERVISOR', 'OWNER_ADMIN'],
      );
      addTearDown(harness.close);
      await harness.sessionStore.saveCompanyDeviceCredential(
        'device-credential',
      );
      SessionTokens? signedIn;
      await tester.pumpWidget(
        MaterialApp(
          home: LoginScreen(
            dependencies: harness.dependencies,
            onSignedIn: (tokens) async => signedIn = tokens,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('workspace-chooser')), findsOneWidget);
      expect(find.byKey(const Key('choose-DRIVER')), findsOneWidget);
      expect(find.byKey(const Key('choose-SUPERVISOR')), findsOneWidget);
      expect(find.byKey(const Key('choose-OWNER_ADMIN')), findsOneWidget);
      expect(find.text('Administrator'), findsNothing);

      await tester.tap(find.byKey(const Key('choose-SUPERVISOR')));
      await tester.pumpAndSettle();
      expect(harness.selectedMembership, 'membership-SUPERVISOR');
      expect(signedIn?.role, 'SUPERVISOR');
    },
  );

  testWidgets('revoked Build 28 credential returns to activation', (
    tester,
  ) async {
    final harness = _Harness(
      deviceResult: DeviceAuthenticationResult.authenticated,
      revokeLogin: true,
    );
    addTearDown(harness.close);
    await harness.sessionStore.saveCompanyDeviceCredential(
      'revoked-credential',
    );
    await tester.pumpWidget(
      MaterialApp(
        home: LoginScreen(
          dependencies: harness.dependencies,
          onSignedIn: (_) async {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('company-phone')), findsOneWidget);
    expect(await harness.sessionStore.readCompanyDeviceCredential(), isNull);
  });
}

class _FakeDeviceAuthenticator implements DeviceAuthenticator {
  _FakeDeviceAuthenticator(this.result);

  final DeviceAuthenticationResult result;
  int calls = 0;

  @override
  Future<DeviceAuthenticationResult> authenticate() async {
    calls += 1;
    return result;
  }
}

class _Harness {
  _Harness({
    this.revokeLogin = false,
    this.deviceResult = DeviceAuthenticationResult.unavailable,
    this.roles = const ['OWNER_ADMIN'],
  }) {
    deviceAuthenticator = _FakeDeviceAuthenticator(deviceResult);
    sessionStore = SecureSessionStore();
    api = ApiClient(
      baseUrl: 'http://test',
      persistSession: sessionStore.save,
      client: MockClient((request) async {
        final payload = request.body.isEmpty
            ? <String, dynamic>{}
            : jsonDecode(request.body) as Map<String, dynamic>;
        if (request.url.path == '/api/v1/auth/company/activate') {
          activationPhone = payload['phone'] as String?;
          activationCode = payload['activation_code'] as String?;
          return _json({
            'status': 'verified',
            'activation_token': 'device-credential',
            'expires_in': 900,
          });
        }
        if (request.url.path == '/api/v1/auth/company/complete-activation') {
          createdPin = payload['pin'] as String?;
          return _json({
            'status': 'verified',
            'pre_session_token': 'pre-session',
            'expires_in': 300,
            'device_credential': 'device-credential',
          });
        }
        if (request.url.path == '/api/v1/auth/company/device-auth') {
          deviceAuthPayload = payload;
          if (revokeLogin) return _reactivationRequired();
          return _preSession();
        }
        if (request.url.path == '/api/v1/auth/company/pin-auth') {
          fallbackPin = payload['pin'] as String?;
          if (revokeLogin) return _reactivationRequired();
          return _preSession();
        }
        if (request.url.path == '/api/v1/auth/memberships') {
          return _json({
            'memberships': [
              for (final role in roles)
                {
                  'membership_id': 'membership-$role',
                  'company_id': 'company-1',
                  'company_name': 'Alpha Construction',
                  'role': role,
                },
            ],
          });
        }
        if (request.url.path == '/api/v1/auth/session') {
          selectedMembership = payload['membership_id'] as String?;
          final role = selectedMembership!.replaceFirst('membership-', '');
          return _tokens(role: role);
        }
        return http.Response('{}', 404);
      }),
    );
    database = LocalDatabase(NativeDatabase.memory());
    dependencies = DriverAppDependencies(
      api: api,
      sessionStore: sessionStore,
      sync: SyncEngine(
        database: database,
        remote: api,
        installationIdentifier: 'company-pin-test',
      ),
      installationIdentifier: 'company-pin-test',
      deviceAuthenticator: deviceAuthenticator,
      loginAuthProvider: const CompanyPinAuthProvider(),
    );
  }

  final bool revokeLogin;
  final DeviceAuthenticationResult deviceResult;
  final List<String> roles;
  String? activationPhone;
  String? activationCode;
  String? createdPin;
  String? fallbackPin;
  String? selectedMembership;
  Map<String, dynamic>? deviceAuthPayload;
  late final _FakeDeviceAuthenticator deviceAuthenticator;
  late final ApiClient api;
  late final LocalDatabase database;
  late final SecureSessionStore sessionStore;
  late final DriverAppDependencies dependencies;

  http.Response _preSession() => _json({
    'status': 'verified',
    'pre_session_token': 'pre-session',
    'expires_in': 300,
  });

  http.Response _reactivationRequired() => _json({
    'detail': {
      'code': 'DEVICE_REACTIVATION_REQUIRED',
      'message': 'This device must be activated again.',
    },
  }, 401);

  http.Response _tokens({required String role}) => _json({
    'access_token': 'access-token',
    'refresh_token': 'refresh-token',
    'token_type': 'bearer',
    'expires_in': 600,
    'membership_id': 'membership-$role',
    'company_id': 'company-1',
    'role': role,
  });

  http.Response _json(Map<String, dynamic> body, [int status = 200]) =>
      http.Response(jsonEncode(body), status);

  Future<void> close() => database.close();
}
