import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:fleet_manager_mobile/data/api_client.dart';
import 'package:fleet_manager_mobile/data/local_database.dart'
    hide PendingEvent;
import 'package:fleet_manager_mobile/data/sync_engine.dart';
import 'package:fleet_manager_mobile/domain/driver_models.dart';
import 'package:fleet_manager_mobile/domain/role_models.dart';

void main() {
  test(
    'retryable network failure retains the event and later syncs it',
    () async {
      final database = LocalDatabase(NativeDatabase.memory());
      final remote = _ControlledRemote()..submitFailures = 1;
      final engine = SyncEngine(
        database: database,
        remote: remote,
        installationIdentifier: 'test-device',
      );
      final id = await engine.enqueue(
        assignment: _assignment,
        eventType: DriverEventType.tripComplete,
      );

      expect(await engine.syncPending(), 0);
      expect((await database.eventById(id))?.syncState, 'syncFailed');
      expect(await engine.lastSyncErrorCategory(), 'BACKEND_UNAVAILABLE');

      expect(await engine.syncPending(), 1);
      expect((await database.eventById(id))?.syncState, 'synced');
      await database.close();
    },
  );

  test(
    'server commit followed by a lost response remains logically idempotent',
    () async {
      final database = LocalDatabase(NativeDatabase.memory());
      final remote = _ControlledRemote()..commitThenFail = true;
      final engine = SyncEngine(
        database: database,
        remote: remote,
        installationIdentifier: 'test-device',
      );
      final id = await engine.enqueue(
        assignment: _assignment,
        eventType: DriverEventType.tripComplete,
      );

      expect(await engine.syncPending(), 0);
      expect(await engine.syncPending(), 1);
      expect(remote.logicalEvents, {id});
      expect(remote.submitAttempts, 2);
      await database.close();
    },
  );

  test(
    'expired access token refreshes once before retrying the queued event',
    () async {
      final database = LocalDatabase(NativeDatabase.memory());
      final remote = _ControlledRemote()..unauthorizedOnce = true;
      var refreshes = 0;
      final engine = SyncEngine(
        database: database,
        remote: remote,
        installationIdentifier: 'test-device',
        refreshSession: () async => refreshes++,
      );
      await engine.enqueue(
        assignment: _assignment,
        eventType: DriverEventType.tripComplete,
      );

      expect(await engine.syncPending(), 1);
      expect(refreshes, 1);
      await database.close();
    },
  );

  test('evidence outage does not submit or lose the event', () async {
    final database = LocalDatabase(NativeDatabase.memory());
    final remote = _ControlledRemote()..evidenceFailures = 1;
    final engine = SyncEngine(
      database: database,
      remote: remote,
      installationIdentifier: 'test-device',
    );
    final id = await engine.enqueue(
      assignment: _assignment,
      eventType: DriverEventType.diesel,
      payload: {'litres': '30'},
      evidencePath: 'meter.jpg',
    );

    expect(await engine.syncPending(), 0);
    expect(remote.submitAttempts, 0);
    expect((await database.eventById(id))?.syncState, 'syncFailed');
    await database.close();
  });

  test(
    'maintenance proof uploads first and survives a retryable submit failure',
    () async {
      final database = LocalDatabase(NativeDatabase.memory());
      final remote = _ControlledRemote()..maintenanceFailures = 1;
      final engine = SyncEngine(
        database: database,
        remote: remote,
        installationIdentifier: 'test-device',
      );
      final id = await engine.enqueue(
        assignment: _assignment,
        eventType: DriverEventType.maintenanceProof,
        payload: {'schedule_id': 'schedule-1'},
        evidencePath: 'service.jpg',
      );

      expect(await engine.syncPending(), 0);
      expect((await database.eventById(id))?.syncState, 'syncFailed');
      expect(remote.submitAttempts, 0);

      expect(await engine.syncPending(), 1);
      expect((await database.eventById(id))?.syncState, 'synced');
      expect(remote.maintenanceSubmissions, 2);
      expect(remote.lastMaintenancePayload?['schedule_id'], 'schedule-1');
      expect(
        remote.lastMaintenancePayload?['object_reference'],
        'evidence/$id',
      );
      await database.close();
    },
  );

  test('due maintenance list survives an offline restart cache read', () async {
    final database = LocalDatabase(NativeDatabase.memory());
    final engine = SyncEngine(
      database: database,
      remote: _ControlledRemote(),
      installationIdentifier: 'test-device',
    );
    await engine.cacheDueMaintenance(const [
      DriverMaintenanceItem(
        scheduleId: 'schedule-1',
        assetId: 'asset-1',
        taskLabel: 'Engine oil',
        status: 'OVERDUE',
      ),
    ], assignmentId: 'assignment');

    final restarted = SyncEngine(
      database: database,
      remote: _ControlledRemote(),
      installationIdentifier: 'test-device',
    );
    final cached = await restarted.localDueMaintenance(
      assignmentId: 'assignment',
    );
    expect(cached, hasLength(1));
    expect(cached.single.taskLabel, 'Engine oil');
    expect(cached.single.status, 'OVERDUE');
    expect(
      await restarted.localDueMaintenance(assignmentId: 'other-assignment'),
      isEmpty,
    );
    await database.close();
  });
}

const _assignment = DriverAssignment(
  assignmentId: 'assignment',
  tipperId: 'tipper',
  tipperRegistrationNumber: 'PILOT-12',
  tipperShortName: 'Tipper 12',
  siteId: 'site',
  siteName: 'Pilot Site',
  supervisorName: 'Pilot Supervisor',
);

class _ControlledRemote implements DriverRemoteApi, DriverMaintenanceRemote {
  int submitFailures = 0;
  int evidenceFailures = 0;
  int maintenanceFailures = 0;
  bool unauthorizedOnce = false;
  bool commitThenFail = false;
  int submitAttempts = 0;
  int maintenanceSubmissions = 0;
  Map<String, dynamic>? lastMaintenancePayload;
  final Set<String> logicalEvents = <String>{};

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
  }) async {
    if (evidenceFailures > 0) {
      evidenceFailures--;
      throw const ApiException(503, 'object storage unavailable');
    }
    return 'evidence/$clientEventUuid';
  }

  @override
  Future<void> submitEvent({
    required PendingEvent event,
    required String installationIdentifier,
  }) async {
    submitAttempts++;
    if (unauthorizedOnce) {
      unauthorizedOnce = false;
      throw const ApiException(401, 'expired');
    }
    if (submitFailures > 0) {
      submitFailures--;
      throw const ApiException(503, 'backend unavailable');
    }
    logicalEvents.add(event.clientEventUuid);
    if (commitThenFail) {
      commitThenFail = false;
      throw const ApiException(503, 'response lost after commit');
    }
  }

  @override
  Future<void> submitMaintenanceProof({required PendingEvent event}) async {
    maintenanceSubmissions++;
    lastMaintenancePayload = event.payload;
    if (maintenanceFailures > 0) {
      maintenanceFailures--;
      throw const ApiException(503, 'maintenance endpoint unavailable');
    }
  }
}
