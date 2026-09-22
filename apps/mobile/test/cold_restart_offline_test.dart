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
    'durable queue survives a cold database restart and syncs once',
    () async {
      final directory = await Directory.systemTemp.createTemp(
        'fleet-manager-cold-restart-',
      );
      final databaseFile = File(
        '${directory.path}${Platform.pathSeparator}driver.sqlite',
      );
      final remote = _IdempotentRemote();
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
      final firstEngine = SyncEngine(
        database: database,
        remote: remote,
        installationIdentifier: 'pilot-device',
      );
      final eventId = await firstEngine.enqueue(
        assignment: assignment,
        eventType: DriverEventType.kmReading,
        payload: {'reading_type': 'START_READING', 'reading_value': '10000'},
        evidencePath: 'pilot-meter.jpg',
      );
      expect(await database.eventById(eventId), isNotNull);
      await database.close();

      // A new LocalDatabase instance models a terminated process reopening the
      // same on-device SQLite file; this is deliberately not an in-memory DB.
      database = LocalDatabase(NativeDatabase(databaseFile));
      final restartedEngine = SyncEngine(
        database: database,
        remote: remote,
        installationIdentifier: 'pilot-device',
      );
      expect((await database.pendingForSync()).single.clientEventUuid, eventId);
      expect(await restartedEngine.syncPending(), 1);
      expect(remote.submittedEventIds, {eventId});

      await database.close();
      database = LocalDatabase(NativeDatabase(databaseFile));
      final secondRestartEngine = SyncEngine(
        database: database,
        remote: remote,
        installationIdentifier: 'pilot-device',
      );
      expect(await secondRestartEngine.syncPending(), 0);
      expect(remote.submissionCount(eventId), 1);
      await database.close();
      await directory.delete(recursive: true);
    },
  );
}

class _IdempotentRemote implements DriverRemoteApi {
  final Set<String> submittedEventIds = <String>{};
  final Map<String, int> _submissions = <String, int>{};

  int submissionCount(String eventId) => _submissions[eventId] ?? 0;

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
    _submissions.update(
      event.clientEventUuid,
      (count) => count + 1,
      ifAbsent: () => 1,
    );
    submittedEventIds.add(event.clientEventUuid);
  }
}
