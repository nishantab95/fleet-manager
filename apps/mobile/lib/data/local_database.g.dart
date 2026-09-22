// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'local_database.dart';

// ignore_for_file: type=lint
class $PendingEventsTable extends PendingEvents
    with TableInfo<$PendingEventsTable, PendingEvent> {
  @override
  final GeneratedDatabase attachedDatabase;
  final String? _alias;
  $PendingEventsTable(this.attachedDatabase, [this._alias]);
  static const VerificationMeta _clientEventUuidMeta = const VerificationMeta(
    'clientEventUuid',
  );
  @override
  late final GeneratedColumn<String> clientEventUuid = GeneratedColumn<String>(
    'client_event_uuid',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _eventTypeMeta = const VerificationMeta(
    'eventType',
  );
  @override
  late final GeneratedColumn<String> eventType = GeneratedColumn<String>(
    'event_type',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _assignmentIdMeta = const VerificationMeta(
    'assignmentId',
  );
  @override
  late final GeneratedColumn<String> assignmentId = GeneratedColumn<String>(
    'assignment_id',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _tipperIdMeta = const VerificationMeta(
    'tipperId',
  );
  @override
  late final GeneratedColumn<String> tipperId = GeneratedColumn<String>(
    'tipper_id',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _siteIdMeta = const VerificationMeta('siteId');
  @override
  late final GeneratedColumn<String> siteId = GeneratedColumn<String>(
    'site_id',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _supervisorNameMeta = const VerificationMeta(
    'supervisorName',
  );
  @override
  late final GeneratedColumn<String> supervisorName = GeneratedColumn<String>(
    'supervisor_name',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _deviceCreatedAtMeta = const VerificationMeta(
    'deviceCreatedAt',
  );
  @override
  late final GeneratedColumn<DateTime> deviceCreatedAt =
      GeneratedColumn<DateTime>(
        'device_created_at',
        aliasedName,
        false,
        type: DriftSqlType.dateTime,
        requiredDuringInsert: true,
      );
  static const VerificationMeta _syncStateMeta = const VerificationMeta(
    'syncState',
  );
  @override
  late final GeneratedColumn<String> syncState = GeneratedColumn<String>(
    'sync_state',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _retryCountMeta = const VerificationMeta(
    'retryCount',
  );
  @override
  late final GeneratedColumn<int> retryCount = GeneratedColumn<int>(
    'retry_count',
    aliasedName,
    false,
    type: DriftSqlType.int,
    requiredDuringInsert: false,
    defaultValue: const Constant(0),
  );
  static const VerificationMeta _payloadJsonMeta = const VerificationMeta(
    'payloadJson',
  );
  @override
  late final GeneratedColumn<String> payloadJson = GeneratedColumn<String>(
    'payload_json',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _evidencePathMeta = const VerificationMeta(
    'evidencePath',
  );
  @override
  late final GeneratedColumn<String> evidencePath = GeneratedColumn<String>(
    'evidence_path',
    aliasedName,
    true,
    type: DriftSqlType.string,
    requiredDuringInsert: false,
  );
  static const VerificationMeta _lastSyncErrorMeta = const VerificationMeta(
    'lastSyncError',
  );
  @override
  late final GeneratedColumn<String> lastSyncError = GeneratedColumn<String>(
    'last_sync_error',
    aliasedName,
    true,
    type: DriftSqlType.string,
    requiredDuringInsert: false,
  );
  static const VerificationMeta _createdAtMeta = const VerificationMeta(
    'createdAt',
  );
  @override
  late final GeneratedColumn<DateTime> createdAt = GeneratedColumn<DateTime>(
    'created_at',
    aliasedName,
    false,
    type: DriftSqlType.dateTime,
    requiredDuringInsert: true,
  );
  @override
  List<GeneratedColumn> get $columns => [
    clientEventUuid,
    eventType,
    assignmentId,
    tipperId,
    siteId,
    supervisorName,
    deviceCreatedAt,
    syncState,
    retryCount,
    payloadJson,
    evidencePath,
    lastSyncError,
    createdAt,
  ];
  @override
  String get aliasedName => _alias ?? actualTableName;
  @override
  String get actualTableName => $name;
  static const String $name = 'pending_events';
  @override
  VerificationContext validateIntegrity(
    Insertable<PendingEvent> instance, {
    bool isInserting = false,
  }) {
    final context = VerificationContext();
    final data = instance.toColumns(true);
    if (data.containsKey('client_event_uuid')) {
      context.handle(
        _clientEventUuidMeta,
        clientEventUuid.isAcceptableOrUnknown(
          data['client_event_uuid']!,
          _clientEventUuidMeta,
        ),
      );
    } else if (isInserting) {
      context.missing(_clientEventUuidMeta);
    }
    if (data.containsKey('event_type')) {
      context.handle(
        _eventTypeMeta,
        eventType.isAcceptableOrUnknown(data['event_type']!, _eventTypeMeta),
      );
    } else if (isInserting) {
      context.missing(_eventTypeMeta);
    }
    if (data.containsKey('assignment_id')) {
      context.handle(
        _assignmentIdMeta,
        assignmentId.isAcceptableOrUnknown(
          data['assignment_id']!,
          _assignmentIdMeta,
        ),
      );
    } else if (isInserting) {
      context.missing(_assignmentIdMeta);
    }
    if (data.containsKey('tipper_id')) {
      context.handle(
        _tipperIdMeta,
        tipperId.isAcceptableOrUnknown(data['tipper_id']!, _tipperIdMeta),
      );
    } else if (isInserting) {
      context.missing(_tipperIdMeta);
    }
    if (data.containsKey('site_id')) {
      context.handle(
        _siteIdMeta,
        siteId.isAcceptableOrUnknown(data['site_id']!, _siteIdMeta),
      );
    } else if (isInserting) {
      context.missing(_siteIdMeta);
    }
    if (data.containsKey('supervisor_name')) {
      context.handle(
        _supervisorNameMeta,
        supervisorName.isAcceptableOrUnknown(
          data['supervisor_name']!,
          _supervisorNameMeta,
        ),
      );
    } else if (isInserting) {
      context.missing(_supervisorNameMeta);
    }
    if (data.containsKey('device_created_at')) {
      context.handle(
        _deviceCreatedAtMeta,
        deviceCreatedAt.isAcceptableOrUnknown(
          data['device_created_at']!,
          _deviceCreatedAtMeta,
        ),
      );
    } else if (isInserting) {
      context.missing(_deviceCreatedAtMeta);
    }
    if (data.containsKey('sync_state')) {
      context.handle(
        _syncStateMeta,
        syncState.isAcceptableOrUnknown(data['sync_state']!, _syncStateMeta),
      );
    } else if (isInserting) {
      context.missing(_syncStateMeta);
    }
    if (data.containsKey('retry_count')) {
      context.handle(
        _retryCountMeta,
        retryCount.isAcceptableOrUnknown(data['retry_count']!, _retryCountMeta),
      );
    }
    if (data.containsKey('payload_json')) {
      context.handle(
        _payloadJsonMeta,
        payloadJson.isAcceptableOrUnknown(
          data['payload_json']!,
          _payloadJsonMeta,
        ),
      );
    } else if (isInserting) {
      context.missing(_payloadJsonMeta);
    }
    if (data.containsKey('evidence_path')) {
      context.handle(
        _evidencePathMeta,
        evidencePath.isAcceptableOrUnknown(
          data['evidence_path']!,
          _evidencePathMeta,
        ),
      );
    }
    if (data.containsKey('last_sync_error')) {
      context.handle(
        _lastSyncErrorMeta,
        lastSyncError.isAcceptableOrUnknown(
          data['last_sync_error']!,
          _lastSyncErrorMeta,
        ),
      );
    }
    if (data.containsKey('created_at')) {
      context.handle(
        _createdAtMeta,
        createdAt.isAcceptableOrUnknown(data['created_at']!, _createdAtMeta),
      );
    } else if (isInserting) {
      context.missing(_createdAtMeta);
    }
    return context;
  }

  @override
  Set<GeneratedColumn> get $primaryKey => {clientEventUuid};
  @override
  PendingEvent map(Map<String, dynamic> data, {String? tablePrefix}) {
    final effectivePrefix = tablePrefix != null ? '$tablePrefix.' : '';
    return PendingEvent(
      clientEventUuid: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}client_event_uuid'],
      )!,
      eventType: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}event_type'],
      )!,
      assignmentId: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}assignment_id'],
      )!,
      tipperId: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}tipper_id'],
      )!,
      siteId: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}site_id'],
      )!,
      supervisorName: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}supervisor_name'],
      )!,
      deviceCreatedAt: attachedDatabase.typeMapping.read(
        DriftSqlType.dateTime,
        data['${effectivePrefix}device_created_at'],
      )!,
      syncState: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}sync_state'],
      )!,
      retryCount: attachedDatabase.typeMapping.read(
        DriftSqlType.int,
        data['${effectivePrefix}retry_count'],
      )!,
      payloadJson: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}payload_json'],
      )!,
      evidencePath: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}evidence_path'],
      ),
      lastSyncError: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}last_sync_error'],
      ),
      createdAt: attachedDatabase.typeMapping.read(
        DriftSqlType.dateTime,
        data['${effectivePrefix}created_at'],
      )!,
    );
  }

  @override
  $PendingEventsTable createAlias(String alias) {
    return $PendingEventsTable(attachedDatabase, alias);
  }
}

