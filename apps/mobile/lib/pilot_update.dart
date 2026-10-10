import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

import 'domain/role_models.dart';

const pilotPackageName = 'com.fleetmanager.fleet_manager_mobile.pilot';
const pilotSignerSha256 =
    'fd25115e20ac18a8a7cda91b9f4d5f6153f54b4d79c751b5005a3ac734cc3c29';

class PilotUpdateException implements Exception {
  const PilotUpdateException(this.code, this.message);

  final String code;
  final String message;

  @override
  String toString() => '$code: $message';
}

class PilotInstalledApp {
  const PilotInstalledApp({
    required this.packageName,
    required this.versionName,
    required this.versionCode,
  });

  final String packageName;
  final String versionName;
  final int versionCode;
}

class PilotArchiveInfo {
  const PilotArchiveInfo({
    required this.packageName,
    required this.versionName,
    required this.versionCode,
    required this.signerSha256,
  });

  final String packageName;
  final String versionName;
  final int versionCode;
  final String signerSha256;
}

abstract class PilotUpdatePlatform {
  Future<PilotInstalledApp> installedApp();
  Future<PilotArchiveInfo> inspectArchive(String apkPath);
  Future<bool> canRequestPackageInstalls();
  Future<void> openUnknownSourcesSettings();
  Future<void> launchInstaller(String apkPath);
}

class AndroidPilotUpdatePlatform implements PilotUpdatePlatform {
  const AndroidPilotUpdatePlatform();

  static const _channel = MethodChannel('fleet_manager/pilot_update');

  @override
  Future<PilotInstalledApp> installedApp() async {
    final value = await _channel.invokeMapMethod<String, Object?>(
      'installedApp',
    );
    if (value == null) {
      throw const PilotUpdateException(
        'PLATFORM_INFO_MISSING',
        'Android did not return installed app information.',
      );
    }
    return PilotInstalledApp(
      packageName: value['packageName'] as String,
      versionName: value['versionName'] as String,
      versionCode: (value['versionCode'] as num).toInt(),
    );
  }

  @override
  Future<PilotArchiveInfo> inspectArchive(String apkPath) async {
    final value = await _channel.invokeMapMethod<String, Object?>(
      'inspectArchive',
      <String, Object?>{'path': apkPath},
    );
    if (value == null) {
      throw const PilotUpdateException(
        'APK_INFO_MISSING',
        'Android could not inspect the downloaded APK.',
      );
    }
    return PilotArchiveInfo(
      packageName: value['packageName'] as String,
      versionName: value['versionName'] as String,
      versionCode: (value['versionCode'] as num).toInt(),
      signerSha256: (value['signerSha256'] as String).toLowerCase(),
    );
  }

  @override
  Future<bool> canRequestPackageInstalls() async =>
      await _channel.invokeMethod<bool>('canRequestPackageInstalls') ?? false;

  @override
  Future<void> openUnknownSourcesSettings() =>
      _channel.invokeMethod<void>('openUnknownSourcesSettings');

  @override
  Future<void> launchInstaller(String apkPath) => _channel.invokeMethod<void>(
    'launchInstaller',
    <String, Object?>{'path': apkPath},
  );
}

class PilotRelease {
  const PilotRelease({
    required this.versionName,
    required this.versionCode,
    required this.apkUrl,
    required this.sha256,
    required this.mandatory,
    this.publishedAt,
    this.sourceCommit,
  });

  final String versionName;
  final int versionCode;
  final Uri apkUrl;
  final String sha256;
  final bool mandatory;
  final DateTime? publishedAt;
  final String? sourceCommit;

