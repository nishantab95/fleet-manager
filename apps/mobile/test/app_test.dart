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

const _tipper = DriverAssignment(
  assignmentId: 'tipper-assignment',
  tipperId: 'tipper',
  tipperRegistrationNumber: 'KA01AB1234',
  tipperShortName: 'Alpha One',
  tipperAssetCode: 'TIPPER-01',
  siteId: 'site',
  siteName: 'Alpha Site',
  supervisorName: 'Supervisor A',
);

const _machinery = DriverAssignment(
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

void main() {
  testWidgets('off-duty tipper shows only Start Duty and Emergency', (
    tester,
  ) async {
    final harness = _Harness();
    addTearDown(harness.close);
    await _pumpDriver(
      tester,
      harness.dependencies,
      assignment: _tipper,
      duty: const DriverDutyState.none(),
    );

    expect(find.text('Alpha One'), findsOneWidget);
    expect(find.text('TIPPER-01'), findsOneWidget);
    expect(find.text('KA01AB1234'), findsOneWidget);
    expect(find.text('Alpha Site'), findsOneWidget);
    expect(find.text('OFF DUTY'), findsOneWidget);
    expect(find.text('START DUTY'), findsOneWidget);
    expect(find.text('EMERGENCY'), findsOneWidget);
    expect(find.text('TRIP COMPLETE'), findsNothing);
    expect(find.text('DIESEL'), findsNothing);
    expect(find.text('KM READING'), findsNothing);
    expect(find.text('MAINTENANCE'), findsNothing);
    expect(find.text('END DUTY'), findsNothing);
    expect(find.byType(FilledButton), findsNWidgets(2));
  });

  testWidgets('on-duty tipper follows the working-action hierarchy', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(390, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final harness = _Harness();
    addTearDown(harness.close);
    await _pumpDriver(
      tester,
      harness.dependencies,
      assignment: _tipper,
      duty: const DriverDutyState(status: DriverDutyStatus.active),
    );

    expect(find.text('DUTY ACTIVE'), findsOneWidget);
    expect(find.text('EMERGENCY'), findsOneWidget);
    expect(find.text('TRIP COMPLETE'), findsOneWidget);
    expect(find.text('DIESEL'), findsOneWidget);
    expect(find.text('MAINTENANCE'), findsOneWidget);
    expect(find.text('Coming later'), findsOneWidget);
    expect(find.text('END DUTY'), findsOneWidget);
    expect(find.text('KM READING'), findsNothing);
    expect(find.text('HMR READING'), findsNothing);
    expect(find.text('START DUTY'), findsNothing);

    final emergencyY = tester.getTopLeft(find.text('EMERGENCY')).dy;
    final tripY = tester.getTopLeft(find.text('TRIP COMPLETE')).dy;
    final maintenanceY = tester.getTopLeft(find.text('MAINTENANCE')).dy;
    final endDutyY = tester.getTopLeft(find.text('END DUTY')).dy;
    expect(emergencyY, lessThan(tripY));
    expect(endDutyY, greaterThan(maintenanceY));
    expect(
      tester
          .widget<FilledButton>(
            find.widgetWithText(FilledButton, 'MAINTENANCE'),
          )
          .onPressed,
      isNull,
    );

    await tester.tap(find.text('TRIP COMPLETE'));
    await tester.pumpAndSettle();
    expect(find.text('Mark this trip as completed?'), findsOneWidget);
    await tester.tap(find.text('YES'));
    await tester.pump();
    final queued = await harness.database.pendingForSync();
    expect(queued, hasLength(1));
    expect(queued.single.eventType, 'TRIP_COMPLETE');
    expect(find.text('Trip recorded'), findsOneWidget);
    expect(
      tester.getTopLeft(find.text('Trip recorded')).dy,
      lessThan(tester.getTopLeft(find.text('END DUTY')).dy),
    );
    await harness.dependencies.sync.syncPending();
    final synced = await harness.database.eventById(
      queued.single.clientEventUuid,
    );
    expect(synced?.syncState, 'synced');
    await tester.pump(const Duration(seconds: 7));
    expect(find.text('Trip recorded'), findsNothing);
  });

  testWidgets('off-duty machinery shows only Start Duty and Emergency', (
    tester,
  ) async {
    final harness = _Harness();
    addTearDown(harness.close);
    await _pumpDriver(
      tester,
      harness.dependencies,
      assignment: _machinery,
      duty: const DriverDutyState.none(),
    );

    expect(find.text('CAT 320'), findsOneWidget);
    expect(find.text('EXC-01'), findsOneWidget);
    expect(find.text('Test Site B'), findsOneWidget);
    expect(find.text('START DUTY'), findsOneWidget);
    expect(find.text('EMERGENCY'), findsOneWidget);
    expect(find.text('TRIP COMPLETE'), findsNothing);
    expect(find.text('DIESEL'), findsNothing);
    expect(find.text('HMR READING'), findsNothing);
    expect(find.text('MAINTENANCE'), findsNothing);
    expect(find.text('END DUTY'), findsNothing);
  });

  testWidgets('on-duty machinery omits Trip and keeps End Duty last', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(390, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final harness = _Harness();
    addTearDown(harness.close);
    await _pumpDriver(
      tester,
      harness.dependencies,
      assignment: _machinery,
      duty: const DriverDutyState(status: DriverDutyStatus.active),
    );

    expect(find.text('EMERGENCY'), findsOneWidget);
    expect(find.text('DIESEL'), findsOneWidget);
    expect(find.text('MAINTENANCE'), findsOneWidget);
    expect(find.text('Coming later'), findsOneWidget);
    expect(find.text('END DUTY'), findsOneWidget);
    expect(find.text('TRIP COMPLETE'), findsNothing);
    expect(find.text('HMR READING'), findsNothing);
    expect(
      tester.getTopLeft(find.text('END DUTY')).dy,
      greaterThan(tester.getTopLeft(find.text('MAINTENANCE')).dy),
    );
  });

  testWidgets('dual-meter tipper captures KM and HMR in one duty form', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(800, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final harness = _Harness();
    addTearDown(harness.close);

    await _pumpDriver(
      tester,
      harness.dependencies,
      assignment: _tipper,
      duty: const DriverDutyState.none(),
    );
    await tester.tap(find.text('START DUTY'));
    await tester.pumpAndSettle();
    expect(find.text('START READINGS'), findsOneWidget);
    expect(find.text('Odometer KM'), findsOneWidget);
    expect(find.text('Hour Meter / HMR'), findsOneWidget);
    await tester.tap(find.text('CANCEL'));
    await tester.pumpAndSettle();

    await _pumpDriver(
      tester,
      harness.dependencies,
      assignment: _tipper,
      duty: const DriverDutyState(status: DriverDutyStatus.active),
    );
    await tester.tap(find.text('END DUTY'));
    await tester.pumpAndSettle();
    expect(find.text('END READINGS'), findsOneWidget);
    expect(find.text('Odometer KM'), findsOneWidget);
    expect(find.text('Hour Meter / HMR'), findsOneWidget);
  });

  testWidgets('machinery duty start and end require the matching HMR', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(800, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final harness = _Harness();
    addTearDown(harness.close);

    await _pumpDriver(
      tester,
      harness.dependencies,
      assignment: _machinery,
      duty: const DriverDutyState.none(),
    );
    await tester.tap(find.text('START DUTY'));
    await tester.pumpAndSettle();
    expect(find.text('START HMR'), findsOneWidget);
    expect(find.text('Hours'), findsOneWidget);
    await tester.tap(find.text('CANCEL'));
    await tester.pumpAndSettle();

    await _pumpDriver(
      tester,
      harness.dependencies,
      assignment: _machinery,
      duty: const DriverDutyState(status: DriverDutyStatus.active),
    );
    await tester.tap(find.text('END DUTY'));
    await tester.pumpAndSettle();
    expect(find.text('END HMR'), findsOneWidget);
    expect(find.text('Hours'), findsOneWidget);
  });

  testWidgets('rejected START keeps an explicit secondary correction path', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(800, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final harness = _Harness();
    addTearDown(harness.close);
    await _pumpDriver(
      tester,
      harness.dependencies,
      assignment: _tipper,
      duty: const DriverDutyState(
        status: DriverDutyStatus.active,
        localState: LocalDutyState.needsAttention,
      ),
    );

    expect(find.text('KM READING'), findsNothing);
    expect(find.text('CORRECT START KM + HMR'), findsOneWidget);
    await tester.tap(find.text('CORRECT START KM + HMR'));
    await tester.pumpAndSettle();
    expect(find.text('START READINGS'), findsOneWidget);
    await tester.tap(find.text('CANCEL'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('END DUTY'));
    await tester.pumpAndSettle();
    expect(find.text('END READINGS'), findsOneWidget);
    expect(find.text('Correct the rejected START KM'), findsNothing);
  });

  testWidgets('rejected machinery START keeps correction separate from END', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(800, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final harness = _Harness();
    addTearDown(harness.close);
    await _pumpDriver(
      tester,
      harness.dependencies,
      assignment: _machinery,
      duty: const DriverDutyState(
        status: DriverDutyStatus.active,
        localState: LocalDutyState.needsAttention,
      ),
    );

    expect(find.text('CORRECT START HMR'), findsOneWidget);
    await tester.tap(find.text('CORRECT START HMR'));
    await tester.pumpAndSettle();
    expect(find.text('START HMR'), findsOneWidget);
    await tester.tap(find.text('CANCEL'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('END DUTY'));
    await tester.pumpAndSettle();
    expect(find.text('END HMR'), findsOneWidget);
    expect(find.text('Correct the rejected START HMR'), findsNothing);
  });

  testWidgets('Diesel keeps its event type and payload in the offline queue', (
    tester,
  ) async {
    final harness = _Harness();
    addTearDown(harness.close);
    await _pumpDriver(
      tester,
      harness.dependencies,
      assignment: _tipper,
      duty: const DriverDutyState(status: DriverDutyStatus.active),
    );

    await tester.tap(find.text('DIESEL'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '25.5');
    await tester.tap(find.text('CONTINUE'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue Without Photo'));
    await tester.pump();

    final queued = await harness.database.pendingForSync();
    expect(queued, hasLength(1));
    expect(queued.single.eventType, 'DIESEL');
    expect(queued.single.payloadJson, contains('"litres":"25.5"'));
    expect(find.text('Diesel recorded'), findsOneWidget);
  });

  testWidgets('Emergency remains available and keeps local-first delivery', (
    tester,
  ) async {
    final harness = _Harness();
    addTearDown(harness.close);
    await _pumpDriver(
      tester,
      harness.dependencies,
      assignment: _tipper,
      duty: const DriverDutyState.none(),
    );

    await tester.tap(find.text('EMERGENCY'));
    await tester.pumpAndSettle();
    expect(find.text('Send emergency alert?'), findsOneWidget);
    await tester.tap(find.text('NO'));
    await tester.pumpAndSettle();
    expect(await harness.database.pendingForSync(), isEmpty);

    await tester.tap(find.text('EMERGENCY'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('SEND'));
    await tester.pump();
    expect(
      find.text('Emergency saved on phone — not yet delivered'),
      findsOneWidget,
    );
    final queued = await harness.database.pendingForSync();
    expect(queued, hasLength(1));
    expect(queued.single.eventType, 'EMERGENCY');
  });

  for (final width in [360.0, 390.0, 412.0]) {
    testWidgets('driver layouts fit Android width ${width.toInt()}', (
      tester,
    ) async {
      await tester.binding.setSurfaceSize(Size(width, 900));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final harness = _Harness();
      addTearDown(harness.close);

      await _pumpDriver(
        tester,
        harness.dependencies,
        assignment: _tipper,
        duty: const DriverDutyState(status: DriverDutyStatus.active),
      );
      expect(find.text('TRIP COMPLETE'), findsOneWidget);
      expect(find.text('DIESEL'), findsOneWidget);
      expect(tester.takeException(), isNull);

      await _pumpDriver(
        tester,
        harness.dependencies,
        assignment: _machinery,
        duty: const DriverDutyState.none(),
      );
      expect(find.text('START DUTY'), findsOneWidget);
      expect(find.text('EMERGENCY'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('absurd START KM is rejected before offline enqueue', (
    tester,
  ) async {
    final harness = _Harness();
    addTearDown(harness.close);
    await _pumpDriver(
      tester,
      harness.dependencies,
      assignment: _tipper,
      duty: const DriverDutyState.none(),
    );
    await tester.tap(find.text('START DUTY'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).first, '5676543455.81');
    await tester.enterText(find.byType(TextField).last, '1250.25');
    await tester.tap(find.text('CONTINUE'));
    await tester.pump();

    expect(
      find.text(
        'Enter both valid readings. Neither meter is optional for this asset.',
      ),
      findsOneWidget,
    );
    expect(await harness.database.pendingForSync(), isEmpty);
  });

  testWidgets('pending and confirmed starts keep working actions available', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(800, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final harness = _Harness();
    addTearDown(harness.close);

    for (final localState in [
      LocalDutyState.startPendingSync,
      LocalDutyState.activeConfirmed,
      LocalDutyState.needsAttention,
    ]) {
      await _pumpDriver(
        tester,
        harness.dependencies,
        assignment: _tipper,
        duty: DriverDutyState(
          status: DriverDutyStatus.active,
          localState: localState,
        ),
      );
      for (final label in [
        'TRIP COMPLETE',
        'DIESEL',
        'EMERGENCY',
        'END DUTY',
      ]) {
        expect(
          tester
              .widget<FilledButton>(find.widgetWithText(FilledButton, label))
              .onPressed,
          isNotNull,
        );
      }
      expect(find.text('KM READING'), findsNothing);
    }
  });

  testWidgets('manual Sync refreshes no-assignment and asset changes', (
    tester,
  ) async {
    final harness = _Harness();
    addTearDown(harness.close);
    const rented = DriverAssignment(
      assignmentId: 'assignment-rented',
      tipperId: 'rented',
      tipperRegistrationNumber: 'TESTRENT03',
      tipperShortName: 'Rented tipper 3',
      siteId: 'site',
      siteName: 'Test Site B',
      supervisorName: 'Test Supervisor Two',
    );
    DriverAssignment? current = _tipper;
    DriverAssignment? next;
    late StateSetter updateHarness;

    await tester.pumpWidget(
      StatefulBuilder(
        builder: (context, setState) {
          updateHarness = setState;
          return MaterialApp(
            home: DriverHomeScreen(
              dependencies: harness.dependencies,
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
    for (final label in ['START DUTY', 'EMERGENCY']) {
      expect(
        tester
            .widget<FilledButton>(find.widgetWithText(FilledButton, label))
            .onPressed,
        isNull,
      );
    }
    expect(find.text('TRIP COMPLETE'), findsNothing);
    expect(find.text('DIESEL'), findsNothing);

    next = rented;
    await tester.tap(find.byTooltip('Sync'));
    await tester.pumpAndSettle();
    expect(find.text('TESTRENT03'), findsOneWidget);
    expect(find.text('Test Site B'), findsOneWidget);
    expect(find.text('KA01AB1234'), findsNothing);

    next = _tipper;
    await tester.tap(find.byTooltip('Sync'));
    await tester.pumpAndSettle();
    expect(find.text('KA01AB1234'), findsOneWidget);
    expect(find.text('TESTRENT03'), findsNothing);
  });
}

Future<void> _pumpDriver(
  WidgetTester tester,
  DriverAppDependencies dependencies, {
  required DriverAssignment? assignment,
  required DriverDutyState duty,
}) async {
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
}

class _Harness {
  _Harness() {
    database = LocalDatabase(NativeDatabase.memory());
    dependencies = DriverAppDependencies(
      api: ApiClient(),
      sessionStore: SecureSessionStore(),
      sync: SyncEngine(
        database: database,
        remote: _FakeRemote(),
        installationIdentifier: 'test-device',
      ),
      installationIdentifier: 'test-device',
    );
  }

  late final LocalDatabase database;
  late final DriverAppDependencies dependencies;

  Future<void> close() => database.close();
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