class PendingEvent extends DataClass implements Insertable<PendingEvent> {
  final String clientEventUuid;
  final String eventType;
  final String assignmentId;
  final String tipperId;
  final String siteId;
  final String supervisorName;
  final DateTime deviceCreatedAt;
  final String syncState;
  final int retryCount;
  final String payloadJson;
  final String? evidencePath;
  final String? lastSyncError;
  final DateTime createdAt;
  const PendingEvent({
    required this.clientEventUuid,
    required this.eventType,
    required this.assignmentId,
    required this.tipperId,
    required this.siteId,
    required this.supervisorName,
    required this.deviceCreatedAt,
    required this.syncState,
    required this.retryCount,
    required this.payloadJson,
    this.evidencePath,
    this.lastSyncError,
    required this.createdAt,
  });
  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    map['client_event_uuid'] = Variable<String>(clientEventUuid);
    map['event_type'] = Variable<String>(eventType);
    map['assignment_id'] = Variable<String>(assignmentId);
    map['tipper_id'] = Variable<String>(tipperId);
    map['site_id'] = Variable<String>(siteId);
    map['supervisor_name'] = Variable<String>(supervisorName);
    map['device_created_at'] = Variable<DateTime>(deviceCreatedAt);
    map['sync_state'] = Variable<String>(syncState);
    map['retry_count'] = Variable<int>(retryCount);
    map['payload_json'] = Variable<String>(payloadJson);
    if (!nullToAbsent || evidencePath != null) {
      map['evidence_path'] = Variable<String>(evidencePath);
    }
    if (!nullToAbsent || lastSyncError != null) {
      map['last_sync_error'] = Variable<String>(lastSyncError);
    }
    map['created_at'] = Variable<DateTime>(createdAt);
    return map;
  }

  PendingEventsCompanion toCompanion(bool nullToAbsent) {
    return PendingEventsCompanion(
      clientEventUuid: Value(clientEventUuid),
      eventType: Value(eventType),
      assignmentId: Value(assignmentId),
      tipperId: Value(tipperId),
      siteId: Value(siteId),
      supervisorName: Value(supervisorName),
      deviceCreatedAt: Value(deviceCreatedAt),
      syncState: Value(syncState),
      retryCount: Value(retryCount),
      payloadJson: Value(payloadJson),
      evidencePath: evidencePath == null && nullToAbsent
          ? const Value.absent()
          : Value(evidencePath),
      lastSyncError: lastSyncError == null && nullToAbsent
          ? const Value.absent()
          : Value(lastSyncError),
      createdAt: Value(createdAt),
    );
  }

  factory PendingEvent.fromJson(
    Map<String, dynamic> json, {
    ValueSerializer? serializer,
  }) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return PendingEvent(
      clientEventUuid: serializer.fromJson<String>(json['clientEventUuid']),
      eventType: serializer.fromJson<String>(json['eventType']),
      assignmentId: serializer.fromJson<String>(json['assignmentId']),
      tipperId: serializer.fromJson<String>(json['tipperId']),
      siteId: serializer.fromJson<String>(json['siteId']),
      supervisorName: serializer.fromJson<String>(json['supervisorName']),
      deviceCreatedAt: serializer.fromJson<DateTime>(json['deviceCreatedAt']),
      syncState: serializer.fromJson<String>(json['syncState']),
      retryCount: serializer.fromJson<int>(json['retryCount']),
      payloadJson: serializer.fromJson<String>(json['payloadJson']),
      evidencePath: serializer.fromJson<String?>(json['evidencePath']),
      lastSyncError: serializer.fromJson<String?>(json['lastSyncError']),
      createdAt: serializer.fromJson<DateTime>(json['createdAt']),
    );
  }
  @override
  Map<String, dynamic> toJson({ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return <String, dynamic>{
      'clientEventUuid': serializer.toJson<String>(clientEventUuid),
      'eventType': serializer.toJson<String>(eventType),
      'assignmentId': serializer.toJson<String>(assignmentId),
      'tipperId': serializer.toJson<String>(tipperId),
      'siteId': serializer.toJson<String>(siteId),
      'supervisorName': serializer.toJson<String>(supervisorName),
      'deviceCreatedAt': serializer.toJson<DateTime>(deviceCreatedAt),
      'syncState': serializer.toJson<String>(syncState),
      'retryCount': serializer.toJson<int>(retryCount),
      'payloadJson': serializer.toJson<String>(payloadJson),
      'evidencePath': serializer.toJson<String?>(evidencePath),
      'lastSyncError': serializer.toJson<String?>(lastSyncError),
      'createdAt': serializer.toJson<DateTime>(createdAt),
    };
  }

  PendingEvent copyWith({
    String? clientEventUuid,
    String? eventType,
    String? assignmentId,
    String? tipperId,
    String? siteId,
    String? supervisorName,
    DateTime? deviceCreatedAt,
    String? syncState,
    int? retryCount,
    String? payloadJson,
    Value<String?> evidencePath = const Value.absent(),
    Value<String?> lastSyncError = const Value.absent(),
    DateTime? createdAt,
  }) => PendingEvent(
    clientEventUuid: clientEventUuid ?? this.clientEventUuid,
    eventType: eventType ?? this.eventType,
    assignmentId: assignmentId ?? this.assignmentId,
    tipperId: tipperId ?? this.tipperId,
    siteId: siteId ?? this.siteId,
    supervisorName: supervisorName ?? this.supervisorName,
    deviceCreatedAt: deviceCreatedAt ?? this.deviceCreatedAt,
    syncState: syncState ?? this.syncState,
    retryCount: retryCount ?? this.retryCount,
    payloadJson: payloadJson ?? this.payloadJson,
    evidencePath: evidencePath.present ? evidencePath.value : this.evidencePath,
    lastSyncError: lastSyncError.present
        ? lastSyncError.value
        : this.lastSyncError,
    createdAt: createdAt ?? this.createdAt,
  );
  PendingEvent copyWithCompanion(PendingEventsCompanion data) {
    return PendingEvent(
      clientEventUuid: data.clientEventUuid.present
          ? data.clientEventUuid.value
          : this.clientEventUuid,
      eventType: data.eventType.present ? data.eventType.value : this.eventType,
      assignmentId: data.assignmentId.present
          ? data.assignmentId.value
          : this.assignmentId,
      tipperId: data.tipperId.present ? data.tipperId.value : this.tipperId,
      siteId: data.siteId.present ? data.siteId.value : this.siteId,
      supervisorName: data.supervisorName.present
          ? data.supervisorName.value
          : this.supervisorName,
      deviceCreatedAt: data.deviceCreatedAt.present
          ? data.deviceCreatedAt.value
          : this.deviceCreatedAt,
      syncState: data.syncState.present ? data.syncState.value : this.syncState,
      retryCount: data.retryCount.present
          ? data.retryCount.value
          : this.retryCount,
      payloadJson: data.payloadJson.present
          ? data.payloadJson.value
          : this.payloadJson,
      evidencePath: data.evidencePath.present
          ? data.evidencePath.value
          : this.evidencePath,
      lastSyncError: data.lastSyncError.present
          ? data.lastSyncError.value
          : this.lastSyncError,
      createdAt: data.createdAt.present ? data.createdAt.value : this.createdAt,
    );
  }

  @override
  String toString() {
    return (StringBuffer('PendingEvent(')
          ..write('clientEventUuid: $clientEventUuid, ')
          ..write('eventType: $eventType, ')
          ..write('assignmentId: $assignmentId, ')
          ..write('tipperId: $tipperId, ')
          ..write('siteId: $siteId, ')
          ..write('supervisorName: $supervisorName, ')
          ..write('deviceCreatedAt: $deviceCreatedAt, ')
          ..write('syncState: $syncState, ')
          ..write('retryCount: $retryCount, ')
          ..write('payloadJson: $payloadJson, ')
          ..write('evidencePath: $evidencePath, ')
          ..write('lastSyncError: $lastSyncError, ')
          ..write('createdAt: $createdAt')
          ..write(')'))
        .toString();
  }

  @override
  int get hashCode => Object.hash(
    clientEventUuid,
    eventType,
    assignmentId,
    tipperId,
    siteId,
    supervisorName,
    deviceCreatedAt,
    syncState,
    retryCount,
    payloadJson,
    evidencePath,
    lastSyncError,
    createdAt,
  );
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is PendingEvent &&
          other.clientEventUuid == this.clientEventUuid &&
          other.eventType == this.eventType &&
          other.assignmentId == this.assignmentId &&
          other.tipperId == this.tipperId &&
          other.siteId == this.siteId &&
          other.supervisorName == this.supervisorName &&
          other.deviceCreatedAt == this.deviceCreatedAt &&
          other.syncState == this.syncState &&
          other.retryCount == this.retryCount &&
          other.payloadJson == this.payloadJson &&
          other.evidencePath == this.evidencePath &&
          other.lastSyncError == this.lastSyncError &&
          other.createdAt == this.createdAt);
}

