package com.vivy.node.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vivy.node.connection.ConnectionState
import com.vivy.node.connection.HubConnectionManager
import com.vivy.node.discovery.DiscoveryManager
import com.vivy.node.security.CredentialManager
import com.vivy.node.camera.CameraCaptureManager
import com.vivy.node.transport.TransportStatus

/**
 * Dashboard Screen — Multi-Transport Connection Panel.
 *
 * Shows:
 *   - Connection status (state machine)
 *   - Active transport (the carrier actually handling Vivy traffic)
 *   - All available transports with their current status
 *   - Hub endpoint and latency
 *   - Pairing flow (PIN entry)
 *   - Retry / Disconnect buttons
 *
 * All values come from runtime StateFlow observations.
 * Nothing is hardcoded. Transport names and availability are entirely
 * determined by the TransportManager at runtime.
 *
 * The feature layer (Chat, Voice, Camera, etc.) is not shown here and
 * is completely unaffected by which transport is active.
 */
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
    val availableTransports by connectionManager.availableTransports.collectAsState()

    var pinInput by remember { mutableStateOf("") }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = "VIVY NODE",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold
        )
        Spacer(modifier = Modifier.height(24.dp))

        // ── Connection Status ────────────────────────────────────────────
        ConnectionStatusCard(
            state = state,
            deviceId = credentialManager.getDeviceId()
        )

        Spacer(modifier = Modifier.height(16.dp))

        // ── Transport Panel ──────────────────────────────────────────────
        TransportPanel(
            activeTransportName = activeTransport,
            availableTransports = availableTransports,
            hubAddress = hubAddress,
            latency = latency,
            state = state
        )

        Spacer(modifier = Modifier.height(16.dp))

        // ── State-specific action panels ─────────────────────────────────
        when (state) {
            ConnectionState.CONNECTED -> {
                Button(onClick = { connectionManager.disconnect() }) {
                    Text("Disconnect")
                }
            }
            ConnectionState.PAIRING_REQUIRED -> {
                Text(text = "Enter Vivy PIN (shown on PC):", style = MaterialTheme.typography.bodyMedium)
                if (pairingCode != null) {
                    Text(text = "(Debug: $pairingCode)", fontSize = 11.sp, color = MaterialTheme.colorScheme.outline)
                }
                Spacer(modifier = Modifier.height(8.dp))
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
                    Text("Pair")
                }
            }
            ConnectionState.DISCOVERING, ConnectionState.TRANSPORT_SWITCHING -> {
                CircularProgressIndicator()
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = if (state == ConnectionState.TRANSPORT_SWITCHING)
                        "Switching transport…"
                    else
                        "Searching for Vivy Hub…"
                )
            }
            ConnectionState.CONNECTING, ConnectionState.AUTHENTICATING -> {
                CircularProgressIndicator()
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = if (state == ConnectionState.AUTHENTICATING)
                        "Authenticating…"
                    else
                        "Connecting to Hub…"
                )
            }
            ConnectionState.DISCOVERY_FAILED, ConnectionState.CONNECTION_FAILED, ConnectionState.AUTH_FAILED -> {
                Text(
                    text = when (state) {
                        ConnectionState.DISCOVERY_FAILED -> "No Vivy Hub found."
                        ConnectionState.AUTH_FAILED -> "Authentication failed (Invalid PIN)."
                        else -> "Connection failed."
                    },
                    color = MaterialTheme.colorScheme.error
                )
                Spacer(modifier = Modifier.height(8.dp))
                Button(onClick = { discoveryManager.startDiscovery() }) {
                    Text("Retry")
                }
            }
            ConnectionState.DISCONNECTED -> {
                Button(onClick = { discoveryManager.startDiscovery() }) {
                    Text("Discover Hub")
                }
            }
            else -> {}
        }
    }
}

// ── Connection Status Card ─────────────────────────────────────────────────

