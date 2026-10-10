import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/services.dart' show appFlavor;

import '../data/api_client.dart';
import '../domain/role_models.dart';

enum FleetAuthMode { pilot, firebase }

const _configuredAuthMode = String.fromEnvironment('FLEET_AUTH_MODE');
const _configuredBuildProfile = String.fromEnvironment('FLEET_BUILD_PROFILE');

FleetAuthMode resolveFleetAuthMode({
  required String configured,
  required bool pilotBuild,
  required bool productionBuild,
}) {
  final normalized = configured.trim().toLowerCase();
  if (productionBuild && normalized == 'pilot') {
    throw StateError('Pilot authentication cannot run in a production build.');
  }
  if (normalized == 'pilot') return FleetAuthMode.pilot;
  if (normalized == 'firebase') return FleetAuthMode.firebase;
  if (normalized.isNotEmpty) {
    throw StateError('FLEET_AUTH_MODE must be pilot or firebase.');
  }
  return pilotBuild ? FleetAuthMode.pilot : FleetAuthMode.firebase;
}

FleetAuthMode get fleetAuthMode => resolveFleetAuthMode(
  configured: _configuredAuthMode,
  pilotBuild: isPilotBuild,
  productionBuild: appFlavor == 'production',
);

bool pilotRuntimeFeaturesEnabled({
  required bool pilotBuild,
  required FleetAuthMode authMode,
}) => pilotBuild && authMode == FleetAuthMode.pilot;

String resolveFirebaseBuildProfile({
  required String configured,
  required bool pilotBuild,
  required FleetAuthMode authMode,
}) {
  final normalized = configured.trim().toLowerCase();
  if (normalized.isEmpty) return '';
  if (normalized != 'firebase-staging' && normalized != 'firebase-company') {
    throw StateError('FLEET_BUILD_PROFILE is not supported.');
  }
  if (!pilotBuild || authMode != FleetAuthMode.firebase) {
    throw StateError(
      'Firebase profiles require the update-compatible Pilot package and Firebase authentication.',
    );
  }
  return normalized;
}

bool resolveFirebaseStagingProfile({
  required String configured,
  required bool pilotBuild,
  required FleetAuthMode authMode,
}) =>
    resolveFirebaseBuildProfile(
      configured: configured,
      pilotBuild: pilotBuild,
      authMode: authMode,
    ) ==
    'firebase-staging';

bool resolveFirebaseCompanyProfile({
  required String configured,
  required bool pilotBuild,
  required FleetAuthMode authMode,
}) =>
    resolveFirebaseBuildProfile(
      configured: configured,
      pilotBuild: pilotBuild,
      authMode: authMode,
    ) ==
    'firebase-company';

bool get isFirebaseStagingBuild => resolveFirebaseStagingProfile(
  configured: _configuredBuildProfile,
  pilotBuild: isPilotBuild,
  authMode: fleetAuthMode,
);

bool get isFirebaseCompanyBuild => resolveFirebaseCompanyProfile(
  configured: _configuredBuildProfile,
  pilotBuild: isPilotBuild,
  authMode: fleetAuthMode,
);

bool privateApkUpdatesEnabled({
  required bool pilotBuild,
  required FleetAuthMode authMode,
  required bool firebaseCompanyBuild,
}) =>
    pilotBuild &&
    (authMode == FleetAuthMode.pilot ||
        (authMode == FleetAuthMode.firebase && firebaseCompanyBuild));

class LoginChallenge {
  const LoginChallenge({
    required this.id,
    this.resendToken,
    this.automaticallyVerified = false,
  });

  final String id;
  final int? resendToken;
  final bool automaticallyVerified;
}

class LoginAuthException implements Exception {
  const LoginAuthException(this.message, {this.code});

  final String message;
  final String? code;

  @override
  String toString() => message;
}

abstract interface class FleetLoginAuthProvider {
  FleetAuthMode get mode;

  Future<LoginChallenge> sendOtp(
    String phone, {
    String? requestedRole,
    bool forceResend = false,
  });

  Future<String> verifyOtp(LoginChallenge challenge, String otp);

  Future<void> signOut();
}

class PilotOtpAuthProvider implements FleetLoginAuthProvider {
  PilotOtpAuthProvider(this.api);

  final ApiClient api;

  @override
  FleetAuthMode get mode => FleetAuthMode.pilot;

  @override
  Future<LoginChallenge> sendOtp(
    String phone, {
    String? requestedRole,
    bool forceResend = false,
  }) async {
    final challengeId = await api.requestOtp(
      phone,
      requestedRole: requestedRole,
    );
    return LoginChallenge(id: challengeId);
  }

  @override
  Future<String> verifyOtp(LoginChallenge challenge, String otp) =>
      api.verifyOtp(challengeId: challenge.id, otp: otp);

  @override
  Future<void> signOut() async {}
}

class FirebasePhoneAuthProvider implements FleetLoginAuthProvider {
  FirebasePhoneAuthProvider(this.api, {FirebaseAuth? firebaseAuth})
    : _firebaseAuth = firebaseAuth ?? FirebaseAuth.instance;