  static PilotRelease parse(String body, Uri manifestUri) {
    Object? decoded;
    try {
      decoded = jsonDecode(body);
    } on FormatException {
      throw const PilotUpdateException(
        'MANIFEST_INVALID',
        'The update manifest is not valid JSON.',
      );
    }
    if (decoded is! Map<String, dynamic>) {
      throw const PilotUpdateException(
        'MANIFEST_INVALID',
        'The update manifest must be a JSON object.',
      );
    }
    const allowed = <String>{
      'version_name',
      'version_code',
      'apk_url',
      'sha256',
      'mandatory',
      'published_at',
      'source_commit',
    };
    if (decoded.keys.any((key) => !allowed.contains(key))) {
      throw const PilotUpdateException(
        'MANIFEST_INVALID',
        'The update manifest contains unsupported fields.',
      );
    }
    final versionName = decoded['version_name'];
    final versionCode = decoded['version_code'];
    final rawUrl = decoded['apk_url'];
    final digest = decoded['sha256'];
    final mandatory = decoded['mandatory'];
    if (versionName is! String ||
        versionName.trim().isEmpty ||
        versionCode is! int ||
        versionCode <= 0 ||
        rawUrl is! String ||
        digest is! String ||
        !RegExp(r'^[0-9a-fA-F]{64}$').hasMatch(digest) ||
        mandatory is! bool) {
      throw const PilotUpdateException(
        'MANIFEST_INVALID',
        'The update manifest has missing or invalid release fields.',
      );
    }
    final apkUrl = Uri.tryParse(rawUrl);
    if (apkUrl == null ||
        apkUrl.scheme != 'https' ||
        apkUrl.host.isEmpty ||
        apkUrl.authority.toLowerCase() != manifestUri.authority.toLowerCase() ||
        !apkUrl.path.startsWith('/pilot/') ||
        !apkUrl.path.toLowerCase().endsWith('.apk')) {
      throw const PilotUpdateException(
        'APK_URL_INVALID',
        'The APK URL must use private HTTPS on the Pilot server.',
      );
    }
    final rawPublishedAt = decoded['published_at'];
    final rawSourceCommit = decoded['source_commit'];
    final publishedAt = rawPublishedAt == null
        ? null
        : rawPublishedAt is String
        ? DateTime.tryParse(rawPublishedAt)
        : null;
    if (rawPublishedAt != null && publishedAt == null) {
      throw const PilotUpdateException(
        'MANIFEST_INVALID',
        'The update publication timestamp is invalid.',
      );
    }
    if (rawSourceCommit != null &&
        (rawSourceCommit is! String ||
            !RegExp(r'^[0-9a-f]{40}$').hasMatch(rawSourceCommit))) {
      throw const PilotUpdateException(
        'MANIFEST_INVALID',
        'The update source commit is invalid.',
      );
    }
    return PilotRelease(
      versionName: versionName.trim(),
      versionCode: versionCode,
      apkUrl: apkUrl,
      sha256: digest.toLowerCase(),
      mandatory: mandatory,
      publishedAt: publishedAt,
      sourceCommit: rawSourceCommit as String?,
    );
  }
}

enum PilotUpdateCheckState { current, available, unavailable, notPilot }

class PilotUpdateCheck {
  const PilotUpdateCheck(this.state, this.installed, {this.release});

  final PilotUpdateCheckState state;
  final PilotInstalledApp installed;
  final PilotRelease? release;
}

class PilotDownloadCancellation {
  bool _cancelled = false;
  bool get isCancelled => _cancelled;
  void cancel() => _cancelled = true;
}

class PilotValidatedApk {
  const PilotValidatedApk(this.path, this.release);
  final String path;
  final PilotRelease release;
}

enum PilotInstallDisposition { launched, permissionRequired }

typedef PilotProgress = void Function(int received, int? total);
typedef PilotTempDirectory = Future<Directory> Function();

class PilotUpdateService {
  PilotUpdateService({
    required this.baseUrl,
    required this.platform,
    http.Client? client,
    PilotTempDirectory? temporaryDirectory,
    this.manifestTimeout = const Duration(seconds: 8),
    this.pilotEnabled = isPilotBuild,
  }) : client = client ?? http.Client(),
       temporaryDirectory = temporaryDirectory ?? getTemporaryDirectory;

  final String Function() baseUrl;
  final PilotUpdatePlatform platform;
  final http.Client client;
  final PilotTempDirectory temporaryDirectory;
  final Duration manifestTimeout;
  final bool pilotEnabled;

  Uri _manifestUri() {
    final root = Uri.tryParse(baseUrl().trim());
    if (root == null || root.scheme != 'https' || root.host.isEmpty) {
      throw const PilotUpdateException(
        'PILOT_SERVER_NOT_PRIVATE_HTTPS',
        'Set the Pilot server to its private Tailscale HTTPS address.',
      );
    }
    return root.resolve('/pilot/release.json');
  }

