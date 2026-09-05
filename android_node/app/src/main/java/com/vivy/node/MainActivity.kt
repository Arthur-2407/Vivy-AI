package com.vivy.node

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.vivy.node.connection.HubConnectionManager
import com.vivy.node.discovery.DiscoveryManager
import com.vivy.node.camera.CameraCaptureManager
import com.vivy.node.camera.AudioStreamManager
import com.vivy.node.security.CredentialManager
import com.vivy.node.ui.MultimodalApp

class MainActivity : ComponentActivity() {

    private lateinit var connectionManager: HubConnectionManager
    private lateinit var discoveryManager: DiscoveryManager
    private lateinit var cameraCaptureManager: CameraCaptureManager
    private lateinit var audioStreamManager: AudioStreamManager
    private lateinit var credentialManager: CredentialManager

    /**
     * Core permissions required before starting any system (camera, audio).
     * Bluetooth and Wi-Fi Direct permissions are requested separately so that
     * a denial does not block Wi-Fi operation.
     */
    private val corePermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val cameraGranted = permissions[Manifest.permission.CAMERA] ?: false
        val audioGranted = permissions[Manifest.permission.RECORD_AUDIO] ?: false

        if (cameraGranted) {
            startSystems(audioGranted)
        }
        // Request Bluetooth + Wi-Fi Direct permissions after core permissions are resolved.
        // Denial here does not block Wi-Fi transport.
        requestWirelessTransportPermissions()
    }

    /**
     * Bluetooth / Wi-Fi Direct permissions.
     * On denial: log, continue without those transports. Wi-Fi is unaffected.
     * Transport availability is determined dynamically — no crash, no blocking.
     */
    private val wirelessPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val btScan = permissions[Manifest.permission.BLUETOOTH_SCAN] ?: false
        val btConnect = permissions[Manifest.permission.BLUETOOTH_CONNECT] ?: false
        // NEARBY_WIFI_DEVICES is used for Wi-Fi Direct on Android 13+
        val nearbyWifi = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions[Manifest.permission.NEARBY_WIFI_DEVICES] ?: false
        } else {
            true // not required on older API
        }
        val fineLocation = permissions[Manifest.permission.ACCESS_FINE_LOCATION] ?: false

        android.util.Log.i(
            "MainActivity",
            "Wireless permissions: BT_SCAN=$btScan BT_CONNECT=$btConnect " +
            "NEARBY_WIFI=$nearbyWifi FINE_LOCATION=$fineLocation — " +
            "TransportManager will skip unavailable transports gracefully."
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        credentialManager = CredentialManager(this)
        connectionManager = HubConnectionManager(credentialManager)
        discoveryManager = DiscoveryManager(this, connectionManager, credentialManager)
        cameraCaptureManager = CameraCaptureManager(this, connectionManager)
        audioStreamManager = AudioStreamManager(connectionManager)

        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    MultimodalApp(connectionManager, discoveryManager, credentialManager, cameraCaptureManager)
                }
            }
        }

        val cameraOk = ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) ==
                PackageManager.PERMISSION_GRANTED
        val audioOk = ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) ==
                PackageManager.PERMISSION_GRANTED

        if (cameraOk && audioOk) {
            startSystems(true)
            requestWirelessTransportPermissions()
        } else {
            corePermissionLauncher.launch(
                arrayOf(Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO)
            )
        }
    }

    /** Start sensor streaming systems. */
    private fun startSystems(audioGranted: Boolean) {
        discoveryManager.startDiscovery()
        cameraCaptureManager.startCamera()
        if (audioGranted) {
            audioStreamManager.startStreaming()
        }
    }

    /**
     * Request Bluetooth and Wi-Fi Direct runtime permissions.
     *
     * Required for:
     *   - BLUETOOTH_SCAN / BLUETOOTH_CONNECT (Android 12+ API 31+)
     *   - ACCESS_FINE_LOCATION (BLE scan pre-API 31; Wi-Fi Direct)
     *   - NEARBY_WIFI_DEVICES (Android 13+ API 33+ for Wi-Fi Direct)
     *
     * Denial is handled gracefully — only those transports are skipped.
     * Wi-Fi transport is not affected by Bluetooth permission state.
     */
    private fun requestWirelessTransportPermissions() {
        val needed = mutableListOf<String>()

        fun needsPerm(perm: String) =
            ContextCompat.checkSelfPermission(this, perm) != PackageManager.PERMISSION_GRANTED

        // Bluetooth (Android 12+ / API 31+)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            if (needsPerm(Manifest.permission.BLUETOOTH_SCAN))
                needed.add(Manifest.permission.BLUETOOTH_SCAN)
            if (needsPerm(Manifest.permission.BLUETOOTH_CONNECT))
                needed.add(Manifest.permission.BLUETOOTH_CONNECT)
        }

        // ACCESS_FINE_LOCATION: required for BLE scan < API 31 and Wi-Fi Direct
        if (needsPerm(Manifest.permission.ACCESS_FINE_LOCATION))
            needed.add(Manifest.permission.ACCESS_FINE_LOCATION)

        // NEARBY_WIFI_DEVICES (Android 13+ / API 33+) for Wi-Fi Direct
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (needsPerm(Manifest.permission.NEARBY_WIFI_DEVICES))
                needed.add(Manifest.permission.NEARBY_WIFI_DEVICES)
        }

        if (needed.isNotEmpty()) {
            wirelessPermissionLauncher.launch(needed.toTypedArray())
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        discoveryManager.stopDiscovery()
        discoveryManager.destroy()
        audioStreamManager.stopStreaming()
        connectionManager.disconnect()
    }
}
