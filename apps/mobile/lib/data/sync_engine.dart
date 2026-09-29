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

  static const lastSuccessfulSyncKey = 'last_successful_sync_at';
  static const lastSyncErrorKey = 'last_sync_error_category';
  static const lastSyncErrorMessageKey = 'last_sync_error_message';
  static const lastSyncHttpStatusKey = 'last_sync_http_status';
  static const lastSyncErrorCodeKey = 'last_sync_error_code';
  static const lastSyncFailureStageKey = 'last_sync_failure_stage';
  bool _syncInProgress = false;

  Future<String> enqueue({
    required DriverAssignment assignment,
    required DriverEventType eventType,
    Map<String, dynamic> payload = const <String, dynamic>{},
    String? evidencePath,
  }) async {
    final clientEventUuid = _uuid.v4();
    final now = DateTime.now().toUtc();
    final isStart = _isStartEvent(eventType, payload);
    final isEnd = _isEndEvent(eventType, payload);
    final isEmergency = eventType == DriverEventType.emergency;
    final existing = await database.latestLocalDutySession(
      assignmentId: assignment.assignmentId,
    );
    final activeSession =
        existing != null &&
        existing.endedAt == null &&
        _isLocallyActive(existing.state);
    final localSessionId = isStart ? _uuid.v4() : existing?.localSessionId;
    final dependency = activeSession && !isEmergency && !isStart
        ? existing.lastEventUuid
        : null;
    final blockedForStartCorrection =
        !isEmergency &&
        !isStart &&
        existing?.state == LocalDutyState.needsAttention.name;
    final storedPayload = <String, dynamic>{
      ...payload,
      if (localSessionId != null) '_duty_session_id': localSessionId,
      if (dependency != null) '_depends_on_event_uuid': dependency,
    };
    final event = local.PendingEventsCompanion.insert(
      clientEventUuid: clientEventUuid,
      eventType: eventType.wireName,
      assignmentId: assignment.assignmentId,
      tipperId: assignment.tipperId,
      siteId: assignment.siteId,
      supervisorName: assignment.supervisorName,
      deviceCreatedAt: now,
      syncState: blockedForStartCorrection
          ? 'blockedPendingStartCorrection'
          : 'pending',
      payloadJson: jsonEncode(storedPayload),
      evidencePath: Value(evidencePath),
      createdAt: now,
    );
    await database.transaction(() async {
      await database.enqueue(event);
      if (isStart) {
        await database.saveLocalDutySession(
          local.LocalDutySession(
            localSessionId: localSessionId!,
            assignmentId: assignment.assignmentId,
            tipperId: assignment.tipperId,
            tipperRegistrationNumber: assignment.tipperRegistrationNumber,
            tipperShortName: assignment.tipperShortName,
            siteId: assignment.siteId,
            siteName: assignment.siteName,
            supervisorName: assignment.supervisorName,
            startClientEventUuid: clientEventUuid,
            startKm: _readingValue(payload),
            startedAt: now,
            endClientEventUuid: null,
            endKm: null,
            endedAt: null,
            state: 'startPendingSync',
            serverSessionId: null,
            lastEventUuid: clientEventUuid,
            createdAt: now,
            updatedAt: now,
          ),
          makeCurrent: true,
        );
      } else if (existing != null && activeSession && !isEmergency) {
        await database.updateLocalDutySession(
          existing.copyWith(
            endClientEventUuid: isEnd ? clientEventUuid : null,
            endKm: isEnd ? _readingValue(payload) : null,
            endedAt: isEnd ? now : null,
            state: isEnd
                ? (existing.state == LocalDutyState.needsAttention.name
                      ? LocalDutyState.needsAttention.name
                      : LocalDutyState.endPendingSync.name)
                : null,
            lastEventUuid: clientEventUuid,
            updatedAt: now,
          ),
        );
      }
    });
    return clientEventUuid;
  }

  Future<String> correctStart({
    required String assignmentId,
    required String readingValue,
    required String evidencePath,
  }) async {
    final session = await database.latestLocalDutySession(
      assignmentId: assignmentId,
    );
    if (session == null ||
        session.state != LocalDutyState.needsAttention.name) {
      throw StateError('There is no rejected START KM to correct.');
    }
    final start = await database.eventById(session.startClientEventUuid);
    if (start == null) {
      throw StateError('The original START KM event is missing.');
    }
    final payload = _decodeStoredPayload(start.payloadJson)
      ..['reading_type'] = 'START_READING'
      ..['reading_value'] = readingValue;
    final parsed = double.tryParse(readingValue);
    if (parsed == null) throw StateError('The corrected START KM is invalid.');
    final now = DateTime.now().toUtc();
    await database.transaction(() async {
      await database.replaceEventForRetry(
        clientEventUuid: session.startClientEventUuid,
        payloadJson: jsonEncode(payload),
        evidencePath: evidencePath,
      );
      await database.unblockDutyDependentEvents(session.localSessionId);
      await database.updateLocalDutySession(
        session.copyWith(
          startKm: parsed,
          state: LocalDutyState.startPendingSync.name,
          updatedAt: now,
        ),
      );
    });
    return session.startClientEventUuid;
  }

  Future<DriverAssignment?> localAssignment() async {
    final row = await database.latestLocalDutySession();
    if (row == null) return null;
    return DriverAssignment(
      assignmentId: row.assignmentId,
      tipperId: row.tipperId,
      tipperRegistrationNumber: row.tipperRegistrationNumber,
      tipperShortName: row.tipperShortName,
      siteId: row.siteId,
      siteName: row.siteName,
      supervisorName: row.supervisorName,
    );
  }

  Future<DriverDutyState> localDutyState(String assignmentId) async {
    final row = await database.latestLocalDutySession(
      assignmentId: assignmentId,
    );
    return row == null ? const DriverDutyState.none() : _fromLocal(row);
  }

  Future<DriverDutyState> effectiveDuty(
    String assignmentId,
    DriverDutyState serverDuty,
  ) async {
    final row = await database.latestLocalDutySession(
      assignmentId: assignmentId,
    );
    if (row == null) return serverDuty;
    var state = _localState(row.state);
    if (state == LocalDutyState.startPendingSync && serverDuty.isActive) {
      state = LocalDutyState.activeConfirmed;
      await database.updateLocalDutySession(
        row.copyWith(
          state: 'activeConfirmed',
          serverSessionId: serverDuty.sessionId,
          updatedAt: DateTime.now().toUtc(),
        ),
      );
    } else if (state == LocalDutyState.endPendingSync &&
        serverDuty.status == DriverDutyStatus.closed) {
      state = LocalDutyState.closedConfirmed;
      await database.updateLocalDutySession(
        row.copyWith(
          state: 'closedConfirmed',
          updatedAt: DateTime.now().toUtc(),
        ),
      );
    }
    return _fromLocal(row, state: state, serverDuty: serverDuty);
  }

  Future<int> syncPending() async {
    while (_syncInProgress) {
      await Future<void>.delayed(const Duration(milliseconds: 25));
    }
    _syncInProgress = true;
    try {
      return await _syncPending();
    } finally {
      _syncInProgress = false;
    }
  }

  Future<int> _syncPending() async {
    final rows = await database.pendingForSync();
    rows.sort((left, right) {
      final leftEmergency =
          left.eventType == DriverEventType.emergency.wireName;
      final rightEmergency =
          right.eventType == DriverEventType.emergency.wireName;
      if (leftEmergency == rightEmergency) {
        return left.createdAt.compareTo(right.createdAt);
      }
      return leftEmergency ? -1 : 1;
    });
    var synced = 0;
    var attempted = 0;
    for (final row in rows) {
      final storedPayload = _decodeStoredPayload(row.payloadJson);
      final dependency = storedPayload['_depends_on_event_uuid'] as String?;
      if (dependency != null) {
        final dependencyRow = await database.eventById(dependency);
        if (dependencyRow?.syncState != 'synced' &&
            dependencyRow?.syncState != 'reconciledActiveDuty') {
          continue;
        }
      }
      attempted++;
      await database.markSyncing(row.clientEventUuid);
      final event = _toDomain(row);
      try {
        await _syncOne(event);
        await database.markSynced(event.clientEventUuid);
        await _markLocalDutySynced(row);
        synced++;
      } on ApiException catch (error) {
        final dutySessionId = storedPayload['_duty_session_id'] as String?;
        final activeDuty = await _matchingActiveDutyForConflict(event, error);
        if (activeDuty != null && dutySessionId != null) {
          await database.markReconciledActiveDuty(event.clientEventUuid);
          await database.markDutyStartSynced(
            dutySessionId,
            DateTime.now().toUtc(),
            serverSessionId: activeDuty.sessionId,
          );
          await database.unblockDutyDependentEvents(dutySessionId);
          synced++;
          continue;
        }
        await database.markFailed(event.clientEventUuid, error.message);
        if (_isDeterministicStartFailure(event, error) &&
            dutySessionId != null) {
          await database.markDutyNeedsAttention(dutySessionId);
          await database.blockDutyDependentEvents(
            dutySessionId,
            row.clientEventUuid,
          );
        }
        await database.setMetadata(lastSyncErrorKey, _errorCategory(error));
        await database.setMetadata(lastSyncErrorMessageKey, error.message);
        await database.setMetadata(
          lastSyncHttpStatusKey,
          error.statusCode.toString(),
        );
        await database.setMetadata(lastSyncErrorCodeKey, error.code ?? '');
        await database.setMetadata(
          lastSyncFailureStageKey,
          error.context?['sync_stage'] as String? ?? 'UNKNOWN',
        );
      } on Object catch (error) {
        await database.markFailed(event.clientEventUuid, error.toString());
        await database.setMetadata(lastSyncErrorKey, 'LOCAL_OR_NETWORK_ERROR');
        await database.setMetadata(lastSyncErrorMessageKey, error.toString());
      }
    }
    if (attempted == 0 || synced == attempted) {
      await database.setMetadata(
        lastSuccessfulSyncKey,
        DateTime.now().toUtc().toIso8601String(),
      );
    }
    if (attempted > 0 && synced == attempted) {
      await database.setMetadata(lastSyncErrorKey, '');
      await database.setMetadata(lastSyncErrorMessageKey, '');
      await database.setMetadata(lastSyncHttpStatusKey, '');
      await database.setMetadata(lastSyncErrorCodeKey, '');
      await database.setMetadata(lastSyncFailureStageKey, '');
      if ((await database.pendingForSync()).isNotEmpty) {
        return synced + await _syncPending();
      }
    }
    return synced;
  }

  Future<int> pendingCount() => database.unsyncedCount();

  Future<List<Map<String, String>>> diagnosticEventRows() async {
    final rows = await database.allEventsForDiagnostics();
    return rows.map((row) {
      final payload = _decodeStoredPayload(row.payloadJson);
      return <String, String>{
        'uuid': row.clientEventUuid,
        'type': row.eventType,
        'reading': '${payload['reading_type'] ?? ''}',
        'state': row.syncState,
        'retries': '${row.retryCount}',
        'duty': '${payload['_duty_session_id'] ?? ''}',
        'depends': '${payload['_depends_on_event_uuid'] ?? ''}',
        'created': row.createdAt.toUtc().toIso8601String(),
        'error': row.lastSyncError ?? '',
      };
    }).toList();
  }

  Future<List<Map<String, String>>> diagnosticDutyRows() async {
    final rows = await database.allLocalDutySessions();
    final current = await database.latestLocalDutySession();
    return rows.map((row) {
      return <String, String>{
        'session': row.localSessionId,
        'current': '${row.localSessionId == current?.localSessionId}',
        'assignment': row.assignmentId,
        'startEvent': row.startClientEventUuid,
        'state': row.state,
        'startKm': '${row.startKm}',
        'started': row.startedAt.toUtc().toIso8601String(),
        'endEvent': row.endClientEventUuid ?? '',
        'ended': row.endedAt?.toUtc().toIso8601String() ?? '',
        'updated': row.updatedAt.toUtc().toIso8601String(),
      };
    }).toList();
  }

  Future<String?> eventSyncState(String clientEventUuid) async =>
      (await database.eventById(clientEventUuid))?.syncState;

  Future<void> _markLocalDutySynced(local.PendingEvent row) async {
    final storedPayload = _decodeStoredPayload(row.payloadJson);
    final sessionId = storedPayload['_duty_session_id'] as String?;
    if (sessionId == null) return;
    final now = DateTime.now().toUtc();
    if (_isStartEvent(
      DriverEventType.values.firstWhere(
        (value) => value.wireName == row.eventType,
      ),
      _eventPayload(row.payloadJson),
    )) {
      await database.markDutyStartSynced(sessionId, now);
      await database.unblockDutyDependentEvents(sessionId);
    } else if (_isEndEvent(
      DriverEventType.values.firstWhere(
        (value) => value.wireName == row.eventType,
      ),
      _eventPayload(row.payloadJson),
    )) {
      await database.markDutyEndSynced(sessionId, now);
    }
  }

  static bool _isStartEvent(
    DriverEventType eventType,
    Map<String, dynamic> payload,
  ) =>
      eventType == DriverEventType.kmReading &&
      payload['reading_type'] == 'START_READING';

  static bool _isEndEvent(
    DriverEventType eventType,
    Map<String, dynamic> payload,
  ) =>
      eventType == DriverEventType.kmReading &&
      payload['reading_type'] == 'END_READING';

  static double _readingValue(Map<String, dynamic> payload) =>
      double.tryParse('${payload['reading_value']}') ?? 0;

  static Map<String, dynamic> _decodeStoredPayload(String payloadJson) {
    try {
      final decoded = jsonDecode(payloadJson);
      if (decoded is Map<String, dynamic>) return decoded;
    } on Object {
      // The sync attempt will report malformed payloads to diagnostics.
    }
    return <String, dynamic>{};
  }

  static Map<String, dynamic> _eventPayload(String payloadJson) {
    final payload = <String, dynamic>{..._decodeStoredPayload(payloadJson)};
    payload.remove('_duty_session_id');
    payload.remove('_depends_on_event_uuid');
    return payload;
  }

  static bool _isLocallyActive(String state) =>
      state == LocalDutyState.startPendingSync.name ||
      state == LocalDutyState.activeConfirmed.name ||
      state == LocalDutyState.needsAttention.name;

  static LocalDutyState _localState(String value) =>
      LocalDutyState.values.firstWhere(
        (state) => state.name == value,
        orElse: () => LocalDutyState.needsAttention,
      );

  static DriverDutyState _fromLocal(
    local.LocalDutySession row, {
    LocalDutyState? state,
    DriverDutyState? serverDuty,
  }) {
    final localState = state ?? _localState(row.state);
    final status = switch (localState) {
      LocalDutyState.startPendingSync ||
      LocalDutyState.activeConfirmed => DriverDutyStatus.active,
      LocalDutyState.closedConfirmed => DriverDutyStatus.closed,
      LocalDutyState.endPendingSync => DriverDutyStatus.active,
      LocalDutyState.needsAttention =>
        row.endedAt == null ? DriverDutyStatus.active : DriverDutyStatus.closed,
    };
    final useServer =
        serverDuty?.isActive == true &&
        localState == LocalDutyState.activeConfirmed;
    return DriverDutyState(
      status: status,
      localState: localState,
      sessionId: useServer ? serverDuty!.sessionId : row.serverSessionId,
      assignmentId: row.assignmentId,
      tipperId: row.tipperId,
      siteId: row.siteId,
      startedAt: useServer
          ? serverDuty!.startedAt ?? row.startedAt
          : row.startedAt,
      startKm: useServer ? serverDuty!.startKm ?? row.startKm : row.startKm,
      endedAt: useServer ? serverDuty!.endedAt ?? row.endedAt : row.endedAt,
      endKm: useServer ? serverDuty!.endKm ?? row.endKm : row.endKm,
      regularDutyMinutes: serverDuty?.regularDutyMinutes,
    );
  }

  static bool _isDeterministicStartFailure(
    PendingEvent event,
    ApiException error,
  ) {
    if (!_isStartEvent(event.eventType, event.payload)) return false;
    const codes = {
      'ODOMETER_CONTINUITY',
      'ODOMETER_OUT_OF_RANGE',
      'ASSIGNMENT_INVALID',
      'ASSIGNMENT_NOT_FOUND',
    };
    return codes.contains(error.code);
  }

  Future<DriverDutyState?> _matchingActiveDutyForConflict(
    PendingEvent event,
    ApiException error,
  ) async {
    if (error.code != 'DUTY_ALREADY_STARTED' ||
        !_isStartEvent(event.eventType, event.payload)) {
      return null;
    }
    if (remote is! DriverDutyLookup) return null;
    try {
      final duty = await (remote as DriverDutyLookup).currentDuty();
      final startedAt = duty.startedAt;
      if (!duty.isActive ||
          duty.assignmentId != event.assignmentId ||
          duty.tipperId != event.tipperId ||
          duty.siteId != event.siteId ||
          (startedAt != null && startedAt.isAfter(event.deviceCreatedAt))) {
        return null;
      }
      return duty;
    } on Object {
      return null;
    }
  }

  Future<DateTime?> lastSuccessfulSync() async {
    final value = await database.metadata(lastSuccessfulSyncKey);
    return value == null ? null : DateTime.tryParse(value)?.toUtc();
  }

  Future<String?> lastSyncErrorCategory() async {
    final value = await database.metadata(lastSyncErrorKey);
    return value == null || value.isEmpty ? null : value;
  }

  Future<String?> lastSyncErrorMessage() async {
    final value = await database.metadata(lastSyncErrorMessageKey);
    return value == null || value.isEmpty ? null : value;
  }

  Future<String?> lastSyncHttpStatus() async {
    final value = await database.metadata(lastSyncHttpStatusKey);
    return value == null || value.isEmpty ? null : value;
  }

  Future<String?> lastSyncErrorCode() async {
    final value = await database.metadata(lastSyncErrorCodeKey);
    return value == null || value.isEmpty ? null : value;
  }

  Future<String?> lastSyncFailureStage() async {
    final value = await database.metadata(lastSyncFailureStageKey);
    return value == null || value.isEmpty ? null : value;
  }

  static String _errorCategory(ApiException error) {
    if (error.code == 'ODOMETER_CONTINUITY') return 'ODOMETER_CONTINUITY';
    if (error.code == 'ODOMETER_OUT_OF_RANGE') return 'ODOMETER_OUT_OF_RANGE';
    if (error.code == 'EVIDENCE_FORMAT_UNSUPPORTED' ||
        error.code == 'EVIDENCE_FORMAT_MISMATCH' ||
        error.code == 'EVIDENCE_FILE_UNREADABLE') {
      return 'EVIDENCE_FILE_INVALID';
    }
    if (error.statusCode == 401) return 'AUTH_REQUIRED';
    if (error.statusCode == 403) return 'ACCESS_REVOKED_OR_DENIED';
    if (error.statusCode >= 500 || error.statusCode == 0) {
      return 'BACKEND_UNAVAILABLE';
    }
    if (error.statusCode == 408 || error.statusCode == 429) {
      return 'RETRY_LATER';
    }
    return 'REQUEST_REJECTED_${error.statusCode}';
  }

  Future<void> _syncOne(PendingEvent event) async {
    var refreshed = false;
    while (true) {
      try {
        var payload = <String, dynamic>{...event.payload};
        if (event.evidencePath != null) {
          late final String objectReference;
          try {
            objectReference = await remote.uploadEvidence(
              clientEventUuid: event.clientEventUuid,
              evidencePath: event.evidencePath!,
            );
          } on ApiException catch (error) {
            throw error.atSyncStage('EVIDENCE_UPLOAD');
          }
          payload['object_reference'] = objectReference;
        }
        try {
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
        } on ApiException catch (error) {
          throw error.atSyncStage('EVENT_SUBMISSION');
        }
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
      payload: _eventPayload(row.payloadJson),
      state: SyncState.values.firstWhere(
        (value) => value.name == row.syncState,
      ),
      retryCount: row.retryCount,
      createdAt: row.createdAt,
      evidencePath: row.evidencePath,
      lastSyncError: row.lastSyncError,
      dutySessionId:
          (_decodeStoredPayload(row.payloadJson)['_duty_session_id'])
              as String?,
      dependsOnEventUuid:
          (_decodeStoredPayload(row.payloadJson)['_depends_on_event_uuid'])
              as String?,
    );
  }
}
