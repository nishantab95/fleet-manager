import 'package:flutter/material.dart';

import 'app.dart';
import 'data/api_client.dart';
import 'data/local_database.dart';
import 'data/secure_session_store.dart';
import 'data/sync_engine.dart';
import 'domain/role_models.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final sessionStore = SecureSessionStore();
  final api = ApiClient();
  if (isPilotBuild) {
    final pilotBaseUrl = await sessionStore.readPilotBaseUrl();
    if (pilotBaseUrl != null && pilotBaseUrl.isNotEmpty) {
      try {
        api.setBaseUrl(pilotBaseUrl);
      } on FormatException {
        // Ignore a stale/invalid local setting and keep the compile-time default.
      }
    }
  }
  final tokens = await sessionStore.read();
  if (tokens != null) api.setSession(tokens);
  final installationIdentifier = await sessionStore.installationIdentifier();
  final database = await openLocalDatabase();
  final sync = SyncEngine(
    database: database,
    remote: api,
    installationIdentifier: installationIdentifier,
    refreshSession: () async {
      final refreshed = await api.refreshSession();
      await sessionStore.save(refreshed);
    },
  );
  runApp(
    FleetManagerApp(
      dependencies: DriverAppDependencies(
        api: api,
        sessionStore: sessionStore,
        sync: sync,
        installationIdentifier: installationIdentifier,
      ),
    ),
  );
}
