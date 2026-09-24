import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:fleet_manager_mobile/data/api_client.dart';
import 'package:fleet_manager_mobile/domain/role_models.dart';
import 'package:fleet_manager_mobile/role_screens.dart';

void main() {
  testWidgets(
    'supervisor home puts emergencies first and groups site tippers',
    (tester) async {
      final api = _FakeRoleApi();
      await tester.pumpWidget(
        MaterialApp(
          home: SupervisorHomeScreen(api: api, onSignOut: () async {}),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('EMERGENCIES'), findsOneWidget);
      expect(find.text('SITES / TIPPERS'), findsOneWidget);
      expect(find.text('PILOT-12'), findsOneWidget);
      expect(find.text('OPEN EMERGENCIES'), findsOneWidget);
      expect(find.text('ACKNOWLEDGE'), findsOneWidget);
    },
  );

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
    expect(find.text('TIPPERS'), findsOneWidget);
    expect(find.text('REPORTS'), findsOneWidget);
    await tester.tap(find.text('REPORTS'));
    await tester.pump();
    expect(find.text('DRIVER DUTY / OVERTIME'), findsOneWidget);
    expect(find.text('25 min'), findsOneWidget);
  });
}

class _FakeRoleApi extends ApiClient {
  _FakeRoleApi() : super(baseUrl: 'http://test');

  final _site = const SupervisorSite(id: 'site-1', name: 'Pilot Site');

  @override
  Future<List<SupervisorSite>> supervisorSites() async => [_site];

  @override
  Future<List<SupervisorEvent>> supervisorEvents(
    String siteId, {
    String? verificationStatus,
    DateTime? reviewDate,
  }) async => [
    SupervisorEvent.fromJson({
      'event_id': 'event-1',
      'event_type': 'EMERGENCY',
      'assignment_id': 'assignment-1',
      'driver_name': 'Pilot Driver',
      'driver_phone': '9606743463',
      'tipper_registration_number': 'PILOT-12',
      'site_id': siteId,
      'site_name': 'Pilot Site',
      'device_created_at': '2026-09-25T08:00:00Z',
      'verification_status': 'PENDING_VERIFICATION',
      'emergency_category': 'BREAKDOWN',
      'emergency_status': 'OPEN',
      'evidence_available': false,
      'verification_history': [],
    }),
    SupervisorEvent.fromJson({
      'event_id': 'event-2',
      'event_type': 'TRIP_COMPLETE',
      'assignment_id': 'assignment-1',
      'driver_name': 'Pilot Driver',
      'tipper_registration_number': 'PILOT-12',
      'site_id': siteId,
      'site_name': 'Pilot Site',
      'device_created_at': '2026-09-25T07:00:00Z',
      'verification_status': 'PENDING_VERIFICATION',
      'evidence_available': false,
      'verification_history': [],
    }),
  ];

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
      'tipper_registration_number': 'PILOT-12',
      'site_name': 'Pilot Site',
      'duty_start': '2026-09-25T05:00:00Z',
      'start_km': 10000,
      'regular_duty_minutes': 600,
      'regular_duty_ends_at': '2026-09-25T15:00:00Z',
      'actual_duty_end': '2026-09-25T15:25:00Z',
      'end_km': 10120,
      'actual_duty_span_seconds': 37500,
      'overtime_minutes': 25,
      'status': 'CLOSED',
    }),
  ];
}
