import 'dart:convert';
import 'dart:io';

import 'package:drift/drift.dart';
import 'package:drift/native.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

part 'local_database.g.dart';

class PendingEvents extends Table {
  TextColumn get clientEventUuid => text()();
  TextColumn get eventType => text()();
  TextColumn get assignmentId => text()();
  TextColumn get tipperId => text()();
  TextColumn get siteId => text()();
  TextColumn get supervisorName => text()();
  DateTimeColumn get deviceCreatedAt => dateTime()();
  TextColumn get syncState => text()();
  IntColumn get retryCount => integer().withDefault(const Constant(0))();
  TextColumn get payloadJson => text()();
  TextColumn get evidencePath => text().nullable()();
  TextColumn get lastSyncError => text().nullable()();
  DateTimeColumn get createdAt => dateTime()();

  @override
  Set<Column<Object>> get primaryKey => {clientEventUuid};
}

class SyncMetadata extends Table {
  TextColumn get key => text()();
  TextColumn get value => text()();

  @override
  Set<Column<Object>> get primaryKey => {key};
}

class LocalDutySession {
  const LocalDutySession({
    required this.localSessionId,
    required this.assignmentId,
    required this.tipperId,
    required this.tipperRegistrationNumber,
    required this.tipperShortName,
    required this.siteId,
    required this.siteName,
    required this.supervisorName,
    required this.startClientEventUuid,
    required this.startKm,
    required this.startedAt,
    required this.endClientEventUuid,
    required this.endKm,
    required this.endedAt,
    required this.state,
    required this.serverSessionId,
    required this.lastEventUuid,
    required this.createdAt,
    required this.updatedAt,
  });

  final String localSessionId;
  final String assignmentId;
  final String tipperId;
  final String tipperRegistrationNumber;
  final String? tipperShortName;
  final String siteId;
  final String siteName;
  final String supervisorName;
  final String startClientEventUuid;
  final double startKm;
  final DateTime startedAt;
  final String? endClientEventUuid;
  final double? endKm;
  final DateTime? endedAt;
  final String state;
  final String? serverSessionId;
  final String? lastEventUuid;
  final DateTime createdAt;
  final DateTime updatedAt;

  LocalDutySession copyWith({
    double? startKm,
    String? state,
    String? serverSessionId,
    String? endClientEventUuid,
    double? endKm,
    DateTime? endedAt,
    String? lastEventUuid,
    DateTime? updatedAt,
  }) {
    return LocalDutySession(
      localSessionId: localSessionId,
      assignmentId: assignmentId,
      tipperId: tipperId,
      tipperRegistrationNumber: tipperRegistrationNumber,
      tipperShortName: tipperShortName,
      siteId: siteId,
      siteName: siteName,
      supervisorName: supervisorName,
      startClientEventUuid: startClientEventUuid,
      startKm: startKm ?? this.startKm,
      startedAt: startedAt,
      endClientEventUuid: endClientEventUuid ?? this.endClientEventUuid,
      endKm: endKm ?? this.endKm,
      endedAt: endedAt ?? this.endedAt,
      state: state ?? this.state,
      serverSessionId: serverSessionId ?? this.serverSessionId,
      lastEventUuid: lastEventUuid ?? this.lastEventUuid,
      createdAt: createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
    );
  }

  Map<String, dynamic> toJson() => {
    'localSessionId': localSessionId,
    'assignmentId': assignmentId,
    'tipperId': tipperId,
    'tipperRegistrationNumber': tipperRegistrationNumber,
    'tipperShortName': tipperShortName,
    'siteId': siteId,
    'siteName': siteName,
    'supervisorName': supervisorName,
    'startClientEventUuid': startClientEventUuid,
    'startKm': startKm,
    'startedAt': startedAt.toIso8601String(),
    'endClientEventUuid': endClientEventUuid,
    'endKm': endKm,
    'endedAt': endedAt?.toIso8601String(),
    'state': state,
    'serverSessionId': serverSessionId,
    'lastEventUuid': lastEventUuid,
    'createdAt': createdAt.toIso8601String(),
    'updatedAt': updatedAt.toIso8601String(),
  };

  factory LocalDutySession.fromJson(Map<String, dynamic> json) {
    return LocalDutySession(
      localSessionId: json['localSessionId'] as String,
      assignmentId: json['assignmentId'] as String,
      tipperId: json['tipperId'] as String,
      tipperRegistrationNumber: json['tipperRegistrationNumber'] as String,
      tipperShortName: json['tipperShortName'] as String?,
      siteId: json['siteId'] as String,
      siteName: json['siteName'] as String,
      supervisorName: json['supervisorName'] as String,
      startClientEventUuid: json['startClientEventUuid'] as String,
      startKm: (json['startKm'] as num).toDouble(),
      startedAt: DateTime.parse(json['startedAt'] as String).toUtc(),
      endClientEventUuid: json['endClientEventUuid'] as String?,
      endKm: (json['endKm'] as num?)?.toDouble(),
      endedAt: (json['endedAt'] as String?) == null
          ? null
          : DateTime.parse(json['endedAt'] as String).toUtc(),
      state: json['state'] as String,
      serverSessionId: json['serverSessionId'] as String?,
      lastEventUuid: json['lastEventUuid'] as String?,
      createdAt: DateTime.parse(json['createdAt'] as String).toUtc(),
      updatedAt: DateTime.parse(json['updatedAt'] as String).toUtc(),
    );
  }
}

