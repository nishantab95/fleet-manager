import 'dart:convert';

import 'package:drift/drift.dart';
import 'package:uuid/uuid.dart';

import '../domain/driver_models.dart';
import 'api_client.dart';
import 'local_database.dart' as local;

typedef RefreshSession = Future<void> Function();

class SyncEngine {
  SyncEngine({
    required this.database,
    required this.remote,
    required this.installationIdentifier,
    this.refreshSession,
    Uuid? uuid,
  }) : _uuid = uuid ?? const Uuid();

  final local.LocalDatabase database;
  final DriverRemoteApi remote;
  final String installationIdentifier;
  final RefreshSession? refreshSession;
  final Uuid _uuid;

  Future<String> enqueue({
    required DriverAssignment assignment,
    required DriverEventType eventType,
    Map<String, dynamic> payload = const <String, dynamic>{},
    String? evidencePath,
  }) async {
    final clientEventUuid = _uuid.v4();
    await database.enqueue(
      local.PendingEventsCompanion.insert(
        clientEventUuid: clientEventUuid,
        eventType: eventType.wireName,
        assignmentId: assignment.assignmentId,
        tipperId: assignment.tipperId,
        siteId: assignment.siteId,
        supervisorName: assignment.supervisorName,
        deviceCreatedAt: DateTime.now().toUtc(),
        syncState: 'pending',
        payloadJson: jsonEncode(payload),
        evidencePath: Value(evidencePath),
        createdAt: DateTime.now().toUtc(),
      ),
    );
    return clientEventUuid;
  }

  Future<int> syncPending() async {
    final rows = await database.pendingForSync();
    var synced = 0;
    for (final row in rows) {
      await database.markSyncing(row.clientEventUuid);
      final event = _toDomain(row);
      try {
        await _syncOne(event);
        await database.markSynced(event.clientEventUuid);
        synced++;
      } on ApiException catch (error) {
        await database.markFailed(event.clientEventUuid, error.message);
      } on Object catch (error) {
        await database.markFailed(event.clientEventUuid, error.toString());
      }
    }
    return synced;
  }

  Future<void> _syncOne(PendingEvent event) async {
    var refreshed = false;
    while (true) {
      try {
        var payload = <String, dynamic>{...event.payload};
        if (event.evidencePath != null) {
          final objectReference = await remote.uploadEvidence(
            clientEventUuid: event.clientEventUuid,
            evidencePath: event.evidencePath!,
          );
          payload['object_reference'] = objectReference;
        }
        await remote.submitEvent(
          event: PendingEvent(
            clientEventUuid: event.clientEventUuid,
            assignmentId: event.assignmentId,
            tipperId: event.tipperId,
            siteId: event.siteId,
            supervisorName: event.supervisorName,
            eventType: event.eventType,
            deviceCreatedAt: event.deviceCreatedAt,
            payload: payload,
            state: event.state,
            retryCount: event.retryCount,
            createdAt: event.createdAt,
            evidencePath: event.evidencePath,
            lastSyncError: event.lastSyncError,
          ),
          installationIdentifier: installationIdentifier,
        );
        return;
      } on ApiException catch (error) {
        if (error.isUnauthorized && !refreshed && refreshSession != null) {
          refreshed = true;
          await refreshSession!();
          continue;
        }
        if (error.isRetryable) {
          final delayMs = (event.retryCount + 1).clamp(1, 4) * 250;
          await Future<void>.delayed(Duration(milliseconds: delayMs));
        }
        rethrow;
      }
    }
  }

  static PendingEvent _toDomain(local.PendingEvent row) {
    return PendingEvent(
      clientEventUuid: row.clientEventUuid,
      assignmentId: row.assignmentId,
      tipperId: row.tipperId,
      siteId: row.siteId,
      supervisorName: row.supervisorName,
      eventType: DriverEventType.values.firstWhere(
        (value) => value.wireName == row.eventType,
      ),
      deviceCreatedAt: row.deviceCreatedAt,
      payload: jsonDecode(row.payloadJson) as Map<String, dynamic>,
      state: SyncState.values.firstWhere(
        (value) => value.name == row.syncState,
      ),
      retryCount: row.retryCount,
      createdAt: row.createdAt,
      evidencePath: row.evidencePath,
      lastSyncError: row.lastSyncError,
    );
  }
}
