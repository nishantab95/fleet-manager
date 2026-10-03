package com.fleetmanager.fleet_manager_mobile

import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.security.MessageDigest

class MainActivity : FlutterActivity() {
    private val updateChannel = "fleet_manager/pilot_update"
    private val pilotPackage = "com.fleetmanager.fleet_manager_mobile.pilot"

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, updateChannel)
            .setMethodCallHandler { call, result ->
                try {
                    requirePilotBuild()
                    handleUpdateCall(call, result)
                } catch (error: Exception) {
                    result.error("PILOT_UPDATE_FAILED", error.message, null)
                }
            }
    }

    private fun requirePilotBuild() {
        check(packageName == pilotPackage) {
            "Private APK updates are available only in the Pilot flavor."
        }
    }

    private fun handleUpdateCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "installedApp" -> result.success(packageMap(packageManager.getPackageInfo(packageName, 0)))
            "inspectArchive" -> {
                val apk = privateApk(call.argument<String>("path"))
                val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    PackageManager.GET_SIGNING_CERTIFICATES
                } else {
                    @Suppress("DEPRECATION")
                    PackageManager.GET_SIGNATURES
                }
                val info = packageManager.getPackageArchiveInfo(apk.path, flags)
                    ?: error("Android could not parse the downloaded APK.")
                result.success(packageMap(info) + mapOf("signerSha256" to signerSha256(info)))
            }
            "canRequestPackageInstalls" -> result.success(
                Build.VERSION.SDK_INT < Build.VERSION_CODES.O ||
                    packageManager.canRequestPackageInstalls()
            )
            "openUnknownSourcesSettings" -> {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    startActivity(
                        Intent(
                            Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                            Uri.parse("package:$packageName"),
                        )
                    )
                }
                result.success(null)
            }
            "launchInstaller" -> {
                val apk = privateApk(call.argument<String>("path"))
                val contentUri = FileProvider.getUriForFile(
                    this,
                    "$packageName.fileprovider",
                    apk,
                )
                val intent = Intent(Intent.ACTION_VIEW).apply {
                    setDataAndType(contentUri, "application/vnd.android.package-archive")
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                check(intent.resolveActivity(packageManager) != null) {
                    "No Android package installer is available."
                }
                startActivity(intent)
                result.success(null)
            }
            else -> result.notImplemented()
        }
    }

    private fun privateApk(rawPath: String?): File {
        val apk = File(rawPath ?: error("APK path is missing.")).canonicalFile
        val cache = cacheDir.canonicalFile
        check(apk.path.startsWith(cache.path + File.separator) && apk.isFile && apk.extension == "apk") {
            "The APK must be an app-private cache file."
        }
        return apk
    }

    private fun packageMap(info: PackageInfo): Map<String, Any> = mapOf(
        "packageName" to info.packageName,
        "versionName" to (info.versionName ?: ""),
        "versionCode" to if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            info.longVersionCode
        } else {
            @Suppress("DEPRECATION")
            info.versionCode.toLong()
        },
    )

    private fun signerSha256(info: PackageInfo): String {
        val signatures = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            info.signingInfo?.apkContentsSigners
        } else {
            @Suppress("DEPRECATION")
            info.signatures
        } ?: error("The APK has no signing certificate.")
        check(signatures.size == 1) { "The APK signer set is not supported." }
        return MessageDigest.getInstance("SHA-256")
            .digest(signatures[0].toByteArray())
            .joinToString("") { "%02x".format(it) }
    }
}
