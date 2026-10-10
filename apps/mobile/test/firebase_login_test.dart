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
  test('production builds reject pilot authentication', () {
    expect(
      () => resolveFleetAuthMode(
        configured: 'pilot',
        pilotBuild: false,
        productionBuild: true,
      ),
      throwsStateError,
    );
  });

  setUp(() => FlutterSecureStorage.setMockInitialValues({}));

  for (final role in const ['DRIVER', 'SUPERVISOR', 'OWNER_ADMIN']) {
    testWidgets(
      'Firebase login routes an authorized $role without role selection',
      (tester) async {
        final auth = _FakeFirebaseLoginAuth();
        final harness = _Harness(auth: auth, role: role);
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

        expect(find.byType(SegmentedButton<String>), findsNothing);
        await tester.enterText(
          find.byKey(const Key('firebase-phone')),
          '9876543210',
        );
        await tester.tap(find.widgetWithText(FilledButton, 'SEND OTP'));
        await tester.pumpAndSettle();
        expect(auth.sentPhone, '+919876543210');

        await tester.enterText(find.byKey(const Key('otp-code')), '123456');
        await tester.tap(find.widgetWithText(FilledButton, 'VERIFY'));
        await tester.pumpAndSettle();

        expect(auth.verifiedCode, '123456');
        expect(signedIn?.role, role);
        expect((await harness.sessionStore.read())?.role, role);
      },
    );
  }

  testWidgets('Firebase wrong and expired codes show safe provider messages', (
    tester,
  ) async {
    final auth = _FakeFirebaseLoginAuth(
      verifyError: const LoginAuthException(
        'The verification code is incorrect.',
        code: 'WRONG_OTP',
      ),
    );
    final harness = _Harness(auth: auth, role: 'OWNER_ADMIN');
    addTearDown(harness.close);

    await tester.pumpWidget(
      MaterialApp(
        home: LoginScreen(
          dependencies: harness.dependencies,
          onSignedIn: (_) async {},
        ),
      ),
    );
    await tester.enterText(
      find.byKey(const Key('firebase-phone')),
      '9876543210',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'SEND OTP'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('otp-code')), '000000');
    await tester.tap(find.widgetWithText(FilledButton, 'VERIFY'));
    await tester.pumpAndSettle();

    expect(find.text('The verification code is incorrect.'), findsOneWidget);
  });

  testWidgets('Firebase expired code shows a safe provider message', (
    tester,
  ) async {
    final auth = _FakeFirebaseLoginAuth(
      verifyError: const LoginAuthException(
        'The verification code has expired. Request a new code.',
        code: 'EXPIRED_OTP',
      ),
    );
    final harness = _Harness(auth: auth, role: 'DRIVER');
    addTearDown(harness.close);

    await tester.pumpWidget(
      MaterialApp(
        home: LoginScreen(
          dependencies: harness.dependencies,
          onSignedIn: (_) async {},
        ),
      ),
    );
    await tester.enterText(
      find.byKey(const Key('firebase-phone')),
      '9876543210',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'SEND OTP'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('otp-code')), '123456');
    await tester.tap(find.widgetWithText(FilledButton, 'VERIFY'));
    await tester.pumpAndSettle();

    expect(
      find.text('The verification code has expired. Request a new code.'),
      findsOneWidget,
    );
  });

  testWidgets('Firebase invalid phone is rejected before requesting SMS', (
    tester,
  ) async {
    final auth = _FakeFirebaseLoginAuth();
    final harness = _Harness(auth: auth, role: 'DRIVER');
    addTearDown(harness.close);

    await tester.pumpWidget(
      MaterialApp(
        home: LoginScreen(
          dependencies: harness.dependencies,
          onSignedIn: (_) async {},
        ),
      ),
    );
    await tester.enterText(find.byKey(const Key('firebase-phone')), '12345');
    await tester.tap(find.widgetWithText(FilledButton, 'SEND OTP'));
    await tester.pumpAndSettle();

    expect(find.text('Enter a valid 10-digit mobile number.'), findsOneWidget);
    expect(auth.sendCount, 0);
  });

  testWidgets('Firebase resend requests a new provider challenge', (
    tester,
  ) async {
    final auth = _FakeFirebaseLoginAuth();
    final harness = _Harness(auth: auth, role: 'OWNER_ADMIN');
    addTearDown(harness.close);

    await tester.pumpWidget(
      MaterialApp(
        home: LoginScreen(
          dependencies: harness.dependencies,
          onSignedIn: (_) async {},
        ),
      ),
    );
    await tester.enterText(
      find.byKey(const Key('firebase-phone')),
      '9876543210',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'SEND OTP'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Resend OTP'));
    await tester.pumpAndSettle();

    expect(auth.sendCount, 2);
    expect(auth.lastForceResend, isTrue);
  });

  testWidgets('Firebase verified phone with no Fleet membership is denied', (
    tester,
  ) async {
    final auth = _FakeFirebaseLoginAuth();
    final harness = _Harness(auth: auth, role: null);
    addTearDown(harness.close);

    await tester.pumpWidget(
      MaterialApp(
        home: LoginScreen(
          dependencies: harness.dependencies,
          onSignedIn: (_) async {},
        ),
      ),
    );
    await tester.enterText(
      find.byKey(const Key('firebase-phone')),
      '9876543210',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'SEND OTP'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('otp-code')), '123456');
    await tester.tap(find.widgetWithText(FilledButton, 'VERIFY'));
    await tester.pumpAndSettle();

    expect(
      find.text(
        'This mobile number is not registered with your company. '
        'Contact your Fleet Manager administrator.',
      ),
      findsOneWidget,
    );
  });

  testWidgets('Firebase disabled Fleet account is denied cleanly', (
    tester,
  ) async {
    final auth = _FakeFirebaseLoginAuth(
      verifyError: const LoginAuthException(
        'This account is disabled. Contact your Fleet Manager administrator.',
        code: 'ACCESS_DENIED',
      ),
    );
    final harness = _Harness(auth: auth, role: null);
    addTearDown(harness.close);

    await tester.pumpWidget(
      MaterialApp(
        home: LoginScreen(
          dependencies: harness.dependencies,
          onSignedIn: (_) async {},
        ),
      ),
    );
    await tester.enterText(
      find.byKey(const Key('firebase-phone')),
      '9876543210',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'SEND OTP'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('otp-code')), '123456');
    await tester.tap(find.widgetWithText(FilledButton, 'VERIFY'));
    await tester.pumpAndSettle();

    expect(
      find.text(
        'This account is disabled. Contact your Fleet Manager administrator.',
      ),
      findsOneWidget,
    );
  });

  testWidgets('restored Firebase session signs out Fleet and Firebase', (
    tester,
  ) async {
    final auth = _FakeFirebaseLoginAuth();
    final harness = _Harness(auth: auth, role: 'OWNER_ADMIN');
    addTearDown(harness.close);
    const tokens = SessionTokens(
      accessToken: 'restored-access',
      refreshToken: 'restored-refresh',
      expiresIn: 600,
      membershipId: 'membership-1',
      companyId: 'company-1',
      role: 'OWNER_ADMIN',
    );
    await harness.sessionStore.save(tokens);
    harness.api.setSession(tokens);

    await tester.pumpWidget(
      FleetManagerApp(dependencies: harness.dependencies),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Sign out'));
    await tester.pumpAndSettle();

    expect(auth.signOutCount, 1);
    expect(harness.api.session, isNull);
    expect(await harness.sessionStore.read(), isNull);
    expect(find.byKey(const Key('firebase-phone')), findsOneWidget);
  });
}

