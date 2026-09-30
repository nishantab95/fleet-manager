import 'dart:convert';

import 'package:fleet_manager_mobile/data/api_client.dart';
import 'package:fleet_manager_mobile/domain/driver_models.dart';
import 'package:fleet_manager_mobile/domain/role_models.dart';
import 'package:fleet_manager_mobile/owner_people_sites.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets('people list filters and remains scrollable at 200 records', (
    tester,
  ) async {
    final api = _FakePeopleSitesApi(
      people: [for (var index = 0; index < 200; index++) _person(index)],
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: OwnerPeopleScreen(api: api)),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('owner-people-list')), findsOneWidget);
    await tester.enterText(
      find.byKey(const Key('people-search')),
      'Person 199',
    );
    await tester.pump();
    expect(find.byKey(const Key('person-membership-199')), findsOneWidget);
    expect(find.byKey(const Key('person-membership-0')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Driver detail shows the current Asset and Site read only', (
    tester,
  ) async {
    final person = OwnerPerson.fromJson({
      ..._personJson(1),
      'has_active_assignment': true,
      'current_asset_id': 'asset-1',
      'current_asset_code': 'OWN-T02',
      'current_site_id': 'site-1',
      'current_site_name': 'Test Site B',
    });
    final api = _FakePeopleSitesApi(people: [person]);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: OwnerPeopleScreen(api: api)),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('person-membership-1')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('person-current-assignment')), findsOneWidget);
    expect(find.text('OWN-T02'), findsOneWidget);
    expect(find.text('Test Site B'), findsOneWidget);
  });

  testWidgets('sites list renders 50 records and opens supervisor detail', (
    tester,
  ) async {
    final api = _FakePeopleSitesApi(
      people: [_person(1, role: 'SUPERVISOR')],
      sites: [for (var index = 0; index < 50; index++) _site(index)],
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: OwnerSitesScreen(api: api)),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('owner-sites-list')), findsOneWidget);
    await tester.enterText(find.byKey(const Key('site-search')), 'Site 49');
    await tester.pump();
    await tester.tap(find.byKey(const Key('site-site-49')));
    await tester.pumpAndSettle();
    expect(find.text('SUPERVISORS'), findsOneWidget);
    expect(find.byKey(const Key('site-supervisor')), findsOneWidget);
  });

  testWidgets(
    'site detail lists deployed assets and deploys an available asset',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(1080, 2400));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final api = _FakePeopleSitesApi(
        sites: [_site(1, assetCount: 20)],
        assets: [_asset(21)],
        siteAssets: [
          for (var index = 1; index <= 20; index++) _siteAsset(index),
        ],
      );
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: OwnerSitesScreen(api: api, assetApi: api),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('site-site-1')));
      await tester.pumpAndSettle();
      expect(find.text('ASSETS — 20'), findsOneWidget);
      expect(find.byKey(const Key('site-asset-asset-1')), findsOneWidget);
      expect(find.textContaining('Driver: Unassigned'), findsWidgets);

      await tester.tap(find.byKey(const Key('deploy-site-asset')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('site-deploy-asset-selector')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('ASSET-21 / REG-21').last);
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('confirm-site-deploy')))
            .onPressed,
        isNotNull,
      );
      await tester.tap(find.byKey(const Key('confirm-site-deploy')));
      await tester.pumpAndSettle();

      expect(api.lastDeployment, ('asset-21', 'site-1'));
      expect(find.text('ASSETS — 21'), findsOneWidget);
      expect(find.byKey(const Key('site-asset-asset-21')), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('five sites summarize one hundred deployed assets', (
    tester,
  ) async {
    final api = _FakePeopleSitesApi(
      sites: [
        for (var index = 1; index <= 5; index++) _site(index, assetCount: 20),
      ],
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: OwnerSitesScreen(api: api)),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('20 active assets'), findsNWidgets(5));
    expect(tester.takeException(), isNull);
  });

  test('people and site mutations retry after shared token refresh', () async {
    var refreshes = 0;
    var protectedCalls = 0;
    final api =
        ApiClient(
          baseUrl: 'http://test',
          client: MockClient((request) async {
            if (request.url.path == '/api/v1/auth/refresh') {
              refreshes++;
              return http.Response(
                jsonEncode({
                  'access_token': 'new-access',
                  'refresh_token': 'new-refresh',
                  'token_type': 'bearer',
                  'expires_in': 900,
                  'membership_id': 'owner-1',
                  'company_id': 'company-1',
                  'role': 'OWNER_ADMIN',
                }),
                200,
              );
            }
            protectedCalls++;
            if (request.headers['authorization'] == 'Bearer expired-access') {
              return http.Response('{}', 401);
            }
            expect(request.headers['authorization'], 'Bearer new-access');
            if (request.url.path.contains('/people/')) {
              return http.Response(jsonEncode(_personJson(1)), 200);
            }
            return http.Response(jsonEncode(_siteJson(1)), 200);
          }),
        )..setSession(
          const SessionTokens(
            accessToken: 'expired-access',
            refreshToken: 'valid-refresh',
            expiresIn: 900,
            membershipId: 'owner-1',
            companyId: 'company-1',
            role: 'OWNER_ADMIN',
          ),
        );

    await api.inviteOwnerPerson(
      const OwnerPersonInput(
        displayName: 'Person 1',
        role: 'DRIVER',
        phone: '+919876543210',
      ),
    );
    api.setSession(
      const SessionTokens(
        accessToken: 'expired-access',
        refreshToken: 'valid-refresh',
        expiresIn: 900,
        membershipId: 'owner-1',
        companyId: 'company-1',
        role: 'OWNER_ADMIN',
      ),
    );
    await api.createOwnerSite(const OwnerSiteInput(name: 'Site 1'));

    expect(refreshes, 2);
    expect(protectedCalls, 4);
  });
}

