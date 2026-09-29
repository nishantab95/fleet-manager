import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:fleet_manager_mobile/data/api_client.dart';
import 'package:fleet_manager_mobile/data/local_database.dart'
    hide PendingEvent;
import 'package:fleet_manager_mobile/data/sync_engine.dart';
import 'package:fleet_manager_mobile/domain/driver_models.dart';

void main() {
  for (final status in [408, 429, 503]) {
    test('START HTTP $status remains operational and retryable', () async {
      final database = LocalDatabase(NativeDatabase.memory());
      final remote = _FailureRemote(
        submitError: ApiException(status, 'temporary failure'),
      );
      final engine = _engine(database, remote);
      await _start(engine);

      expect(await engine.syncPending(), 0);
      final duty = await engine.localDutyState(_assignment.assignmentId);
      expect(duty.localState, LocalDutyState.startPendingSync);
      expect(duty.isOperationallyActive, isTrue);
      expect(duty.canEnd, isTrue);
      await database.close();
    });
  }

  test('evidence validation error is not classified as bad START KM', () async {
    final database = LocalDatabase(NativeDatabase.memory());
    final remote = _FailureRemote(
      evidenceError: const ApiException(
        422,
        'unsupported evidence type',
        code: 'VALIDATION_ERROR',
      ),
    );
    final engine = _engine(database, remote);
    await _start(engine);

    expect(await engine.syncPending(), 0);
    final duty = await engine.localDutyState(_assignment.assignmentId);
    expect(duty.localState, LocalDutyState.startPendingSync);
    expect(duty.isOperationallyActive, isTrue);
    expect(await engine.lastSyncHttpStatus(), '422');
    expect(await engine.lastSyncErrorCode(), 'VALIDATION_ERROR');
    expect(await engine.lastSyncFailureStage(), 'EVIDENCE_UPLOAD');
    expect(remote.submitAttempts, 0);
    await database.close();
  });

  test(
    'bad START preserves later capture, blocks dependents, and lets emergency pass',
    () async {
      final database = LocalDatabase(NativeDatabase.memory());
      final remote = _FailureRemote(rejectStartCount: 99);
      final engine = _engine(database, remote);
      await _start(engine);
      expect(await engine.syncPending(), 0);

      final trip = await engine.enqueue(
        assignment: _assignment,
        eventType: DriverEventType.tripComplete,
      );
      final diesel = await engine.enqueue(
        assignment: _assignment,
        eventType: DriverEventType.diesel,
        payload: {'litres': '30'},
      );
      final end = await engine.enqueue(
        assignment: _assignment,
        eventType: DriverEventType.kmReading,
        payload: {'reading_type': 'END_READING', 'reading_value': '52400'},
        evidencePath: 'end.jpg',
      );
      final emergency = await engine.enqueue(
        assignment: _assignment,
        eventType: DriverEventType.emergency,
      );

      expect(await engine.syncPending(), 1);
      expect(
        (await database.eventById(trip))?.syncState,
        'blockedPendingStartCorrection',
      );
      expect(
        (await database.eventById(diesel))?.syncState,
        'blockedPendingStartCorrection',
      );
      expect(
        (await database.eventById(end))?.syncState,
        'blockedPendingStartCorrection',
      );
      expect((await database.eventById(emergency))?.syncState, 'synced');
      expect(await engine.pendingCount(), 4);
      expect(remote.acceptedTypes, [DriverEventType.emergency]);
      final duty = await engine.localDutyState(_assignment.assignmentId);
      expect(duty.localState, LocalDutyState.needsAttention);
      expect(duty.endKm, 52400);
      expect(duty.canCorrectStart, isTrue);
      await database.close();
    },
  );

  test(
    'corrected START releases dependents in original causal order',
    () async {
      final database = LocalDatabase(NativeDatabase.memory());
      final remote = _FailureRemote(rejectStartCount: 1);
      final engine = _engine(database, remote);
      final start = await _start(engine, reading: '51000');
      final trip = await engine.enqueue(
        assignment: _assignment,
        eventType: DriverEventType.tripComplete,
      );

      expect(await engine.syncPending(), 0);
      expect(
        (await database.eventById(trip))?.syncState,
        'blockedPendingStartCorrection',
      );
      expect(
        await engine.correctStart(
          assignmentId: _assignment.assignmentId,
          readingValue: '52300',
          evidencePath: 'corrected-start.jpg',
        ),
        start,
      );

      expect(await engine.syncPending(), 2);
      expect(remote.acceptedTypes, [
        DriverEventType.kmReading,
        DriverEventType.tripComplete,
      ]);
      expect((await database.eventById(start))?.syncState, 'synced');
      expect((await database.eventById(trip))?.syncState, 'synced');
      expect(
        (await engine.localDutyState(_assignment.assignmentId)).startKm,
        52300,
      );
      await database.close();
    },
  );
}

SyncEngine _engine(LocalDatabase database, DriverRemoteApi remote) =>
    SyncEngine(
      database: database,
      remote: remote,
      installationIdentifier: 'test-device',
    );

Future<String> _start(SyncEngine engine, {String reading = '52300'}) =>
    engine.enqueue(
      assignment: _assignment,
      eventType: DriverEventType.kmReading,
      payload: {'reading_type': 'START_READING', 'reading_value': reading},
      evidencePath: 'start.jpg',
    );

const _assignment = DriverAssignment(
  assignmentId: 'assignment',
  tipperId: 'tipper',
  tipperRegistrationNumber: 'KA01AB1234',
  tipperShortName: 'Pilot tipper',
  siteId: 'site',
  siteName: 'Pilot site',
  supervisorName: 'Supervisor',
);

class _FailureRemote implements DriverRemoteApi {
  _FailureRemote({
    this.evidenceError,
    this.submitError,
    this.rejectStartCount = 0,
  });

  final ApiException? evidenceError;
  final ApiException? submitError;
  int rejectStartCount;
  int submitAttempts = 0;
  final List<DriverEventType> acceptedTypes = [];

  @override
  Future<void> registerDevice({required String installationIdentifier}) async {}

  @override
  Future<String> uploadEvidence({
    required String clientEventUuid,
    required String evidencePath,
  }) async {
    if (evidenceError case final error?) throw error;
    return 'evidence/$clientEventUuid';
  }

  @override
  Future<void> submitEvent({
    required PendingEvent event,
    required String installationIdentifier,
  }) async {
    submitAttempts++;
    if (submitError case final error?) throw error;
    if (event.eventType == DriverEventType.kmReading &&
        event.payload['reading_type'] == 'START_READING' &&
        rejectStartCount > 0) {
      rejectStartCount--;
      throw const ApiException(
        422,
        'START KM does not continue the last known odometer.',
        code: 'ODOMETER_CONTINUITY',
      );
    }
    acceptedTypes.add(event.eventType);
  }
}
