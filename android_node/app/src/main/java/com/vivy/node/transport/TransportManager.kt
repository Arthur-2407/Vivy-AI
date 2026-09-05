package com.vivy.node.transport

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.util.Log
import com.vivy.node.connection.ConnectionState
import com.vivy.node.connection.HubConnectionManager
import com.vivy.node.security.CredentialManager
import kotlinx.coroutines.*
import java.net.InetSocketAddress
import java.net.Socket
import kotlinx.coroutines.flow.collectLatest

class TransportManager(
    private val context: Context,
    private val connectionManager: HubConnectionManager,
    private val credentialManager: CredentialManager
) {
    private val nsdManager = context.getSystemService(Context.NSD_SERVICE) as NsdManager
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var discoveryJob: Job? = null
    private var currentDiscoveryListener: NsdManager.DiscoveryListener? = null

    init {
        scope.launch {
            connectionManager.state.collectLatest { state ->
                if (state == ConnectionState.CONNECTED) {
                    // On successful connect and auth, save the endpoint
                    val currentHost = connectionManager.hubAddress.value?.split("://")?.getOrNull(1)?.substringBefore(":")
                    val currentPort = connectionManager.hubAddress.value?.substringAfterLast(":")?.toIntOrNull()
                    if (currentHost != null && currentPort != null) {
                        credentialManager.saveLastEndpoint(currentHost, currentPort)
                    }
                }
            }
        }
    }

    fun discoverAndConnect() {
        if (discoveryJob?.isActive == true) return
        
        connectionManager.setDiscovering()
        
        discoveryJob = scope.launch {
            Log.i("TransportManager", "Starting discovery sequence...")
            
            // 1. Try Cached Endpoint Fast-Reconnect
            val lastEndpoint = credentialManager.getLastEndpoint()
            if (lastEndpoint != null) {
                val (host, port) = lastEndpoint
                Log.i("TransportManager", "Found cached endpoint: $host:$port. Probing...")
                if (probePort(host, port, 2000)) {
                    Log.i("TransportManager", "Cached endpoint is reachable! Fast-reconnecting.")
                    withContext(Dispatchers.Main) {
                        connectionManager.connect(host, port, WiFiTransport())
                    }
                    return@launch
                } else {
                    Log.w("TransportManager", "Cached endpoint unreachable. Falling back to mDNS.")
                }
            }
            
            // 2. Fallbacks: mDNS, BLE, UDP (run concurrently)
            val discoveryDeferred = CompletableDeferred<Pair<String, Int>?>()
            
            val bleDiscovery = com.vivy.node.discovery.BleDiscovery(context) { ip, port ->
                Log.i("TransportManager", "Found via BLE: $ip:$port")
                discoveryDeferred.complete(Pair(ip, port))
            }
            val udpDiscovery = com.vivy.node.discovery.UdpDiscovery { ip, port ->
                Log.i("TransportManager", "Found via UDP: $ip:$port")
                discoveryDeferred.complete(Pair(ip, port))
            }
            
            bleDiscovery.startScan()
            udpDiscovery.startListening()
            
            val newListener = object : NsdManager.DiscoveryListener {
                override fun onDiscoveryStarted(regType: String) {}
                override fun onServiceFound(service: NsdServiceInfo) {
                    if (service.serviceType.contains("_vivy._tcp")) {
                        nsdManager.resolveService(service, object : NsdManager.ResolveListener {
                            override fun onResolveFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {}
                            override fun onServiceResolved(serviceInfo: NsdServiceInfo) {
                                val host = serviceInfo.host?.hostAddress
                                val port = serviceInfo.port
                                if (host != null) {
                                    discoveryDeferred.complete(Pair(host, port))
                                }
                            }
                        })
                    }
                }
                override fun onServiceLost(service: NsdServiceInfo) {}
                override fun onDiscoveryStopped(serviceType: String) {}
                override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
                    // Don't fail the whole deferred, other methods might succeed
                }
                override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {
                    nsdManager.stopServiceDiscovery(this)
                }
            }
            
            currentDiscoveryListener = newListener
            try {
                nsdManager.discoverServices("_vivy._tcp.", NsdManager.PROTOCOL_DNS_SD, newListener)
            } catch (e: Exception) {
                // Ignore
            }
            
            // Wait for any discovery method with a 30 second timeout
            try {
                val result = withTimeout(30000) { discoveryDeferred.await() }
                if (result != null) {
                    Log.i("TransportManager", "Discovery successful: ${result.first}:${result.second}")
                    withContext(Dispatchers.Main) {
                        connectionManager.connect(result.first, result.second, WiFiTransport())
                    }
                } else {
                    handleDiscoveryFailed()
                }
            } catch (e: TimeoutCancellationException) {
                Log.w("TransportManager", "Discovery timed out after 30 seconds.")
                handleDiscoveryFailed()
            } finally {
                bleDiscovery.stopScan()
                udpDiscovery.stopListening()
                stopMdns()
            }
        }
    }

    private suspend fun handleDiscoveryFailed() {
        withContext(Dispatchers.Main) {
            connectionManager.setDiscoveryFailed()
        }
    }

    fun stopDiscovery() {
        discoveryJob?.cancel()
        // MDNS is stopped by cancellation of the launch block via finally, but to be safe:
        stopMdns()
    }

    private fun stopMdns() {
        currentDiscoveryListener?.let {
            try {
                nsdManager.stopServiceDiscovery(it)
            } catch (e: Exception) {
                // Ignore
            }
            currentDiscoveryListener = null
        }
    }

    private fun probePort(host: String, port: Int, timeoutMs: Int): Boolean {
        return try {
            val socket = Socket()
            socket.connect(InetSocketAddress(host, port), timeoutMs)
            socket.close()
            true
        } catch (e: Exception) {
            false
        }
    }
}