class _FakePeopleSitesApi implements OwnerPeopleSiteApi, OwnerAssetApi {
  _FakePeopleSitesApi({
    this.people = const [],
    this.sites = const [],
    this.assets = const [],
    this.siteAssets = const [],
  });

  List<OwnerPerson> people;
  List<OwnerManagedSite> sites;
  List<OwnerAsset> assets;
  List<SiteDeployedAsset> siteAssets;
  (String, String)? lastDeployment;

  @override
  Future<List<OwnerPerson>> ownerPeople() async => people;

  @override
  Future<List<OwnerManagedSite>> ownerSites() async => sites;

  @override
  Future<OwnerPerson> inviteOwnerPerson(OwnerPersonInput input) async =>
      _person(999);

  @override
  Future<OwnerPerson> updateOwnerPerson(
    String membershipId,
    OwnerPersonInput input,
  ) async => _person(999);

  @override
  Future<OwnerPerson> setOwnerPersonActive(
    String membershipId,
    bool active,
  ) async => _person(999, status: active ? 'ACTIVE' : 'INACTIVE');

  @override
  Future<OwnerManagedSite> createOwnerSite(OwnerSiteInput input) async =>
      _site(999);

  @override
  Future<OwnerManagedSite> updateOwnerSite(
    String siteId,
    OwnerSiteInput input,
  ) async => _site(999);

  @override
  Future<OwnerManagedSite> setOwnerSiteActive(
    String siteId,
    bool active,
  ) async => _site(999, status: active ? 'ACTIVE' : 'INACTIVE');

  @override
  Future<OwnerManagedSite> grantOwnerSiteSupervisor(
    String siteId,
    String membershipId,
  ) async => _site(999);

  @override
  Future<OwnerManagedSite> revokeOwnerSiteSupervisor(
    String siteId,
    String membershipId,
  ) async => _site(999);

  @override
  Future<List<OwnerAsset>> ownerAssets({
    String? status,
    String? ownershipType,
    String? assetType,
  }) async => assets;

  @override
  Future<OwnerAsset> ownerAsset(String assetId) async =>
      assets.firstWhere((asset) => asset.id == assetId);

  @override
  Future<OwnerAsset> createOwnerAsset(OwnerAssetInput input) async =>
      _asset(999);

  @override
  Future<OwnerAsset> updateOwnerAsset(
    String assetId,
    OwnerAssetInput input,
  ) async => ownerAsset(assetId);

  @override
  Future<OwnerAsset> deactivateOwnerAsset(String assetId) =>
      ownerAsset(assetId);

  @override
  Future<OwnerAsset> reactivateOwnerAsset(String assetId) =>
      ownerAsset(assetId);

  @override
  Future<List<OwnerManagedSite>> ownerDeploymentSites() async => sites;

  @override
  Future<List<SiteDeployedAsset>> ownerSiteAssets(String siteId) async =>
      siteAssets
          .where((asset) => asset.currentDeployment.siteId == siteId)
          .toList();