class PendingEventsCompanion extends UpdateCompanion<PendingEvent> {
  final Value<String> clientEventUuid;
  final Value<String> eventType;
  final Value<String> assignmentId;
  final Value<String> tipperId;
  final Value<String> siteId;
  final Value<String> supervisorName;
  final Value<DateTime> deviceCreatedAt;
  final Value<String> syncState;
  final Value<int> retryCount;
  final Value<String> payloadJson;
  final Value<String?> evidencePath;
  final Value<String?> lastSyncError;
  final Value<DateTime> createdAt;
  final Value<int> rowid;
  const PendingEventsCompanion({
    this.clientEventUuid = const Value.absent(),
    this.eventType = const Value.absent(),
    this.assignmentId = const Value.absent(),
    this.tipperId = const Value.absent(),
    this.siteId = const Value.absent(),
    this.supervisorName = const Value.absent(),
    this.deviceCreatedAt = const Value.absent(),
    this.syncState = const Value.absent(),
    this.retryCount = const Value.absent(),
    this.payloadJson = const Value.absent(),
    this.evidencePath = const Value.absent(),
    this.lastSyncError = const Value.absent(),
    this.createdAt = const Value.absent(),
    this.rowid = const Value.absent(),
  });
  PendingEventsCompanion.insert({
    required String clientEventUuid,
    required String eventType,
    required String assignmentId,
    required String tipperId,
    required String siteId,
    required String supervisorName,
    required DateTime deviceCreatedAt,
    required String syncState,
    this.retryCount = const Value.absent(),
    required String payloadJson,
    this.evidencePath = const Value.absent(),
    this.lastSyncError = const Value.absent(),
    required DateTime createdAt,
    this.rowid = const Value.absent(),
  }) : clientEventUuid = Value(clientEventUuid),
       eventType = Value(eventType),
       assignmentId = Value(assignmentId),
       tipperId = Value(tipperId),
       siteId = Value(siteId),
       supervisorName = Value(supervisorName),
       deviceCreatedAt = Value(deviceCreatedAt),
       syncState = Value(syncState),
       payloadJson = Value(payloadJson),
       createdAt = Value(createdAt);
  static Insertable<PendingEvent> custom({
    Expression<String>? clientEventUuid,
    Expression<String>? eventType,
    Expression<String>? assignmentId,
    Expression<String>? tipperId,
    Expression<String>? siteId,
    Expression<String>? supervisorName,
    Expression<DateTime>? deviceCreatedAt,
    Expression<String>? syncState,
    Expression<int>? retryCount,
    Expression<String>? payloadJson,
    Expression<String>? evidencePath,
    Expression<String>? lastSyncError,
    Expression<DateTime>? createdAt,
    Expression<int>? rowid,
  }) {
    return RawValuesInsertable({
      if (clientEventUuid != null) 'client_event_uuid': clientEventUuid,
      if (eventType != null) 'event_type': eventType,
      if (assignmentId != null) 'assignment_id': assignmentId,
      if (tipperId != null) 'tipper_id': tipperId,
      if (siteId != null) 'site_id': siteId,
      if (supervisorName != null) 'supervisor_name': supervisorName,
      if (deviceCreatedAt != null) 'device_created_at': deviceCreatedAt,
      if (syncState != null) 'sync_state': syncState,
      if (retryCount != null) 'retry_count': retryCount,
      if (payloadJson != null) 'payload_json': payloadJson,
      if (evidencePath != null) 'evidence_path': evidencePath,
      if (lastSyncError != null) 'last_sync_error': lastSyncError,
      if (createdAt != null) 'created_at': createdAt,
      if (rowid != null) 'rowid': rowid,
    });
  }

