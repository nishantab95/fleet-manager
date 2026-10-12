import 'package:local_auth/local_auth.dart';

enum DeviceAuthenticationResult { authenticated, cancelled, unavailable }

abstract interface class DeviceAuthenticator {
  Future<DeviceAuthenticationResult> authenticate();
}

class SystemDeviceAuthenticator implements DeviceAuthenticator {
  SystemDeviceAuthenticator({LocalAuthentication? localAuthentication})
    : _localAuthentication = localAuthentication ?? LocalAuthentication();

  final LocalAuthentication _localAuthentication;

  @override
  Future<DeviceAuthenticationResult> authenticate() async {
    try {
      if (!await _localAuthentication.isDeviceSupported()) {
        return DeviceAuthenticationResult.unavailable;
      }
      final authenticated = await _localAuthentication.authenticate(
        localizedReason: 'Unlock Fleet AI Systems',
        biometricOnly: false,
        persistAcrossBackgrounding: true,
        sensitiveTransaction: true,
      );
      return authenticated
          ? DeviceAuthenticationResult.authenticated
          : DeviceAuthenticationResult.cancelled;
    } on LocalAuthException {
      return DeviceAuthenticationResult.unavailable;
    }
  }
}
