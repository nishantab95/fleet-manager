import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fleet_manager_mobile/data/api_client.dart';
import 'package:fleet_manager_mobile/domain/driver_models.dart';

void main() {
  late Directory directory;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('fleet-evidence-mime-');
  });

  tearDown(() => directory.delete(recursive: true));

  Future<String> image(String name, List<int> bytes) async {
    final file = File('${directory.path}${Platform.pathSeparator}$name');
    await file.writeAsBytes(bytes);
    return file.path;
  }

  test('maps a phone JPEG signature to image/jpeg', () async {
    final file = await image('camera.jpg', [0xff, 0xd8, 0xff, 0xe0, 0, 1]);
    expect(await evidenceMimeTypeForPath(file), 'image/jpeg');
  });

  test('maps a PNG signature to image/png', () async {
    final file = await image('meter.png', [
      0x89,
      0x50,
      0x4e,
      0x47,
      0x0d,
      0x0a,
      0x1a,
      0x0a,
      0,
    ]);
    expect(await evidenceMimeTypeForPath(file), 'image/png');
  });

  test('maps a WEBP signature to image/webp', () async {
    final file = await image('meter.webp', [
      ...'RIFF'.codeUnits,
      0,
      0,
      0,
      0,
      ...'WEBP'.codeUnits,
    ]);
    expect(await evidenceMimeTypeForPath(file), 'image/webp');
  });

  test('rejects unsupported evidence locally', () async {
    final file = await image('meter.gif', [...'GIF89a'.codeUnits, 0, 0]);
    await expectLater(
      evidenceMimeTypeForPath(file),
      throwsA(
        isA<ApiException>().having(
          (error) => error.code,
          'code',
          'EVIDENCE_FORMAT_UNSUPPORTED',
        ),
      ),
    );
  });

  test(
    'upload writes the detected image MIME into the multipart part',
    () async {
      final file = await image('camera.jpg', [0xff, 0xd8, 0xff, 0xe0, 0, 1]);
      String? multipartBody;
      final api =
          ApiClient(
            baseUrl: 'http://fleet.test',
            client: MockClient((request) async {
              multipartBody = latin1.decode(request.bodyBytes).toLowerCase();
              return http.Response(
                jsonEncode({'object_reference': 'evidence/test'}),
                200,
                headers: {'content-type': 'application/json'},
              );
            }),
          )..setSession(
            const SessionTokens(
              accessToken: 'access',
              refreshToken: 'refresh',
              expiresIn: 900,
              membershipId: 'membership',
              companyId: 'company',
              role: 'DRIVER',
            ),
          );

      expect(
        await api.uploadEvidence(
          clientEventUuid: '00000000-0000-0000-0000-000000000001',
          evidencePath: file,
        ),
        'evidence/test',
      );
      expect(multipartBody, contains('content-type: image/jpeg'));
      expect(multipartBody, isNot(contains('application/octet-stream')));
    },
  );
}
