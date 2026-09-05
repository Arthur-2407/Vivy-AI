package com.vivy.node

import android.Manifest
import android.content.pm.PackageManager
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

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val cameraGranted = permissions[Manifest.permission.CAMERA] ?: false
        val audioGranted = permissions[Manifest.permission.RECORD_AUDIO] ?: false
        
        if (cameraGranted) {
            startSystems(audioGranted)
        }
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

        val cameraPermission = ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
        val audioPermission = ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)

        if (cameraPermission == PackageManager.PERMISSION_GRANTED && audioPermission == PackageManager.PERMISSION_GRANTED) {
            startSystems(true)
        } else {
            requestPermissionLauncher.launch(arrayOf(Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO))
        }
    }

    private fun startSystems(audioGranted: Boolean) {
        discoveryManager.startDiscovery()
        cameraCaptureManager.startCamera()
        if (audioGranted) {
            audioStreamManager.startStreaming()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        discoveryManager.stopDiscovery()
        audioStreamManager.stopStreaming()
        connectionManager.disconnect()
    }
}
