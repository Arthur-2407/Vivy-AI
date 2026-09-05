package com.vivy.node.discovery

import android.content.Context
import android.content.pm.PackageManager
import android.os.BatteryManager
import android.os.Build
import android.app.ActivityManager

class NodeCapabilityDetector(private val context: Context) {
    fun detectCapabilities(): Map<String, Any> {
        val pm = context.packageManager
        val am = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val memInfo = ActivityManager.MemoryInfo()
        am.getMemoryInfo(memInfo)

        val bm = context.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
        val batteryPct = bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)

        val hasCamera = pm.hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY)
        val hasMic = pm.hasSystemFeature(PackageManager.FEATURE_MICROPHONE)
        val hasGps = pm.hasSystemFeature(PackageManager.FEATURE_LOCATION_GPS)
        val hasBluetooth = pm.hasSystemFeature(PackageManager.FEATURE_BLUETOOTH)

        return mapOf(
            "cpu_cores" to Runtime.getRuntime().availableProcessors(),
            "ram_mb" to (memInfo.totalMem / (1024 * 1024)).toInt(),
            "gpu_available" to false, // Android apps usually don't expose direct CUDA/Vulkan compute to Python backends easily
            "camera_available" to hasCamera,
            "mic_available" to hasMic,
            "speaker_available" to true,
            "display_available" to true,
            "gps_available" to hasGps,
            "bluetooth_available" to hasBluetooth,
            "battery_pct" to batteryPct.toDouble(),
            "performance_class" to if (memInfo.totalMem > 4L * 1024 * 1024 * 1024) "medium" else "low",
            "metadata" to mapOf(
                "device_model" to Build.MODEL,
                "os_version" to Build.VERSION.RELEASE
            )
        )
    }

    fun getCapabilityList(): List<String> {
        val caps = mutableListOf<String>()
        val hw = detectCapabilities()
        if (hw["camera_available"] == true) {
            caps.addAll(listOf("vision.stream", "vision.face", "vision.emotion", "vision.gaze"))
        }
        if (hw["mic_available"] == true) {
            caps.addAll(listOf("audio.stream", "audio.stt"))
        }
        caps.add("audio.tts")
        caps.add("display.avatar")
        if (hw["gps_available"] == true) {
            caps.addAll(listOf("gps.read", "gps.update"))
        }
        return caps
    }
}
