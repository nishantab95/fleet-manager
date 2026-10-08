plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Signing credentials are loaded from the user's Gradle configuration, never this repository.
val pilotSigningStoreFile = providers.gradleProperty("fleetPilotStoreFile").orNull
val pilotSigningStorePassword = providers.gradleProperty("fleetPilotStorePassword").orNull
val pilotSigningKeyAlias = providers.gradleProperty("fleetPilotKeyAlias").orNull
val pilotSigningKeyPassword = providers.gradleProperty("fleetPilotKeyPassword").orNull

android {
    namespace = "com.fleetmanager.fleet_manager_mobile"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    signingConfigs {
        create("fleetPilotRelease") {
            if (pilotSigningStoreFile != null) {
                storeFile = file(pilotSigningStoreFile)
            }
            storePassword = pilotSigningStorePassword
            keyAlias = pilotSigningKeyAlias
            keyPassword = pilotSigningKeyPassword
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.fleetmanager.fleet_manager_mobile"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        manifestPlaceholders["appLabel"] = "Fleet Manager"
        manifestPlaceholders["usesCleartextTraffic"] = "false"
    }

    flavorDimensions += "environment"
    productFlavors {
        create("pilot") {
            dimension = "environment"
            applicationIdSuffix = ".pilot"
            versionNameSuffix = "-pilot"
            manifestPlaceholders["appLabel"] = "Fleet Manager Pilot"
            manifestPlaceholders["usesCleartextTraffic"] = "true"
        }
        create("production") {
            dimension = "environment"
            manifestPlaceholders["appLabel"] = "Fleet Manager"
            manifestPlaceholders["usesCleartextTraffic"] = "false"
        }
    }

    buildTypes {
        release {
            // TODO: Add your own signing config for the release build.
            // Signing with the debug keys for now, so `flutter run --release` works.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

// Keep production signing behavior unchanged; only Pilot release builds use the
// permanent Fleet Pilot signing identity. Missing credentials never fall back to debug.
androidComponents {
    onVariants(selector().withFlavor("environment" to "pilot").withBuildType("release")) { variant ->
        variant.signingConfig?.setConfig(android.signingConfigs.getByName("fleetPilotRelease"))
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
