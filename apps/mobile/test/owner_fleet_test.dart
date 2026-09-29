import 'package:fleet_manager_mobile/data/api_client.dart';
import 'package:fleet_manager_mobile/domain/role_models.dart';
import 'package:fleet_manager_mobile/owner_fleet.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
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
    expect(find.text('ADD TIPPER'), findsWidgets);
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
}) => OwnerAsset.fromJson({
  'id': '$index',
  'asset_code': 'TIPPER-$index',
  'asset_type': 'TIPPER',
  'ownership_type': ownership,
  'registration_number': 'KA01AB${index.toString().padLeft(4, '0')}',
  'short_name': 'Tipper $index',
  'manufacturer': 'Tata',
  'model': 'Prima',
  'status': status,
  'rental_party_name': rentalParty,
  'rental_start_date': ownership == 'RENTED' ? '2026-09-01' : null,
  'rental_end_date': null,
  'has_active_assignment': index == 1,
  'active_assignment': index == 1
      ? {
          'assignment_id': 'assignment-1',
          'site_id': 'site-1',
          'site_name': 'Pilot Site',
          'driver_membership_id': 'driver-1',
          'driver_name': 'Ramesh',
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

  @override
  Future<List<OwnerAsset>> ownerAssets({
    String? status,
    String? ownershipType,
    String assetType = 'TIPPER',
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
        'has_active_assignment': false,
        'active_assignment': null,
      });
}
