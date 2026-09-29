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

class _FakePeopleSitesApi implements OwnerPeopleSiteApi {
  _FakePeopleSitesApi({this.people = const [], this.sites = const []});

  List<OwnerPerson> people;
  List<OwnerManagedSite> sites;

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

OwnerManagedSite _site(int index, {String status = 'ACTIVE'}) =>
    OwnerManagedSite.fromJson(_siteJson(index, status: status));

Map<String, dynamic> _siteJson(int index, {String status = 'ACTIVE'}) => {
  'id': 'site-$index',
  'name': 'Site $index',
  'code': 'S-$index',
  'location_description': null,
  'latitude': null,
  'longitude': null,
  'status': status,
  'supervisors': <dynamic>[],
  'asset_count': 0,
};
