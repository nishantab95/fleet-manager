import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:uuid/uuid.dart';

import '../domain/driver_models.dart';

class SecureSessionStore {
  SecureSessionStore({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  static const _sessionKey = 'fleet_manager_driver_session';
  static const _installationKey = 'fleet_manager_installation_id';
  final FlutterSecureStorage _storage;

  Future<void> save(SessionTokens tokens) {
    return _storage.write(key: _sessionKey, value: jsonEncode(tokens.toJson()));
  }

  Future<SessionTokens?> read() async {
    final encoded = await _storage.read(key: _sessionKey);
    if (encoded == null) return null;
    try {
      return SessionTokens.fromJson(
        jsonDecode(encoded) as Map<String, dynamic>,
      );
    } on Object {
      await clear();
      return null;
    }
  }

  Future<void> clear() => _storage.delete(key: _sessionKey);

  Future<String> installationIdentifier() async {
    final existing = await _storage.read(key: _installationKey);
    if (existing != null && existing.isNotEmpty) return existing;
    final created = const Uuid().v4();
    await _storage.write(key: _installationKey, value: created);
    return created;
  }
}
