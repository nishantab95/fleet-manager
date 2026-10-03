import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:fleet_manager_mobile/data/api_client.dart';
import 'package:fleet_manager_mobile/domain/role_models.dart';
import 'package:fleet_manager_mobile/role_screens.dart';

void main() {
  testWidgets('supervisor home is a compact four-category attention inbox', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final api = _FakeRoleApi();
    await tester.pumpWidget(
      MaterialApp(
        home: SupervisorHomeScreen(api: api, onSignOut: () async {}),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Nagaraj'), findsOneWidget);
    expect(find.text('ABL Railway'), findsOneWidget);
    expect(find.text('EMERGENCIES'), findsOneWidget);
    expect(find.text('DIESEL APPROVALS'), findsOneWidget);
    expect(find.text('TRIP APPROVALS'), findsOneWidget);
    expect(find.text('METER READINGS'), findsOneWidget);
    expect(find.byKey(const Key('supervisor-attention-grid')), findsOneWidget);
    expect(
      find.byKey(const Key('supervisor-pending-notifications')),
      findsOneWidget,
    );
    expect(find.text('Pending notifications'), findsOneWidget);
    expect(
      tester
          .widget<Text>(find.byKey(const Key('supervisor-pending-total')))
          .data,
      '2',
    );
    expect(find.byKey(const Key('supervisor-site-selector')), findsNothing);
    for (final removed in const [
      'Review queue',
      'ON DUTY',
      'UNASSIGNED',
      'PENDING REVIEW',
      'Search assets or drivers',
      'NEED REVIEW',
      'Site fleet',
      'Recent activity',
    ]) {
      expect(find.text(removed), findsNothing);
    }
    await tester.tap(
      find.byKey(const Key('supervisor-notification-emergency')),
    );
    await tester.pumpAndSettle();
    expect(find.text('Emergencies'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'approved START disappears from review count while emergency stays separate',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(390, 844));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final api = _FakeRoleApi();
      await tester.pumpWidget(
        MaterialApp(
          home: SupervisorHomeScreen(api: api, onSignOut: () async {}),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        tester
            .widget<Text>(find.byKey(const Key('supervisor-count-meter')))
            .data,
        '1',
      );
      await tester.tap(find.byKey(const Key('supervisor-tile-meter')));
      await tester.pumpAndSettle();
      expect(find.text('Meter readings'), findsOneWidget);
      expect(find.text('START ODOMETER · 10000 KM'), findsOneWidget);
      expect(find.text('APPROVE'), findsOneWidget);
      await tester.tap(find.text('APPROVE'));
      await tester.pumpAndSettle();

      expect(api.approvedEventId, _FakeRoleApi.startEventId);
      expect(find.text('Nothing pending.'), findsOneWidget);
      expect(find.text('PENDING 0'), findsOneWidget);
      await tester.tap(find.text('HISTORY'));
      await tester.pumpAndSettle();
      expect(find.text('START ODOMETER · 10000 KM'), findsOneWidget);
      expect(find.text('APPROVED'), findsOneWidget);
      await tester.pageBack();
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<Text>(find.byKey(const Key('supervisor-count-meter')))
            .data,
        '0',
      );
      expect(
        tester
            .widget<Text>(find.byKey(const Key('supervisor-count-emergency')))
            .data,
        '1',
      );
      expect(
        tester
            .widget<Text>(find.byKey(const Key('supervisor-pending-total')))
            .data,
        '1',
      );
    },
  );

  testWidgets('resolved emergency moves from Pending to Emergency History', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final api = _FakeRoleApi();
    await tester.pumpWidget(
      MaterialApp(
        home: SupervisorHomeScreen(api: api, onSignOut: () async {}),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('supervisor-tile-emergency')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ACKNOWLEDGE'));
    await tester.pumpAndSettle();
    expect(find.text('RESOLVE'), findsOneWidget);
    await tester.tap(find.text('RESOLVE'));
    await tester.pumpAndSettle();
    expect(find.text('PENDING 0'), findsOneWidget);
    expect(find.text('No open emergencies.'), findsOneWidget);
    await tester.tap(find.text('HISTORY'));
    await tester.pumpAndSettle();
    expect(find.text('BREAKDOWN · RESOLVED'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(
      tester
          .widget<Text>(find.byKey(const Key('supervisor-count-emergency')))
          .data,
      '0',
    );
  });

  testWidgets('Emergency opens a separate category page', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      MaterialApp(
        home: SupervisorHomeScreen(
          api: _AttentionRoleApi(),
          onSignOut: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('supervisor-tile-emergency')));
    await tester.pumpAndSettle();
    expect(find.text('Emergencies'), findsOneWidget);
    expect(find.text('Attention fixture emergency'), findsOneWidget);
    expect(find.text('21 LITRES'), findsNothing);
    expect(find.text('Trip Complete'), findsNothing);
    expect(find.text('START ODOMETER · 777 KM'), findsNothing);
  });

  testWidgets('zero-count category keeps Pending and History available', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      MaterialApp(
        home: SupervisorHomeScreen(
          api: _ScaleRoleApi(assetCount: 1),
          onSignOut: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('supervisor-tile-diesel')));
    await tester.pumpAndSettle();
    expect(find.text('PENDING 0'), findsOneWidget);
    expect(find.text('Nothing pending.'), findsOneWidget);
    await tester.tap(find.text('HISTORY'));
    await tester.pumpAndSettle();
    expect(find.text('No diesel history.'), findsOneWidget);
  });

  testWidgets('Diesel opens a separate category page', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      MaterialApp(
        home: SupervisorHomeScreen(
          api: _AttentionRoleApi(),
          onSignOut: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      tester
          .widget<Text>(find.byKey(const Key('supervisor-count-emergency')))
          .data,
      '1',
    );
    expect(
      tester
          .widget<Text>(find.byKey(const Key('supervisor-count-diesel')))
          .data,
      '2',
    );
    expect(
      tester.widget<Text>(find.byKey(const Key('supervisor-count-trips'))).data,
      '1',
    );
    expect(
      tester.widget<Text>(find.byKey(const Key('supervisor-count-meter'))).data,
      '1',
    );
    expect(
      tester
          .widget<Text>(find.byKey(const Key('supervisor-pending-total')))
          .data,
      '5',
    );

    await tester.tap(find.byKey(const Key('supervisor-tile-diesel')));
    await tester.pumpAndSettle();
    expect(find.text('Diesel'), findsOneWidget);
    expect(find.text('21 LITRES'), findsOneWidget);
    expect(find.text('42 LITRES'), findsOneWidget);
    expect(find.text('Attention fixture emergency'), findsNothing);
    expect(find.text('Trip Complete'), findsNothing);
    expect(find.text('START ODOMETER · 777 KM'), findsNothing);
  });

  testWidgets('Trips opens a separate category page', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      MaterialApp(
        home: SupervisorHomeScreen(
          api: _AttentionRoleApi(),
          onSignOut: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('supervisor-tile-trips')));
    await tester.pumpAndSettle();
    expect(find.text('Trips'), findsOneWidget);
    expect(find.text('Trip Complete'), findsOneWidget);
    expect(find.text('Attention fixture emergency'), findsNothing);
    expect(find.text('21 LITRES'), findsNothing);
    expect(find.text('START ODOMETER · 777 KM'), findsNothing);
  });

  testWidgets('Meter opens a separate page with capability-correct readings', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(390, 2000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      MaterialApp(
        home: SupervisorHomeScreen(
          api: _CapabilityRoleApi(),
          onSignOut: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('supervisor-tile-meter')));
    await tester.pumpAndSettle();
    expect(find.text('Meter readings'), findsOneWidget);
    expect(find.text('START ODOMETER · 10000 KM'), findsOneWidget);
    expect(find.text('END ODOMETER · 10120 KM'), findsOneWidget);
    expect(find.text('START HMR · 3240.50 hours'), findsOneWidget);
    expect(find.text('END HMR · 3248 hours'), findsOneWidget);
    expect(find.textContaining('Trip Complete'), findsNothing);
    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('supervisor-tile-trips')));
    await tester.pumpAndSettle();
    expect(find.text('Tipper trip'), findsOneWidget);
    expect(find.text('Machinery trip must stay hidden'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('each category exposes isolated history', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 1100));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      MaterialApp(
        home: SupervisorHomeScreen(
          api: _HistoryRoleApi(),
          onSignOut: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    for (final scenario in const [
      (
        'supervisor-tile-emergency',
        'Resolved emergency',
        <String>['Approved diesel', 'Approved trip', 'Approved meter'],
      ),
      (
        'supervisor-tile-diesel',
        'Approved diesel',
        <String>['Resolved emergency', 'Approved trip', 'Approved meter'],
      ),
      (
        'supervisor-tile-trips',
        'Approved trip',
        <String>['Resolved emergency', 'Approved diesel', 'Approved meter'],
      ),
      (
        'supervisor-tile-meter',
        'Approved meter',
        <String>['Resolved emergency', 'Approved diesel', 'Approved trip'],
      ),
    ]) {
      await tester.tap(find.byKey(Key(scenario.$1)));
      await tester.pumpAndSettle();
      await tester.tap(find.text('HISTORY'));
      await tester.pumpAndSettle();
      expect(find.text(scenario.$2), findsOneWidget);
      for (final excluded in scenario.$3) {
        expect(find.text(excluded), findsNothing);
      }
      await tester.pageBack();
      await tester.pumpAndSettle();
    }
  });

  testWidgets('multi-site selector scopes Home counts and category content', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(390, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final api = _MultiSiteRoleApi();
    await tester.pumpWidget(
      MaterialApp(
        home: SupervisorHomeScreen(api: api, onSignOut: () async {}),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('supervisor-site-selector')), findsOneWidget);
    expect(find.text('NORTH'), findsWidgets);
    expect(find.text('NORTH'), findsWidgets);
    expect(
      tester
          .widget<Text>(find.byKey(const Key('supervisor-count-emergency')))
          .data,
      '0',
    );
    expect(find.text('South emergency'), findsNothing);
    await tester.tap(find.byKey(const Key('supervisor-site-selector')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('SOUTH').last);
    await tester.pumpAndSettle();
    expect(
      tester
          .widget<Text>(find.byKey(const Key('supervisor-count-emergency')))
          .data,
      '1',
    );
    await tester.tap(find.byKey(const Key('supervisor-tile-emergency')));
    await tester.pumpAndSettle();
    expect(find.text('SOUTH'), findsOneWidget);
    expect(find.text('South emergency'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  for (final width in [360.0, 390.0, 412.0]) {
    testWidgets('supervisor action grid is stable at ${width.toInt()} px', (
      tester,
    ) async {
      await tester.binding.setSurfaceSize(Size(width, 900));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(
        MaterialApp(
          home: SupervisorHomeScreen(
            api: _ScaleRoleApi(assetCount: 1),
            onSignOut: () async {},
          ),
        ),
      );
      await tester.pumpAndSettle();

      for (final key in const [
        'supervisor-tile-emergency',
        'supervisor-tile-diesel',
        'supervisor-tile-trips',
        'supervisor-tile-meter',
      ]) {
        final tile = find.byKey(Key(key));
        expect(tile, findsOneWidget);
        expect(tester.getSize(tile).width, greaterThan(150));
        expect(tester.getSize(tile).height, greaterThan(90));
      }
      for (final key in const [
        'supervisor-count-emergency',
        'supervisor-count-diesel',
        'supervisor-count-trips',
        'supervisor-count-meter',
      ]) {
        expect(tester.widget<Text>(find.byKey(Key(key))).data, '0');
      }
      expect(find.text('Nothing requires your attention.'), findsOneWidget);
      expect(
        tester
            .getBottomRight(
              find.byKey(const Key('supervisor-pending-notifications')),
            )
            .dy,
        lessThanOrEqualTo(900),
      );
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('attention tiles open the matching oldest-first review queue', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(390, 1400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      MaterialApp(
        home: SupervisorHomeScreen(
          api: _AttentionRoleApi(),
          onSignOut: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('supervisor-tile-diesel')));
    await tester.pumpAndSettle();
    expect(find.text('21 LITRES'), findsOneWidget);
    expect(find.text('42 LITRES'), findsOneWidget);
    expect(
      tester
          .widgetList<Text>(find.textContaining('LITRES'))
          .map((widget) => widget.data)
          .toList(),
      ['21 LITRES', '42 LITRES'],
    );
    expect(find.text('Trip Complete'), findsNothing);

    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('supervisor-tile-trips')));
    await tester.pumpAndSettle();
    expect(find.text('Trip Complete'), findsOneWidget);
    expect(find.text('42 LITRES'), findsNothing);

    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('supervisor-tile-meter')));
    await tester.pumpAndSettle();
    expect(find.text('START ODOMETER · 777 KM'), findsOneWidget);
    expect(find.text('Trip Complete'), findsNothing);

    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('supervisor-tile-emergency')));
    await tester.pumpAndSettle();
    expect(find.text('Attention fixture emergency'), findsOneWidget);
    expect(find.text('START ODOMETER · 777 KM'), findsNothing);
  });

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
    await tester.binding.setSurfaceSize(const Size(1080, 3200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
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

  testWidgets('owner reports creates and selects a custom report template', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1080, 2400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final api = _FakeRoleApi();
    await tester.pumpWidget(
      MaterialApp(
        home: OwnerHomeScreen(api: api, onSignOut: () async {}),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('REPORTS'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('report-template-selector')), findsOneWidget);
    expect(find.text('Management Summary'), findsWidgets);
    expect(find.text('Detailed Operations'), findsOneWidget);
    expect(find.text('Diesel Report'), findsOneWidget);
    expect(find.byKey(const Key('export-template-excel')), findsOneWidget);

    await tester.tap(find.byKey(const Key('new-report-template')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('report-template-editor-name')),
      'Custom Minimal',
    );
    await tester.tap(find.text('MANAGEMENT DASHBOARD COLUMNS'));
    await tester.pumpAndSettle();
    final assetTile = tester.widget<CheckboxListTile>(
      find.byWidgetPredicate(
        (widget) =>
            widget is CheckboxListTile &&
            widget.title is Text &&
            (widget.title as Text).data == 'Asset',
      ),
    );
    expect(assetTile.value, isTrue);
    expect(assetTile.onChanged, isNull);
    await tester.tap(find.text('MANAGEMENT DASHBOARD COLUMNS'));
    await tester.pumpAndSettle();
    for (final sheet in const [
      'Management Dashboard',
      'Tipper Daily',
      'Machinery Daily',
      'Exceptions',
    ]) {
      await tester.tap(find.text(sheet).last);
    }
    await tester.tap(find.byKey(const Key('save-report-template')));
    await tester.pump();
    expect(find.text('Select at least one sheet.'), findsOneWidget);
    await tester.tap(find.text('Management Dashboard').last);
    await tester.tap(find.byKey(const Key('save-report-template')));
    await tester.pumpAndSettle();

    expect(api.createdTemplate?.name, 'Custom Minimal');
    expect(api.createdTemplate?.includedSheets, ['management_dashboard']);
    expect(api.createdTemplate?.managementDashboardColumns.first, 'asset');
    expect(find.text('Custom Minimal'), findsWidgets);

    final builtinCard = find.byKey(
      const Key('report-template-management-summary'),
    );
    await tester.tap(
      find.descendant(
        of: builtinCard,
        matching: find.byType(PopupMenuButton<String>),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Duplicate'), findsOneWidget);
    expect(find.text('Edit'), findsNothing);
    expect(find.text('Delete'), findsNothing);
    await tester.tapAt(const Offset(20, 20));
    await tester.pumpAndSettle();

    final customCard = find.byKey(const Key('report-template-custom-minimal'));
    await tester.tap(
      find.descendant(
        of: customCard,
        matching: find.byType(PopupMenuButton<String>),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Set as default'));
    await tester.pumpAndSettle();
    expect(api.defaultTemplateId, 'custom-minimal');

    await tester.tap(
      find.descendant(
        of: customCard,
        matching: find.byType(PopupMenuButton<String>),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Edit'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('report-template-editor-name')),
      'Custom Edited',
    );
    await tester.tap(find.byKey(const Key('save-report-template')));
    await tester.pumpAndSettle();
    expect(api.updatedTemplateName, 'Custom Edited');

    await tester.tap(
      find.descendant(
        of: customCard,
        matching: find.byType(PopupMenuButton<String>),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Duplicate'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('report-template-name')),
      'Custom Copy',
    );
    await tester.tap(find.text('SAVE'));
    await tester.pumpAndSettle();
    expect(api.duplicatedTemplateName, 'Custom Copy');

    await tester.tap(
      find.descendant(
        of: customCard,
        matching: find.byType(PopupMenuButton<String>),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('DELETE'));
    await tester.pumpAndSettle();
    expect(api.deletedTemplateId, 'custom-minimal');

    await tester.tap(find.byKey(const Key('new-report-template')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('report-template-editor-name')),
      'management summary',
    );
    await tester.tap(find.byKey(const Key('save-report-template')));
    await tester.pumpAndSettle();
    expect(
      find.text('A report template with this name already exists.'),
      findsOneWidget,
    );
  });
}

class _FakeRoleApi extends ApiClient {
  _FakeRoleApi() : super(baseUrl: 'http://test');

  @override
  Future<String> currentDisplayName() async => 'Nagaraj';

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

  final _site = const SupervisorSite(
    id: 'site-1',
    name: 'Pilot Site',
    shortName: 'ABL Railway',
  );
  String? approvedEventId;
  String? assignedAssetId;
  String? assignedDriverId;
  String? assignmentSiteId;
  ReportTemplateInput? createdTemplate;
  String? defaultTemplateId;
  String? updatedTemplateName;
  String? duplicatedTemplateName;
  String? deletedTemplateId;
  late final List<SupervisorEvent> _supervisorEventStore = [
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
  final List<ReportTemplate> _reportTemplates = [
    ReportTemplate(
      id: 'management-summary',
      name: 'Management Summary',
      isBuiltin: true,
      isDefault: true,
      includedSheets: const [
        'management_dashboard',
        'tipper_daily',
        'machinery_daily',
        'exceptions',
      ],
      managementDashboardColumns: managementReportColumnLabels.keys.toList(),
      tipperDailyColumns: tipperReportColumnLabels.keys.toList(),
      machineryDailyColumns: machineryReportColumnLabels.keys.toList(),
    ),
    ReportTemplate(
      id: 'detailed-operations',
      name: 'Detailed Operations',
      isBuiltin: true,
      isDefault: false,
      includedSheets: reportSheetLabels.keys.toList(),
      managementDashboardColumns: managementReportColumnLabels.keys.toList(),
      tipperDailyColumns: tipperReportColumnLabels.keys.toList(),
      machineryDailyColumns: machineryReportColumnLabels.keys.toList(),
    ),
    ReportTemplate(
      id: 'diesel-report',
      name: 'Diesel Report',
      isBuiltin: true,
      isDefault: false,
      includedSheets: const [
        'management_dashboard',
        'diesel_register',
        'exceptions',
      ],
      managementDashboardColumns: const [
        'asset',
        'asset_type',
        'site',
        'operator',
        'verified_diesel_l',
        'pending_status',
      ],
      tipperDailyColumns: tipperReportColumnLabels.keys.toList(),
      machineryDailyColumns: machineryReportColumnLabels.keys.toList(),
    ),
  ];

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
  }) async => _supervisorEventStore
      .where(
        (event) =>
            event.siteId == siteId &&
            (verificationStatus == null ||
                event.verificationStatus == verificationStatus),
      )
      .toList();

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
    final index = _supervisorEventStore.indexWhere(
      (event) => event.id == eventId,
    );
    final updated = _copySupervisorEvent(
      _supervisorEventStore[index],
      verificationStatus: decision,
    );
    _supervisorEventStore[index] = updated;
    return updated;
  }

  @override
  Future<SupervisorEvent> acknowledgeEmergency(String eventId) async =>
      _updateEmergency(eventId, 'ACKNOWLEDGED');

  @override
  Future<SupervisorEvent> resolveEmergency(String eventId) async =>
      _updateEmergency(eventId, 'RESOLVED');

  SupervisorEvent _updateEmergency(String eventId, String status) {
    final index = _supervisorEventStore.indexWhere(
      (event) => event.id == eventId,
    );
    final updated = _copySupervisorEvent(
      _supervisorEventStore[index],
      emergencyStatus: status,
    );
    _supervisorEventStore[index] = updated;
    return updated;
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

  @override
  Future<List<ReportTemplate>> reportTemplates() async =>
      List.unmodifiable(_reportTemplates);

  @override
  Future<ReportTemplate> createReportTemplate(ReportTemplateInput input) async {
    if (_reportTemplates.any(
      (item) => item.name.toLowerCase() == input.name.toLowerCase(),
    )) {
      throw const ApiException(
        409,
        'A report template with this name already exists.',
      );
    }
    createdTemplate = input;
    final template = ReportTemplate(
      id: 'custom-minimal',
      name: input.name,
      isBuiltin: false,
      isDefault: false,
      includedSheets: input.includedSheets,
      managementDashboardColumns: input.managementDashboardColumns,
      tipperDailyColumns: input.tipperDailyColumns,
      machineryDailyColumns: input.machineryDailyColumns,
    );
    _reportTemplates.add(template);
    return template;
  }

  @override
  Future<ReportTemplate> updateReportTemplate(
    String templateId,
    ReportTemplateInput input,
  ) async {
    updatedTemplateName = input.name;
    final index = _reportTemplates.indexWhere((item) => item.id == templateId);
    final current = _reportTemplates[index];
    final updated = ReportTemplate(
      id: current.id,
      name: input.name,
      isBuiltin: current.isBuiltin,
      isDefault: current.isDefault,
      includedSheets: input.includedSheets,
      managementDashboardColumns: input.managementDashboardColumns,
      tipperDailyColumns: input.tipperDailyColumns,
      machineryDailyColumns: input.machineryDailyColumns,
    );
    _reportTemplates[index] = updated;
    return updated;
  }

  @override
  Future<ReportTemplate> duplicateReportTemplate(
    String templateId,
    String name,
  ) async {
    duplicatedTemplateName = name;
    final source = _reportTemplates.firstWhere((item) => item.id == templateId);
    final duplicate = ReportTemplate(
      id: 'custom-copy',
      name: name,
      isBuiltin: false,
      isDefault: false,
      includedSheets: source.includedSheets,
      managementDashboardColumns: source.managementDashboardColumns,
      tipperDailyColumns: source.tipperDailyColumns,
      machineryDailyColumns: source.machineryDailyColumns,
    );
    _reportTemplates.add(duplicate);
    return duplicate;
  }

  @override
  Future<void> deleteReportTemplate(String templateId) async {
    deletedTemplateId = templateId;
    final wasDefault = _reportTemplates
        .firstWhere((item) => item.id == templateId)
        .isDefault;
    _reportTemplates.removeWhere((item) => item.id == templateId);
    if (wasDefault) await setDefaultReportTemplate('management-summary');
  }

  @override
  Future<ReportTemplate> setDefaultReportTemplate(String templateId) async {
    defaultTemplateId = templateId;
    final updated = [
      for (final item in _reportTemplates)
        ReportTemplate(
          id: item.id,
          name: item.name,
          isBuiltin: item.isBuiltin,
          isDefault: item.id == templateId,
          includedSheets: item.includedSheets,
          managementDashboardColumns: item.managementDashboardColumns,
          tipperDailyColumns: item.tipperDailyColumns,
          machineryDailyColumns: item.machineryDailyColumns,
        ),
    ];
    _reportTemplates
      ..clear()
      ..addAll(updated);
    return _reportTemplates.firstWhere((item) => item.id == templateId);
  }
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
  static const _north = SupervisorSite(
    id: 'north',
    name: 'North Site',
    shortName: 'NORTH',
  );
  static const _south = SupervisorSite(
    id: 'south',
    name: 'South Site',
    shortName: 'SOUTH',
  );

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

class _AttentionRoleApi extends _FakeRoleApi {
  @override
  Future<List<SupervisorEvent>> supervisorEvents(
    String siteId, {
    String? verificationStatus,
    DateTime? reviewDate,
  }) async => [
    _attentionEvent(
      id: 'diesel-oldest',
      type: 'DIESEL',
      createdAt: '2026-09-30T05:00:00Z',
      litres: 21,
    ),
    _attentionEvent(
      id: 'diesel-newer',
      type: 'DIESEL',
      createdAt: '2026-09-30T06:00:00Z',
      litres: 42,
    ),
    _attentionEvent(
      id: 'trip',
      type: 'TRIP_COMPLETE',
      createdAt: '2026-09-30T07:00:00Z',
    ),
    _attentionEvent(
      id: 'meter',
      type: 'KM_READING',
      createdAt: '2026-09-30T08:00:00Z',
      readingType: 'START_READING',
      readingValue: 777,
    ),
    _attentionEvent(
      id: 'emergency',
      type: 'EMERGENCY',
      createdAt: '2026-09-30T09:00:00Z',
      emergencyDescription: 'Attention fixture emergency',
    ),
  ];
}

SupervisorEvent _attentionEvent({
  required String id,
  required String type,
  required String createdAt,
  double? litres,
  String? readingType,
  double? readingValue,
  String? emergencyDescription,
}) => SupervisorEvent.fromJson({
  'event_id': id,
  'event_type': type,
  'assignment_id': 'attention-assignment',
  'driver_name': 'Attention Driver',
  'driver_phone': '9606743463',
  'asset_code': 'TIPPER-12',
  'asset_short_name': 'Attention Tipper',
  'tipper_registration_number': 'PILOT-12',
  'site_id': 'site-1',
  'site_name': 'Pilot Site',
  'device_created_at': createdAt,
  'verification_status': 'PENDING_VERIFICATION',
  'litres': litres,
  'reading_type': readingType,
  'reading_value': readingValue,
  'emergency_status': type == 'EMERGENCY' ? 'OPEN' : null,
  'emergency_description': emergencyDescription,
  'evidence_available': type == 'DIESEL',
});

SupervisorEvent _copySupervisorEvent(
  SupervisorEvent event, {
  String? verificationStatus,
  String? emergencyStatus,
}) => SupervisorEvent(
  id: event.id,
  eventType: event.eventType,
  assignmentId: event.assignmentId,
  driverName: event.driverName,
  tipperRegistration: event.tipperRegistration,
  siteId: event.siteId,
  siteName: event.siteName,
  deviceCreatedAt: event.deviceCreatedAt,
  verificationStatus: verificationStatus ?? event.verificationStatus,
  evidenceAvailable: event.evidenceAvailable,
  assetCode: event.assetCode,
  assetType: event.assetType,
  dutySessionId: event.dutySessionId,
  driverPhone: event.driverPhone,
  readingType: event.readingType,
  readingValue: event.readingValue,
  litres: event.litres,
  emergencyCategory: event.emergencyCategory,
  emergencyStatus: emergencyStatus ?? event.emergencyStatus,
  emergencyDescription: event.emergencyDescription,
  history: event.history,
  assetShortName: event.assetShortName,
);

class _HistoryRoleApi extends _FakeRoleApi {
  @override
  Future<List<SupervisorEvent>> supervisorEvents(
    String siteId, {
    String? verificationStatus,
    DateTime? reviewDate,
  }) async => [
    for (final item in const [
      ('history-emergency', 'EMERGENCY', 'Resolved emergency'),
      ('history-diesel', 'DIESEL', 'Approved diesel'),
      ('history-trip', 'TRIP_COMPLETE', 'Approved trip'),
      ('history-meter', 'KM_READING', 'Approved meter'),
    ])
      SupervisorEvent.fromJson({
        'event_id': item.$1,
        'event_type': item.$2,
        'assignment_id': 'history-assignment',
        'driver_name': 'History Driver',
        'asset_code': 'TIPPER-HISTORY',
        'asset_short_name': item.$3,
        'asset_type': 'TIPPER',
        'tipper_registration_number': 'HISTORY-01',
        'site_id': siteId,
        'site_name': 'Pilot Site',
        'device_created_at': '2026-09-29T08:00:00Z',
        'verification_status': 'APPROVED',
        'emergency_status': item.$2 == 'EMERGENCY' ? 'RESOLVED' : null,
        'reading_type': item.$2 == 'KM_READING' ? 'END_READING' : null,
        'reading_value': item.$2 == 'KM_READING' ? 10120 : null,
        'litres': item.$2 == 'DIESEL' ? 25 : null,
        'evidence_available': false,
      }),
  ];
}

class _CapabilityRoleApi extends _FakeRoleApi {
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
      ('start-km', 'START_READING', 10000.0, '2026-09-30T07:30:00Z'),
      ('end-km', 'END_READING', 10120.0, '2026-09-30T17:00:00Z'),
    ])
      SupervisorEvent.fromJson({
        'event_id': reading.$1,
        'event_type': 'KM_READING',
        'assignment_id': 'tipper-assignment',
        'driver_name': 'Tipper Driver',
        'asset_code': 'TIPPER-01',
        'asset_short_name': 'Tipper meter',
        'asset_type': 'TIPPER',
        'tipper_registration_number': 'TIPPER-01',
        'site_id': siteId,
        'site_name': 'Pilot Site',
        'device_created_at': reading.$4,
        'verification_status': 'PENDING_VERIFICATION',
        'reading_type': reading.$2,
        'reading_value': reading.$3,
        'evidence_available': true,
      }),
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
    SupervisorEvent.fromJson({
      'event_id': 'tipper-trip',
      'event_type': 'TRIP_COMPLETE',
      'assignment_id': 'tipper-assignment',
      'driver_name': 'Tipper Driver',
      'asset_code': 'TIPPER-01',
      'asset_short_name': 'Tipper trip',
      'asset_type': 'TIPPER',
      'tipper_registration_number': 'TIPPER-01',
      'site_id': siteId,
      'site_name': 'Pilot Site',
      'device_created_at': '2026-09-30T12:30:00Z',
      'verification_status': 'PENDING_VERIFICATION',
      'evidence_available': false,
    }),
    SupervisorEvent.fromJson({
      'event_id': 'machinery-trip-invalid',
      'event_type': 'TRIP_COMPLETE',
      'assignment_id': 'exc-assignment',
      'driver_name': 'Machinery Operator',
      'asset_code': 'EXC-01',
      'asset_short_name': 'Machinery trip must stay hidden',
      'asset_type': 'EXCAVATOR',
      'tipper_registration_number': 'EXC-01',
      'site_id': siteId,
      'site_name': 'Pilot Site',
      'device_created_at': '2026-09-30T12:31:00Z',
      'verification_status': 'PENDING_VERIFICATION',
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
