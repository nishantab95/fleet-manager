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

      await engine.enqueue(
        assignment: assignment,
        eventType: DriverEventType.tripComplete,
      );
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

      expect(await engine.syncPending(), 4);
      expect(remote.eventTypes, [
        DriverEventType.kmReading,
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
    expect((await database.eventById(tripId))?.syncState, 'blocked');
    expect(remote.eventTypes, [DriverEventType.kmReading]);
    await database.close();
  });
}

bool _hasNoLocalEnvelope(Map<String, dynamic> payload) =>
    !payload.containsKey('_duty_session_id') &&
    !payload.containsKey('_depends_on_event_uuid');

class _RecordingRemote implements DriverRemoteApi {
  _RecordingRemote({this.rejectStart = false});

  final bool rejectStart;
  final List<DriverEventType> eventTypes = <DriverEventType>[];
  final List<Map<String, dynamic>> payloads = <Map<String, dynamic>>[];

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
  }) async {
    eventTypes.add(event.eventType);
    payloads.add(event.payload);
    if (rejectStart &&
        event.eventType == DriverEventType.kmReading &&
        event.payload['reading_type'] == 'START_READING') {
      throw const ApiException(
        422,
        'START KM does not continue the last known odometer.',
        code: 'ODOMETER_CONTINUITY',
      );
    }
  }
}
