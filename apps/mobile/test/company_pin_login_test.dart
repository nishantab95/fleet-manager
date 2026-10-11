import 'dart:convert';

import 'package:drift/native.dart';
import 'package:fleet_manager_mobile/app.dart';
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
    'first use activates device, confirms PIN, and stores credential',
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

  testWidgets('returning device shows only PIN and authenticates', (
    tester,
  ) async {
    final harness = _Harness();
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

    expect(find.byKey(const Key('company-phone')), findsNothing);
    expect(find.byKey(const Key('company-pin')), findsOneWidget);
    await tester.enterText(find.byKey(const Key('company-pin')), '246810');
    await tester.tap(find.byKey(const Key('pin-login')));
    await tester.pumpAndSettle();

    expect(harness.loginPin, '246810');
    expect(harness.loginCredential, 'device-credential');
    expect(signedIn?.role, 'OWNER_ADMIN');
  });

  testWidgets('revoked device credential returns to activation', (
    tester,
  ) async {
    final harness = _Harness(revokeLogin: true);
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
    await tester.enterText(find.byKey(const Key('company-pin')), '246810');
    await tester.tap(find.byKey(const Key('pin-login')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('company-phone')), findsOneWidget);
    expect(await harness.sessionStore.readCompanyDeviceCredential(), isNull);
  });
}

class _Harness {
  _Harness({this.revokeLogin = false}) {
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
          return http.Response(
            jsonEncode({
              'status': 'verified',
              'activation_token': 'device-credential',
              'expires_in': 900,
            }),
            200,
          );
        }
        if (request.url.path == '/api/v1/auth/company/set-pin') {
          createdPin = payload['pin'] as String?;
          return _tokens(deviceCredential: 'device-credential');
        }
        if (request.url.path == '/api/v1/auth/company/pin-login') {
          loginPin = payload['pin'] as String?;
          loginCredential = payload['device_credential'] as String?;
          if (revokeLogin) {
            return http.Response(
              jsonEncode({
                'detail': {
                  'code': 'DEVICE_REACTIVATION_REQUIRED',
                  'message': 'This device must be activated again.',
                },
              }),
              401,
            );
          }
          return _tokens();
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
      loginAuthProvider: const CompanyPinAuthProvider(),
    );
  }

  final bool revokeLogin;
  String? activationPhone;
  String? activationCode;
  String? createdPin;
  String? loginPin;
  String? loginCredential;
  late final ApiClient api;
  late final LocalDatabase database;
  late final SecureSessionStore sessionStore;
  late final DriverAppDependencies dependencies;

  http.Response _tokens({String? deviceCredential}) => http.Response(
    jsonEncode({
      'access_token': 'access-token',
      'refresh_token': 'refresh-token',
      'token_type': 'bearer',
      'expires_in': 600,
      'membership_id': 'membership-1',
      'company_id': 'company-1',
      'role': 'OWNER_ADMIN',
      if (deviceCredential != null) 'device_credential': deviceCredential,
    }),
    200,
  );

  Future<void> close() => database.close();
}
