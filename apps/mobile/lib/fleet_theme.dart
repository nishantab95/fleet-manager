import 'package:flutter/material.dart';

abstract final class FleetColors {
  static const deepGreen = Color(0xFF164C45);
  static const deepGreenStrong = Color(0xFF103A35);
  static const teal = Color(0xFF28776B);
  static const steel = Color(0xFF526774);
  static const amber = Color(0xFFB47516);
  static const success = Color(0xFF287358);
  static const danger = Color(0xFFB54235);
  static const canvas = Color(0xFFF3F5F2);
  static const surface = Color(0xFFFCFDFB);
  static const outline = Color(0xFFD4DDD8);
  static const outlineVariant = Color(0xFFE5EAE7);
  static const ink = Color(0xFF17211F);
  static const muted = Color(0xFF62716C);
}

abstract final class FleetSpacing {
  static const xs = 4.0;
  static const sm = 8.0;
  static const md = 12.0;
  static const lg = 16.0;
  static const xl = 24.0;
}

abstract final class FleetRadius {
  static const sm = 8.0;
  static const md = 12.0;
  static const lg = 16.0;
}

ThemeData fleetTheme() {
  const scheme = ColorScheme.light(
    primary: FleetColors.deepGreen,
    onPrimary: Colors.white,
    primaryContainer: Color(0xFFDDECE6),
    onPrimaryContainer: FleetColors.deepGreenStrong,
    secondary: FleetColors.steel,
    onSecondary: Colors.white,
    secondaryContainer: Color(0xFFE2EAF0),
    onSecondaryContainer: Color(0xFF263B47),
    tertiary: FleetColors.amber,
    onTertiary: Colors.white,
    tertiaryContainer: Color(0xFFFFEDC4),
    onTertiaryContainer: Color(0xFF684300),
    error: FleetColors.danger,
    onError: Colors.white,
    errorContainer: Color(0xFFFFE5E0),
    onErrorContainer: Color(0xFF74271F),
    surface: FleetColors.surface,
    onSurface: FleetColors.ink,
    onSurfaceVariant: FleetColors.muted,
    outline: FleetColors.outline,
    outlineVariant: Color(0xFFE5EAE7),
  );
  const rounded = RoundedRectangleBorder(
    borderRadius: BorderRadius.all(Radius.circular(FleetRadius.md)),
  );
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: FleetColors.canvas,
    visualDensity: VisualDensity.standard,
    splashFactory: InkSparkle.splashFactory,
    appBarTheme: const AppBarTheme(
      centerTitle: false,
      elevation: 0,
      scrolledUnderElevation: 1,
      backgroundColor: FleetColors.surface,
      foregroundColor: FleetColors.ink,
      surfaceTintColor: Colors.transparent,
    ),
    cardTheme: const CardThemeData(
      elevation: 0,
      color: FleetColors.surface,
      surfaceTintColor: Colors.transparent,
      margin: EdgeInsets.zero,
      shape: rounded,
    ),
    inputDecorationTheme: const InputDecorationTheme(
      filled: true,
      fillColor: FleetColors.surface,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.all(Radius.circular(FleetRadius.sm)),
        borderSide: BorderSide(color: FleetColors.outline),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.all(Radius.circular(FleetRadius.sm)),
        borderSide: BorderSide(color: FleetColors.outline),
      ),
      contentPadding: EdgeInsets.symmetric(horizontal: 14, vertical: 13),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(48, 48),
        shape: rounded,
        textStyle: const TextStyle(fontWeight: FontWeight.w700),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(48, 48),
        shape: rounded,
        side: const BorderSide(color: FleetColors.outline),
        textStyle: const TextStyle(fontWeight: FontWeight.w700),
      ),
    ),
    navigationBarTheme: const NavigationBarThemeData(
      height: 68,
      elevation: 4,
      backgroundColor: FleetColors.surface,
      indicatorColor: Color(0xFFDDECE6),
      labelTextStyle: WidgetStatePropertyAll(
        TextStyle(fontSize: 11, fontWeight: FontWeight.w700),
      ),
    ),
    chipTheme: const ChipThemeData(
      side: BorderSide(color: FleetColors.outline),
      shape: StadiumBorder(),
      labelStyle: TextStyle(fontSize: 12, fontWeight: FontWeight.w700),
    ),
    dividerTheme: const DividerThemeData(color: FleetColors.outlineVariant),
    textTheme: const TextTheme(
      headlineMedium: TextStyle(
        fontWeight: FontWeight.w800,
        letterSpacing: -0.5,
      ),
      headlineSmall: TextStyle(
        fontWeight: FontWeight.w800,
        letterSpacing: -0.35,
      ),
      titleLarge: TextStyle(fontWeight: FontWeight.w700),
      titleMedium: TextStyle(fontWeight: FontWeight.w700),
      labelLarge: TextStyle(fontWeight: FontWeight.w700),
      bodyMedium: TextStyle(height: 1.35),
    ).apply(bodyColor: FleetColors.ink, displayColor: FleetColors.ink),
  );
}