  final ApiClient api;
  final FirebaseAuth _firebaseAuth;
  PhoneAuthCredential? _automaticCredential;
  int? _resendToken;

  @override
  FleetAuthMode get mode => FleetAuthMode.firebase;

  @override
  Future<LoginChallenge> sendOtp(
    String phone, {
    String? requestedRole,
    bool forceResend = false,
  }) async {
    final completer = Completer<LoginChallenge>();
    _automaticCredential = null;
    try {
      await _firebaseAuth.verifyPhoneNumber(
        phoneNumber: phone,
        forceResendingToken: forceResend ? _resendToken : null,
        timeout: const Duration(seconds: 60),
        verificationCompleted: (credential) {
          _automaticCredential = credential;
          if (!completer.isCompleted) {
            completer.complete(
              const LoginChallenge(
                id: 'automatic',
                automaticallyVerified: true,
              ),
            );
          }
        },
        verificationFailed: (error) {
          if (!completer.isCompleted) {
            completer.completeError(_safeFirebaseError(error));
          }
        },
        codeSent: (verificationId, resendToken) {
          _resendToken = resendToken;
          if (!completer.isCompleted) {
            completer.complete(
              LoginChallenge(id: verificationId, resendToken: resendToken),
            );
          }
        },
        codeAutoRetrievalTimeout: (verificationId) {
          if (!completer.isCompleted) {
            completer.complete(
              LoginChallenge(id: verificationId, resendToken: _resendToken),
            );
          }
        },
      );
      return await completer.future;
    } on FirebaseAuthException catch (error) {
      throw _safeFirebaseError(error);
    } on TimeoutException {
      throw const LoginAuthException(
        'Phone verification timed out. Please request a new code.',
        code: 'TIMEOUT',
      );
    } on Object {
      throw const LoginAuthException(
        'Phone authentication is temporarily unavailable. Please try again.',
        code: 'UNAVAILABLE',
      );
    }
  }

  @override
  Future<String> verifyOtp(LoginChallenge challenge, String otp) async {
    final automatic = _automaticCredential;
    final credential =
        automatic ??
        PhoneAuthProvider.credential(
          verificationId: challenge.id,
          smsCode: otp,
        );
    try {
      final result = await _firebaseAuth.signInWithCredential(credential);
      final idToken = await result.user?.getIdToken(true);
      if (idToken == null || idToken.isEmpty) {
        throw const LoginAuthException(
          'Phone verification could not be completed. Please try again.',
          code: 'TOKEN_MISSING',
        );
      }
      return await api.verifyFirebaseToken(idToken);
    } on FirebaseAuthException catch (error) {
      throw _safeFirebaseError(error);
    }
  }

  @override
  Future<void> signOut() => _firebaseAuth.signOut();
}

class UnavailableFirebaseAuthProvider implements FleetLoginAuthProvider {
  const UnavailableFirebaseAuthProvider();

  @override
  FleetAuthMode get mode => FleetAuthMode.firebase;

  @override
  Future<LoginChallenge> sendOtp(
    String phone, {
    String? requestedRole,
    bool forceResend = false,
  }) {
    throw const LoginAuthException(
      'Phone authentication is not configured on this build.',
      code: 'NOT_CONFIGURED',
    );
  }

  @override
  Future<String> verifyOtp(LoginChallenge challenge, String otp) {
    throw const LoginAuthException(
      'Phone authentication is not configured on this build.',
      code: 'NOT_CONFIGURED',
    );
  }

  @override
  Future<void> signOut() async {}
}

LoginAuthException _safeFirebaseError(FirebaseAuthException error) {
  return switch (error.code) {
    'invalid-phone-number' => const LoginAuthException(
      'Enter a valid mobile number.',
      code: 'INVALID_PHONE',
    ),
    'invalid-verification-code' ||
    'missing-verification-code' => const LoginAuthException(
      'The verification code is incorrect.',
      code: 'WRONG_OTP',
    ),
    'session-expired' || 'code-expired' => const LoginAuthException(
      'The verification code has expired. Request a new code.',
      code: 'EXPIRED_OTP',
    ),
    'too-many-requests' => const LoginAuthException(
      'Too many attempts. Please wait before trying again.',
      code: 'TOO_MANY_ATTEMPTS',
    ),
    'quota-exceeded' => const LoginAuthException(
      'SMS service is temporarily unavailable. Please contact your administrator.',
      code: 'SMS_QUOTA',
    ),
    'network-request-failed' => const LoginAuthException(
      'A network connection is required to sign in.',
      code: 'NETWORK_UNAVAILABLE',
    ),
    'web-context-cancelled' ||
    'cancelled-popup-request' => const LoginAuthException(
      'Phone verification was cancelled.',
      code: 'CANCELLED',
    ),
    _ => const LoginAuthException(
      'Phone authentication is temporarily unavailable. Please try again.',
      code: 'FIREBASE_UNAVAILABLE',
    ),
  };
}