  PendingEventsCompanion copyWith({
    Value<String>? clientEventUuid,
    Value<String>? eventType,
    Value<String>? assignmentId,
    Value<String>? tipperId,
    Value<String>? siteId,
    Value<String>? supervisorName,
    Value<DateTime>? deviceCreatedAt,
    Value<String>? syncState,
    Value<int>? retryCount,
    Value<String>? payloadJson,
    Value<String?>? evidencePath,
    Value<String?>? lastSyncError,
    Value<DateTime>? createdAt,
    Value<int>? rowid,
  }) {
    return PendingEventsCompanion(
      clientEventUuid: clientEventUuid ?? this.clientEventUuid,
      eventType: eventType ?? this.eventType,
      assignmentId: assignmentId ?? this.assignmentId,
      tipperId: tipperId ?? this.tipperId,
      siteId: siteId ?? this.siteId,
      supervisorName: supervisorName ?? this.supervisorName,
      deviceCreatedAt: deviceCreatedAt ?? this.deviceCreatedAt,
      syncState: syncState ?? this.syncState,
      retryCount: retryCount ?? this.retryCount,
      payloadJson: payloadJson ?? this.payloadJson,
      evidencePath: evidencePath ?? this.evidencePath,
      lastSyncError: lastSyncError ?? this.lastSyncError,
      createdAt: createdAt ?? this.createdAt,
      rowid: rowid ?? this.rowid,
    );
  }

  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    if (clientEventUuid.present) {
      map['client_event_uuid'] = Variable<String>(clientEventUuid.value);
    }
    if (eventType.present) {
      map['event_type'] = Variable<String>(eventType.value);
    }
    if (assignmentId.present) {
      map['assignment_id'] = Variable<String>(assignmentId.value);
    }
    if (tipperId.present) {
      map['tipper_id'] = Variable<String>(tipperId.value);
    }
    if (siteId.present) {
      map['site_id'] = Variable<String>(siteId.value);
    }
    if (supervisorName.present) {
      map['supervisor_name'] = Variable<String>(supervisorName.value);
    }
    if (deviceCreatedAt.present) {
      map['device_created_at'] = Variable<DateTime>(deviceCreatedAt.value);
    }
    if (syncState.present) {
      map['sync_state'] = Variable<String>(syncState.value);
    }
    if (retryCount.present) {
      map['retry_count'] = Variable<int>(retryCount.value);
    }
    if (payloadJson.present) {
      map['payload_json'] = Variable<String>(payloadJson.value);
    }
    if (evidencePath.present) {
      map['evidence_path'] = Variable<String>(evidencePath.value);
    }
    if (lastSyncError.present) {
      map['last_sync_error'] = Variable<String>(lastSyncError.value);
    }
    if (createdAt.present) {
      map['created_at'] = Variable<DateTime>(createdAt.value);
    }
    if (rowid.present) {
      map['rowid'] = Variable<int>(rowid.value);
    }
    return map;
  }

  @override
  String toString() {
    return (StringBuffer('PendingEventsCompanion(')
          ..write('clientEventUuid: $clientEventUuid, ')
          ..write('eventType: $eventType, ')
          ..write('assignmentId: $assignmentId, ')
          ..write('tipperId: $tipperId, ')
          ..write('siteId: $siteId, ')
          ..write('supervisorName: $supervisorName, ')
          ..write('deviceCreatedAt: $deviceCreatedAt, ')
          ..write('syncState: $syncState, ')
          ..write('retryCount: $retryCount, ')
          ..write('payloadJson: $payloadJson, ')
          ..write('evidencePath: $evidencePath, ')
          ..write('lastSyncError: $lastSyncError, ')
          ..write('createdAt: $createdAt, ')
          ..write('rowid: $rowid')
          ..write(')'))
        .toString();
  }
}