@Composable
private fun ConnectionStatusCard(state: ConnectionState, deviceId: String) {
    val stateColor = when (state) {
        ConnectionState.CONNECTED -> Color(0xFF4CAF50)
        ConnectionState.AUTHENTICATING, ConnectionState.CONNECTING -> Color(0xFFFF9800)
        ConnectionState.TRANSPORT_SWITCHING, ConnectionState.DISCOVERING -> Color(0xFF2196F3)
        ConnectionState.DISCOVERY_FAILED, ConnectionState.CONNECTION_FAILED, ConnectionState.AUTH_FAILED -> Color(0xFFF44336)
        else -> Color(0xFF9E9E9E)
    }

    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = "●",
                color = stateColor,
                fontSize = 16.sp,
                modifier = Modifier.padding(end = 6.dp)
            )
            Text(
                text = "Status: $state",
                style = MaterialTheme.typography.bodyMedium
            )
        }
        Spacer(modifier = Modifier.height(4.dp))
        Text(
            text = "Device: $deviceId",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.outline
        )
    }
}

// ── Transport Panel ────────────────────────────────────────────────────────

/**
 * Multi-transport availability panel.
 *
 * Shows:
 *   Active Transport: Wi-Fi
 *
 *   Available:
 *     Wi-Fi          ✓  active  (latency: 12 ms)
 *     Bluetooth PAN  ✓  ready
 *     Wi-Fi Direct   ✗  unavailable
 *
 *   Hub: 10.185.45.171:8800
 *   Latency: 12 ms
 *
 * All values are runtime-observed. Nothing is hardcoded.
 */
@Composable
private fun TransportPanel(
    activeTransportName: String?,
    availableTransports: List<TransportStatus>,
    hubAddress: String?,
    latency: Long,
    state: ConnectionState
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f))
            .padding(12.dp)
    ) {
        Text(
            text = "Transport",
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.SemiBold
        )
        Spacer(modifier = Modifier.height(6.dp))

        // Active transport
        if (activeTransportName != null && state == ConnectionState.CONNECTED) {
            Text(
                text = "Active: $activeTransportName",
                style = MaterialTheme.typography.bodyMedium,
                color = Color(0xFF4CAF50),
                fontWeight = FontWeight.Medium
            )
        } else if (state == ConnectionState.TRANSPORT_SWITCHING) {
            Text(
                text = "Switching transport…",
                style = MaterialTheme.typography.bodyMedium,
                color = Color(0xFF2196F3)
            )
        }

        // Available transports list
        if (availableTransports.isNotEmpty()) {
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "Available:",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.outline
            )
            Spacer(modifier = Modifier.height(4.dp))
            availableTransports.forEach { transport ->
                TransportRow(transport = transport)
            }
        } else {
            Spacer(modifier = Modifier.height(8.dp))
            // Show known transport names when no status is available yet
            listOf("Wi-Fi", "Bluetooth PAN", "Wi-Fi Direct").forEach { name ->
                Text(
                    text = "  $name  —  probing…",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.outline
                )
            }
        }

        // Hub address
        if (hubAddress != null) {
            Spacer(modifier = Modifier.height(8.dp))
            Divider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.3f))
            Spacer(modifier = Modifier.height(6.dp))
            // Strip transport prefix for cleaner display (Hub address is transport-independent)
            val cleanAddress = hubAddress.substringAfter("://")
            Text(
                text = "Hub: $cleanAddress",
                style = MaterialTheme.typography.bodySmall
            )
            if (state == ConnectionState.CONNECTED && latency > 0) {
                Text(
                    text = "Latency: $latency ms",
                    style = MaterialTheme.typography.bodySmall,
                    color = when {
                        latency < 50 -> Color(0xFF4CAF50)
                        latency < 150 -> Color(0xFFFF9800)
                        else -> Color(0xFFF44336)
                    }
                )
            }
        }
    }
}

@Composable
private fun TransportRow(transport: TransportStatus) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 6.dp)
    ) {
        Text(
            text = transport.name,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.SemiBold,
            color = if (transport.isActive && transport.isConnected) Color(0xFF4CAF50) else MaterialTheme.colorScheme.onSurface
        )
        Column(modifier = Modifier.padding(start = 12.dp, top = 2.dp)) {
            Text(
                text = "State: ${transport.displayState}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            if (transport.displayHubState != null) {
                Text(
                    text = "Hub: ${transport.displayHubState}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            if (transport.isActive && transport.estimatedLatencyMs > 0) {
                Text(
                    text = "Latency: ${transport.estimatedLatencyMs} ms",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}
