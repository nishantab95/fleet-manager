import 'package:drift/native.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:fleet_manager_mobile/app.dart';
import 'package:fleet_manager_mobile/data/api_client.dart';
import 'package:fleet_manager_mobile/data/local_database.dart'
    hide PendingEvent;
import 'package:fleet_manager_mobile/data/secure_session_store.dart';
import 'package:fleet_manager_mobile/data/sync_engine.dart';
import 'package:fleet_manager_mobile/domain/driver_models.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('pilot driver shell exposes four actions and diagnostics', (
    tester,
  ) async {
    final database = LocalDatabase(NativeDatabase.memory());
    final dependencies = DriverAppDependencies(
      api: ApiClient(),
      sessionStore: SecureSessionStore(),
      sync: SyncEngine(
        database: database,
        remote: _FakeRemote(),
        installationIdentifier: 'integration-device',
      ),
      installationIdentifier: 'integration-device',
    );
    const assignment = DriverAssignment(
      assignmentId: 'assignment',
      tipperId: 'tipper',
      tipperRegistrationNumber: 'PILOT-12',
      tipperShortName: 'Tipper 12',
      siteId: 'site',
      siteName: 'Pilot Site',
      supervisorName: 'Pilot Supervisor',
    );

    await tester.pumpWidget(
      MaterialApp(
        home: DriverHomeScreen(
          dependencies: dependencies,
          assignment: assignment,
          onSignOut: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('TRIP COMPLETE'), findsOneWidget);
    expect(find.text('KM READING'), findsOneWidget);
    expect(find.text('DIESEL'), findsOneWidget);
    expect(find.text('EMERGENCY'), findsOneWidget);
    await tester.tap(find.byTooltip('Diagnostics'));
    await tester.pumpAndSettle();
    expect(find.text('App version'), findsOneWidget);
    expect(find.text('integration-device'), findsOneWidget);
    await database.close();
  });
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
