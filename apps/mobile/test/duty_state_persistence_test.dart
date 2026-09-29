import 'dart:io';

import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:fleet_manager_mobile/data/api_client.dart';
import 'package:fleet_manager_mobile/data/local_database.dart'
    hide PendingEvent;
import 'package:fleet_manager_mobile/data/sync_engine.dart';
import 'package:fleet_manager_mobile/domain/driver_models.dart';

void main() {
  test(
    'offline duty state and causal event order survive a cold restart',
    () async {
      final directory = await Directory.systemTemp.createTemp(
        'fleet-manager-duty-state-',
      );
      final databaseFile = File(
        '${directory.path}${Platform.pathSeparator}driver.sqlite',
      );
      final remote = _RecordingRemote();
      const assignment = DriverAssignment(
        assignmentId: 'assignment-12',
        tipperId: 'tipper-12',
        tipperRegistrationNumber: 'PILOT-12',
        tipperShortName: 'Tipper 12',
        siteId: 'pilot-site',
        siteName: 'Pilot Site',
        supervisorName: 'Pilot Supervisor',
      );

      var database = LocalDatabase(NativeDatabase(databaseFile));
      var engine = SyncEngine(
        database: database,
        remote: remote,
        installationIdentifier: 'pilot-device',
      );
      await engine.enqueue(
        assignment: assignment,
        eventType: DriverEventType.kmReading,
        payload: {'reading_type': 'START_READING', 'reading_value': '10000'},
        evidencePath: 'pilot-start.jpg',
      );
      var localDuty = await engine.localDutyState(assignment.assignmentId);
      expect(localDuty.localState, LocalDutyState.startPendingSync);
      expect(localDuty.isOperationallyActive, isTrue);
      expect(localDuty.canEnd, isTrue);

      for (var trip = 0; trip < 4; trip++) {
        await engine.enqueue(
          assignment: assignment,
          eventType: DriverEventType.tripComplete,
        );
      }
      await engine.enqueue(
        assignment: assignment,
        eventType: DriverEventType.diesel,
        payload: {'litres': '30'},
      );
      await engine.enqueue(
        assignment: assignment,
        eventType: DriverEventType.kmReading,
        payload: {'reading_type': 'END_READING', 'reading_value': '10120'},
        evidencePath: 'pilot-end.jpg',
      );
      await database.close();

      database = LocalDatabase(NativeDatabase(databaseFile));
      engine = SyncEngine(
        database: database,
        remote: remote,
        installationIdentifier: 'pilot-device',
      );
      final restoredAssignment = await engine.localAssignment();
      expect(restoredAssignment?.assignmentId, assignment.assignmentId);
      expect(
        restoredAssignment?.tipperRegistrationNumber,
        assignment.tipperRegistrationNumber,
      );
      expect(restoredAssignment?.siteName, assignment.siteName);
      localDuty = await engine.localDutyState(assignment.assignmentId);
      expect(localDuty.localState, LocalDutyState.endPendingSync);
      expect(localDuty.isOperationallyActive, isFalse);
      expect(localDuty.endKm, 10120);

      expect(await engine.syncPending(), 7);
      expect(remote.eventTypes, [
        DriverEventType.kmReading,
        DriverEventType.tripComplete,
        DriverEventType.tripComplete,
        DriverEventType.tripComplete,
        DriverEventType.tripComplete,
        DriverEventType.diesel,
        DriverEventType.kmReading,
      ]);
      expect(remote.payloads.every(_hasNoLocalEnvelope), isTrue);

      localDuty = await engine.localDutyState(assignment.assignmentId);
      expect(localDuty.localState, LocalDutyState.closedConfirmed);
      expect(localDuty.canStart, isTrue);
      await database.close();

      database = LocalDatabase(NativeDatabase(databaseFile));
      engine = SyncEngine(
        database: database,
        remote: remote,
        installationIdentifier: 'pilot-device',
      );
      expect(
        (await engine.localDutyState(assignment.assignmentId)).localState,
        LocalDutyState.closedConfirmed,
      );
      await database.close();
      await directory.delete(recursive: true);
    },
  );

  test('deterministic START rejection blocks dependent events', () async {
    final database = LocalDatabase(NativeDatabase.memory());
    final remote = _RecordingRemote(rejectStart: true);
    const assignment = DriverAssignment(
      assignmentId: 'assignment-rejected',
      tipperId: 'tipper-rejected',
      tipperRegistrationNumber: 'PILOT-REJECTED',
      tipperShortName: 'Rejected Tipper',
      siteId: 'pilot-site',
      siteName: 'Pilot Site',
      supervisorName: 'Pilot Supervisor',
    );
    final engine = SyncEngine(
      database: database,
      remote: remote,
      installationIdentifier: 'pilot-device',
    );

    await engine.enqueue(
      assignment: assignment,
      eventType: DriverEventType.kmReading,
      payload: {'reading_type': 'START_READING', 'reading_value': '9000'},
      evidencePath: 'pilot-start.jpg',
    );
    final tripId = await engine.enqueue(
      assignment: assignment,
      eventType: DriverEventType.tripComplete,
    );

    expect(await engine.syncPending(), 0);
    expect(
      (await engine.localDutyState(assignment.assignmentId)).localState,
      LocalDutyState.needsAttention,
    );
    expect(
      (await database.eventById(tripId))?.syncState,
      'blockedPendingStartCorrection',
    );
    final duty = await engine.localDutyState(assignment.assignmentId);
    expect(duty.isOperationallyActive, isTrue);
    expect(duty.canEnd, isTrue);
    expect(remote.eventTypes, [DriverEventType.kmReading]);
    await database.close();
  });

  test(
    'legacy snapshots reconcile by start chronology, not retry updates',
    () async {
      final database = LocalDatabase(NativeDatabase.memory());
      final older = _localSession(
        id: 'session-a',
        startEventId: 'start-a',
        startedAt: DateTime.utc(2026, 9, 25, 8),
        updatedAt: DateTime.utc(2026, 9, 29, 10),
        state: 'needsAttention',
      );
      final newer = _localSession(
        id: 'session-b',
        startEventId: 'start-b',
        startedAt: DateTime.utc(2026, 9, 29, 9),
        updatedAt: DateTime.utc(2026, 9, 29, 9),
        state: 'startPendingSync',
      );

      // saveLocalDutySession without makeCurrent models data written by 1.0.3.
      await database.saveLocalDutySession(older);
      await database.saveLocalDutySession(newer);
      await database.reconcileCurrentDutySession();

      expect(
        (await database.latestLocalDutySession())?.localSessionId,
        'session-b',
      );
      await database.markDutyNeedsAttention('session-a');
      expect(
        (await database.latestLocalDutySession())?.localSessionId,
        'session-b',
      );
      await database.close();
    },
  );

  test('retry failure on old START cannot supersede newer duty', () async {
    final database = LocalDatabase(NativeDatabase.memory());
    final remote = _RecordingRemote(rejectFirstStartOnly: true);
    const assignment = DriverAssignment(
      assignmentId: 'assignment-current',
      tipperId: 'tipper-current',
      tipperRegistrationNumber: 'PILOT-CURRENT',
      tipperShortName: 'Current Tipper',
      siteId: 'pilot-site',
      siteName: 'Pilot Site',
      supervisorName: 'Pilot Supervisor',
    );
    final engine = SyncEngine(
      database: database,
      remote: remote,
      installationIdentifier: 'pilot-device',
    );

    await engine.enqueue(
      assignment: assignment,
      eventType: DriverEventType.kmReading,
      payload: {'reading_type': 'START_READING', 'reading_value': '9000'},
      evidencePath: 'old-start.jpg',
    );
    await Future<void>.delayed(const Duration(milliseconds: 2));
    await engine.enqueue(
      assignment: assignment,
      eventType: DriverEventType.kmReading,
      payload: {'reading_type': 'START_READING', 'reading_value': '9100'},
      evidencePath: 'new-start.jpg',
    );

    expect(await engine.syncPending(), 1);
    final sessions = await database.allLocalDutySessions();
    expect(sessions, hasLength(2));
    expect(
      sessions.firstWhere((item) => item.startKm == 9000).state,
      'needsAttention',
    );
    expect(
      sessions.firstWhere((item) => item.startKm == 9100).state,
      'activeConfirmed',
    );
    final current = await engine.localDutyState(assignment.assignmentId);
    expect(current.startKm, 9100);
    expect(current.localState, LocalDutyState.activeConfirmed);
    expect(current.isOperationallyActive, isTrue);
    expect(current.canEnd, isTrue);
    await database.close();
  });

  test(
    'DUTY_ALREADY_STARTED reconciles a matching active server duty',
    () async {
      final database = LocalDatabase(NativeDatabase.memory());
      const assignment = DriverAssignment(
        assignmentId: 'assignment-reconciled',
        tipperId: 'tipper-reconciled',
        tipperRegistrationNumber: 'PILOT-RECONCILED',
        tipperShortName: 'Reconciled Tipper',
        siteId: 'pilot-site',
        siteName: 'Pilot Site',
        supervisorName: 'Pilot Supervisor',
      );
      final remote = _RecordingRemote(
        rejectStart: true,
        startErrorCode: 'DUTY_ALREADY_STARTED',
        currentDutyState: DriverDutyState(
          status: DriverDutyStatus.active,
          localState: LocalDutyState.activeConfirmed,
          sessionId: 'server-duty',
          assignmentId: assignment.assignmentId,
          tipperId: assignment.tipperId,
          siteId: assignment.siteId,
          startedAt: DateTime.utc(2026, 9, 25),
          startKm: 10000,
        ),
      );
      final engine = SyncEngine(
        database: database,
        remote: remote,
        installationIdentifier: 'pilot-device',
      );

      final startId = await engine.enqueue(
        assignment: assignment,
        eventType: DriverEventType.kmReading,
        payload: {'reading_type': 'START_READING', 'reading_value': '12000'},
        evidencePath: 'duplicate-start.jpg',
      );
      final tripId = await engine.enqueue(
        assignment: assignment,
        eventType: DriverEventType.tripComplete,
      );
      final endId = await engine.enqueue(
        assignment: assignment,
        eventType: DriverEventType.kmReading,
        payload: {'reading_type': 'END_READING', 'reading_value': '12100'},
        evidencePath: 'end.jpg',
      );

      expect(await engine.syncPending(), 3);
      expect(
        (await database.eventById(startId))?.syncState,
        'reconciledActiveDuty',
      );
      expect((await database.eventById(tripId))?.syncState, 'synced');
      expect((await database.eventById(endId))?.syncState, 'synced');
      expect(await engine.pendingCount(), 0);
      final duty = await engine.localDutyState(assignment.assignmentId);
      expect(duty.localState, LocalDutyState.closedConfirmed);
      expect(duty.canStart, isTrue);
      await database.close();
    },
  );
}