  Future<PilotUpdateCheck> check() async {
    final installed = await platform.installedApp();
    if (!pilotEnabled || installed.packageName != pilotPackageName) {
      return PilotUpdateCheck(PilotUpdateCheckState.notPilot, installed);
    }
    try {
      final manifestUri = _manifestUri();
      final response = await client.get(manifestUri).timeout(manifestTimeout);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        return PilotUpdateCheck(PilotUpdateCheckState.unavailable, installed);
      }
      final release = PilotRelease.parse(response.body, manifestUri);
      return PilotUpdateCheck(
        release.versionCode > installed.versionCode
            ? PilotUpdateCheckState.available
            : PilotUpdateCheckState.current,
        installed,
        release: release,
      );
    } on PilotUpdateException {
      rethrow;
    } on TimeoutException {
      return PilotUpdateCheck(PilotUpdateCheckState.unavailable, installed);
    } on SocketException {
      return PilotUpdateCheck(PilotUpdateCheckState.unavailable, installed);
    } on http.ClientException {
      return PilotUpdateCheck(PilotUpdateCheckState.unavailable, installed);
    }
  }

  Future<PilotValidatedApk> downloadAndValidate(
    PilotRelease release, {
    PilotProgress? onProgress,
    PilotDownloadCancellation? cancellation,
  }) async {
    File? destination;
    IOSink? sink;
    Future<void> discardPartialDownload() async {
      try {
        await sink?.close();
      } on Object {
        // Preserve the original validation/download failure.
      }
      try {
        await destination?.delete();
      } on Object {
        // App-private cache cleanup is best effort after a failed download.
      }
    }

    try {
      final request = http.Request('GET', release.apkUrl);
      final response = await client.send(request).timeout(manifestTimeout);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw PilotUpdateException(
          'DOWNLOAD_FAILED',
          'The Pilot APK download failed (${response.statusCode}).',
        );
      }
      final directory = await temporaryDirectory();
      await directory.create(recursive: true);
      destination = File(
        path.join(directory.path, 'fleet-pilot-${release.versionCode}.apk'),
      );
      sink = destination.openWrite(mode: FileMode.writeOnly);
      var received = 0;
      await for (final chunk in response.stream.timeout(
        const Duration(seconds: 30),
      )) {
        if (cancellation?.isCancelled == true) {
          throw const PilotUpdateException(
            'DOWNLOAD_CANCELLED',
            'The update download was cancelled.',
          );
        }
        sink.add(chunk);
        received += chunk.length;
        onProgress?.call(received, response.contentLength);
      }
      await sink.flush();
      await sink.close();
      sink = null;

      final actualDigest = (await sha256.bind(destination.openRead()).first)
          .toString();
      if (actualDigest != release.sha256) {
        throw const PilotUpdateException(
          'SHA256_MISMATCH',
          'The downloaded APK failed its SHA-256 integrity check.',
        );
      }
      final installed = await platform.installedApp();
      final archive = await platform.inspectArchive(destination.path);
      if (archive.packageName != pilotPackageName) {
        throw const PilotUpdateException(
          'WRONG_PACKAGE',
          'The downloaded APK is not Fleet AI Systems Pilot.',
        );
      }
      if (archive.signerSha256.toLowerCase() != pilotSignerSha256) {
        throw const PilotUpdateException(
          'WRONG_SIGNER',
          'The downloaded APK was signed by an untrusted certificate.',
        );
      }
      if (archive.versionCode != release.versionCode) {
        throw const PilotUpdateException(
          'VERSION_MISMATCH',
          'The APK version does not match the published release.',
        );
      }
      if (archive.versionCode <= installed.versionCode) {
        throw const PilotUpdateException(
          'DOWNGRADE_REFUSED',
          'The APK is not newer than the installed Pilot build.',
        );
      }
      return PilotValidatedApk(destination.path, release);
    } on PilotUpdateException {
      await discardPartialDownload();
      rethrow;
    } on FileSystemException {
      await discardPartialDownload();
      throw const PilotUpdateException(
        'INSUFFICIENT_STORAGE',
        'The update could not be saved. Free device storage and try again.',
      );
    } on TimeoutException {
      await discardPartialDownload();
      throw const PilotUpdateException(
        'DOWNLOAD_INTERRUPTED',
        'The update download was interrupted. Check Tailscale and try again.',
      );
    } on SocketException {
      await discardPartialDownload();
      throw const PilotUpdateException(
        'DOWNLOAD_INTERRUPTED',
        'The update download was interrupted. Check Tailscale and try again.',
      );
    } on http.ClientException {
      await discardPartialDownload();
      throw const PilotUpdateException(
        'DOWNLOAD_INTERRUPTED',
        'The update download was interrupted. Check Tailscale and try again.',
      );
    } on Object {
      await discardPartialDownload();
      throw const PilotUpdateException(
        'DOWNLOAD_FAILED',
        'The Pilot update could not be downloaded or validated.',
      );
    }
  }

  Future<PilotInstallDisposition> install(PilotValidatedApk apk) async {
    if (!pilotEnabled) {
      throw const PilotUpdateException(
        'NOT_PILOT',
        'Private APK installation is disabled outside the Pilot build.',
      );
    }
    if (!await platform.canRequestPackageInstalls()) {
      return PilotInstallDisposition.permissionRequired;
    }
    await platform.launchInstaller(apk.path);
    return PilotInstallDisposition.launched;
  }
}

