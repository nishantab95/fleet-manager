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
val playSigningStoreFile = providers.gradleProperty("fleetPlayStoreFile").orNull
val playSigningStorePassword = providers.gradleProperty("fleetPlayStorePassword").orNull
val playSigningKeyAlias = providers.gradleProperty("fleetPlayKeyAlias").orNull
val playSigningKeyPassword = providers.gradleProperty("fleetPlayKeyPassword").orNull
val companyMobileBuild = System.getenv("FLEET_MOBILE_COMPANY_BUILD") == "1"

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
        create("fleetPlayUploadRelease") {
            if (playSigningStoreFile != null) {
                storeFile = file(playSigningStoreFile)
            }
            storePassword = playSigningStorePassword
            keyAlias = playSigningKeyAlias
            keyPassword = playSigningKeyPassword
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
        // Google Play requires new submissions and updates to target Android 16.
        // Keep this explicit so an older local Flutter SDK cannot lower a release.
        targetSdk = 36
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        manifestPlaceholders["appLabel"] = "Fleet AI Systems"
        manifestPlaceholders["usesCleartextTraffic"] = "false"
    }

    flavorDimensions += "environment"
    productFlavors {
        create("pilot") {
            dimension = "environment"
            applicationIdSuffix = ".pilot"
            versionNameSuffix = "-pilot"
            manifestPlaceholders["appLabel"] = if (companyMobileBuild) {
                "Fleet AI Systems"
            } else {
                "Fleet AI Systems Pilot"
            }
            manifestPlaceholders["usesCleartextTraffic"] = "true"
        }
        create("production") {
            dimension = "environment"
            manifestPlaceholders["appLabel"] = "Fleet AI Systems"
            manifestPlaceholders["usesCleartextTraffic"] = "false"
        }
    }

    buildTypes {
        release {
            // Release variants are assigned an explicit protected identity below.
            // A missing identity fails the build instead of falling back to debug.
        }
    }
}

// Pilot and Google Play are separate package/signing boundaries. Never reuse or
// replace the permanent Pilot identity while preparing a Play release.
androidComponents {
    onVariants(selector().withFlavor("environment" to "pilot").withBuildType("release")) { variant ->
        variant.signingConfig?.setConfig(android.signingConfigs.getByName("fleetPilotRelease"))
    }
    onVariants(selector().withFlavor("environment" to "production").withBuildType("release")) { variant ->
        variant.signingConfig?.setConfig(android.signingConfigs.getByName("fleetPlayUploadRelease"))
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