LocalDutySession _localSession({
  required String id,
  required String startEventId,
  required DateTime startedAt,
  required DateTime updatedAt,
  required String state,
}) {
  return LocalDutySession(
    localSessionId: id,
    assignmentId: 'assignment-current',
    tipperId: 'tipper-current',
    tipperRegistrationNumber: 'PILOT-CURRENT',
    tipperShortName: 'Current Tipper',
    siteId: 'pilot-site',
    siteName: 'Pilot Site',
    supervisorName: 'Pilot Supervisor',
    startClientEventUuid: startEventId,
    startKm: id == 'session-a' ? 9000 : 9100,
    startedAt: startedAt,
    endClientEventUuid: null,
    endKm: null,
    endedAt: null,
    state: state,
    serverSessionId: null,
    lastEventUuid: startEventId,
    createdAt: startedAt,
    updatedAt: updatedAt,
  );
}

bool _hasNoLocalEnvelope(Map<String, dynamic> payload) =>
    !payload.containsKey('_duty_session_id') &&
    !payload.containsKey('_depends_on_event_uuid');

class _RecordingRemote implements DriverRemoteApi, DriverDutyLookup {
  _RecordingRemote({
    this.rejectStart = false,
    this.rejectFirstStartOnly = false,
    this.currentDutyState = const DriverDutyState.none(),
    this.startErrorCode = 'ODOMETER_CONTINUITY',
  });

