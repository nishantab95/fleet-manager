import 'dart:convert';
import 'dart:io';

import 'package:drift/native.dart';
import 'package:fleet_manager_mobile/app.dart';
import 'package:fleet_manager_mobile/data/api_client.dart';
import 'package:fleet_manager_mobile/data/local_database.dart' as local;
import 'package:fleet_manager_mobile/data/secure_session_store.dart';
import 'package:fleet_manager_mobile/data/sync_engine.dart';
import 'package:fleet_manager_mobile/domain/driver_models.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _server = 'http://pilot.test:8000';
const _company = 'company-a';
const _driverA = 'driver-a';
const _driverB = 'driver-b';

void main() {
  test('pending Driver A event blocks handover and remains isolated', () async {
    final database = local.LocalDatabase(NativeDatabase.memory());
    final remote = _RecordingRemote();
    final engine = SyncEngine(
      database: database,
      remote: remote,
      installationIdentifier: 'phone-1',
    );
    addTearDown(database.close);

    await _activate(engine, _driverA);
    await engine.enqueue(
      assignment: _assignment('assignment-a'),
      eventType: DriverEventType.tripComplete,
    );

    final safety = await engine.prepareHandover(
      serverIdentity: _server,
      companyId: _company,
      oldMembershipId: _driverA,
    );
    expect(safety.isSafe, isFalse);
    expect(safety.unsyncedEventCount, 1);
    expect(safety.hasActiveDuty, isFalse);

    await _activate(engine, _driverB);
    expect(await engine.pendingCount(), 0);
    expect(await engine.localAssignment(), isNull);
    expect(await engine.syncPending(), 0);
    expect(remote.submittedEventIds, isEmpty);

    await _activate(engine, _driverA);
    expect(await engine.pendingCount(), 1);
    expect(await engine.diagnosticEventRows(), hasLength(1));
  });

  test('active Driver A duty blocks handover even after START sync', () async {
    final database = local.LocalDatabase(NativeDatabase.memory());
    final engine = SyncEngine(
      database: database,
      remote: _RecordingRemote(),
      installationIdentifier: 'phone-1',
    );
    addTearDown(database.close);

    await _activate(engine, _driverA);
    final startId = await engine.enqueue(
      assignment: _assignment('assignment-a'),
      eventType: DriverEventType.kmReading,
      payload: const {'reading_type': 'START_READING', 'reading_value': '100'},
    );
    await database.markSynced(startId);

    final safety = await engine.prepareHandover(
      serverIdentity: _server,
      companyId: _company,
      oldMembershipId: _driverA,
    );
    expect(safety.unsyncedEventCount, 0);
    expect(safety.hasActiveDuty, isTrue);
    expect(safety.isSafe, isFalse);
  });

  test(
    'closed current duty ignores a stale historical active snapshot',
    () async {
      final database = local.LocalDatabase(NativeDatabase.memory());
      addTearDown(database.close);
      final closed = _closedLegacyDuty();
      await database.saveLocalDutySession(
        local.LocalDutySession(
          localSessionId: 'stale-active-duty',
          assignmentId: closed.assignmentId,
          tipperId: closed.tipperId,
          tipperRegistrationNumber: closed.tipperRegistrationNumber,
          tipperShortName: closed.tipperShortName,
          siteId: closed.siteId,
          siteName: closed.siteName,
          supervisorName: closed.supervisorName,
          startClientEventUuid: 'stale-start',
          startKm: 14000,
          startedAt: closed.startedAt.subtract(const Duration(days: 1)),
          endClientEventUuid: null,
          endKm: null,
          endedAt: null,
          state: LocalDutyState.activeConfirmed.name,
          serverSessionId: 'stale-server-duty',
          lastEventUuid: 'stale-start',
          createdAt: closed.startedAt.subtract(const Duration(days: 1)),
          updatedAt: closed.startedAt.subtract(const Duration(days: 1)),
        ),
      );
      await database.saveLocalDutySession(closed, makeCurrent: true);

      final safety = await database.prepareHandover(
        SyncEngine.accountScope(
          serverIdentity: _server,
          companyId: _company,
          membershipId: _driverA,
        ),
      );

      expect(safety.unsyncedEventCount, 0);
      expect(safety.hasActiveDuty, isFalse);
      expect(safety.isSafe, isTrue);
    },
  );

  test(
    'legacy code8 state is archived to Driver A and survives restart',
    () async {
      final directory = await Directory.systemTemp.createTemp(
        'fleet-handover-',
      );
      final file = File(
        '${directory.path}${Platform.pathSeparator}driver.sqlite',
      );
      addTearDown(() async {
        if (directory.existsSync()) await directory.delete(recursive: true);
      });

      var database = local.LocalDatabase(NativeDatabase(file));
      final closed = _closedLegacyDuty();
      await database.saveLocalDutySession(closed, makeCurrent: true);
      await database.enqueue(
        local.PendingEventsCompanion.insert(
          clientEventUuid: 'legacy-event',
          eventType: 'TRIP_COMPLETE',
          assignmentId: closed.assignmentId,
          tipperId: closed.tipperId,
          siteId: closed.siteId,
          supervisorName: closed.supervisorName,
          deviceCreatedAt: closed.startedAt,
          syncState: 'synced',
          payloadJson: '{}',
          createdAt: closed.startedAt,
        ),
      );

      final scopeA = SyncEngine.accountScope(
        serverIdentity: _server,
        companyId: _company,
        membershipId: _driverA,
      );
      final safety = await database.prepareHandover(scopeA);
      expect(safety.isSafe, isTrue);
      await database.close();

      database = local.LocalDatabase(NativeDatabase(file));
      await database.activateAccount(
        SyncEngine.accountScope(
          serverIdentity: _server,
          companyId: _company,
          membershipId: _driverB,
        ),
      );
      expect(await database.latestLocalDutySession(), isNull);
      expect(await database.allEventsForDiagnostics(), isEmpty);

      await database.activateAccount(scopeA);
      expect(
        (await database.latestLocalDutySession())?.assignmentId,
        closed.assignmentId,
      );
      expect(await database.allEventsForDiagnostics(), hasLength(1));
      await database.close();
    },
  );

  test('schema v2 migration preserves code8 queue and duty snapshot', () async {
    final directory = await Directory.systemTemp.createTemp('fleet-schema-v2-');
    final file = File(
      '${directory.path}${Platform.pathSeparator}driver.sqlite',
    );
    addTearDown(() async {
      if (directory.existsSync()) await directory.delete(recursive: true);
    });
    final closed = _closedLegacyDuty();
    final database = local.LocalDatabase(
      NativeDatabase(
        file,
        setup: (raw) {
          raw.execute('PRAGMA user_version = 2');
          raw.execute('''
            CREATE TABLE pending_events (
              client_event_uuid TEXT NOT NULL PRIMARY KEY,
              event_type TEXT NOT NULL,
              assignment_id TEXT NOT NULL,
              tipper_id TEXT NOT NULL,
              site_id TEXT NOT NULL,
              supervisor_name TEXT NOT NULL,
              device_created_at INTEGER NOT NULL,
              sync_state TEXT NOT NULL,
              retry_count INTEGER NOT NULL DEFAULT 0,
              payload_json TEXT NOT NULL,
              evidence_path TEXT,
              last_sync_error TEXT,
              created_at INTEGER NOT NULL
            )
          ''');
          raw.execute('''
            CREATE TABLE sync_metadata (
              key TEXT NOT NULL PRIMARY KEY,
              value TEXT NOT NULL
            )
          ''');
          raw.execute(
            '''
              INSERT INTO pending_events (
                client_event_uuid, event_type, assignment_id, tipper_id,
                site_id, supervisor_name, device_created_at, sync_state,
                retry_count, payload_json, created_at
              ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            [
              'v2-event',
              'TRIP_COMPLETE',
              closed.assignmentId,
              closed.tipperId,
              closed.siteId,
              closed.supervisorName,
              closed.startedAt.millisecondsSinceEpoch,
              'synced',
              0,
              '{}',
              closed.startedAt.millisecondsSinceEpoch,
            ],
          );
          raw.execute('INSERT INTO sync_metadata (key, value) VALUES (?, ?)', [
            'local_duty:${closed.localSessionId}',
            jsonEncode(closed.toJson()),
          ]);
          raw.execute('INSERT INTO sync_metadata (key, value) VALUES (?, ?)', [
            'current_local_duty_session_id',
            closed.localSessionId,
          ]);
        },
      ),
    );
    addTearDown(database.close);

    final scopeA = SyncEngine.accountScope(
      serverIdentity: _server,
      companyId: _company,
      membershipId: _driverA,
    );
    await database.claimLegacyData(scopeA);
    await database.activateAccount(scopeA);

    expect(await database.allEventsForDiagnostics(), hasLength(1));
    expect(
      (await database.latestLocalDutySession())?.localSessionId,
      closed.localSessionId,
    );
  });

  test('clean registration preflight performs guarded handover', () async {
    final database = local.LocalDatabase(NativeDatabase.memory());
    addTearDown(database.close);
    await database.saveLocalDutySession(_closedLegacyDuty(), makeCurrent: true);
    final requests = <Map<String, dynamic>>[];
    final api = ApiClient(
      baseUrl: _server,
      client: MockClient((request) async {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        requests.add(body);
        if (body['allow_handover'] != true) {
          return http.Response(
            jsonEncode({
              'detail': {
                'code': 'DEVICE_HANDOVER_REQUIRED',
                'message': 'device handover confirmation is required',
                'current_membership_id': _driverA,
              },
            }),
            409,
          );
        }
        return http.Response(
          jsonEncode({
            'device_id': 'device-1',
            'membership_id': _driverB,
            'handed_over': true,
          }),
          200,
        );
      }),
    );
    const tokens = SessionTokens(
      accessToken: 'access',
      refreshToken: 'refresh',
      expiresIn: 900,
      membershipId: _driverB,
      companyId: _company,
      role: 'DRIVER',
    );
    api.setSession(tokens);
    final sync = SyncEngine(
      database: database,
      remote: api,
      installationIdentifier: 'phone-1',
    );
    final dependencies = DriverAppDependencies(
      api: api,
      sessionStore: SecureSessionStore(),
      sync: sync,
      installationIdentifier: 'phone-1',
    );

    await dependencies.registerDriverAccount(tokens);

    expect(requests, hasLength(2));
    expect(requests.first['allow_handover'], isFalse);
    expect(requests.last['allow_handover'], isTrue);
    expect(requests.last['local_state_clear'], isTrue);
    expect(await sync.localAssignment(), isNull);
    await _activate(sync, _driverA);
    expect(
      (await sync.localAssignment())?.assignmentId,
      _closedLegacyDuty().assignmentId,
    );
  });
}

Future<void> _activate(SyncEngine engine, String membershipId) {
  return engine.activateAccount(
    serverIdentity: _server,
    companyId: _company,
    membershipId: membershipId,
  );
}

DriverAssignment _assignment(String id) => DriverAssignment(
  assignmentId: id,
  tipperId: 'tipper-a',
  tipperRegistrationNumber: 'PILOT12',
  tipperShortName: 'Tipper 12',
  siteId: 'site-a',
  siteName: 'Pilot Site',
  supervisorName: 'Pilot Supervisor',
);

local.LocalDutySession _closedLegacyDuty() {
  final started = DateTime.utc(2026, 9, 29, 10);
  return local.LocalDutySession(
    localSessionId: 'legacy-duty',
    assignmentId: 'assignment-a',
    tipperId: 'tipper-a',
    tipperRegistrationNumber: 'PILOT12',
    tipperShortName: 'Tipper 12',
    siteId: 'site-a',
    siteName: 'Pilot Site',
    supervisorName: 'Pilot Supervisor',
    startClientEventUuid: 'legacy-start',
    startKm: 15000,
    startedAt: started,
    endClientEventUuid: 'legacy-end',
    endKm: 18000,
    endedAt: started.add(const Duration(hours: 1)),
    state: LocalDutyState.closedConfirmed.name,
    serverSessionId: 'server-duty',
    lastEventUuid: 'legacy-end',
    createdAt: started,
    updatedAt: started.add(const Duration(hours: 1)),
  );
}

class _RecordingRemote implements DriverRemoteApi {
  final List<String> submittedEventIds = [];

  @override
  Future<DeviceRegistration> registerDevice({
    required String installationIdentifier,
    bool allowHandover = false,
    bool localStateClear = false,
  }) async => const DeviceRegistration(
    deviceId: 'device-1',
    membershipId: _driverA,
    handedOver: false,
  );

  @override
  Future<void> submitEvent({
    required PendingEvent event,
    required String installationIdentifier,
  }) async {
    submittedEventIds.add(event.clientEventUuid);
  }

  @override
  Future<String> uploadEvidence({
    required String clientEventUuid,
    required String evidencePath,
  }) async => 'evidence/$clientEventUuid';
}