class $SyncMetadataTable extends SyncMetadata
    with TableInfo<$SyncMetadataTable, SyncMetadataData> {
  @override
  final GeneratedDatabase attachedDatabase;
  final String? _alias;
  $SyncMetadataTable(this.attachedDatabase, [this._alias]);
  static const VerificationMeta _keyMeta = const VerificationMeta('key');
  @override
  late final GeneratedColumn<String> key = GeneratedColumn<String>(
    'key',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _valueMeta = const VerificationMeta('value');
  @override
  late final GeneratedColumn<String> value = GeneratedColumn<String>(
    'value',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  @override
  List<GeneratedColumn> get $columns => [key, value];
  @override
  String get aliasedName => _alias ?? actualTableName;
  @override
  String get actualTableName => $name;
  static const String $name = 'sync_metadata';
  @override
  VerificationContext validateIntegrity(
    Insertable<SyncMetadataData> instance, {
    bool isInserting = false,
  }) {
    final context = VerificationContext();
    final data = instance.toColumns(true);
    if (data.containsKey('key')) {
      context.handle(
        _keyMeta,
        key.isAcceptableOrUnknown(data['key']!, _keyMeta),
      );
    } else if (isInserting) {
      context.missing(_keyMeta);
    }
    if (data.containsKey('value')) {
      context.handle(
        _valueMeta,
        value.isAcceptableOrUnknown(data['value']!, _valueMeta),
      );
    } else if (isInserting) {
      context.missing(_valueMeta);
    }
    return context;
  }

  @override
  Set<GeneratedColumn> get $primaryKey => {key};
  @override
  SyncMetadataData map(Map<String, dynamic> data, {String? tablePrefix}) {
    final effectivePrefix = tablePrefix != null ? '$tablePrefix.' : '';
    return SyncMetadataData(
      key: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}key'],
      )!,
      value: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}value'],
      )!,
    );
  }

  @override
  $SyncMetadataTable createAlias(String alias) {
    return $SyncMetadataTable(attachedDatabase, alias);
  }
}

class SyncMetadataData extends DataClass
    implements Insertable<SyncMetadataData> {
  final String key;
  final String value;
  const SyncMetadataData({required this.key, required this.value});
  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    map['key'] = Variable<String>(key);
    map['value'] = Variable<String>(value);
    return map;
  }

  SyncMetadataCompanion toCompanion(bool nullToAbsent) {
    return SyncMetadataCompanion(key: Value(key), value: Value(value));
  }

  factory SyncMetadataData.fromJson(
    Map<String, dynamic> json, {
    ValueSerializer? serializer,
  }) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return SyncMetadataData(
      key: serializer.fromJson<String>(json['key']),
      value: serializer.fromJson<String>(json['value']),
    );
  }
  @override
  Map<String, dynamic> toJson({ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return <String, dynamic>{
      'key': serializer.toJson<String>(key),
      'value': serializer.toJson<String>(value),
    };
  }

  SyncMetadataData copyWith({String? key, String? value}) =>
      SyncMetadataData(key: key ?? this.key, value: value ?? this.value);
  SyncMetadataData copyWithCompanion(SyncMetadataCompanion data) {
    return SyncMetadataData(
      key: data.key.present ? data.key.value : this.key,
      value: data.value.present ? data.value.value : this.value,
    );
  }

  @override
  String toString() {
    return (StringBuffer('SyncMetadataData(')
          ..write('key: $key, ')
          ..write('value: $value')
          ..write(')'))
        .toString();
  }

  @override
  int get hashCode => Object.hash(key, value);
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is SyncMetadataData &&
          other.key == this.key &&
          other.value == this.value);
}

