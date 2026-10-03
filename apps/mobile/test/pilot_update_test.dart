import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:fleet_manager_mobile/pilot_update.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  group('release checks', () {
    for (final scenario in <(String, int, PilotUpdateCheckState)>[
      ('same versionCode is current', 19, PilotUpdateCheckState.current),
      ('older versionCode is current', 18, PilotUpdateCheckState.current),
      ('higher versionCode is offered', 20, PilotUpdateCheckState.available),
    ]) {
      test(scenario.$1, () async {
        final platform = _FakePlatform(installedVersionCode: 19);
        final service = _service(
          platform,
          response: _manifestResponse(versionCode: scenario.$2),
        );

        final result = await service.check();

        expect(result.state, scenario.$3);
      });
    }

    test('malformed or unsafe release manifests are rejected', () {
      final manifestUri = Uri.parse(
        'https://fleet.example.ts.net/pilot/release.json',
      );
      expect(
        () => PilotRelease.parse('{broken', manifestUri),
        throwsA(isA<PilotUpdateException>()),
      );
      expect(
        () => PilotRelease.parse(
          jsonEncode(<String, Object?>{
            'version_name': '2.0.0-pilot',
            'version_code': 20,
            'apk_url': 'https://attacker.example/update.apk',
            'sha256': 'a' * 64,
            'mandatory': false,
          }),
          manifestUri,
        ),
        throwsA(
          isA<PilotUpdateException>().having(
            (error) => error.code,
            'code',
            'APK_URL_INVALID',
          ),
        ),
      );
    });
  });

  group('download validation', () {
    test('download failure is reported', () async {
      final service = _service(
        _FakePlatform(),
        response: http.Response('offline', 503),
      );
      await expectLater(
        service.downloadAndValidate(_release(sha: 'a' * 64)),
        throwsA(
          isA<PilotUpdateException>().having(
            (error) => error.code,
            'code',
            'DOWNLOAD_FAILED',
          ),
        ),
      );
    });

    test('SHA-256 mismatch deletes and rejects the APK', () async {
      final temp = await Directory.systemTemp.createTemp('fleet-update-test-');
      addTearDown(() => temp.delete(recursive: true));
      final service = _service(
        _FakePlatform(),
        bytes: utf8.encode('downloaded apk'),
        temporaryDirectory: () async => temp,
      );

      await expectLater(
        service.downloadAndValidate(_release(sha: '0' * 64)),
        throwsA(
          isA<PilotUpdateException>().having(
            (error) => error.code,
            'code',
            'SHA256_MISMATCH',
          ),
        ),
      );
      expect(temp.listSync(), isEmpty);
    });

    test('storage failure has a recoverable operator message', () async {
      final service = _service(
        _FakePlatform(),
        bytes: utf8.encode('downloaded apk'),
        temporaryDirectory: () async =>
            throw const FileSystemException('No space left on device'),
      );

      await expectLater(
        service.downloadAndValidate(_release()),
        throwsA(
          isA<PilotUpdateException>()
              .having((error) => error.code, 'code', 'INSUFFICIENT_STORAGE')
              .having(
                (error) => error.message,
                'message',
                contains('Free device storage'),
              ),
        ),
      );
    });

    test('wrong package is rejected after integrity succeeds', () async {
      final bytes = utf8.encode('signed bytes');
      final temp = await Directory.systemTemp.createTemp('fleet-update-test-');
      addTearDown(() => temp.delete(recursive: true));
      final platform = _FakePlatform(archivePackage: 'com.example.not_fleet');
      final service = _service(
        platform,
        bytes: bytes,
        temporaryDirectory: () async => temp,
      );

      await expectLater(
        service.downloadAndValidate(
          _release(sha: sha256.convert(bytes).toString()),
        ),
        throwsA(
          isA<PilotUpdateException>().having(
            (error) => error.code,
            'code',
            'WRONG_PACKAGE',
          ),
        ),
      );
    });

    test('wrong signing certificate is rejected', () async {
      final bytes = utf8.encode('signed bytes');
      final temp = await Directory.systemTemp.createTemp('fleet-update-test-');
      addTearDown(() => temp.delete(recursive: true));
      final platform = _FakePlatform(archiveSigner: '0' * 64);
      final service = _service(
        platform,
        bytes: bytes,
        temporaryDirectory: () async => temp,
      );

      await expectLater(
        service.downloadAndValidate(
          _release(sha: sha256.convert(bytes).toString()),
        ),
        throwsA(
          isA<PilotUpdateException>().having(
            (error) => error.code,
            'code',
            'WRONG_SIGNER',
          ),
        ),
      );
    });

    test('downgrade or reinstall is refused', () async {
      final bytes = utf8.encode('signed bytes');
      final temp = await Directory.systemTemp.createTemp('fleet-update-test-');
      addTearDown(() => temp.delete(recursive: true));
      final platform = _FakePlatform(
        installedVersionCode: 20,
        archiveVersionCode: 20,
      );
      final service = _service(
        platform,
        bytes: bytes,
        temporaryDirectory: () async => temp,
      );

      await expectLater(
        service.downloadAndValidate(
          _release(versionCode: 20, sha: sha256.convert(bytes).toString()),
        ),
        throwsA(
          isA<PilotUpdateException>().having(
            (error) => error.code,
            'code',
            'DOWNGRADE_REFUSED',
          ),
        ),
      );
    });
  });

  test(
    'unknown-sources permission and installer handoff are abstracted',
    () async {
      final platform = _FakePlatform(canInstall: false);
      final service = _service(platform);
      final apk = PilotValidatedApk('/private/cache/update.apk', _release());

      expect(
        await service.install(apk),
        PilotInstallDisposition.permissionRequired,
      );
      expect(platform.launchedPath, isNull);
      await platform.openUnknownSourcesSettings();
      expect(platform.settingsOpened, isTrue);

      platform.canInstall = true;
      expect(await service.install(apk), PilotInstallDisposition.launched);
      expect(platform.launchedPath, '/private/cache/update.apk');
    },
  );

  testWidgets('optional update can be deferred with Later', (tester) async {
    final controller = PilotUpdateController(
      service: _service(
        _FakePlatform(installedVersionCode: 19),
        response: _manifestResponse(versionCode: 20),
      ),
      pilotEnabled: true,
    );

    await tester.pumpWidget(
      MaterialApp(
        home: PilotUpdateGate(
          controller: controller,
          child: const Scaffold(body: Text('Operational app')),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Fleet Manager update available'), findsOneWidget);
    await tester.tap(find.text('LATER'));
    await tester.pumpAndSettle();
    expect(find.text('Fleet Manager update available'), findsNothing);
    expect(find.text('Operational app'), findsOneWidget);
  });

  testWidgets('mandatory update prompt cannot be dismissed with Back', (
    tester,
  ) async {
    final controller = PilotUpdateController(
      service: _service(
        _FakePlatform(installedVersionCode: 19),
        response: _manifestResponse(versionCode: 20, mandatory: true),
      ),
      pilotEnabled: true,
    );

    await tester.pumpWidget(
      MaterialApp(
        home: PilotUpdateGate(
          controller: controller,
          child: const Scaffold(body: Text('Operational app')),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Update required'), findsOneWidget);
    expect(find.text('LATER'), findsNothing);
    await tester.binding.handlePopRoute();
    await tester.pump();
    expect(find.text('Update required'), findsOneWidget);
  });
}

PilotUpdateService _service(
  _FakePlatform platform, {
  http.Response? response,
  List<int>? bytes,
  Future<Directory> Function()? temporaryDirectory,
}) {
  final client = MockClient((_) async {
    if (response != null) return response;
    if (bytes != null) return http.Response.bytes(bytes, 200);
    return _manifestResponse(versionCode: 20);
  });
  return PilotUpdateService(
    baseUrl: () => 'https://fleet.example.ts.net',
    platform: platform,
    client: client,
    temporaryDirectory: temporaryDirectory,
    pilotEnabled: true,
  );
}

http.Response _manifestResponse({
  required int versionCode,
  bool mandatory = false,
}) => http.Response(
  jsonEncode(<String, Object?>{
    'version_name': '2.0.0-pilot',
    'version_code': versionCode,
    'apk_url':
        'https://fleet.example.ts.net/pilot/FleetManager-Pilot-latest.apk',
    'sha256': 'a' * 64,
    'mandatory': mandatory,
    'published_at': '2026-10-03T10:00:00Z',
    'source_commit': 'b' * 40,
  }),
  200,
);

PilotRelease _release({int versionCode = 20, String? sha}) => PilotRelease(
  versionName: '2.0.0-pilot',
  versionCode: versionCode,
  apkUrl: Uri.parse(
    'https://fleet.example.ts.net/pilot/FleetManager-Pilot-latest.apk',
  ),
  sha256: sha ?? 'a' * 64,
  mandatory: false,
);

class _FakePlatform implements PilotUpdatePlatform {
  _FakePlatform({
    this.installedVersionCode = 19,
    this.archiveVersionCode = 20,
    this.archivePackage = pilotPackageName,
    this.archiveSigner = pilotSignerSha256,
    this.canInstall = true,
  });

  int installedVersionCode;
  int archiveVersionCode;
  String archivePackage;
  String archiveSigner;
  bool canInstall;
  bool settingsOpened = false;
  String? launchedPath;

  @override
  Future<PilotInstalledApp> installedApp() async => PilotInstalledApp(
    packageName: pilotPackageName,
    versionName: '1.0.0-pilot',
    versionCode: installedVersionCode,
  );

  @override
  Future<PilotArchiveInfo> inspectArchive(String apkPath) async =>
      PilotArchiveInfo(
        packageName: archivePackage,
        versionName: '2.0.0-pilot',
        versionCode: archiveVersionCode,
        signerSha256: archiveSigner,
      );

  @override
  Future<bool> canRequestPackageInstalls() async => canInstall;

  @override
  Future<void> openUnknownSourcesSettings() async {
    settingsOpened = true;
  }

  @override
  Future<void> launchInstaller(String apkPath) async {
    launchedPath = apkPath;
  }
}
