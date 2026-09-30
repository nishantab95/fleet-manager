import 'dart:io';

import 'package:drift/native.dart';
import 'package:fleet_manager_mobile/data/api_client.dart';
import 'package:fleet_manager_mobile/data/local_database.dart' as local;
import 'package:fleet_manager_mobile/data/sync_engine.dart';
import 'package:fleet_manager_mobile/domain/driver_models.dart';
import 'package:flutter_test/flutter_test.dart';

const _server = 'http://pilot.test:8000';
const _company = 'company-a';
const _driver = 'driver-a';

const _owned = DriverAssignment(
  assignmentId: 'assignment-owned',
  tipperId: 'owned-tipper',
  tipperRegistrationNumber: 'TESTOWN02',
  tipperShortName: 'Owned tipper 2',
  siteId: 'test-site',
  siteName: 'Test Site B',
  supervisorName: 'Test Supervisor Two',
);

const _rented = DriverAssignment(
  assignmentId: 'assignment-rented',
  tipperId: 'rented-tipper',
  tipperRegistrationNumber: 'TESTRENT03',
  tipperShortName: 'Rented tipper 3',
  siteId: 'test-site',
  siteName: 'Test Site B',
  supervisorName: 'Test Supervisor Two',
);

void main() {
  test(
    'server-confirmed none clears current cache but preserves duty history',
    () async {
      final database = local.LocalDatabase(NativeDatabase.memory());
      addTearDown(database.close);
      final remote = _StateRemote(assignment: null);
      final sync = _engine(database, remote);
      await _activate(sync);
      await sync.cacheCurrentAssignment(_owned);
      await database.saveLocalDutySession(_closedDuty(), makeCurrent: true);

      final state = await sync.reconcileDriverState();

      expect(state.authority, DriverAssignmentAuthority.serverNoAssignment);
      expect(state.assignment, isNull);
      expect(await sync.localAssignment(), isNull);
      expect(await database.allLocalDutySessions(), hasLength(1));
      expect(
        (await database.allLocalDutySessions()).single.assignmentId,
        _owned.assignmentId,
      );
    },
  );

  test('manual reconciliation follows OWN to RENT and back to OWN', () async {
    final database = local.LocalDatabase(NativeDatabase.memory());
    addTearDown(database.close);
    final remote = _StateRemote(assignment: _owned);
    final sync = _engine(database, remote);
    await _activate(sync);

    expect(
      (await sync.reconcileDriverState()).assignment?.assignmentId,
      _owned.assignmentId,
    );
    remote.assignment = _rented;
    expect(
      (await sync.reconcileDriverState()).assignment?.assignmentId,
      _rented.assignmentId,
    );
    remote.assignment = _owned;
    expect(
      (await sync.reconcileDriverState()).assignment?.assignmentId,
      _owned.assignmentId,
    );
  });

  test('server none and network failure retain distinct authority', () async {
    final database = local.LocalDatabase(NativeDatabase.memory());
    addTearDown(database.close);
    final remote = _StateRemote(assignment: _owned);
    final sync = _engine(database, remote);
    await _activate(sync);
    await sync.reconcileDriverState();

    remote.unavailable = true;
    var state = await sync.reconcileDriverState();
    expect(state.authority, DriverAssignmentAuthority.offlineCache);
    expect(state.assignment?.assignmentId, _owned.assignmentId);

    remote
      ..unavailable = false
      ..assignment = null;
    state = await sync.reconcileDriverState();
    expect(state.authority, DriverAssignmentAuthority.serverNoAssignment);
    expect(state.assignment, isNull);

    remote.unavailable = true;
    state = await sync.reconcileDriverState();
    expect(state.authority, DriverAssignmentAuthority.offlineCache);
    expect(state.assignment, isNull);
  });

  test('cold restart uses reachable server none and reassignment', () async {
    final directory = await Directory.systemTemp.createTemp(
      'fleet-assignment-reconciliation-',
    );
    final file = File(
      '${directory.path}${Platform.pathSeparator}driver.sqlite',
    );
    addTearDown(() async {
      if (directory.existsSync()) await directory.delete(recursive: true);
    });
    final remote = _StateRemote(assignment: _owned);

    var database = local.LocalDatabase(NativeDatabase(file));
    var sync = _engine(database, remote);
    await _activate(sync);
    await sync.reconcileDriverState();
    await database.close();

    remote.assignment = _rented;
    database = local.LocalDatabase(NativeDatabase(file));
    sync = _engine(database, remote);
    await _activate(sync);
    expect(
      (await sync.reconcileDriverState()).assignment?.assignmentId,
      _rented.assignmentId,
    );
    await database.close();

    remote.assignment = null;
    database = local.LocalDatabase(NativeDatabase(file));
    sync = _engine(database, remote);
    await _activate(sync);
    expect((await sync.reconcileDriverState()).assignment, isNull);
    await database.close();

    database = local.LocalDatabase(NativeDatabase(file));
    sync = _engine(database, remote);
    await _activate(sync);
    expect((await sync.reconcileDriverState()).assignment, isNull);
    expect(await sync.localAssignment(), isNull);
    await database.close();
  });

  test('active or unsynced local work blocks silent asset switching', () async {
    final database = local.LocalDatabase(NativeDatabase.memory());
    addTearDown(database.close);
    final remote = _StateRemote(assignment: _rented);
    final sync = _engine(database, remote);
    await _activate(sync);
    await sync.cacheCurrentAssignment(_owned);
    await sync.enqueue(
      assignment: _owned,
      eventType: DriverEventType.kmReading,
      payload: const {
        'reading_type': 'START_READING',
        'reading_value': '12000',
      },
    );

    final state = await sync.reconcileDriverState();

    expect(state.authority, DriverAssignmentAuthority.protectedLocalWork);
    expect(state.assignment?.assignmentId, _owned.assignmentId);
    expect(state.warning, contains('active or unsynced work'));
    expect(await sync.pendingCount(), 1);
  });
}

