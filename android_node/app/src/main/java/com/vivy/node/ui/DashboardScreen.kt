package com.vivy.node.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.vivy.node.connection.ConnectionState
import com.vivy.node.connection.HubConnectionManager
import com.vivy.node.discovery.DiscoveryManager
import com.vivy.node.security.CredentialManager
import com.vivy.node.camera.CameraCaptureManager

@Composable
fun DashboardScreen(
    connectionManager: HubConnectionManager,
    discoveryManager: DiscoveryManager,
    credentialManager: CredentialManager,
    cameraCaptureManager: CameraCaptureManager
) {
    val state by connectionManager.state.collectAsState()
    val pairingCode by connectionManager.pairingCode.collectAsState()
    val hubAddress by connectionManager.hubAddress.collectAsState()
    val activeTransport by connectionManager.activeTransportName.collectAsState()
    val latency by connectionManager.latency.collectAsState()

    var pinInput by remember { mutableStateOf("") }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(text = "VIVY NODE", style = MaterialTheme.typography.headlineMedium)
        Spacer(modifier = Modifier.height(24.dp))

        Text(text = "Status: $state")
        if (activeTransport != null && state == ConnectionState.CONNECTED) {
            Text(text = "Transport: $activeTransport")
        }
        Text(text = "Device ID: ${credentialManager.getDeviceId()}")

        Spacer(modifier = Modifier.height(16.dp))

        if (hubAddress != null) {
            Text(text = "Hub: $hubAddress")
        }

        if (state == ConnectionState.CONNECTED) {
            Text(text = "Latency: $latency ms")
            Spacer(modifier = Modifier.height(16.dp))
            Button(onClick = { connectionManager.disconnect() }) {
                Text("Disconnect")
            }
        } else if (state == ConnectionState.PAIRING_REQUIRED) {
            Spacer(modifier = Modifier.height(16.dp))
            Text(text = "Enter Vivy PIN (shown on PC):")
            if (pairingCode != null) {
                Text(text = "(Debug PIN: $pairingCode)")
            }
            OutlinedTextField(
                value = pinInput,
                onValueChange = { pinInput = it },
                label = { Text("PIN") }
            )
            Spacer(modifier = Modifier.height(8.dp))
            Button(onClick = { 
                connectionManager.sendPairingResponse(pinInput)
                pinInput = ""
            }) {
                Text("Connect")
            }
        } else if (state == ConnectionState.DISCOVERING || state == ConnectionState.TRANSPORT_SWITCHING) {
            Spacer(modifier = Modifier.height(16.dp))
            CircularProgressIndicator()
            Spacer(modifier = Modifier.height(8.dp))
            if (state == ConnectionState.TRANSPORT_SWITCHING) {
                Text("Switching transport (Fast Reconnect/Fallback)...")
            } else {
                Text("Searching local network...")
            }
        } else if (state == ConnectionState.DISCOVERY_FAILED) {
            Spacer(modifier = Modifier.height(16.dp))
            Text("No Vivy Hub found.", color = MaterialTheme.colorScheme.error)
            Spacer(modifier = Modifier.height(8.dp))
            Button(onClick = { discoveryManager.startDiscovery() }) {
                Text("Retry Discovery")
            }
        } else if (state == ConnectionState.CONNECTING) {
            Spacer(modifier = Modifier.height(16.dp))
            CircularProgressIndicator()
            Spacer(modifier = Modifier.height(8.dp))
            Text("Connecting to Hub...")
        } else if (state == ConnectionState.CONNECTION_FAILED) {
            Spacer(modifier = Modifier.height(16.dp))
            Text("Connection Failed.", color = MaterialTheme.colorScheme.error)
            Spacer(modifier = Modifier.height(8.dp))
            Button(onClick = { discoveryManager.startDiscovery() }) {
                Text("Retry Connection")
            }
        } else if (state == ConnectionState.AUTHENTICATING) {
            Spacer(modifier = Modifier.height(16.dp))
            CircularProgressIndicator()
            Spacer(modifier = Modifier.height(8.dp))
            Text("Authenticating...")
        } else if (state == ConnectionState.AUTH_FAILED) {
            Spacer(modifier = Modifier.height(16.dp))
            Text("Authentication Failed (Invalid PIN).", color = MaterialTheme.colorScheme.error)
            Spacer(modifier = Modifier.height(8.dp))
            Button(onClick = { discoveryManager.startDiscovery() }) {
                Text("Start Over")
            }
        } else if (state == ConnectionState.DISCONNECTED) {
            Spacer(modifier = Modifier.height(16.dp))
            Button(onClick = { discoveryManager.startDiscovery() }) {
                Text("Discover Hub")
            }
        }
    }
}
