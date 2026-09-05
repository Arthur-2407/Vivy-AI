package com.vivy.node.discovery

import android.content.Context
import com.vivy.node.connection.HubConnectionManager
import com.vivy.node.security.CredentialManager
import com.vivy.node.transport.TransportManager

class DiscoveryManager(context: Context, connectionManager: HubConnectionManager, credentialManager: CredentialManager) {
    
    private val transportManager = TransportManager(context, connectionManager, credentialManager)

    fun startDiscovery() {
        transportManager.discoverAndConnect()
    }

    fun stopDiscovery() {
        transportManager.stopDiscovery()
    }
}
