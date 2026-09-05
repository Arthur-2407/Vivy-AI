package com.vivy.node.discovery

import android.content.Context
import com.vivy.node.connection.HubConnectionManager
import com.vivy.node.security.CredentialManager
import com.vivy.node.transport.TransportManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

/**
 * Discovery Manager — thin façade over TransportManager.
 *
 * Wires the failover callback between HubConnectionManager and TransportManager
 * so that transport failures automatically trigger multi-transport failover
 * without creating circular dependencies at construction time.
 */
class DiscoveryManager(
    context: Context,
    val connectionManager: HubConnectionManager,
    credentialManager: CredentialManager
) {
    private val transportManager = TransportManager(context, connectionManager, credentialManager)
    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())

    init {
        // Wire failover: when HubConnectionManager loses its transport,
        // TransportManager.tryFailover() is called to switch to an alternate.
        connectionManager.onTransportLost = { transportManager.tryFailover() }

        // Forward available-transport updates to HubConnectionManager for UI consumption
        scope.launch {
            transportManager.availableTransports.collectLatest { statuses ->
                connectionManager.updateAvailableTransports(statuses)
            }
        }
    }

    fun startDiscovery() {
        transportManager.discoverAndConnect()
    }

    fun stopDiscovery() {
        transportManager.stopDiscovery()
    }

    fun destroy() {
        transportManager.destroy()
    }
}
