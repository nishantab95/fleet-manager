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
      startKm: startKm,
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
    final rows = await select(syncMetadata).get();
    final sessions = <LocalDutySession>[];
    for (final row in rows.where((row) => row.key.startsWith('local_duty:'))) {
      try {
        final session = LocalDutySession.fromJson(
          jsonDecode(row.value) as Map<String, dynamic>,
        );
        if (assignmentId == null || session.assignmentId == assignmentId) {
          sessions.add(session);
        }
      } on Object {
        // Ignore a corrupt snapshot; the pending queue remains authoritative.
      }
    }
    if (sessions.isEmpty) return null;
    sessions.sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
    return sessions.first;
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

  Future<void> saveLocalDutySession(LocalDutySession session) {
    return setMetadata(
      'local_duty:${session.localSessionId}',
      jsonEncode(session.toJson()),
    );
  }

  Future<void> updateLocalDutySession(LocalDutySession session) {
    return saveLocalDutySession(session);
  }

  Future<void> markDutyStartSynced(
    String localSessionId,
    DateTime updatedAt,
  ) async {
    final row = await localDutySession(localSessionId);
    if (row?.localSessionId == localSessionId) {
      await updateLocalDutySession(
        row!.copyWith(state: 'activeConfirmed', updatedAt: updatedAt),
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

  Future<void> blockDependentEvents(String eventUuid) async {
    final rows = await pendingForSync();
    for (final row in rows) {
      final payload = _decodeEventPayload(row.payloadJson);
      if (payload['_depends_on_event_uuid'] != eventUuid) continue;
      await (update(pendingEvents)
            ..where((item) => item.clientEventUuid.equals(row.clientEventUuid)))
          .write(
            const PendingEventsCompanion(
              syncState: Value('blocked'),
              lastSyncError: Value('START_KM_NEEDS_CORRECTION'),
            ),
          );
    }
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
}

Future<LocalDatabase> openLocalDatabase() async {
  final directory = await getApplicationDocumentsDirectory();
  final file = File(path.join(directory.path, 'fleet_manager_driver.sqlite'));
  return LocalDatabase(NativeDatabase.createInBackground(file));
}
