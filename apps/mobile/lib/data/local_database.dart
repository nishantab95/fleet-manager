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

@DriftDatabase(tables: [PendingEvents])
class LocalDatabase extends _$LocalDatabase {
  LocalDatabase(super.e);

  @override
  int get schemaVersion => 1;

  Future<void> enqueue(PendingEventsCompanion event) {
    return into(pendingEvents).insertOnConflictUpdate(event);
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
