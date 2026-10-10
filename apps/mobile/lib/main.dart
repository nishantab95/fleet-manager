import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';

import 'app.dart';
import 'auth/firebase_options.dart';
import 'auth/login_auth_provider.dart';
import 'data/api_client.dart';
import 'data/local_database.dart';
import 'data/secure_session_store.dart';
import 'data/sync_engine.dart';
import 'domain/role_models.dart';
import 'pilot_update.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final sessionStore = SecureSessionStore();
  final api = ApiClient(persistSession: sessionStore.save);
  FleetLoginAuthProvider loginAuthProvider;
  if (fleetAuthMode == FleetAuthMode.firebase) {
    try {
      await Firebase.initializeApp(options: FleetFirebaseOptions.android);
      loginAuthProvider = FirebasePhoneAuthProvider(api);
    } on Object {
      loginAuthProvider = const UnavailableFirebaseAuthProvider();
    }
  } else {
    loginAuthProvider = PilotOtpAuthProvider(api);
  }
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
  );
  final pilotUpdater = isPilotBuild
      ? PilotUpdateController(
          service: PilotUpdateService(
            baseUrl: () => api.baseUrl,
            platform: const AndroidPilotUpdatePlatform(),
          ),
        )
      : null;
  runApp(
    FleetManagerApp(
      dependencies: DriverAppDependencies(
        api: api,
        sessionStore: sessionStore,
        sync: sync,
        installationIdentifier: installationIdentifier,
        loginAuthProvider: loginAuthProvider,
        pilotUpdater: pilotUpdater,
      ),
    ),
  );
}