@DriftDatabase(tables: [PendingEvents, SyncMetadata])
class LocalDatabase extends _$LocalDatabase {
  LocalDatabase(super.e);

  static const _currentDutySessionKey = 'current_local_duty_session_id';

  @override
  int get schemaVersion => 2;

  @override
  MigrationStrategy get migration => MigrationStrategy(
    onCreate: (m) => m.createAll(),
    onUpgrade: (m, from, to) async {
      if (from < 2) await m.createTable(syncMetadata);
    },
  );

  Future<void> setMetadata(String key, String value) {
    return into(syncMetadata).insertOnConflictUpdate(
      SyncMetadataCompanion.insert(key: key, value: value),
    );
  }

  Future<String?> metadata(String key) async {
    final row = await (select(
      syncMetadata,
    )..where((item) => item.key.equals(key))).getSingleOrNull();
    return row?.value;
  }

  Future<void> enqueue(PendingEventsCompanion event) {
    return into(pendingEvents).insertOnConflictUpdate(event);
  }

  Future<LocalDutySession?> latestLocalDutySession({
    String? assignmentId,
  }) async {
    final sessions = await allLocalDutySessions();
    if (sessions.isEmpty) return null;

    final currentId = await metadata(_currentDutySessionKey);
    LocalDutySession? current;
    for (final session in sessions) {
      if (session.localSessionId == currentId) {
        current = session;
        break;
      }
    }

    if (current == null) {
      // Reconcile databases written by releases before the explicit current
      // marker existed. Operational chronology is immutable: error retries may
      // change updatedAt, but must never make an old duty current again.
      current = sessions.first;
      await setMetadata(_currentDutySessionKey, current.localSessionId);
    }

    if (assignmentId == null || current.assignmentId == assignmentId) {
      return current;
    }

    for (final session in sessions) {
      if (session.assignmentId == assignmentId) return session;
    }
    return null;
  }

  Future<List<LocalDutySession>> allLocalDutySessions() async {
    final rows = await select(syncMetadata).get();
    final sessions = <LocalDutySession>[];
    for (final row in rows.where((row) => row.key.startsWith('local_duty:'))) {
      try {
        sessions.add(
          LocalDutySession.fromJson(
            jsonDecode(row.value) as Map<String, dynamic>,
          ),
        );
      } on Object {
        // Ignore a corrupt snapshot; the pending queue remains authoritative.
      }
    }
    sessions.sort(_compareDutyChronology);
    return sessions;
  }

  Future<void> reconcileCurrentDutySession() async {
    await latestLocalDutySession();
  }

  Future<LocalDutySession?> localDutySession(String localSessionId) async {
    final value = await metadata('local_duty:$localSessionId');
    if (value == null) return null;
    try {
      return LocalDutySession.fromJson(
        jsonDecode(value) as Map<String, dynamic>,
      );
    } on Object {
      return null;
    }
  }

  Future<void> saveLocalDutySession(
    LocalDutySession session, {
    bool makeCurrent = false,
  }) async {
    await setMetadata(
      'local_duty:${session.localSessionId}',
      jsonEncode(session.toJson()),
    );
    if (makeCurrent) {
      await setMetadata(_currentDutySessionKey, session.localSessionId);
    }
  }

  Future<void> updateLocalDutySession(LocalDutySession session) {
    return saveLocalDutySession(session);
  }

  Future<void> markDutyStartSynced(
    String localSessionId,
    DateTime updatedAt, {
    String? serverSessionId,
  }) async {
    final row = await localDutySession(localSessionId);
    if (row?.localSessionId == localSessionId) {
      await updateLocalDutySession(
        row!.copyWith(
          state: 'activeConfirmed',
          serverSessionId: serverSessionId,
          updatedAt: updatedAt,
        ),
      );
    }
  }

  Future<void> markDutyEndSynced(
    String localSessionId,
    DateTime updatedAt,
  ) async {
    final row = await localDutySession(localSessionId);
    if (row?.localSessionId == localSessionId) {
      await updateLocalDutySession(
        row!.copyWith(state: 'closedConfirmed', updatedAt: updatedAt),
      );
    }
  }

  Future<void> markDutyNeedsAttention(String localSessionId) async {
    final row = await localDutySession(localSessionId);
    if (row?.localSessionId == localSessionId) {
      await updateLocalDutySession(
        row!.copyWith(
          state: 'needsAttention',
          updatedAt: DateTime.now().toUtc(),
        ),
      );
    }
  }

