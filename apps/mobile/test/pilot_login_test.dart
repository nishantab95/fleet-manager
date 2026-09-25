import 'package:drift/native.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:fleet_manager_mobile/app.dart';
import 'package:fleet_manager_mobile/data/api_client.dart';
import 'package:fleet_manager_mobile/data/local_database.dart'
    hide PendingEvent;
import 'package:fleet_manager_mobile/data/secure_session_store.dart';
import 'package:fleet_manager_mobile/data/sync_engine.dart';
import 'package:fleet_manager_mobile/domain/driver_models.dart';
import 'package:fleet_manager_mobile/domain/role_models.dart';

void main() {
  test('compiled flavor selects the safe Pilot mode and URL', () {
    if (isPilotBuild) {
      expect(defaultApiBaseUrl, 'http://127.0.0.1:8000');
    } else {
      expect(defaultApiBaseUrl, 'https://api.fleetmanager.example');
      expect(defaultApiBaseUrl, isNot('http://10.0.2.2:8000'));
    }
  });

  testWidgets(
    'Pilot login exposes badge, settings, editing, and connection test',
    (tester) async {
      final database = LocalDatabase(NativeDatabase.memory());
      final dependencies = DriverAppDependencies(
        api: ApiClient(baseUrl: defaultApiBaseUrl),
        sessionStore: SecureSessionStore(),
        sync: SyncEngine(
          database: database,
          remote: _FakeRemote(),
          installationIdentifier: 'pilot-login-test',
        ),
        installationIdentifier: 'pilot-login-test',
      );

      await tester.pumpWidget(
        MaterialApp(
          home: LoginScreen(
            dependencies: dependencies,
            onSignedIn: (_) async {},
          ),
        ),
      );
      await tester.pump();

      if (isPilotBuild) {
        expect(find.text('PILOT / TEST'), findsOneWidget);
        expect(find.byTooltip('Server settings'), findsOneWidget);
        await tester.tap(find.byTooltip('Server settings'));
        await tester.pumpAndSettle();
        expect(find.text('Server URL'), findsOneWidget);
      expect(find.text('TEST CONNECTION'), findsOneWidget);
      expect(find.text('SAVE'), findsOneWidget);
      final fields = find.byType(TextField);
      await tester.enterText(fields.last, 'http://192.168.1.20:8000');
      expect(find.text('http://192.168.1.20:8000'), findsWidgets);
      } else {
        expect(find.text('PILOT / TEST'), findsNothing);
        expect(find.byTooltip('Server settings'), findsNothing);
      }

      await database.close();
    },
  );
}

class _FakeRemote implements DriverRemoteApi {
  @override
  Future<void> registerDevice({required String installationIdentifier}) async {}

  @override
  Future<String> uploadEvidence({
    required String clientEventUuid,
    required String evidencePath,
  }) async => 'evidence/$clientEventUuid';

  @override
  Future<void> submitEvent({
    required PendingEvent event,
    required String installationIdentifier,
  }) async {}
}
