import 'package:fleet_manager_mobile/data/api_client.dart';
import 'package:fleet_manager_mobile/domain/role_models.dart';
import 'package:fleet_manager_mobile/owner_fleet.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('assigns an eligible driver to a deployed asset', (tester) async {
    final api = _AssignmentOwnerApi([_asset(4, deployed: true)]);
    await _pumpFleet(tester, api);

    await tester.tap(find.byKey(const Key('assign-driver-4')));
    await tester.pumpAndSettle();
    expect(find.text('ASSIGN DRIVER / OPERATOR · KA01AB0004'), findsOneWidget);
    expect(find.byKey(const Key('assignment-site')), findsOneWidget);
    expect(find.text('Pilot Site'), findsWidgets);
    await tester.tap(find.byKey(const Key('confirm-driver-assignment')));
    await tester.pumpAndSettle();

    expect(api.assignedDriverIds, ['driver-available']);
  });

  testWidgets('changes and unassigns a Driver from an assigned asset', (
    tester,
  ) async {
    final api = _AssignmentOwnerApi([_asset(1)]);
    await _pumpFleet(tester, api);

    await tester.tap(find.byKey(const Key('assign-driver-1')));
    await tester.pumpAndSettle();
    expect(find.text('CHANGE DRIVER / OPERATOR · KA01AB0001'), findsOneWidget);
    await tester.tap(find.byKey(const Key('confirm-driver-assignment')));
    await tester.pumpAndSettle();
    expect(api.reassignFlags, [true]);

    await tester.tap(find.byKey(const Key('assign-driver-1')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('unassign-driver')));
    await tester.pumpAndSettle();
    expect(api.unassignedAssetIds, ['1']);
  });

  testWidgets('assignment picker handles 30 available Drivers', (tester) async {
    final api = _AssignmentOwnerApi([
      _asset(4, deployed: true),
    ], candidateCount: 30);
    await _pumpFleet(tester, api);

    await tester.tap(find.byKey(const Key('assign-driver-4')));
    await tester.pumpAndSettle();
    final dropdown = tester.widget<DropdownButton<String>>(
      find.byType(DropdownButton<String>),
    );
    expect(dropdown.items, hasLength(30));
    expect(tester.takeException(), isNull);
  });

  testWidgets('assigned detail shows Driver Site and assignment start', (
    tester,
  ) async {
    final api = _AssignmentOwnerApi([_asset(1)]);
    await tester.pumpWidget(
      MaterialApp(
        home: OwnerAssetDetailScreen(api: api, asset: api.assets.single),
      ),
    );
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.byKey(const Key('current-driver-assignment')),
      300,
      scrollable: find.byType(Scrollable).last,
    );
    expect(find.text('Current Driver assignment'), findsOneWidget);
    expect(find.text('Ramesh'), findsOneWidget);
    expect(find.text('Pilot Site'), findsWidgets);
    expect(find.text('2026-09-30'), findsOneWidget);
    expect(find.byKey(const Key('asset-driver-action')), findsOneWidget);
  });

  testWidgets('machinery exposes Operator assignment controls', (tester) async {
    final api = _AssignmentOwnerApi([
      _asset(4, deployed: true, assetType: 'EXCAVATOR'),
    ]);
    await _pumpFleet(tester, api);

    expect(find.byKey(const Key('assign-driver-4')), findsOneWidget);
  });

  testWidgets(
    'fleet list shows owned and rented cards with filters and search',
    (tester) async {
      final api = _FakeOwnerAssetApi([
        _asset(1),
        _asset(2, ownership: 'RENTED', rentalParty: 'ABC Transport'),
        _asset(3, status: 'INACTIVE'),
      ]);
      await _pumpFleet(tester, api);

      expect(find.text('Total Assets'), findsOneWidget);
      expect(find.text('KA01AB0001'), findsOneWidget);
      expect(find.text('ABC Transport'), findsOneWidget);

      await tester.tap(find.byKey(const Key('fleet-filter-rented')));
      await tester.pump();
      expect(find.byKey(const Key('owner-asset-2')), findsOneWidget);
      expect(find.byKey(const Key('owner-asset-1')), findsNothing);

      await tester.tap(find.byKey(const Key('fleet-filter-all')));
      await tester.enterText(find.byKey(const Key('fleet-search')), 'TIPPER-3');
      await tester.pump();
      expect(find.byKey(const Key('owner-asset-3')), findsOneWidget);
      expect(find.byKey(const Key('owner-asset-2')), findsNothing);
    },
  );

  testWidgets('add form reveals rental fields and creates rented tipper', (
    tester,
  ) async {
    final api = _FakeOwnerAssetApi([]);
    await _pumpFleet(tester, api);

    await tester.tap(find.byKey(const Key('add-tipper')));
    await tester.pumpAndSettle();
    expect(find.text('ADD ASSET'), findsWidgets);
    expect(find.byKey(const Key('rental-fields')), findsNothing);

    await tester.tap(find.text('RENTED'));
    await tester.pump();
    expect(find.byKey(const Key('rental-fields')), findsOneWidget);

    await tester.enterText(
      find.byKey(const Key('asset-code-field')),
      'TIPPER-22',
    );
    await tester.enterText(
      find.byKey(const Key('registration-field')),
      'KA05CD5678',
    );
    await tester.enterText(
      find.byKey(const Key('rental-party-field')),
      'ABC Transport',
    );
    await tester.drag(find.byType(ListView).last, const Offset(0, -700));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('save-tipper')));
    await tester.pumpAndSettle();

    expect(api.created, hasLength(1));
    expect(api.created.single.ownershipType, 'RENTED');
    expect(api.created.single.rentalPartyName, 'ABC Transport');
    expect(find.byKey(const Key('owner-asset-created')), findsOneWidget);
  });

  testWidgets('add form creates machinery without registration', (
    tester,
  ) async {
    final api = _FakeOwnerAssetApi([]);
    await _pumpFleet(tester, api);

    await tester.tap(find.byKey(const Key('add-tipper')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('asset-type-field')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('EXCAVATOR').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('asset-code-field')), 'EXC-01');
    await tester.enterText(
      find.byKey(const Key('short-name-field')),
      'CAT 320',
    );
    await tester.drag(find.byType(ListView).last, const Offset(0, -700));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('save-tipper')));
    await tester.pumpAndSettle();

    expect(api.created, hasLength(1));
    expect(api.created.single.assetType, 'EXCAVATOR');
    expect(api.created.single.registrationNumber, isNull);
    expect(api.created.single.shortName, 'CAT 320');
  });

  testWidgets('edit form saves the existing asset UUID', (tester) async {
    final existing = _asset(7);
    final api = _FakeOwnerAssetApi([existing]);
    await tester.pumpWidget(
      MaterialApp(
        home: OwnerAssetFormScreen(api: api, asset: existing),
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const Key('asset-code-field')),
      'TIPPER-UPDATED',
    );
    await tester.tap(find.byKey(const Key('save-tipper')));
    await tester.pumpAndSettle();

    expect(api.updatedAssetId, existing.id);
    expect(api.updatedInput?.assetCode, 'TIPPER-UPDATED');
  });

  testWidgets('detail deactivates and reactivates without delete controls', (
    tester,
  ) async {
    final api = _FakeOwnerAssetApi([_asset(8)]);
    await tester.pumpWidget(
      MaterialApp(
        home: OwnerAssetDetailScreen(api: api, asset: api.assets.single),
      ),
    );
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.byKey(const Key('asset-status-action')),
      400,
      scrollable: find.byType(Scrollable).last,
    );
    expect(find.text('DEACTIVATE'), findsOneWidget);
    expect(find.textContaining('DELETE'), findsNothing);
    await tester.tap(find.byKey(const Key('asset-status-action')));
    await tester.pumpAndSettle();
    expect(api.deactivated, 1);
    expect(find.text('REACTIVATE'), findsOneWidget);

    await tester.tap(find.byKey(const Key('asset-status-action')));
    await tester.pumpAndSettle();
    expect(api.reactivated, 1);
    expect(find.text('DEACTIVATE'), findsOneWidget);
  });

  testWidgets('fleet cards show deployment and assign an undeployed asset', (
    tester,
  ) async {
    final api = _FakeOwnerAssetApi([_asset(1), _asset(2, deployed: false)]);
    await _pumpFleet(tester, api);

    expect(find.text('Site: Pilot Site'), findsOneWidget);
    expect(find.text('Driver: Ramesh'), findsOneWidget);
    expect(find.text('Site: Not assigned'), findsOneWidget);
    expect(find.text('Driver: Unassigned'), findsOneWidget);

    await tester.drag(
      find.byKey(const Key('owner-fleet-scroll')),
      const Offset(0, -350),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('assign-site-2')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('deployment-site')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Pilot Site').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('confirm-deployment')));
    await tester.pumpAndSettle();

    expect(api.deployedAssetIds, ['2']);
    expect(find.text('Site: Pilot Site'), findsNWidgets(2));
  });

  testWidgets('asset detail moves and removes its Site deployment', (
    tester,
  ) async {
    final api = _FakeOwnerAssetApi([_asset(4, deployed: true)]);
    await tester.pumpWidget(
      MaterialApp(
        home: OwnerAssetDetailScreen(api: api, asset: api.assets.single),
      ),
    );
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.byKey(const Key('asset-deployment-action')),
      300,
      scrollable: find.byType(Scrollable).last,
    );
    await tester.tap(find.byKey(const Key('asset-deployment-action')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('deployment-site')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Second Site').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('confirm-deployment')));
    await tester.pumpAndSettle();
    expect(api.deployedSiteIds.last, 'site-2');

    await tester.scrollUntilVisible(
      find.byKey(const Key('remove-site-deployment')),
      300,
      scrollable: find.byType(Scrollable).last,
    );
    await tester.tap(find.byKey(const Key('remove-site-deployment')));
    await tester.pumpAndSettle();
    expect(api.removedAssetIds, ['4']);
    expect(find.text('Not assigned'), findsWidgets);
  });

  testWidgets('fleet and form show API errors', (tester) async {
    final api = _FakeOwnerAssetApi([])..listError = 'Fleet service unavailable';
    await _pumpFleet(tester, api);
    expect(find.byKey(const Key('fleet-api-error')), findsOneWidget);
    expect(find.text('Fleet service unavailable'), findsOneWidget);

    api.listError = null;
    api.saveError = 'Registration number is already used';
    await tester.tap(find.byKey(const Key('add-tipper')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('asset-code-field')),
      'TIPPER-99',
    );
    await tester.enterText(
      find.byKey(const Key('registration-field')),
      'KA01AB9999',
    );
    await tester.tap(find.byKey(const Key('save-tipper')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('asset-form-error')), findsOneWidget);
    expect(find.text('Registration number is already used'), findsOneWidget);
  });

  for (final count in [1, 3, 10, 50]) {
    testWidgets('fleet remains scrollable with $count assets', (tester) async {
      final api = _FakeOwnerAssetApi([
        for (var index = 1; index <= count; index++) _asset(index),
      ]);
      await _pumpFleet(tester, api);

      expect(find.byKey(const Key('owner-fleet-scroll')), findsOneWidget);
      expect(find.text('$count'), findsWidgets);
      await tester.scrollUntilVisible(
        find.byKey(Key('owner-asset-$count')),
        500,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.byKey(Key('owner-asset-$count')), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }
}

Future<void> _pumpFleet(WidgetTester tester, _FakeOwnerAssetApi api) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(body: OwnerFleetScreen(api: api)),
    ),
  );
  await tester.pumpAndSettle();
}

OwnerAsset _asset(
  int index, {
  String ownership = 'OWNED',
  String status = 'ACTIVE',
  String? rentalParty,
  bool? deployed,
  String assetType = 'TIPPER',
}) => OwnerAsset.fromJson({
  'id': '$index',
  'asset_code': 'TIPPER-$index',
  'asset_type': assetType,
  'ownership_type': ownership,
  'registration_number': 'KA01AB${index.toString().padLeft(4, '0')}',
  'short_name': 'Tipper $index',
  'manufacturer': 'Tata',
  'model': 'Prima',
  'status': status,
  'rental_party_name': rentalParty,
  'rental_start_date': ownership == 'RENTED' ? '2026-09-01' : null,
  'rental_end_date': null,
  'current_deployment': (deployed ?? index == 1)
      ? {
          'id': 'deployment-$index',
          'asset_id': '$index',
          'site_id': 'site-1',
          'site_name': 'Pilot Site',
          'starts_at': '2026-09-29T00:00:00Z',
          'ends_at': null,
        }
      : null,
  'has_active_assignment': index == 1,
  'active_assignment': index == 1
      ? {
          'assignment_id': 'assignment-1',
          'site_id': 'site-1',
          'site_name': 'Pilot Site',
          'driver_membership_id': 'driver-1',
          'driver_name': 'Ramesh',
          'starts_at': '2026-09-30T08:00:00Z',
        }
      : null,
});

class _FakeOwnerAssetApi implements OwnerAssetApi {
  _FakeOwnerAssetApi(this.assets);

  final List<OwnerAsset> assets;
  final List<OwnerAssetInput> created = [];
  String? updatedAssetId;
  OwnerAssetInput? updatedInput;
  String? listError;
  String? saveError;
  int deactivated = 0;
  int reactivated = 0;
  final List<String> deployedAssetIds = [];
  final List<String> deployedSiteIds = [];
  final List<String> removedAssetIds = [];

  @override
  Future<List<OwnerAsset>> ownerAssets({
    String? status,
    String? ownershipType,
    String? assetType,
  }) async {
    if (listError != null) throw ApiException(503, listError!);
    return List<OwnerAsset>.of(assets);
  }

  @override
  Future<OwnerAsset> ownerAsset(String assetId) async =>
      assets.firstWhere((asset) => asset.id == assetId);

  @override
  Future<OwnerAsset> createOwnerAsset(OwnerAssetInput input) async {
    if (saveError != null) throw ApiException(409, saveError!);
    created.add(input);
    final asset = OwnerAsset.fromJson({
      'id': 'created',
      ...input.toJson(includeAssetType: true),
      'status': 'ACTIVE',
      'has_active_assignment': false,
      'active_assignment': null,
    });
    assets.add(asset);
    return asset;
  }

  @override
  Future<OwnerAsset> updateOwnerAsset(
    String assetId,
    OwnerAssetInput input,
  ) async {
    if (saveError != null) throw ApiException(409, saveError!);
    updatedAssetId = assetId;
    updatedInput = input;
    final existing = assets.firstWhere((asset) => asset.id == assetId);
    return OwnerAsset.fromJson({
      'id': assetId,
      ...input.toJson(includeAssetType: true),
      'status': existing.status,
      'has_active_assignment': existing.hasActiveAssignment,
      'active_assignment': null,
    });
  }

  @override
  Future<OwnerAsset> deactivateOwnerAsset(String assetId) async {
    deactivated++;
    return _statusAsset(
      assets.firstWhere((asset) => asset.id == assetId),
      'INACTIVE',
    );
  }

  @override
  Future<OwnerAsset> reactivateOwnerAsset(String assetId) async {
    reactivated++;
    return _statusAsset(
      assets.firstWhere((asset) => asset.id == assetId),
      'ACTIVE',
    );
  }

  @override
  Future<List<OwnerManagedSite>> ownerDeploymentSites() async => [
    _site('site-1', 'Pilot Site'),
    _site('site-2', 'Second Site'),
  ];

  @override
  Future<List<SiteDeployedAsset>> ownerSiteAssets(String siteId) async => [];

  @override
  Future<AssetSiteDeployment> deployOwnerAsset(
    String assetId,
    String siteId,
  ) async {
    deployedAssetIds.add(assetId);
    deployedSiteIds.add(siteId);
    final index = assets.indexWhere((asset) => asset.id == assetId);
    final existing = assets[index];
    final site = (await ownerDeploymentSites()).firstWhere(
      (item) => item.id == siteId,
    );
    final deployment = AssetSiteDeployment.fromJson({
      'id': 'deployment-${deployedAssetIds.length}',
      'asset_id': assetId,
      'site_id': siteId,
      'site_name': site.name,
      'starts_at': '2026-09-29T00:00:00Z',
      'ends_at': null,
    });
    assets[index] = _copyAsset(existing, deployment: deployment);
    return deployment;
  }

  @override
  Future<AssetSiteDeployment> removeOwnerAssetDeployment(String assetId) async {
    removedAssetIds.add(assetId);
    final index = assets.indexWhere((asset) => asset.id == assetId);
    final existing = assets[index];
    final previous = existing.currentDeployment!;
    assets[index] = _copyAsset(existing, deployment: null);
    return AssetSiteDeployment(
      id: previous.id,
      assetId: assetId,
      siteId: previous.siteId,
      siteName: previous.siteName,
      startsAt: previous.startsAt,
      endsAt: DateTime(2026, 9, 30),
    );
  }

  OwnerAsset _statusAsset(OwnerAsset asset, String status) =>
      OwnerAsset.fromJson({
        'id': asset.id,
        'asset_code': asset.assetCode,
        'asset_type': asset.assetType,
        'ownership_type': asset.ownershipType,
        'registration_number': asset.registrationNumber,
        'short_name': asset.shortName,
        'manufacturer': asset.manufacturer,
        'model': asset.model,
        'status': status,
        'rental_party_name': asset.rentalPartyName,
        'rental_start_date': asset.rentalStartDate?.toIso8601String(),
        'rental_end_date': asset.rentalEndDate?.toIso8601String(),
        'current_deployment': asset.currentDeployment == null
            ? null
            : _deploymentJson(asset.currentDeployment!),
        'has_active_assignment': false,
        'active_assignment': null,
      });
}

class _AssignmentOwnerApi extends _FakeOwnerAssetApi
    implements DriverAssignmentApi {
  _AssignmentOwnerApi(super.assets, {this.candidateCount = 1});

  final int candidateCount;
  final List<String> assignedDriverIds = [];
  final List<bool> reassignFlags = [];
  final List<String> unassignedAssetIds = [];

  @override
  Future<List<DriverCandidate>> eligibleDrivers(
    String assetId, {
    String? supervisorSiteId,
  }) async => [
    for (var index = 1; index <= candidateCount; index++)
      DriverCandidate(
        membershipId: candidateCount == 1
            ? 'driver-available'
            : 'driver-$index',
        displayName: candidateCount == 1 ? 'Available Driver' : 'Driver $index',
      ),
  ];

  @override
  Future<DriverAssetAssignment> assignDriver(
    String assetId,
    String driverMembershipId, {
    String? supervisorSiteId,
    bool reassign = false,
  }) async {
    assignedDriverIds.add(driverMembershipId);
    reassignFlags.add(reassign);
    return DriverAssetAssignment.fromJson({
      'assignment_id': 'assignment-new',
      'asset_id': assetId,
      'asset_code': 'TIPPER-4',
      'driver_membership_id': driverMembershipId,
      'driver_name': 'Available Driver',
      'asset_site_deployment_id': 'deployment-1',
      'site_id': 'site-1',
      'site_name': 'Pilot Site',
      'starts_at': '2026-09-30T08:00:00Z',
      'ends_at': null,
      'regular_duty_minutes': 600,
    });
  }

  @override
  Future<DriverAssetAssignment> unassignDriver(
    String assetId, {
    String? supervisorSiteId,
  }) async {
    unassignedAssetIds.add(assetId);
    return DriverAssetAssignment.fromJson({
      'assignment_id': 'assignment-closed',
      'asset_id': assetId,
      'asset_code': 'TIPPER-$assetId',
      'driver_membership_id': 'driver-1',
      'driver_name': 'Ramesh',
      'asset_site_deployment_id': 'deployment-$assetId',
      'site_id': 'site-1',
      'site_name': 'Pilot Site',
      'starts_at': '2026-09-30T08:00:00Z',
      'ends_at': '2026-09-30T09:00:00Z',
      'regular_duty_minutes': 600,
    });
  }
}

OwnerManagedSite _site(String id, String name) => OwnerManagedSite.fromJson({
  'id': id,
  'name': name,
  'code': id.toUpperCase(),
  'status': 'ACTIVE',
  'supervisors': <dynamic>[],
  'asset_count': 0,
});

OwnerAsset _copyAsset(
  OwnerAsset asset, {
  required AssetSiteDeployment? deployment,
}) => OwnerAsset.fromJson({
  'id': asset.id,
  'asset_code': asset.assetCode,
  'asset_type': asset.assetType,
  'ownership_type': asset.ownershipType,
  'registration_number': asset.registrationNumber,
  'short_name': asset.shortName,
  'manufacturer': asset.manufacturer,
  'model': asset.model,
  'status': asset.status,
  'rental_party_name': asset.rentalPartyName,
  'rental_start_date': asset.rentalStartDate?.toIso8601String(),
  'rental_end_date': asset.rentalEndDate?.toIso8601String(),
  'current_deployment': deployment == null ? null : _deploymentJson(deployment),
  'has_active_assignment': asset.hasActiveAssignment,
  'active_assignment': asset.activeAssignment == null
      ? null
      : {
          'assignment_id': asset.activeAssignment!.assignmentId,
          'site_id': asset.activeAssignment!.siteId,
          'site_name': asset.activeAssignment!.siteName,
          'driver_membership_id': asset.activeAssignment!.driverMembershipId,
          'driver_name': asset.activeAssignment!.driverName,
          'starts_at': asset.activeAssignment!.startsAt?.toIso8601String(),
        },
});

Map<String, dynamic> _deploymentJson(AssetSiteDeployment deployment) => {
  'id': deployment.id,
  'asset_id': deployment.assetId,
  'site_id': deployment.siteId,
  'site_name': deployment.siteName,
  'starts_at': deployment.startsAt?.toIso8601String(),
  'ends_at': deployment.endsAt?.toIso8601String(),
};