SyncEngine _engine(local.LocalDatabase database, _StateRemote remote) =>
    SyncEngine(
      database: database,
      remote: remote,
      installationIdentifier: 'phone-1',
    );

Future<void> _activate(SyncEngine engine) => engine.activateAccount(
  serverIdentity: _server,
  companyId: _company,
  membershipId: _driver,
);

local.LocalDutySession _closedDuty() {
  final started = DateTime.utc(2026, 9, 30, 2);
  return local.LocalDutySession(
    localSessionId: 'closed-duty',
    assignmentId: _owned.assignmentId,
    tipperId: _owned.tipperId,
    tipperRegistrationNumber: _owned.tipperRegistrationNumber,
    tipperShortName: _owned.tipperShortName,
    siteId: _owned.siteId,
    siteName: _owned.siteName,
    supervisorName: _owned.supervisorName,
    startClientEventUuid: 'start',
    startKm: 12000,
    startedAt: started,
    endClientEventUuid: 'end',
    endKm: 12020,
    endedAt: started.add(const Duration(minutes: 10)),
    state: LocalDutyState.closedConfirmed.name,
    serverSessionId: 'server-duty',
    lastEventUuid: 'end',
    createdAt: started,
    updatedAt: started.add(const Duration(minutes: 10)),
  );
}

class _StateRemote implements DriverRemoteApi, DriverStateLookup {
  _StateRemote({required this.assignment});

  DriverAssignment? assignment;
  bool unavailable = false;
  DriverDutyState duty = const DriverDutyState.none();

  @override
  Future<DriverAssignment?> currentAssignment() async {
    if (unavailable) throw const ApiException(503, 'offline');
    return assignment;
  }

  @override
  Future<DriverDutyState> currentDuty() async {
    if (unavailable) throw const ApiException(503, 'offline');
    return duty;
  }

  @override
  Future<DeviceRegistration> registerDevice({
    required String installationIdentifier,
    bool allowHandover = false,
    bool localStateClear = false,
  }) async => const DeviceRegistration(
    deviceId: 'device-1',
    membershipId: _driver,
    handedOver: false,
  );

  @override
  Future<void> submitEvent({
    required PendingEvent event,
    required String installationIdentifier,
  }) async {}

  @override
  Future<String> uploadEvidence({
    required String clientEventUuid,
    required String evidencePath,
  }) async => 'evidence/$clientEventUuid';
}
