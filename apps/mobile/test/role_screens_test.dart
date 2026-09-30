import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:fleet_manager_mobile/data/api_client.dart';
import 'package:fleet_manager_mobile/domain/role_models.dart';
import 'package:fleet_manager_mobile/role_screens.dart';

void main() {
  testWidgets(
    'supervisor home puts emergencies first and shows asset-centric cards',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(1080, 2400));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final api = _FakeRoleApi();
      await tester.pumpWidget(
        MaterialApp(
          home: SupervisorHomeScreen(api: api, onSignOut: () async {}),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Emergencies'), findsOneWidget);
      expect(find.text('Assets'), findsWidgets);
      expect(find.text('PILOT-12'), findsWidgets);
      expect(find.text('EXC-07'), findsOneWidget);
      expect(find.text('Unassigned'), findsNWidgets(2));
      expect(find.text('NEED REVIEW'), findsNWidgets(2));
      expect(find.text('Today summary'), findsOneWidget);
      expect(find.text('Review'), findsOneWidget);
      expect(find.text('Timeline'), findsOneWidget);
      expect(find.byKey(const Key('supervisor-site-selector')), findsNothing);
      expect(find.text('Pilot Site'), findsNothing);
      expect(find.text('ACKNOWLEDGE'), findsOneWidget);
    },
  );

  testWidgets(
    'approved START disappears from review count while emergency stays separate',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(1080, 4000));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final api = _FakeRoleApi();
      await tester.pumpWidget(
        MaterialApp(
          home: SupervisorHomeScreen(api: api, onSignOut: () async {}),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('1 pending'), findsNWidgets(2));
      if (find.text('APPROVE').evaluate().isEmpty) {
        await tester.tap(find.text('Review'));
        await tester.pumpAndSettle();
      }
      expect(find.text('APPROVE'), findsOneWidget);
      await tester.tap(find.text('APPROVE'));
      await tester.pumpAndSettle();

      expect(api.approvedEventId, _FakeRoleApi.startEventId);
      expect(find.text('1 pending'), findsNothing);
      expect(find.text('0 pending'), findsOneWidget);
      expect(find.text('APPROVE'), findsNothing);
      expect(find.text('Record approved.'), findsOneWidget);
      expect(find.text('ACKNOWLEDGE'), findsOneWidget);
    },
  );

  testWidgets('supervisor changes driver from an authorized site asset', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1080, 1800));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final api = _FakeRoleApi();
    await tester.pumpWidget(
      MaterialApp(
        home: SupervisorHomeScreen(api: api, onSignOut: () async {}),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(
      find.byKey(const Key('supervisor-assign-driver-pilot-asset')),
    );
    await tester.pumpAndSettle();
    expect(find.text('CHANGE DRIVER / OPERATOR · PILOT-12'), findsOneWidget);
    expect(find.byKey(const Key('assignment-site')), findsOneWidget);
    await tester.tap(find.byKey(const Key('confirm-driver-assignment')));
    await tester.pumpAndSettle();

    expect(api.assignedDriverId, 'driver-2');
    expect(api.assignmentSiteId, 'site-1');
  });

  testWidgets('supervisor assigns an operator to unassigned machinery', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1080, 1800));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final api = _FakeRoleApi();
    await tester.pumpWidget(
      MaterialApp(
        home: SupervisorHomeScreen(api: api, onSignOut: () async {}),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const Key('supervisor-assign-driver-excavator-7')),
      findsOneWidget,
    );
    await tester.tap(
      find.byKey(const Key('supervisor-assign-driver-excavator-7')),
    );
    await tester.pumpAndSettle();
    expect(find.text('ASSIGN DRIVER / OPERATOR · EXC-07'), findsOneWidget);
    await tester.tap(find.byKey(const Key('confirm-driver-assignment')));
    await tester.pumpAndSettle();

    expect(api.assignedAssetId, 'excavator-7');
    expect(api.assignedDriverId, 'driver-2');
  });

  testWidgets('supervisor search and bounded filters reduce the asset list', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1080, 2400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final api = _FakeRoleApi();
    await tester.pumpWidget(
      MaterialApp(
        home: SupervisorHomeScreen(api: api, onSignOut: () async {}),
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const Key('supervisor-asset-search')),
      'EXC-07',
    );
    await tester.pump();
    expect(
      find.byKey(const Key('supervisor-site-asset-excavator-7')),
      findsOneWidget,
    );
    expect(
      find.byKey(const Key('supervisor-site-asset-pilot-asset')),
      findsNothing,
    );

    await tester.enterText(
      find.byKey(const Key('supervisor-asset-search')),
      '',
    );
    await tester.tap(find.text('UNASSIGNED'));
    await tester.pump();
    expect(
      find.byKey(const Key('supervisor-site-asset-pilot-asset')),
      findsNothing,
    );
    expect(
      find.byKey(const Key('supervisor-site-asset-rent-t03')),
      findsOneWidget,
    );
  });

  testWidgets(
    'supervisor machinery card shows HMR hours without trip metrics',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(1080, 2400));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(
        MaterialApp(
          home: SupervisorHomeScreen(
            api: _MachineryRoleApi(),
            onSignOut: () async {},
          ),
        ),
      );
      await tester.pumpAndSettle();

      final card = find.byKey(const Key('supervisor-site-asset-exc-01'));
      expect(card, findsOneWidget);
      expect(
        find.descendant(of: card, matching: find.text('START HMR 3240.50')),
        findsOneWidget,
      );
      expect(
        find.descendant(of: card, matching: find.text('END HMR 3248')),
        findsOneWidget,
      );
      expect(
        find.descendant(of: card, matching: find.text('MACHINE HOURS 7.50')),
        findsOneWidget,
      );
      expect(
        find.descendant(of: card, matching: find.text('Diesel 25 L')),
        findsOneWidget,
      );
      expect(
        find.descendant(of: card, matching: find.textContaining('Trips')),
        findsNothing,
      );
      expect(find.text('2 pending'), findsWidgets);
      expect(find.text('Review'), findsOneWidget);
      expect(find.text('Timeline'), findsOneWidget);
    },
  );

  for (final assetCount in [1, 10, 50]) {
    testWidgets('supervisor fleet list handles $assetCount assets', (
      tester,
    ) async {
      await tester.binding.setSurfaceSize(const Size(390, 844));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final api = _ScaleRoleApi(assetCount: assetCount);
      await tester.pumpWidget(
        MaterialApp(
          home: SupervisorHomeScreen(api: api, onSignOut: () async {}),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('$assetCount'), findsAtLeastNWidgets(1));
      expect(
        find.byKey(const Key('supervisor-site-asset-scale-0')),
        findsOneWidget,
      );
      await tester.scrollUntilVisible(
        find.byKey(Key('supervisor-site-asset-scale-${assetCount - 1}')),
        800,
        scrollable: find.byType(Scrollable).first,
      );
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets(
    'multi-site supervisor uses one selector and keeps emergencies global',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(390, 1000));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final api = _MultiSiteRoleApi();
      await tester.pumpWidget(
        MaterialApp(
          home: SupervisorHomeScreen(api: api, onSignOut: () async {}),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('supervisor-site-selector')), findsOneWidget);
      expect(find.text('North Site'), findsWidgets);
      expect(find.textContaining('South Site'), findsWidgets);
      expect(find.text('South emergency'), findsOneWidget);
      expect(
        find.text('A deliberately very long asset name that must not overflow'),
        findsOneWidget,
      );
      expect(tester.takeException(), isNull);
    },
  );

  test(
    'physical event statuses yield zero normal review items after approval',
    () {
      final events = [
        _FakeRoleApi.event(
          id: _FakeRoleApi.startEventId,
          eventType: 'KM_READING',
          verificationStatus: 'APPROVED',
        ),
        _FakeRoleApi.event(
          id: _FakeRoleApi.emergencyEventId,
          eventType: 'EMERGENCY',
          verificationStatus: 'PENDING_VERIFICATION',
        ),
      ];

      expect(events.first.id, '7cb203af-aaf4-4c8d-af39-84d2ca6e263f');
      expect(events.first.verificationStatus, 'APPROVED');
      expect(events.last.id, 'cb0915c7-4e29-4f19-8e0c-4f6c95d51c74');
      expect(events.last.verificationStatus, 'PENDING_VERIFICATION');
      expect(supervisorReviewPendingCount(events), 0);
    },
  );

  test('supervisor diesel summary adds litres rather than event count', () {
    SupervisorEvent diesel(String id, double litres) =>
        SupervisorEvent.fromJson({
          'event_id': id,
          'event_type': 'DIESEL',
          'assignment_id': 'assignment-1',
          'driver_name': 'Operator',
          'asset_code': 'EXC-01',
          'asset_type': 'EXCAVATOR',
          'tipper_registration_number': 'EXC-01',
          'site_id': 'site-1',
          'site_name': 'Pilot Site',
          'device_created_at': '2026-09-30T08:00:00Z',
          'verification_status': 'PENDING_VERIFICATION',
          'litres': litres,
          'evidence_available': false,
        });

    expect(supervisorDieselLitres([diesel('diesel-10', 10)]), 10);
    expect(
      supervisorDieselLitres([
        diesel('diesel-10', 10),
        diesel('diesel-15', 15),
      ]),
      25,
    );
  });

  testWidgets('owner home exposes management dashboard and duty monitoring', (
    tester,
  ) async {
    final api = _FakeRoleApi();
    await tester.pumpWidget(
      MaterialApp(
        home: OwnerHomeScreen(api: api, onSignOut: () async {}),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('TODAY'), findsOneWidget);
    expect(find.text('ACTIVE TIPPERS'), findsOneWidget);
    expect(find.text('APPROVED TRIPS'), findsOneWidget);
    expect(find.text('FLEET'), findsOneWidget);
    expect(find.text('REPORTS'), findsOneWidget);
    await tester.tap(find.text('REPORTS'));
    await tester.pump();
    expect(find.text('DRIVER DUTY / OVERTIME'), findsOneWidget);
    expect(find.text('25 min'), findsOneWidget);
    expect(find.text('START KM'), findsOneWidget);
    expect(find.text('END KM'), findsOneWidget);
    expect(find.text('DISTANCE'), findsOneWidget);
    expect(find.text('START HMR'), findsOneWidget);
    expect(find.text('END HMR'), findsOneWidget);
    expect(find.text('MACHINE HOURS'), findsOneWidget);
    expect(find.text('1.50 h'), findsOneWidget);
  });
}

class _FakeRoleApi extends ApiClient {
  _FakeRoleApi() : super(baseUrl: 'http://test');

  @override
  Future<List<OwnerAsset>> ownerAssets({
    String? status,
    String? ownershipType,
    String? assetType,
  }) async => [
    OwnerAsset.fromJson({
      'id': 'pilot-asset',
      'asset_code': 'TIPPER-12',
      'asset_type': 'TIPPER',
      'ownership_type': 'OWNED',
      'registration_number': 'PILOT12',
      'short_name': 'Tipper 12',
      'status': 'ACTIVE',
      'has_active_assignment': false,
      'active_assignment': null,
    }),
  ];

  static const startEventId = '7cb203af-aaf4-4c8d-af39-84d2ca6e263f';
  static const emergencyEventId = 'cb0915c7-4e29-4f19-8e0c-4f6c95d51c74';

  final _site = const SupervisorSite(id: 'site-1', name: 'Pilot Site');
  String? approvedEventId;
  String? assignedAssetId;
  String? assignedDriverId;
  String? assignmentSiteId;

  static SupervisorEvent event({
    required String id,
    required String eventType,
    required String verificationStatus,
  }) => SupervisorEvent.fromJson({
    'event_id': id,
    'event_type': eventType,
    'assignment_id': 'assignment-1',
    'driver_name': 'Pilot Driver',
    'driver_phone': '9606743463',
    'tipper_registration_number': 'PILOT-12',
    'site_id': 'site-1',
    'site_name': 'Pilot Site',
    'device_created_at': '2026-09-25T08:00:00Z',
    'verification_status': verificationStatus,
    'emergency_category': eventType == 'EMERGENCY' ? 'BREAKDOWN' : null,
    'emergency_status': eventType == 'EMERGENCY' ? 'OPEN' : null,
    'reading_type': eventType == 'KM_READING' ? 'START_READING' : null,
    'reading_value': eventType == 'KM_READING' ? 10000 : null,
    'evidence_available': false,
    'verification_history': [],
  });

  @override
  Future<List<SupervisorSite>> supervisorSites() async => [_site];

  @override
  Future<List<SiteDeployedAsset>> supervisorSiteAssets(String siteId) async => [
    SiteDeployedAsset.fromJson({
      'asset_id': 'pilot-asset',
      'asset_code': 'TIPPER-12',
      'asset_type': 'TIPPER',
      'ownership_type': 'OWNED',
      'registration_number': 'PILOT-12',
      'short_name': 'Tipper 12',
      'status': 'ACTIVE',
      'current_deployment': {
        'id': 'deployment-1',
        'asset_id': 'pilot-asset',
        'site_id': siteId,
        'site_name': 'Pilot Site',
        'starts_at': '2026-09-25T05:00:00Z',
        'ends_at': null,
      },
      'driver_membership_id': 'driver-1',
      'driver_name': 'Pilot Driver',
      'duty_status': 'ACTIVE',
      'pending_review_count': 1,
    }),
    SiteDeployedAsset.fromJson({
      'asset_id': 'rent-t03',
      'asset_code': 'RENT-T03',
      'asset_type': 'TIPPER',
      'ownership_type': 'RENTED',
      'registration_number': 'RENT-T03',
      'short_name': 'Rental Tipper 03',
      'status': 'ACTIVE',
      'current_deployment': {
        'id': 'deployment-2',
        'asset_id': 'rent-t03',
        'site_id': siteId,
        'site_name': 'Pilot Site',
        'starts_at': '2026-09-26T05:00:00Z',
        'ends_at': null,
      },
      'driver_membership_id': null,
      'driver_name': null,
      'duty_status': null,
      'pending_review_count': 0,
    }),
    SiteDeployedAsset.fromJson({
      'asset_id': 'excavator-7',
      'asset_code': 'EXCAVATOR-07',
      'asset_type': 'EXCAVATOR',
      'ownership_type': 'RENTED',
      'registration_number': 'EXC-07',
      'short_name': 'Excavator 7',
      'status': 'ACTIVE',
      'current_deployment': {
        'id': 'deployment-3',
        'asset_id': 'excavator-7',
        'site_id': siteId,
        'site_name': 'Pilot Site',
        'starts_at': '2026-09-26T05:00:00Z',
        'ends_at': null,
      },
      'driver_membership_id': null,
      'driver_name': null,
      'duty_status': null,
      'pending_review_count': 0,
    }),
  ];

  @override
  Future<List<SupervisorEvent>> supervisorEvents(
    String siteId, {
    String? verificationStatus,
    DateTime? reviewDate,
  }) async => [
    event(
      id: emergencyEventId,
      eventType: 'EMERGENCY',
      verificationStatus: 'PENDING_VERIFICATION',
    ),
    event(
      id: startEventId,
      eventType: 'KM_READING',
      verificationStatus: 'PENDING_VERIFICATION',
    ),
  ];

  @override
  Future<List<DriverCandidate>> eligibleDrivers(
    String assetId, {
    String? supervisorSiteId,
  }) async => const [
    DriverCandidate(membershipId: 'driver-2', displayName: 'Second Driver'),
  ];

  @override
  Future<DriverAssetAssignment> assignDriver(
    String assetId,
    String driverMembershipId, {
    String? supervisorSiteId,
    bool reassign = false,
  }) async {
    assignedAssetId = assetId;
    assignedDriverId = driverMembershipId;
    assignmentSiteId = supervisorSiteId;
    return DriverAssetAssignment.fromJson({
      'assignment_id': 'assignment-2',
      'asset_id': assetId,
      'asset_code': 'TIPPER-12',
      'driver_membership_id': driverMembershipId,
      'driver_name': 'Second Driver',
      'asset_site_deployment_id': 'deployment-1',
      'site_id': supervisorSiteId,
      'site_name': 'Pilot Site',
      'starts_at': '2026-09-30T08:00:00Z',
      'ends_at': null,
      'regular_duty_minutes': 600,
    });
  }

  @override
  Future<SupervisorEvent> verifySupervisorEvent(
    String eventId, {
    required String decision,
    String? reason,
  }) async {
    approvedEventId = eventId;
    return event(
      id: eventId,
      eventType: 'KM_READING',
      verificationStatus: decision,
    );
  }

  @override
  Future<OwnerDashboard> ownerDashboard({DateTime? date}) async =>
      OwnerDashboard.fromJson({
        'operational_date': '2026-09-25',
        'assigned_tippers_count': 1,
        'approved_trip_count': 4,
        'pending_verification_count': 1,
        'total_km': 120,
        'verified_diesel_issued': 30,
        'missing_reading_count': 0,
        'unresolved_emergency_count': 1,
        'drivers_on_duty': 1,
        'drivers_past_regular_duty': 1,
        'sites': [
          {
            'site_id': 'site-1',
            'site_name': 'Pilot Site',
            'assigned_tippers_count': 1,
            'approved_trip_count': 4,
            'total_km': 120,
            'verified_diesel_issued': 30,
            'pending_trip_count': 1,
            'missing_reading_count': 0,
            'unresolved_emergency_count': 1,
            'closure': {'status': 'OPEN'},
          },
        ],
      });

  @override
  Future<List<OwnerTipperReport>> ownerSiteDaily(
    String siteId, {
    DateTime? date,
  }) async => [
    OwnerTipperReport.fromJson({
      'registration': 'PILOT-12',
      'short_name': 'Tipper 12',
      'site_name': 'Pilot Site',
      'driver_name': 'Pilot Driver',
      'approved_trip_count': 4,
      'distance_km': 120,
      'verified_diesel_issued': 30,
      'pending_trip_count': 1,
      'pending_diesel_count': 0,
      'missing_start_reading': false,
      'missing_end_reading': false,
      'events': [],
    }),
  ];

  @override
  Future<List<OwnerDutyReport>> ownerDuty({DateTime? date}) async => [
    OwnerDutyReport.fromJson({
      'driver_name': 'Pilot Driver',
      'asset_code': 'TIPPER-12',
      'asset_type': 'TIPPER',
      'tipper_registration_number': 'PILOT-12',
      'site_name': 'Pilot Site',
      'duty_start': '2026-09-25T05:00:00Z',
      'start_km': 10000,
      'regular_duty_minutes': 600,
      'regular_duty_ends_at': '2026-09-25T15:00:00Z',
      'actual_duty_end': '2026-09-25T15:25:00Z',
      'end_km': 10120,
      'verified_diesel_issued': 30,
      'pending_diesel_issued': 0,
      'actual_duty_span_seconds': 37500,
      'overtime_minutes': 25,
      'status': 'CLOSED',
    }),
    OwnerDutyReport.fromJson({
      'driver_name': 'Test Operator',
      'asset_code': 'EXC-01',
      'asset_type': 'EXCAVATOR',
      'tipper_registration_number': 'EXC-01',
      'site_name': 'Test Site B',
      'duty_start': '2026-09-25T05:00:00Z',
      'start_hmr': 1000,
      'regular_duty_minutes': 600,
      'regular_duty_ends_at': '2026-09-25T15:00:00Z',
      'actual_duty_end': '2026-09-25T06:30:00Z',
      'end_hmr': 1001.5,
      'machine_hours': 1.5,
      'verified_diesel_issued': 0,
      'pending_diesel_issued': 10,
      'actual_duty_span_seconds': 5400,
      'overtime_minutes': 0,
      'status': 'CLOSED',
    }),
  ];
}

class _ScaleRoleApi extends _FakeRoleApi {
  _ScaleRoleApi({required this.assetCount});

  final int assetCount;

  @override
  Future<List<SiteDeployedAsset>> supervisorSiteAssets(String siteId) async =>
      List.generate(
        assetCount,
        (index) => _siteAsset(
          id: 'scale-$index',
          siteId: siteId,
          siteName: 'Scale Site',
          shortName: 'Asset ${index + 1}',
          assetCode: 'ASSET-${index + 1}',
          registration: 'REG-${index + 1}',
          driverName: index.isEven ? 'Driver ${index + 1}' : null,
        ),
      );

  @override
  Future<List<SupervisorEvent>> supervisorEvents(
    String siteId, {
    String? verificationStatus,
    DateTime? reviewDate,
  }) async => const [];
}

class _MultiSiteRoleApi extends _FakeRoleApi {
  static const _north = SupervisorSite(id: 'north', name: 'North Site');
  static const _south = SupervisorSite(id: 'south', name: 'South Site');

  @override
  Future<List<SupervisorSite>> supervisorSites() async => [_north, _south];

  @override
  Future<List<SiteDeployedAsset>> supervisorSiteAssets(String siteId) async => [
    _siteAsset(
      id: '$siteId-asset',
      siteId: siteId,
      siteName: siteId == 'north' ? _north.name : _south.name,
      shortName: siteId == 'north'
          ? 'A deliberately very long asset name that must not overflow'
          : 'South Tipper',
      assetCode: siteId == 'north' ? 'NORTH-01' : 'SOUTH-01',
      registration: siteId == 'north' ? null : 'SOUTH-REG-01',
      driverName: 'A driver with a deliberately long display name',
    ),
  ];

  @override
  Future<List<SupervisorEvent>> supervisorEvents(
    String siteId, {
    String? verificationStatus,
    DateTime? reviewDate,
  }) async {
    if (siteId != 'south') return const [];
    return [
      SupervisorEvent.fromJson({
        'event_id': 'south-emergency',
        'event_type': 'EMERGENCY',
        'assignment_id': 'south-assignment',
        'driver_name': 'South Driver',
        'tipper_registration_number': 'SOUTH-REG-01',
        'site_id': 'south',
        'site_name': 'South Site',
        'device_created_at': '2026-09-30T09:00:00Z',
        'verification_status': 'PENDING_VERIFICATION',
        'emergency_status': 'OPEN',
        'emergency_description': 'South emergency',
        'evidence_available': false,
      }),
    ];
  }
}

class _MachineryRoleApi extends _FakeRoleApi {
  @override
  Future<List<SiteDeployedAsset>> supervisorSiteAssets(String siteId) async => [
    _siteAsset(
      id: 'exc-01',
      siteId: siteId,
      siteName: 'Pilot Site',
      shortName: 'CAT 320',
      assetCode: 'EXC-01',
      registration: null,
      driverName: 'Test Driver Two',
      assetType: 'EXCAVATOR',
    ),
  ];

  @override
  Future<List<SupervisorEvent>> supervisorEvents(
    String siteId, {
    String? verificationStatus,
    DateTime? reviewDate,
  }) async => [
    for (final reading in const [
      ('start-hmr', 'START_READING', 3240.5, '2026-09-30T08:01:00Z'),
      ('end-hmr', 'END_READING', 3248.0, '2026-09-30T17:30:00Z'),
    ])
      SupervisorEvent.fromJson({
        'event_id': reading.$1,
        'event_type': 'HMR_READING',
        'assignment_id': 'exc-assignment',
        'driver_name': 'Test Driver Two',
        'asset_code': 'EXC-01',
        'asset_type': 'EXCAVATOR',
        'tipper_registration_number': 'EXC-01',
        'site_id': siteId,
        'site_name': 'Pilot Site',
        'device_created_at': reading.$4,
        'verification_status': 'PENDING_VERIFICATION',
        'reading_type': reading.$2,
        'reading_value': reading.$3,
        'evidence_available': true,
      }),
    for (final diesel in const [('diesel-10', 10.0), ('diesel-15', 15.0)])
      SupervisorEvent.fromJson({
        'event_id': diesel.$1,
        'event_type': 'DIESEL',
        'assignment_id': 'exc-assignment',
        'driver_name': 'Test Driver Two',
        'asset_code': 'EXC-01',
        'asset_type': 'EXCAVATOR',
        'tipper_registration_number': 'EXC-01',
        'site_id': siteId,
        'site_name': 'Pilot Site',
        'device_created_at': '2026-09-30T12:00:00Z',
        'verification_status': 'APPROVED',
        'litres': diesel.$2,
        'evidence_available': false,
      }),
  ];
}

SiteDeployedAsset _siteAsset({
  required String id,
  required String siteId,
  required String siteName,
  required String shortName,
  required String assetCode,
  required String? registration,
  required String? driverName,
  String assetType = 'TIPPER',
}) => SiteDeployedAsset.fromJson({
  'asset_id': id,
  'asset_code': assetCode,
  'asset_type': assetType,
  'ownership_type': 'OWNED',
  'registration_number': registration,
  'short_name': shortName,
  'status': 'ACTIVE',
  'current_deployment': {
    'id': 'deployment-$id',
    'asset_id': id,
    'site_id': siteId,
    'site_name': siteName,
    'starts_at': '2026-09-25T05:00:00Z',
    'ends_at': null,
  },
  'driver_membership_id': driverName == null ? null : 'driver-$id',
  'driver_name': driverName,
  'duty_status': driverName == null ? null : 'ACTIVE',
  'pending_review_count': 0,
});