class PilotUpdateController {
  PilotUpdateController({
    required this.service,
    this.cooldown = const Duration(minutes: 15),
    this.pilotEnabled = isPilotBuild,
    DateTime Function()? now,
  }) : _now = now ?? DateTime.now;

  final PilotUpdateService service;
  final Duration cooldown;
  final bool pilotEnabled;
  final DateTime Function() _now;
  DateTime? _lastCheck;
  PilotValidatedApk? _pendingInstall;
  bool _waitingForInstallPermission = false;
  bool _presenting = false;

  Future<void> checkAndPresent(
    BuildContext context, {
    bool manual = false,
  }) async {
    if (!pilotEnabled || _presenting) return;
    if (!manual &&
        _lastCheck != null &&
        _now().difference(_lastCheck!) < cooldown) {
      return;
    }
    _lastCheck = _now();
    PilotUpdateCheck check;
    try {
      check = await service.check();
    } on PilotUpdateException catch (error) {
      if (manual && context.mounted) _message(context, error.message);
      return;
    } on PlatformException catch (error) {
      if (manual && context.mounted) {
        _message(context, error.message ?? 'Update check is unavailable.');
      }
      return;
    }
    if (!context.mounted) return;
    if (check.state != PilotUpdateCheckState.available) {
      if (manual) {
        _message(
          context,
          check.state == PilotUpdateCheckState.current
              ? 'Fleet AI Systems Pilot is up to date.'
              : 'The private update server is unavailable. Try again later.',
        );
      }
      return;
    }
    _presenting = true;
    try {
      await _presentRelease(context, check.release!, check.installed);
    } finally {
      _presenting = false;
    }
  }

  Future<void> _presentRelease(
    BuildContext context,
    PilotRelease release,
    PilotInstalledApp installed,
  ) async {
    while (true) {
      if (!context.mounted) return;
      final accepted = await showDialog<bool>(
        context: context,
        barrierDismissible: !release.mandatory,
        builder: (dialogContext) => PopScope(
          canPop: !release.mandatory,
          child: AlertDialog(
            title: Text(
              release.mandatory
                  ? 'Update required'
                  : 'Fleet AI Systems update available',
            ),
            content: Text(
              '${release.mandatory ? 'This version of Fleet AI Systems must be updated before continuing.\n\n' : ''}'
              'Current\n${installed.versionName} (build ${installed.versionCode})\n\n'
              'Available\n${release.versionName} (build ${release.versionCode})',
            ),
            actions: [
              if (!release.mandatory)
                TextButton(
                  onPressed: () => Navigator.pop(dialogContext, false),
                  child: const Text('LATER'),
                ),
              FilledButton(
                onPressed: () => Navigator.pop(dialogContext, true),
                child: const Text('UPDATE NOW'),
              ),
            ],
          ),
        ),
      );
      if (accepted != true || !context.mounted) return;
      final cancellation = PilotDownloadCancellation();
      final result = await showDialog<Object>(
        context: context,
        barrierDismissible: false,
        builder: (_) => _PilotDownloadDialog(
          service: service,
          release: release,
          cancellation: cancellation,
        ),
      );
      if (!context.mounted) return;
      if (result is PilotValidatedApk) {
        await _requestInstallation(context, result);
        return;
      }
      if (result is PilotUpdateException) {
        if (!release.mandatory && result.code == 'DOWNLOAD_CANCELLED') return;
        final retry = await _showRetry(context, result, release.mandatory);
        if (retry != true) return;
      }
    }
  }