  Future<void> blockDutyDependentEvents(
    String localSessionId,
    String startEventUuid,
  ) async {
    final rows = await select(pendingEvents).get();
    for (final row in rows) {
      final payload = _decodeEventPayload(row.payloadJson);
      if (payload['_duty_session_id'] != localSessionId ||
          row.clientEventUuid == startEventUuid ||
          row.syncState == 'synced' ||
          row.syncState == 'reconciledActiveDuty') {
        continue;
      }
      await (update(pendingEvents)
            ..where((item) => item.clientEventUuid.equals(row.clientEventUuid)))
          .write(
            const PendingEventsCompanion(
              syncState: Value('blockedPendingStartCorrection'),
              lastSyncError: Value('START_KM_NEEDS_CORRECTION'),
            ),
          );
    }
  }

  Future<void> unblockDutyDependentEvents(String localSessionId) async {
    final rows = await select(pendingEvents).get();
    for (final row in rows) {
      final payload = _decodeEventPayload(row.payloadJson);
      if (payload['_duty_session_id'] != localSessionId ||
          (row.syncState != 'blockedPendingStartCorrection' &&
              row.syncState != 'blocked')) {
        continue;
      }
      await (update(pendingEvents)
            ..where((item) => item.clientEventUuid.equals(row.clientEventUuid)))
          .write(
            const PendingEventsCompanion(
              syncState: Value('pending'),
              lastSyncError: Value(null),
            ),
          );
    }
  }

  Future<void> replaceEventForRetry({
    required String clientEventUuid,
    required String payloadJson,
    required String evidencePath,
  }) {
    return (update(
      pendingEvents,
    )..where((row) => row.clientEventUuid.equals(clientEventUuid))).write(
      PendingEventsCompanion(
        payloadJson: Value(payloadJson),
        evidencePath: Value(evidencePath),
        syncState: const Value('pending'),
        retryCount: const Value(0),
        lastSyncError: const Value(null),
      ),
    );
  }

  static Map<String, dynamic> _decodeEventPayload(String payloadJson) {
    try {
      final decoded = jsonDecode(payloadJson);
      if (decoded is Map<String, dynamic>) return decoded;
    } on Object {
      // The regular sync path will surface malformed payloads.
    }
    return const <String, dynamic>{};
  }

  Future<List<PendingEvent>> pendingForSync() {
    return (select(pendingEvents)
          ..where(
            (row) => row.syncState.isIn(['pending', 'syncing', 'syncFailed']),
          )
          ..orderBy([(row) => OrderingTerm.asc(row.createdAt)]))
        .get();
  }

  Future<int> unsyncedCount() async {
    final count = pendingEvents.clientEventUuid.count();
    final query = selectOnly(pendingEvents)
      ..addColumns([count])
      ..where(
        pendingEvents.syncState.isNotIn(['synced', 'reconciledActiveDuty']),
      );
    return (await query.map((row) => row.read(count)).getSingle()) ?? 0;
  }

  Future<void> markSyncing(String clientEventUuid) {
    return (update(
      pendingEvents,
    )..where((row) => row.clientEventUuid.equals(clientEventUuid))).write(
      const PendingEventsCompanion(
        syncState: Value('syncing'),
        lastSyncError: Value(null),
      ),
    );
  }

  Future<void> markSynced(String clientEventUuid) {
    return (update(pendingEvents)
          ..where((row) => row.clientEventUuid.equals(clientEventUuid)))
        .write(const PendingEventsCompanion(syncState: Value('synced')));
  }

  Future<void> markReconciledActiveDuty(String clientEventUuid) {
    return (update(
      pendingEvents,
    )..where((row) => row.clientEventUuid.equals(clientEventUuid))).write(
      const PendingEventsCompanion(
        syncState: Value('reconciledActiveDuty'),
        lastSyncError: Value(null),
      ),
    );
  }

  Future<void> markFailed(String clientEventUuid, String message) async {
    final row =
        await (select(pendingEvents)
              ..where((item) => item.clientEventUuid.equals(clientEventUuid)))
            .getSingleOrNull();
    if (row == null) return;
    await (update(
      pendingEvents,
    )..where((item) => item.clientEventUuid.equals(clientEventUuid))).write(
      PendingEventsCompanion(
        syncState: const Value('syncFailed'),
        retryCount: Value(row.retryCount + 1),
        lastSyncError: Value(message),
      ),
    );
  }

  Future<PendingEvent?> eventById(String clientEventUuid) {
    return (select(pendingEvents)
          ..where((row) => row.clientEventUuid.equals(clientEventUuid)))
        .getSingleOrNull();
  }

  Future<List<PendingEvent>> allEventsForDiagnostics() {
    return (select(
      pendingEvents,
    )..orderBy([(row) => OrderingTerm.asc(row.createdAt)])).get();
  }

  static int _compareDutyChronology(LocalDutySession a, LocalDutySession b) {
    final started = b.startedAt.compareTo(a.startedAt);
    if (started != 0) return started;
    final created = b.createdAt.compareTo(a.createdAt);
    if (created != 0) return created;
    return b.localSessionId.compareTo(a.localSessionId);
  }
}

Future<LocalDatabase> openLocalDatabase() async {
  final directory = await getApplicationDocumentsDirectory();
  final file = File(path.join(directory.path, 'fleet_manager_driver.sqlite'));
  final database = LocalDatabase(NativeDatabase.createInBackground(file));
  await database.reconcileCurrentDutySession();
  return database;
}