  final bool rejectStart;
  final bool rejectFirstStartOnly;
  final DriverDutyState currentDutyState;
  final String startErrorCode;
  final List<DriverEventType> eventTypes = <DriverEventType>[];
  final List<Map<String, dynamic>> payloads = <Map<String, dynamic>>[];
  var _startAttempts = 0;

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
  Future<DriverDutyState> currentDuty() async => currentDutyState;

  @override
  Future<String> uploadEvidence({
    required String clientEventUuid,
    required String evidencePath,
  }) async => 'evidence/$clientEventUuid';

  @override
  Future<void> submitEvent({
    required PendingEvent event,
    required String installationIdentifier,
  }) async {
    eventTypes.add(event.eventType);
    payloads.add(event.payload);
    final isStart =
        event.eventType == DriverEventType.kmReading &&
        event.payload['reading_type'] == 'START_READING';
    if (isStart) _startAttempts++;
    if (isStart &&
        (rejectStart || (rejectFirstStartOnly && _startAttempts == 1))) {
      throw ApiException(
        startErrorCode == 'DUTY_ALREADY_STARTED' ? 409 : 422,
        startErrorCode == 'DUTY_ALREADY_STARTED'
            ? 'an active duty session already exists'
            : 'START KM does not continue the last known odometer.',
        code: startErrorCode,
      );
    }
  }
}
