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

void main() {
  testWidgets('driver home exposes exactly four offline actions', (
    tester,
  ) async {
    final database = LocalDatabase(NativeDatabase.memory());
    final sync = SyncEngine(
      database: database,
      remote: _FakeRemote(),
      installationIdentifier: 'test-device',
    );
    final dependencies = DriverAppDependencies(
      api: ApiClient(),
      sessionStore: SecureSessionStore(),
      sync: sync,
      installationIdentifier: 'test-device',
    );
    const assignment = DriverAssignment(
      assignmentId: 'assignment',
      tipperId: 'tipper',
      tipperRegistrationNumber: 'KA01AB1234',
      tipperShortName: 'Alpha One',
      siteId: 'site',
      siteName: 'Alpha Site',
      supervisorName: 'Supervisor A',
    );

    await tester.pumpWidget(
      MaterialApp(
        home: DriverHomeScreen(
          dependencies: dependencies,
          assignment: assignment,
          duty: const DriverDutyState(status: DriverDutyStatus.active),
          onSignOut: () async {},
        ),
      ),
    );
    await tester.pump();

    expect(find.text('TRIP COMPLETE'), findsOneWidget);
    expect(find.text('KM READING'), findsOneWidget);
    expect(find.text('DIESEL'), findsOneWidget);
    expect(find.text('EMERGENCY'), findsOneWidget);
    expect(find.textContaining('Phase 0'), findsNothing);

    await tester.tap(find.text('TRIP COMPLETE'));
    await tester.tap(find.text('TRIP COMPLETE'));
    await tester.pump();
    final queued = await database.pendingForSync();
    expect(queued, hasLength(1));
    expect(queued.single.syncState, 'pending');

    await sync.syncPending();
    final synced = await database.eventById(queued.single.clientEventUuid);
    expect(synced?.syncState, 'synced');
    await database.close();
  });

  testWidgets(
    'driver home keeps four actions while gating NONE and restarting CLOSED duty',
    (tester) async {
      final database = LocalDatabase(NativeDatabase.memory());
      final dependencies = DriverAppDependencies(
        api: ApiClient(),
        sessionStore: SecureSessionStore(),
        sync: SyncEngine(
          database: database,
          remote: _FakeRemote(),
          installationIdentifier: 'test-device',
        ),
        installationIdentifier: 'test-device',
      );
      const assignment = DriverAssignment(
        assignmentId: 'assignment',
        tipperId: 'tipper',
        tipperRegistrationNumber: 'KA01AB1234',
        tipperShortName: 'Alpha One',
        siteId: 'site',
        siteName: 'Alpha Site',
        supervisorName: 'Supervisor A',
      );

      Widget home(DriverDutyState duty) => MaterialApp(
        home: DriverHomeScreen(
          dependencies: dependencies,
          assignment: assignment,
          duty: duty,
          onSignOut: () async {},
        ),
      );

      bool enabled(String label) =>
          tester
              .widget<FilledButton>(find.widgetWithText(FilledButton, label))
              .onPressed !=
          null;

      await tester.pumpWidget(home(const DriverDutyState.none()));
      await tester.pump();
      expect(find.text('TRIP COMPLETE'), findsOneWidget);
      expect(find.text('KM READING'), findsOneWidget);
      expect(find.text('DIESEL'), findsOneWidget);
      expect(find.text('EMERGENCY'), findsOneWidget);
      expect(enabled('TRIP COMPLETE'), isFalse);
      expect(enabled('KM READING'), isTrue);
      expect(enabled('DIESEL'), isFalse);
      expect(enabled('EMERGENCY'), isTrue);

      await tester.pumpWidget(
        home(const DriverDutyState(status: DriverDutyStatus.closed)),
      );
      await tester.pump();
      expect(enabled('TRIP COMPLETE'), isFalse);
      expect(enabled('KM READING'), isTrue);
      expect(enabled('DIESEL'), isFalse);
      expect(enabled('EMERGENCY'), isTrue);
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