class _FakeFirebaseLoginAuth implements FleetLoginAuthProvider {
  _FakeFirebaseLoginAuth({this.verifyError});

  final LoginAuthException? verifyError;
  int sendCount = 0;
  bool lastForceResend = false;
  String? sentPhone;
  String? verifiedCode;
  int signOutCount = 0;

  @override
  FleetAuthMode get mode => FleetAuthMode.firebase;

  @override
  Future<LoginChallenge> sendOtp(
    String phone, {
    String? requestedRole,
    bool forceResend = false,
  }) async {
    sendCount++;
    lastForceResend = forceResend;
    sentPhone = phone;
    return LoginChallenge(id: 'verification-$sendCount');
  }

  @override
  Future<String> verifyOtp(LoginChallenge challenge, String otp) async {
    verifiedCode = otp;
    if (verifyError != null) throw verifyError!;
    return 'fleet-pre-session';
  }

  @override
  Future<void> signOut() async {
    signOutCount++;
  }
}

class _Harness {
  _Harness({required _FakeFirebaseLoginAuth auth, required String? role}) {
    sessionStore = SecureSessionStore();
    api = ApiClient(
      baseUrl: 'http://test',
      persistSession: sessionStore.save,
      client: MockClient((request) async {
        if (request.url.path == '/api/v1/auth/me') {
          return http.Response('{}', 200);
        }
        if (request.url.path == '/api/v1/auth/logout') {
          return http.Response('', 204);
        }
        if (request.url.path == '/api/v1/auth/memberships') {
          return http.Response(
            jsonEncode({
              'memberships': role == null
                  ? <Object>[]
                  : [
                      {
                        'membership_id': 'membership-1',
                        'company_id': 'company-1',
                        'company_name': 'Fleet Test Company',
                        'role': role,
                      },
                    ],
            }),
            200,
          );
        }
        if (request.url.path == '/api/v1/auth/session') {
          return http.Response(
            jsonEncode({
              'access_token': 'access-token',
              'refresh_token': 'refresh-token',
              'token_type': 'bearer',
              'expires_in': 600,
              'membership_id': 'membership-1',
              'company_id': 'company-1',
              'role': role,
            }),
            200,
          );
        }
        if (request.url.path == '/api/v1/driver/device') {
          return http.Response(
            jsonEncode({
              'device_id': 'device-1',
              'membership_id': 'membership-1',
              'handed_over': false,
            }),
            200,
          );
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
        installationIdentifier: 'firebase-login-test',
      ),
      installationIdentifier: 'firebase-login-test',
      loginAuthProvider: auth,
    );
  }

  late final ApiClient api;
  late final LocalDatabase database;
  late final SecureSessionStore sessionStore;
  late final DriverAppDependencies dependencies;

  Future<void> close() => database.close();
}