  Future<bool?> _showRetry(
    BuildContext context,
    PilotUpdateException error,
    bool mandatory,
  ) => showDialog<bool>(
    context: context,
    barrierDismissible: !mandatory,
    builder: (dialogContext) => PopScope(
      canPop: !mandatory,
      child: AlertDialog(
        title: const Text('Update not installed'),
        content: Text(
          '${error.message}\n\nCheck the private connection and retry.',
        ),
        actions: [
          if (!mandatory)
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('CLOSE'),
            ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('TRY AGAIN'),
          ),
        ],
      ),
    ),
  );

  Future<void> _requestInstallation(
    BuildContext context,
    PilotValidatedApk apk,
  ) async {
    _pendingInstall = apk;
    if (await service.install(apk) == PilotInstallDisposition.launched) {
      _waitingForInstallPermission = false;
      return;
    }
    _waitingForInstallPermission = true;
    if (!context.mounted) return;
    final open = await showDialog<bool>(
      context: context,
      barrierDismissible: !apk.release.mandatory,
      builder: (dialogContext) => PopScope(
        canPop: !apk.release.mandatory,
        child: AlertDialog(
          title: const Text('Allow Pilot updates'),
          content: const Text(
            'Android must allow Fleet AI Systems Pilot to install this private '
            'update. Open “Install unknown apps”, allow this app, then return. '
            'Android will still show its normal installer confirmation.',
          ),
          actions: [
            if (!apk.release.mandatory)
              TextButton(
                onPressed: () => Navigator.pop(dialogContext, false),
                child: const Text('LATER'),
              ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('OPEN SETTINGS'),
            ),
          ],
        ),
      ),
    );
    if (open == true) await service.platform.openUnknownSourcesSettings();
  }

  Future<void> resumePendingInstall(BuildContext context) async {
    final pending = _pendingInstall;
    if (!pilotEnabled || pending == null || _presenting) return;
    final installed = await service.platform.installedApp();
    if (installed.versionCode >= pending.release.versionCode) {
      _pendingInstall = null;
      _waitingForInstallPermission = false;
      await File(pending.path).delete().catchError((_) => File(pending.path));
      return;
    }
    if (_waitingForInstallPermission &&
        await service.install(pending) == PilotInstallDisposition.launched) {
      _waitingForInstallPermission = false;
      return;
    }
    if (!pending.release.mandatory || !context.mounted) return;
    _presenting = true;
    try {
      final retry = await showDialog<bool>(
        context: context,
        barrierDismissible: false,
        builder: (dialogContext) => PopScope(
          canPop: false,
          child: AlertDialog(
            title: const Text('Update required'),
            content: const Text(
              'The Android installer was closed before the required update '
              'finished. Tap UPDATE NOW to try again.',
            ),
            actions: [
              FilledButton(
                onPressed: () => Navigator.pop(dialogContext, true),
                child: const Text('UPDATE NOW'),
              ),
            ],
          ),
        ),
      );
      if (retry == true && context.mounted) {
        await _requestInstallation(context, pending);
      }
    } finally {
      _presenting = false;
    }
  }

  static void _message(BuildContext context, String text) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(text)));
  }
}

class PilotUpdateGate extends StatefulWidget {
  const PilotUpdateGate({
    required this.controller,
    required this.child,
    super.key,
  });

  final PilotUpdateController controller;
  final Widget child;

  @override
  State<PilotUpdateGate> createState() => _PilotUpdateGateState();
}

class _PilotUpdateGateState extends State<PilotUpdateGate>
    with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) unawaited(widget.controller.checkAndPresent(context));
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(widget.controller.resumePendingInstall(context));
      unawaited(widget.controller.checkAndPresent(context));
    }
  }

  @override
  Widget build(BuildContext context) => widget.child;
}

class _PilotDownloadDialog extends StatefulWidget {
  const _PilotDownloadDialog({
    required this.service,
    required this.release,
    required this.cancellation,
  });

  final PilotUpdateService service;
  final PilotRelease release;
  final PilotDownloadCancellation cancellation;

  @override
  State<_PilotDownloadDialog> createState() => _PilotDownloadDialogState();
}

class _PilotDownloadDialogState extends State<_PilotDownloadDialog> {
  double? _progress;

  @override
  void initState() {
    super.initState();
    unawaited(_download());
  }

  Future<void> _download() async {
    Object result;
    try {
      result = await widget.service.downloadAndValidate(
        widget.release,
        cancellation: widget.cancellation,
        onProgress: (received, total) {
          if (!mounted) return;
          setState(() {
            _progress = total == null || total <= 0 ? null : received / total;
          });
        },
      );
    } on PilotUpdateException catch (error) {
      result = error;
    }
    if (mounted) Navigator.pop(context, result);
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      child: AlertDialog(
        title: const Text('Downloading Pilot update'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            LinearProgressIndicator(value: _progress),
            const SizedBox(height: 12),
            Text(
              _progress == null
                  ? 'Downloading securely…'
                  : '${(_progress! * 100).clamp(0, 100).round()}%',
            ),
          ],
        ),
        actions: [
          if (!widget.release.mandatory)
            TextButton(
              onPressed: widget.cancellation.cancel,
              child: const Text('CANCEL'),
            ),
        ],
      ),
    );
  }
}