class SyncMetadataCompanion extends UpdateCompanion<SyncMetadataData> {
  final Value<String> key;
  final Value<String> value;
  final Value<int> rowid;
  const SyncMetadataCompanion({
    this.key = const Value.absent(),
    this.value = const Value.absent(),
    this.rowid = const Value.absent(),
  });
  SyncMetadataCompanion.insert({
    required String key,
    required String value,
    this.rowid = const Value.absent(),
  }) : key = Value(key),
       value = Value(value);
  static Insertable<SyncMetadataData> custom({
    Expression<String>? key,
    Expression<String>? value,
    Expression<int>? rowid,
  }) {
    return RawValuesInsertable({
      if (key != null) 'key': key,
      if (value != null) 'value': value,
      if (rowid != null) 'rowid': rowid,
    });
  }

  SyncMetadataCompanion copyWith({
    Value<String>? key,
    Value<String>? value,
    Value<int>? rowid,
  }) {
    return SyncMetadataCompanion(
      key: key ?? this.key,
      value: value ?? this.value,
      rowid: rowid ?? this.rowid,
    );
  }

  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    if (key.present) {
      map['key'] = Variable<String>(key.value);
    }
    if (value.present) {
      map['value'] = Variable<String>(value.value);
    }
    if (rowid.present) {
      map['rowid'] = Variable<int>(rowid.value);
    }
    return map;
  }

  @override
  String toString() {
    return (StringBuffer('SyncMetadataCompanion(')
          ..write('key: $key, ')
          ..write('value: $value, ')
          ..write('rowid: $rowid')
          ..write(')'))
        .toString();
  }
}

abstract class _$LocalDatabase extends GeneratedDatabase {
  _$LocalDatabase(QueryExecutor e) : super(e);
  $LocalDatabaseManager get managers => $LocalDatabaseManager(this);
  late final $PendingEventsTable pendingEvents = $PendingEventsTable(this);
  late final $SyncMetadataTable syncMetadata = $SyncMetadataTable(this);
  @override
  Iterable<TableInfo<Table, Object?>> get allTables =>
      allSchemaEntities.whereType<TableInfo<Table, Object?>>();
  @override
  List<DatabaseSchemaEntity> get allSchemaEntities => [
    pendingEvents,
    syncMetadata,
  ];
}

typedef $$PendingEventsTableCreateCompanionBuilder =
    PendingEventsCompanion Function({
      required String clientEventUuid,
      required String eventType,
      required String assignmentId,
      required String tipperId,
      required String siteId,
      required String supervisorName,
      required DateTime deviceCreatedAt,
      required String syncState,
      Value<int> retryCount,
      required String payloadJson,
      Value<String?> evidencePath,
      Value<String?> lastSyncError,
      required DateTime createdAt,
      Value<int> rowid,
    });
typedef $$PendingEventsTableUpdateCompanionBuilder =
    PendingEventsCompanion Function({
      Value<String> clientEventUuid,
      Value<String> eventType,
      Value<String> assignmentId,
      Value<String> tipperId,
      Value<String> siteId,
      Value<String> supervisorName,
      Value<DateTime> deviceCreatedAt,
      Value<String> syncState,
      Value<int> retryCount,
      Value<String> payloadJson,
      Value<String?> evidencePath,
      Value<String?> lastSyncError,
      Value<DateTime> createdAt,
      Value<int> rowid,
    });

