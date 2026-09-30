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
    expect(find.widgetWithText(FilledButton, 'KM READING'), findsOneWidget);
    expect(find.text('DIESEL'), findsOneWidget);
    expect(find.text('EMERGENCY'), findsOneWidget);
    expect(find.textContaining('Phase 0'), findsNothing);

    await tester.tap(find.text('TRIP COMPLETE'));
    await tester.pumpAndSettle();
    expect(find.text('Mark this trip as completed?'), findsOneWidget);
    await tester.tap(find.text('NO'));
    await tester.pumpAndSettle();
    expect(await database.pendingForSync(), isEmpty);

    await tester.tap(find.text('TRIP COMPLETE'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('YES'));
    await tester.pump();
    final queued = await database.pendingForSync();
    expect(queued, hasLength(1));
    expect(queued.single.syncState, 'pending');

    await sync.syncPending();
    final synced = await database.eventById(queued.single.clientEventUuid);
    expect(synced?.syncState, 'synced');
    await database.close();
  });

  testWidgets('emergency requires confirmation and reports local delivery', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(800, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
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
      tipperAssetCode: 'TIPPER-01',
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

    expect(find.text('Alpha One'), findsOneWidget);
    expect(find.text('TIPPER-01'), findsOneWidget);
    expect(find.text('KA01AB1234'), findsOneWidget);
    expect(find.text('Alpha Site'), findsOneWidget);
    await tester.tap(find.text('EMERGENCY'));
    await tester.pumpAndSettle();
    expect(find.text('Send emergency alert?'), findsOneWidget);
    await tester.tap(find.text('NO'));
    await tester.pumpAndSettle();
    expect(await database.pendingForSync(), isEmpty);

    await tester.tap(find.text('EMERGENCY'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('SEND'));
    await tester.pump();
    expect(
      find.text('Emergency saved on phone — not yet delivered'),
      findsOneWidget,
    );
    expect(await database.pendingForSync(), hasLength(1));
    await database.close();
  });

  testWidgets(
    'machinery header omits missing registration and exposes three actions',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(800, 1000));
      addTearDown(() => tester.binding.setSurfaceSize(null));
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
        assignmentId: 'machinery-assignment',
        tipperId: 'excavator',
        tipperRegistrationNumber: null,
        tipperShortName: 'CAT 320',
        tipperAssetCode: 'EXC-01',
        assetType: 'EXCAVATOR',
        siteId: 'site',
        siteName: 'Test Site B',
        supervisorName: 'Supervisor A',
      );

      await tester.pumpWidget(
        MaterialApp(
          home: DriverHomeScreen(
            dependencies: dependencies,
            assignment: assignment,
            duty: const DriverDutyState(status: DriverDutyStatus.none),
            onSignOut: () async {},
          ),
        ),
      );
      await tester.pump();

      expect(find.text('CAT 320'), findsOneWidget);
      expect(find.text('EXC-01'), findsOneWidget);
      expect(find.text('HMR READING'), findsOneWidget);
      expect(find.text('DIESEL'), findsOneWidget);
      expect(find.text('EMERGENCY'), findsOneWidget);
      expect(find.text('TRIP COMPLETE'), findsNothing);
      expect(find.text('KM READING'), findsNothing);
      expect(find.byType(FilledButton), findsNWidgets(3));
      expect(
        tester
            .widget<FilledButton>(find.widgetWithText(FilledButton, 'DIESEL'))
            .onPressed,
        isNull,
      );

      await tester.tap(find.text('HMR READING'));
      await tester.pumpAndSettle();
      expect(find.text('START HMR'), findsOneWidget);
      expect(find.text('Hours'), findsOneWidget);
      await database.close();
    },
  );

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

  testWidgets(
    'rejects an absurd KM value before it can enter the offline queue',
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

      await tester.pumpWidget(
        MaterialApp(
          home: DriverHomeScreen(
            dependencies: dependencies,
            assignment: assignment,
            duty: const DriverDutyState.none(),
            onSignOut: () async {},
          ),
        ),
      );
      await tester.pump();
      await tester.tap(find.text('KM READING'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).last, '5676543455.81');
      await tester.tap(find.text('CONTINUE'));
      await tester.pump();

      expect(
        find.text(
          'KM reading looks invalid. Please check the odometer and enter the correct value.',
        ),
        findsOneWidget,
      );
      expect(find.widgetWithText(FilledButton, 'KM READING'), findsOneWidget);
      expect(await database.pendingForSync(), isEmpty);
      await database.close();
    },
  );

  testWidgets('START pending sync or verification never gates Driver buttons', (
    tester,
  ) async {
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

    Future<void> verify(DriverDutyState duty) async {
      await tester.pumpWidget(
        MaterialApp(
          home: DriverHomeScreen(
            dependencies: dependencies,
            assignment: assignment,
            duty: duty,
            onSignOut: () async {},
          ),
        ),
      );
      await tester.pump();
      for (final label in ['TRIP COMPLETE', 'KM READING', 'DIESEL']) {
        expect(
          tester
              .widget<FilledButton>(find.widgetWithText(FilledButton, label))
              .onPressed,
          isNotNull,
        );
      }
    }

    await verify(
      const DriverDutyState(
        status: DriverDutyStatus.active,
        localState: LocalDutyState.startPendingSync,
      ),
    );
    await verify(
      const DriverDutyState(
        status: DriverDutyStatus.active,
        localState: LocalDutyState.activeConfirmed,
      ),
    );
    await verify(
      const DriverDutyState(
        status: DriverDutyStatus.active,
        localState: LocalDutyState.needsAttention,
      ),
    );
    await database.close();
  });

  testWidgets(
    'manual Sync refreshes no-assignment and in-session asset changes',
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
      const owned = DriverAssignment(
        assignmentId: 'assignment-owned',
        tipperId: 'owned',
        tipperRegistrationNumber: 'TESTOWN02',
        tipperShortName: 'Owned tipper 2',
        siteId: 'site',
        siteName: 'Test Site B',
        supervisorName: 'Test Supervisor Two',
      );
      const rented = DriverAssignment(
        assignmentId: 'assignment-rented',
        tipperId: 'rented',
        tipperRegistrationNumber: 'TESTRENT03',
        tipperShortName: 'Rented tipper 3',
        siteId: 'site',
        siteName: 'Test Site B',
        supervisorName: 'Test Supervisor Two',
      );
      DriverAssignment? current = owned;
      DriverAssignment? next;
      late StateSetter updateHarness;

      await tester.pumpWidget(
        StatefulBuilder(
          builder: (context, setState) {
            updateHarness = setState;
            return MaterialApp(
              home: DriverHomeScreen(
                dependencies: dependencies,
                assignment: current,
                onRefreshState: () async {
                  updateHarness(() => current = next);
                  return null;
                },
                onSignOut: () async {},
              ),
            );
          },
        ),
      );
      await tester.pump();

      await tester.tap(find.byTooltip('Sync'));
      await tester.pumpAndSettle();
      expect(find.textContaining('NO ACTIVE ASSIGNMENT'), findsOneWidget);
      for (final label in [
        'TRIP COMPLETE',
        'KM READING',
        'DIESEL',
        'EMERGENCY',
      ]) {
        expect(
          tester
              .widget<FilledButton>(find.widgetWithText(FilledButton, label))
              .onPressed,
          isNull,
        );
      }

      next = rented;
      await tester.tap(find.byTooltip('Sync'));
      await tester.pumpAndSettle();
      expect(find.text('TESTRENT03'), findsOneWidget);
      expect(find.text('Test Site B'), findsOneWidget);
      expect(find.text('TESTOWN02'), findsNothing);

      next = owned;
      await tester.tap(find.byTooltip('Sync'));
      await tester.pumpAndSettle();
      expect(find.text('TESTOWN02'), findsOneWidget);
      expect(find.text('TESTRENT03'), findsNothing);
      await database.close();
    },
  );
}

class _FakeRemote implements DriverRemoteApi {
  @override
  Future<DeviceRegistration> registerDevice({
    required String installationIdentifier,
    bool allowHandover = false,
    bool localStateClear = false,
  }) async => const DeviceRegistration(
    deviceId: 'test-device-id',
    membershipId: 'test-membership-id',
    handedOver: false,
  );

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
