import 'dart:io';
import 'package:drift/native.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:fleet_manager_mobile/app.dart';
import 'package:fleet_manager_mobile/data/api_client.dart';
import 'package:fleet_manager_mobile/data/local_database.dart'
    hide PendingEvent;
import 'package:fleet_manager_mobile/data/secure_session_store.dart';
import 'package:fleet_manager_mobile/data/sync_engine.dart';
import 'package:fleet_manager_mobile/domain/driver_models.dart';
import 'package:fleet_manager_mobile/domain/role_models.dart';
import 'package:fleet_manager_mobile/fleet_theme.dart';
import 'package:fleet_manager_mobile/role_screens.dart';

// Run only when approved product imagery needs to be refreshed:
// flutter test --update-goldens tool/marketing_screenshots_test.dart
// The fixtures below are representative and contain no customer records.
void main() {
  setUpAll(() async {
    final bytes = await File(r'C:\Windows\Fonts\segoeui.ttf').readAsBytes();
    await (FontLoader(
      'MarketingSegoe',
    )..addFont(Future.value(ByteData.sublistView(bytes)))).load();
    final iconBytes = await File(
      r'C:\Users\Hp\develop\flutter\bin\cache\artifacts\material_fonts\MaterialIcons-Regular.otf',
    ).readAsBytes();
    await (FontLoader(
      'MaterialIcons',
    )..addFont(Future.value(ByteData.sublistView(iconBytes)))).load();
  });

  testWidgets('capture representative Driver screens', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final database = LocalDatabase(NativeDatabase.memory());
    addTearDown(database.close);
    final api = _MarketingApi();
    final dependencies = DriverAppDependencies(
      api: api,
      sessionStore: SecureSessionStore(),
      sync: SyncEngine(
        database: database,
        remote: _MarketingRemote(),
        installationIdentifier: 'marketing-demo-device',
      ),
      installationIdentifier: 'marketing-demo-device',
    );

    await tester.pumpWidget(
      _MarketingFrame(
        child: DriverHomeScreen(
          dependencies: dependencies,
          assignment: _driverAssignment,
          duty: const DriverDutyState(status: DriverDutyStatus.active),
          onSignOut: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('../../marketing/public/product/driver-operations.png'),
    );

    await tester.pumpWidget(
      _MarketingFrame(
        child: DriverHomeScreen(
          dependencies: dependencies,
          assignment: _driverAssignment,
          duty: const DriverDutyState.none(),
          onSignOut: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('START DUTY'));
    await tester.pumpAndSettle();
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('../../marketing/public/product/driver-start-duty.png'),
    );
  });

  testWidgets('capture representative Supervisor and Maintenance screens', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(390, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final api = _MarketingApi();

    await tester.pumpWidget(
      _MarketingFrame(
        child: SupervisorHomeScreen(api: api, onSignOut: () async {}),
      ),
    );
    await tester.pumpAndSettle();
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('../../marketing/public/product/supervisor-review.png'),
    );

    await tester.tap(
      find.byKey(const Key('supervisor-notification-maintenance')),
    );
    await tester.pumpAndSettle();
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile(
        '../../marketing/public/product/maintenance-review.png',
      ),
    );
  });
}

class _MarketingFrame extends StatelessWidget {
  const _MarketingFrame({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final baseTheme = fleetTheme();
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Fleet AI Systems',
      theme: baseTheme.copyWith(
        textTheme: baseTheme.textTheme.apply(fontFamily: 'MarketingSegoe'),
        primaryTextTheme: baseTheme.primaryTextTheme.apply(
          fontFamily: 'MarketingSegoe',
        ),
      ),
      home: child,
    );
  }
}

const _driverAssignment = DriverAssignment(
  assignmentId: 'demo-assignment',
  tipperId: 'demo-tipper-12',
  tipperRegistrationNumber: 'DEMO-12',
  tipperShortName: 'Demo Tipper 12',
  tipperAssetCode: 'TIPPER-12',
  companyMaintenanceManaged: true,
  siteId: 'demo-site',
  siteName: 'Demo Earthworks Site',
  supervisorName: 'Demo Supervisor',
);

