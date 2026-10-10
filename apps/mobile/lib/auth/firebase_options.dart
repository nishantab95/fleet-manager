import 'package:firebase_core/firebase_core.dart';

/// Non-secret Firebase Android identifiers supplied at build time.
///
/// Prefer `flutterfire configure` for a real environment. This checked-in
/// adapter keeps automated builds credential-free and fails closed when the
/// required values were not supplied.
abstract final class FleetFirebaseOptions {
  static const apiKey = String.fromEnvironment('FIREBASE_ANDROID_API_KEY');
  static const appId = String.fromEnvironment('FIREBASE_ANDROID_APP_ID');
  static const messagingSenderId = String.fromEnvironment(
    'FIREBASE_MESSAGING_SENDER_ID',
  );
  static const projectId = String.fromEnvironment('FIREBASE_PROJECT_ID');

  static bool get isConfigured =>
      apiKey.isNotEmpty &&
      appId.isNotEmpty &&
      messagingSenderId.isNotEmpty &&
      projectId.isNotEmpty;

  static FirebaseOptions get android {
    if (!isConfigured) {
      throw StateError('Firebase Android configuration is missing.');
    }
    return const FirebaseOptions(
      apiKey: apiKey,
      appId: appId,
      messagingSenderId: messagingSenderId,
      projectId: projectId,
    );
  }
}
