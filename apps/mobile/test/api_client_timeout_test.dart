import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:drift/native.dart';
import 'package:fleet_manager_mobile/app.dart';
import 'package:fleet_manager_mobile/data/api_client.dart';
import 'package:fleet_manager_mobile/data/local_database.dart';
import 'package:fleet_manager_mobile/data/secure_session_store.dart';
import 'package:fleet_manager_mobile/data/sync_engine.dart';
import 'package:fleet_manager_mobile/domain/driver_models.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

const _tokens = SessionTokens(
  accessToken: 'timeout-test-access',
  refreshToken: 'timeout-test-refresh',
  expiresIn: 900,
  membershipId: 'membership',
  companyId: 'company',
  role: 'SUPERVISOR',
);

const _assignment = DriverAssignment(
  assignmentId: 'assignment',
  tipperId: 'tipper',
  tipperRegistrationNumber: 'TEST',
  tipperShortName: 'Test tipper',
  siteId: 'site',
  siteName: 'Test site',
  supervisorName: 'Test supervisor',
);

void main() {
  for (final stallBody in [false, true]) {
    for (final evidence in [false, true]) {
      test(
        'timeout aborts ${evidence ? 'upload' : 'JSON'} '
        '${stallBody ? 'body' : 'send'} and preserves authentication',
        () async {
          final client = _StallingClient(stallBody: stallBody);
          final api = ApiClient(
            baseUrl: 'http://test',
            client: client,
            requestTimeout: const Duration(milliseconds: 100),
          )..setSession(_tokens);
          final directory = await Directory.systemTemp.createTemp(
            'fleet-timeout-',
          );
          addTearDown(() => directory.delete(recursive: true));
          final photo = File('${directory.path}/meter.jpg');
          await photo.writeAsBytes([0xff, 0xd8, 0xff, 0xe0, 0, 1]);
          final operation = evidence
              ? api.uploadEvidence(
                  clientEventUuid: 'stable-uuid',
                  evidencePath: photo.path,
                )
              : api.validateSession();

          await expectLater(
            operation,
            throwsA(
              isA<ApiException>()
                  .having((error) => error.statusCode, 'status', 408)
                  .having((error) => error.code, 'code', 'REQUEST_TIMEOUT')
                  .having((error) => error.isRetryable, 'retryable', isTrue),
            ),
          );
          await Future<void>.delayed(Duration.zero);
          expect(client.aborts, 1);
          expect(client.requests, hasLength(1));
          expect(api.session, same(_tokens));
          expect(await photo.exists(), isTrue);
        },
      );
    }
  }

  test(
    'timed out evidence remains queued and retries with its original UUID',
    () async {
      final directory = await Directory.systemTemp.createTemp(
        'fleet-timeout-queue-',
      );
      addTearDown(() => directory.delete(recursive: true));
      final photo = File('${directory.path}/meter.jpg');
      await photo.writeAsBytes([0xff, 0xd8, 0xff, 0xe0, 0, 1]);
      final database = LocalDatabase(
        NativeDatabase(File('${directory.path}/queue.sqlite')),
      );
      addTearDown(database.close);
      final client = _StallingClient(stallBody: true);
      final api = ApiClient(
        baseUrl: 'http://test',
        client: client,
        requestTimeout: const Duration(milliseconds: 100),
      )..setSession(_tokens);
      final engine = SyncEngine(
        database: database,
        remote: api,
        installationIdentifier: 'device',
      );
      final eventId = await engine.enqueue(
        assignment: _assignment,
        eventType: DriverEventType.kmReading,
        payload: {'reading_type': 'START_READING', 'reading_value': '1000'},
        evidencePath: photo.path,
      );

      expect(await engine.syncPending(), 0);
      final pending = (await database.pendingForSync()).single;
      expect(pending.clientEventUuid, eventId);
      expect(pending.evidencePath, photo.path);
      expect(await photo.exists(), isTrue);
      expect(await engine.lastSyncErrorCode(), 'REQUEST_TIMEOUT');
      client.stall = false;
      expect(await engine.syncPending(), 1);
      expect(await engine.syncPending(), 0);
      final uploads = client.requests.where(
        (request) => request.url.path.endsWith('/evidence'),
      );
      expect(uploads, hasLength(2));
      expect(
        uploads.every(
          (request) =>
              request.url.queryParameters['client_event_uuid'] == eventId,
        ),
        isTrue,
      );
      final submission =
          client.requests.singleWhere(
                (request) => request.url.path.endsWith('/events'),
              )
              as http.Request;
      expect(
        (jsonDecode(submission.body)
            as Map<String, dynamic>)['client_event_uuid'],
        eventId,
      );
    },
  );

  testWidgets(
    'logout timeout clears credentials while retaining queued records',
    (tester) async {
      FlutterSecureStorage.setMockInitialValues({});
      final sessionStore = SecureSessionStore();
      await sessionStore.save(_tokens);
      final client = _StallingClient(
        stallBody: false,
        stallPath: '/api/v1/auth/logout',
      );
      final api = ApiClient(
        baseUrl: 'http://test',
        client: client,
        requestTimeout: const Duration(milliseconds: 100),
      )..setSession(_tokens);
      final database = LocalDatabase(NativeDatabase.memory());
      addTearDown(database.close);
      final engine = SyncEngine(
        database: database,
        remote: api,
        installationIdentifier: 'device',
      );
      final eventId = await engine.enqueue(
        assignment: _assignment,
        eventType: DriverEventType.emergency,
      );
      await tester.pumpWidget(
        FleetManagerApp(
          dependencies: DriverAppDependencies(
            api: api,
            sessionStore: sessionStore,
            sync: engine,
            installationIdentifier: 'device',
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Sign out'));
      await tester.pumpAndSettle();

      expect(client.aborts, 1);
      expect(api.session, isNull);
      expect(await sessionStore.read(), isNull);
      expect(await database.eventById(eventId), isNotNull);
      expect(find.text('Sign in'), findsOneWidget);
    },
  );
}

class _StallingClient extends http.BaseClient {
  _StallingClient({required this.stallBody, this.stallPath});
  final bool stallBody;
  final String? stallPath;
  bool stall = true;
  int aborts = 0;
  final requests = <http.BaseRequest>[];

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    requests.add(request);
    await request.finalize().toBytes();
    if (stall && (stallPath == null || request.url.path == stallPath)) {
      final trigger = (request as http.Abortable).abortTrigger!;
      if (!stallBody) {
        await trigger;
        aborts++;
        throw http.RequestAbortedException(request.url);
      }
      final body = StreamController<List<int>>();
      unawaited(
        trigger.then((_) async {
          aborts++;
          body.addError(http.RequestAbortedException(request.url));
          await body.close();
        }),
      );
      return http.StreamedResponse(body.stream, 200);
    }
    final payload = switch (request.url.path) {
      '/api/v1/auth/me' => '{"display_name":"Test supervisor"}',
      '/api/v1/supervisor/sites' => '[]',
      '/api/v1/driver/evidence' => '{"object_reference":"evidence/test"}',
      _ => '{}',
    };
    return http.StreamedResponse(Stream.value(utf8.encode(payload)), 200);
  }
}