class _MarketingApi extends ApiClient {
  _MarketingApi() : super(baseUrl: 'http://marketing-fixture.invalid');

  @override
  Future<String> currentDisplayName() async => 'Demo Supervisor';

  @override
  Future<List<DriverMaintenanceItem>> driverDueMaintenance() async => const [
    DriverMaintenanceItem(
      scheduleId: 'demo-service',
      assetId: 'demo-tipper-12',
      taskLabel: 'Engine oil service',
      status: 'DUE',
    ),
  ];

  @override
  Future<List<SupervisorSite>> supervisorSites() async => const [
    SupervisorSite(
      id: 'demo-site',
      name: 'Demo Earthworks Site',
      shortName: 'DEMO SITE',
    ),
  ];

  @override
  Future<List<SupervisorEvent>> supervisorEvents(
    String siteId, {
    String? verificationStatus,
    DateTime? reviewDate,
  }) async => [
    _event('emergency', 'EMERGENCY', emergencyStatus: 'OPEN'),
    _event('diesel', 'DIESEL', litres: 42),
    _event('trip', 'TRIP_COMPLETE'),
    _event(
      'meter',
      'KM_READING',
      readingType: 'START_READING',
      readingValue: 42150,
    ),
  ];

  SupervisorEvent _event(
    String id,
    String type, {
    String? emergencyStatus,
    double? litres,
    String? readingType,
    double? readingValue,
  }) => SupervisorEvent.fromJson({
    'event_id': id,
    'event_type': type,
    'assignment_id': 'demo-assignment',
    'driver_name': 'Demo Driver',
    'driver_phone': '0000000000',
    'asset_code': 'TIPPER-12',
    'asset_short_name': 'Demo Tipper 12',
    'asset_type': 'TIPPER',
    'tipper_registration_number': 'DEMO-12',
    'site_id': 'demo-site',
    'site_name': 'Demo Earthworks Site',
    'device_created_at': '2026-10-10T08:00:00Z',
    'verification_status': 'PENDING_VERIFICATION',
    'emergency_category': type == 'EMERGENCY' ? 'BREAKDOWN' : null,
    'emergency_status': emergencyStatus,
    'emergency_description': type == 'EMERGENCY'
        ? 'Representative breakdown alert'
        : null,
    'litres': litres,
    'reading_type': readingType,
    'reading_value': readingValue,
    'evidence_available': false,
  });

  @override
  Future<List<MaintenanceProof>> supervisorMaintenanceProofs({
    String? siteId,
  }) async => [
    MaintenanceProof.fromJson({
      'id': 'demo-proof',
      'asset_code': 'TIPPER-12',
      'task_label': 'Engine oil service',
      'status': 'PROOF_SUBMITTED',
      'driver_name': 'Demo Driver',
      'site_id': 'demo-site',
      'site_name': 'Demo Earthworks Site',
      'submitted_at': '2026-10-10T08:00:00Z',
      'evidence': [
        {
          'evidence_id': 'demo-evidence',
          'content_type': 'image/jpeg',
          'size_bytes': 100,
        },
      ],
    }),
  ];
}

class _MarketingRemote implements DriverRemoteApi, DriverMaintenanceRemote {
  @override
  Future<DeviceRegistration> registerDevice({
    required String installationIdentifier,
    bool allowHandover = false,
    bool localStateClear = false,
  }) async => const DeviceRegistration(
    deviceId: 'marketing-device',
    membershipId: 'marketing-membership',
    handedOver: false,
  );

  @override
  Future<void> submitEvent({
    required PendingEvent event,
    required String installationIdentifier,
  }) async {}

  @override
  Future<void> submitMaintenanceProof({required PendingEvent event}) async {}

  @override
  Future<String> uploadEvidence({
    required String clientEventUuid,
    required String evidencePath,
  }) async => 'representative/$clientEventUuid';
}