class $$PendingEventsTableFilterComposer
    extends Composer<_$LocalDatabase, $PendingEventsTable> {
  $$PendingEventsTableFilterComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnFilters<String> get clientEventUuid => $composableBuilder(
    column: $table.clientEventUuid,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get eventType => $composableBuilder(
    column: $table.eventType,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get assignmentId => $composableBuilder(
    column: $table.assignmentId,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get tipperId => $composableBuilder(
    column: $table.tipperId,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get siteId => $composableBuilder(
    column: $table.siteId,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get supervisorName => $composableBuilder(
    column: $table.supervisorName,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<DateTime> get deviceCreatedAt => $composableBuilder(
    column: $table.deviceCreatedAt,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get syncState => $composableBuilder(
    column: $table.syncState,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<int> get retryCount => $composableBuilder(
    column: $table.retryCount,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get payloadJson => $composableBuilder(
    column: $table.payloadJson,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get evidencePath => $composableBuilder(
    column: $table.evidencePath,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get lastSyncError => $composableBuilder(
    column: $table.lastSyncError,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<DateTime> get createdAt => $composableBuilder(
    column: $table.createdAt,
    builder: (column) => ColumnFilters(column),
  );
}

class $$PendingEventsTableOrderingComposer
    extends Composer<_$LocalDatabase, $PendingEventsTable> {
  $$PendingEventsTableOrderingComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnOrderings<String> get clientEventUuid => $composableBuilder(
    column: $table.clientEventUuid,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get eventType => $composableBuilder(
    column: $table.eventType,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get assignmentId => $composableBuilder(
    column: $table.assignmentId,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get tipperId => $composableBuilder(
    column: $table.tipperId,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get siteId => $composableBuilder(
    column: $table.siteId,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get supervisorName => $composableBuilder(
    column: $table.supervisorName,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<DateTime> get deviceCreatedAt => $composableBuilder(
    column: $table.deviceCreatedAt,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get syncState => $composableBuilder(
    column: $table.syncState,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<int> get retryCount => $composableBuilder(
    column: $table.retryCount,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get payloadJson => $composableBuilder(
    column: $table.payloadJson,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get evidencePath => $composableBuilder(
    column: $table.evidencePath,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get lastSyncError => $composableBuilder(
    column: $table.lastSyncError,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<DateTime> get createdAt => $composableBuilder(
    column: $table.createdAt,
    builder: (column) => ColumnOrderings(column),
  );
}

class $$PendingEventsTableAnnotationComposer
    extends Composer<_$LocalDatabase, $PendingEventsTable> {
  $$PendingEventsTableAnnotationComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  GeneratedColumn<String> get clientEventUuid => $composableBuilder(
    column: $table.clientEventUuid,
    builder: (column) => column,
  );

  GeneratedColumn<String> get eventType =>
      $composableBuilder(column: $table.eventType, builder: (column) => column);

  GeneratedColumn<String> get assignmentId => $composableBuilder(
    column: $table.assignmentId,
    builder: (column) => column,
  );

  GeneratedColumn<String> get tipperId =>
      $composableBuilder(column: $table.tipperId, builder: (column) => column);

  GeneratedColumn<String> get siteId =>
      $composableBuilder(column: $table.siteId, builder: (column) => column);

  GeneratedColumn<String> get supervisorName => $composableBuilder(
    column: $table.supervisorName,
    builder: (column) => column,
  );

  GeneratedColumn<DateTime> get deviceCreatedAt => $composableBuilder(
    column: $table.deviceCreatedAt,
    builder: (column) => column,
  );

  GeneratedColumn<String> get syncState =>
      $composableBuilder(column: $table.syncState, builder: (column) => column);

  GeneratedColumn<int> get retryCount => $composableBuilder(
    column: $table.retryCount,
    builder: (column) => column,
  );

  GeneratedColumn<String> get payloadJson => $composableBuilder(
    column: $table.payloadJson,
    builder: (column) => column,
  );

  GeneratedColumn<String> get evidencePath => $composableBuilder(
    column: $table.evidencePath,
    builder: (column) => column,
  );

  GeneratedColumn<String> get lastSyncError => $composableBuilder(
    column: $table.lastSyncError,
    builder: (column) => column,
  );

  GeneratedColumn<DateTime> get createdAt =>
      $composableBuilder(column: $table.createdAt, builder: (column) => column);
}

class $$PendingEventsTableTableManager
    extends
        RootTableManager<
          _$LocalDatabase,
          $PendingEventsTable,
          PendingEvent,
          $$PendingEventsTableFilterComposer,
          $$PendingEventsTableOrderingComposer,
          $$PendingEventsTableAnnotationComposer,
          $$PendingEventsTableCreateCompanionBuilder,
          $$PendingEventsTableUpdateCompanionBuilder,
          (
            PendingEvent,
            BaseReferences<_$LocalDatabase, $PendingEventsTable, PendingEvent>,
          ),
          PendingEvent,
          PrefetchHooks Function()
        > {
  $$PendingEventsTableTableManager(
    _$LocalDatabase db,
    $PendingEventsTable table,
  ) : super(
        TableManagerState(
          db: db,
          table: table,
          createFilteringComposer: () =>
              $$PendingEventsTableFilterComposer($db: db, $table: table),
          createOrderingComposer: () =>
              $$PendingEventsTableOrderingComposer($db: db, $table: table),
          createComputedFieldComposer: () =>
              $$PendingEventsTableAnnotationComposer($db: db, $table: table),
          updateCompanionCallback:
              ({
                Value<String> clientEventUuid = const Value.absent(),
                Value<String> eventType = const Value.absent(),
                Value<String> assignmentId = const Value.absent(),
                Value<String> tipperId = const Value.absent(),
                Value<String> siteId = const Value.absent(),
                Value<String> supervisorName = const Value.absent(),
                Value<DateTime> deviceCreatedAt = const Value.absent(),
                Value<String> syncState = const Value.absent(),
                Value<int> retryCount = const Value.absent(),
                Value<String> payloadJson = const Value.absent(),
                Value<String?> evidencePath = const Value.absent(),
                Value<String?> lastSyncError = const Value.absent(),
                Value<DateTime> createdAt = const Value.absent(),
                Value<int> rowid = const Value.absent(),
              }) => PendingEventsCompanion(
                clientEventUuid: clientEventUuid,
                eventType: eventType,
                assignmentId: assignmentId,
                tipperId: tipperId,
                siteId: siteId,
                supervisorName: supervisorName,
                deviceCreatedAt: deviceCreatedAt,
                syncState: syncState,
                retryCount: retryCount,
                payloadJson: payloadJson,
                evidencePath: evidencePath,
                lastSyncError: lastSyncError,
                createdAt: createdAt,
                rowid: rowid,
              ),
          createCompanionCallback:
              ({
                required String clientEventUuid,
                required String eventType,
                required String assignmentId,
                required String tipperId,
                required String siteId,
                required String supervisorName,
                required DateTime deviceCreatedAt,
                required String syncState,
                Value<int> retryCount = const Value.absent(),
                required String payloadJson,
                Value<String?> evidencePath = const Value.absent(),
                Value<String?> lastSyncError = const Value.absent(),
                required DateTime createdAt,
                Value<int> rowid = const Value.absent(),
              }) => PendingEventsCompanion.insert(
                clientEventUuid: clientEventUuid,
                eventType: eventType,
                assignmentId: assignmentId,
                tipperId: tipperId,
                siteId: siteId,
                supervisorName: supervisorName,
                deviceCreatedAt: deviceCreatedAt,
                syncState: syncState,
                retryCount: retryCount,
                payloadJson: payloadJson,
                evidencePath: evidencePath,
                lastSyncError: lastSyncError,
                createdAt: createdAt,
                rowid: rowid,
              ),
          withReferenceMapper: (p0) => p0
              .map(
                (e) => (
                  e.readTable<$PendingEventsTable, PendingEvent>(table),
                  BaseReferences<
                    _$LocalDatabase,
                    $PendingEventsTable,
                    PendingEvent
                  >(db, table, e),
                ),
              )
              .toList(),
          prefetchHooksCallback: null,
        ),
      );
}

typedef $$PendingEventsTableProcessedTableManager =
    ProcessedTableManager<
      _$LocalDatabase,
      $PendingEventsTable,
      PendingEvent,
      $$PendingEventsTableFilterComposer,
      $$PendingEventsTableOrderingComposer,
      $$PendingEventsTableAnnotationComposer,
      $$PendingEventsTableCreateCompanionBuilder,
      $$PendingEventsTableUpdateCompanionBuilder,
      (
        PendingEvent,
        BaseReferences<_$LocalDatabase, $PendingEventsTable, PendingEvent>,
      ),
      PendingEvent,
      PrefetchHooks Function()
    >;
typedef $$SyncMetadataTableCreateCompanionBuilder =
    SyncMetadataCompanion Function({
      required String key,
      required String value,
      Value<int> rowid,
    });
typedef $$SyncMetadataTableUpdateCompanionBuilder =
    SyncMetadataCompanion Function({
      Value<String> key,
      Value<String> value,
      Value<int> rowid,
    });

class $$SyncMetadataTableFilterComposer
    extends Composer<_$LocalDatabase, $SyncMetadataTable> {
  $$SyncMetadataTableFilterComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnFilters<String> get key => $composableBuilder(
    column: $table.key,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get value => $composableBuilder(
    column: $table.value,
    builder: (column) => ColumnFilters(column),
  );
}

class $$SyncMetadataTableOrderingComposer
    extends Composer<_$LocalDatabase, $SyncMetadataTable> {
  $$SyncMetadataTableOrderingComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnOrderings<String> get key => $composableBuilder(
    column: $table.key,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get value => $composableBuilder(
    column: $table.value,
    builder: (column) => ColumnOrderings(column),
  );
}

class $$SyncMetadataTableAnnotationComposer
    extends Composer<_$LocalDatabase, $SyncMetadataTable> {
  $$SyncMetadataTableAnnotationComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  GeneratedColumn<String> get key =>
      $composableBuilder(column: $table.key, builder: (column) => column);

  GeneratedColumn<String> get value =>
      $composableBuilder(column: $table.value, builder: (column) => column);
}

class $$SyncMetadataTableTableManager
    extends
        RootTableManager<
          _$LocalDatabase,
          $SyncMetadataTable,
          SyncMetadataData,
          $$SyncMetadataTableFilterComposer,
          $$SyncMetadataTableOrderingComposer,
          $$SyncMetadataTableAnnotationComposer,
          $$SyncMetadataTableCreateCompanionBuilder,
          $$SyncMetadataTableUpdateCompanionBuilder,
          (
            SyncMetadataData,
            BaseReferences<
              _$LocalDatabase,
              $SyncMetadataTable,
              SyncMetadataData
            >,
          ),
          SyncMetadataData,
          PrefetchHooks Function()
        > {
  $$SyncMetadataTableTableManager(_$LocalDatabase db, $SyncMetadataTable table)
    : super(
        TableManagerState(
          db: db,
          table: table,
          createFilteringComposer: () =>
              $$SyncMetadataTableFilterComposer($db: db, $table: table),
          createOrderingComposer: () =>
              $$SyncMetadataTableOrderingComposer($db: db, $table: table),
          createComputedFieldComposer: () =>
              $$SyncMetadataTableAnnotationComposer($db: db, $table: table),
          updateCompanionCallback:
              ({
                Value<String> key = const Value.absent(),
                Value<String> value = const Value.absent(),
                Value<int> rowid = const Value.absent(),
              }) => SyncMetadataCompanion(key: key, value: value, rowid: rowid),
          createCompanionCallback:
              ({
                required String key,
                required String value,
                Value<int> rowid = const Value.absent(),
              }) => SyncMetadataCompanion.insert(
                key: key,
                value: value,
                rowid: rowid,
              ),
          withReferenceMapper: (p0) => p0
              .map(
                (e) => (
                  e.readTable<$SyncMetadataTable, SyncMetadataData>(table),
                  BaseReferences<
                    _$LocalDatabase,
                    $SyncMetadataTable,
                    SyncMetadataData
                  >(db, table, e),
                ),
              )
              .toList(),
          prefetchHooksCallback: null,
        ),
      );
}

typedef $$SyncMetadataTableProcessedTableManager =
    ProcessedTableManager<
      _$LocalDatabase,
      $SyncMetadataTable,
      SyncMetadataData,
      $$SyncMetadataTableFilterComposer,
      $$SyncMetadataTableOrderingComposer,
      $$SyncMetadataTableAnnotationComposer,
      $$SyncMetadataTableCreateCompanionBuilder,
      $$SyncMetadataTableUpdateCompanionBuilder,
      (
        SyncMetadataData,
        BaseReferences<_$LocalDatabase, $SyncMetadataTable, SyncMetadataData>,
      ),
      SyncMetadataData,
      PrefetchHooks Function()
    >;

class $LocalDatabaseManager {
  final _$LocalDatabase _db;
  $LocalDatabaseManager(this._db);
  $$PendingEventsTableTableManager get pendingEvents =>
      $$PendingEventsTableTableManager(_db, _db.pendingEvents);
  $$SyncMetadataTableTableManager get syncMetadata =>
      $$SyncMetadataTableTableManager(_db, _db.syncMetadata);
}