  @override
  Future<AssetSiteDeployment> deployOwnerAsset(
    String assetId,
    String siteId,
  ) async {
    lastDeployment = (assetId, siteId);
    final asset = assets.firstWhere((value) => value.id == assetId);
    final deployment = _deployment(assetId, siteId);
    siteAssets = [
      ...siteAssets,
      SiteDeployedAsset(
        assetId: asset.id,
        assetCode: asset.assetCode,
        assetType: asset.assetType,
        ownershipType: asset.ownershipType,
        registrationNumber: asset.registrationNumber,
        shortName: asset.shortName,
        status: asset.status,
        currentDeployment: deployment,
        driverMembershipId: null,
        driverName: null,
        dutyStatus: null,
        pendingReviewCount: 0,
      ),
    ];
    assets = assets.where((value) => value.id != assetId).toList();
    return deployment;
  }

  @override
  Future<AssetSiteDeployment> removeOwnerAssetDeployment(
    String assetId,
  ) async => siteAssets
      .firstWhere((asset) => asset.assetId == assetId)
      .currentDeployment;
}

OwnerPerson _person(
  int index, {
  String role = 'DRIVER',
  String status = 'ACTIVE',
}) => OwnerPerson.fromJson(_personJson(index, role: role, status: status));

Map<String, dynamic> _personJson(
  int index, {
  String role = 'DRIVER',
  String status = 'ACTIVE',
}) => {
  'user_id': 'user-$index',
  'membership_id': 'membership-$index',
  'phone': '+91900000${index.toString().padLeft(4, '0')}',
  'display_name': 'Person $index',
  'role': role,
  'status': status,
  'sites': <dynamic>[],
  'has_active_assignment': false,
  'has_active_duty': false,
};

OwnerManagedSite _site(
  int index, {
  String status = 'ACTIVE',
  int assetCount = 0,
}) => OwnerManagedSite.fromJson(
  _siteJson(index, status: status, assetCount: assetCount),
);

Map<String, dynamic> _siteJson(
  int index, {
  String status = 'ACTIVE',
  int assetCount = 0,
}) => {
  'id': 'site-$index',
  'name': 'Site $index',
  'code': 'S-$index',
  'location_description': null,
  'latitude': null,
  'longitude': null,
  'status': status,
  'supervisors': <dynamic>[],
  'asset_count': assetCount,
};

AssetSiteDeployment _deployment(String assetId, String siteId) =>
    AssetSiteDeployment.fromJson({
      'id': 'deployment-$assetId-$siteId',
      'asset_id': assetId,
      'site_id': siteId,
      'site_name': sitesLabel(siteId),
      'starts_at': '2026-09-29T08:00:00Z',
      'ends_at': null,
    });

String sitesLabel(String siteId) => 'Site ${siteId.replaceFirst('site-', '')}';

OwnerAsset _asset(int index) => OwnerAsset.fromJson({
  'id': 'asset-$index',
  'asset_code': 'ASSET-$index',
  'asset_type': index.isEven ? 'TIPPER' : 'EXCAVATOR',
  'ownership_type': index.isEven ? 'OWNED' : 'RENTED',
  'registration_number': 'REG-$index',
  'short_name': 'Asset $index',
  'manufacturer': null,
  'model': null,
  'status': 'ACTIVE',
  'rental_party_name': index.isEven ? null : 'Rental Partner',
  'rental_start_date': index.isEven ? null : '2026-09-01',
  'rental_end_date': null,
  'current_deployment': null,
  'has_active_assignment': false,
  'active_assignment': null,
});

SiteDeployedAsset _siteAsset(int index) => SiteDeployedAsset.fromJson({
  'asset_id': 'asset-$index',
  'asset_code': 'ASSET-$index',
  'asset_type': index.isEven ? 'TIPPER' : 'EXCAVATOR',
  'ownership_type': index.isEven ? 'OWNED' : 'RENTED',
  'registration_number': 'REG-$index',
  'short_name': 'Asset $index',
  'status': 'ACTIVE',
  'current_deployment': {
    'id': 'deployment-$index-1',
    'asset_id': 'asset-$index',
    'site_id': 'site-1',
    'site_name': 'Site 1',
    'starts_at': '2026-09-29T08:00:00Z',
    'ends_at': null,
  },
  'driver_membership_id': index == 1 ? 'driver-1' : null,
  'driver_name': index == 1 ? 'Driver One' : null,
  'duty_status': index == 1 ? 'ACTIVE' : null,
  'pending_review_count': 0,
});
