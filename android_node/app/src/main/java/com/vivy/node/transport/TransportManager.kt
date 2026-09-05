package com.vivy.node.transport

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.util.Log
import com.vivy.node.connection.ConnectionState
import com.vivy.node.connection.HubConnectionManager
import com.vivy.node.security.CredentialManager
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.collectLatest
import java.net.InetSocketAddress
import java.net.Socket

/**
 * Multi-Transport Manager.
 *
 * Central authority for transport selection, discovery, scoring, failover,
 * and health monitoring. Sits between the Vivy feature layer and the physical
 * network. The feature layer (Chat, Voice, Camera, Screen, Avatar, RVC, etc.)
 * is completely unaware of which transport is active.
 *
 * Architecture:
 *
 *   Vivy Features
 *       ↓
 *   HubConnectionManager  (session, auth, capability, lease)
 *       ↓
 *   TransportManager      (THIS CLASS — selection, scoring, failover)
 *       ↓
 *   ┌──────────────┬────────────────────┬──────────────────────┐
 *   │ WiFiTransport│ BluetoothPanTransp.│ WifiDirectTransport  │
 *   └──────────────┴────────────────────┴──────────────────────┘
 *       ↓
 *   Existing WebSocket → Vivy Hub → Original Vivy
 *
 * Transport selection rules:
 *   1. Probe all available transports.
 *   2. Score each by: reachability, latency, bandwidth class, stability.
 *   3. Select highest-scoring transport that can reach the Hub.
 *   4. On disconnect: evaluate remaining transports and failover.
 *   5. Reverse migration: if a better transport becomes available, switch.
 *
 * Non-negotiable:
 *   - Never hardcode Wi-Fi priority.
 *   - Never hardcode Bluetooth priority.
 *   - Never hardcode Hub IP or transport choice.
 *   - Transport failure → transport FAILED, not Vivy FAILED.
 *   - Discovery has timeout + fallback. No silent infinite loop.
 *   - Session identity (device_id, session_key) is preserved across switches.
 */
class TransportManager(
    private val context: Context,
    private val connectionManager: HubConnectionManager,
    private val credentialManager: CredentialManager
) {
    private val nsdManager = context.getSystemService(Context.NSD_SERVICE) as NsdManager
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var discoveryJob: Job? = null
    private var healthMonitorJob: Job? = null
    private var currentDiscoveryListener: NsdManager.DiscoveryListener? = null

    /** The currently active transport (carrying Vivy traffic). */
    @Volatile private var activeTransport: Transport? = null

    /** Last known reachable Hub endpoint. Never hardcoded. */
    @Volatile private var lastKnownHost: String? = null
    @Volatile private var lastKnownPort: Int = -1

    /** All transports ordered for evaluation. Score determines selection at runtime. */
    private val allTransports: List<Transport> by lazy {
        listOf(
            WiFiTransport(context),
            BluetoothPanTransport(context),
            WifiDirectTransport(context)
        )
    }

    // ── Observable state for UI ───────────────────────────────────────────

    private val _availableTransports = MutableStateFlow<List<TransportStatus>>(emptyList())
    val availableTransports: StateFlow<List<TransportStatus>> = _availableTransports

    // ── Initialization ────────────────────────────────────────────────────

    init {
        // Save endpoint cache on successful connection
        scope.launch {
            connectionManager.state.collectLatest { state ->
                if (state == ConnectionState.CONNECTED) {
                    val host = lastKnownHost
                    val port = lastKnownPort
                    if (host != null && port > 0) {
                        credentialManager.saveLastEndpoint(host, port)
                    }
                }
                // Emit transport status snapshot on any state change
                emitTransportStatus()
            }
        }

        // Register Wi-Fi Direct receiver
        (allTransports.find { it is WifiDirectTransport } as? WifiDirectTransport)
            ?.registerReceiver()
    }

    // ── Public API ────────────────────────────────────────────────────────

    /**
     * Begin the full discovery and connection sequence.
     * Idempotent — safe to call multiple times.
     */
    fun discoverAndConnect() {
        if (discoveryJob?.isActive == true) return

        connectionManager.setDiscovering()

        discoveryJob = scope.launch {
            Log.i(TAG, "=== Starting multi-transport discovery ===")

            // 1. Fast reconnect via cached endpoint
            val lastEndpoint = credentialManager.getLastEndpoint()
            if (lastEndpoint != null) {
                val (host, port) = lastEndpoint
                Log.i(TAG, "Cached endpoint: $host:$port — probing all transports...")
                val chosen = selectBestTransportForEndpoint(host, port)
                if (chosen != null) {
                    Log.i(TAG, "Fast reconnect via ${chosen.name} to $host:$port")
                    connectVia(chosen, host, port)
                    return@launch
                } else {
                    Log.w(TAG, "Cached endpoint unreachable on all transports. Running discovery.")
                }
            }

            // 2. Run all discovery mechanisms concurrently (mDNS + BLE + UDP)
            val discoveryDeferred = CompletableDeferred<Triple<String, Int, Transport>?>()

            // BLE discovery
            val bleDiscovery = com.vivy.node.discovery.BleDiscovery(context) { ip, port ->
                Log.i(TAG, "BLE bootstrap → $ip:$port")
                scope.launch {
                    val transport = selectBestTransportForEndpoint(ip, port)
                    if (transport != null && !discoveryDeferred.isCompleted) {
                        discoveryDeferred.complete(Triple(ip, port, transport))
                    }
                }
            }

            // UDP discovery
            val udpDiscovery = com.vivy.node.discovery.UdpDiscovery { ip, port ->
                Log.i(TAG, "UDP broadcast → $ip:$port")
                scope.launch {
                    val transport = selectBestTransportForEndpoint(ip, port)
                    if (transport != null && !discoveryDeferred.isCompleted) {
                        discoveryDeferred.complete(Triple(ip, port, transport))
                    }
                }
            }

            // Wi-Fi Direct discovery (non-blocking, results via P2P callbacks)
            val wifiDirectTransport =
                allTransports.find { it is WifiDirectTransport } as? WifiDirectTransport
            wifiDirectTransport?.startDiscovery()

            // mDNS discovery
            val mdnsListener = buildMdnsListener { ip, port ->
                scope.launch {
                    val transport = selectBestTransportForEndpoint(ip, port)
                    if (transport != null && !discoveryDeferred.isCompleted) {
                        discoveryDeferred.complete(Triple(ip, port, transport))
                    }
                }
            }
            currentDiscoveryListener = mdnsListener
            try {
                nsdManager.discoverServices("_vivy._tcp.", NsdManager.PROTOCOL_DNS_SD, mdnsListener)
            } catch (e: Exception) {
                Log.w(TAG, "mDNS start failed: ${e.message}")
            }

            bleDiscovery.startScan()
            udpDiscovery.startListening()

            // Wait with 30-second timeout
            try {
                val result = withTimeout(DISCOVERY_TIMEOUT_MS) { discoveryDeferred.await() }
                if (result != null) {
                    val (ip, port, transport) = result
                    Log.i(TAG, "Discovery → ${transport.name} → $ip:$port")
                    connectVia(transport, ip, port)
                } else {
                    handleDiscoveryFailed()
                }
            } catch (e: TimeoutCancellationException) {
                Log.w(TAG, "Discovery timed out after ${DISCOVERY_TIMEOUT_MS / 1000}s")
                handleDiscoveryFailed()
            } finally {
                bleDiscovery.stopScan()
                udpDiscovery.stopListening()
                stopMdns()
            }
        }
    }

    /**
     * Attempt to failover to the best available alternate transport.
     * Called by HubConnectionManager when the active transport disconnects.
     * Preserves device_id, session_key, and Hub endpoint — no re-pairing
     * unless the Hub explicitly rejects the session key.
     */
    fun tryFailover() {
        val host = lastKnownHost ?: return
        val port = lastKnownPort.takeIf { it > 0 } ?: return

        scope.launch {
            Log.i(TAG, "Transport failover: trying alternate transports for $host:$port")
            connectionManager.setTransportSwitching()
            emitTransportStatus()

            val currentName = activeTransport?.name
            val candidate = selectBestTransportForEndpoint(host, port, excludeName = currentName)

            if (candidate != null) {
                Log.i(TAG, "Failover: switching to ${candidate.name}")
                connectVia(candidate, host, port)
            } else {
                Log.w(TAG, "No alternate transport available. Falling back to full discovery.")
                activeTransport = null
                discoverAndConnect()
            }
        }
    }

    fun stopDiscovery() {
        discoveryJob?.cancel()
        healthMonitorJob?.cancel()
        stopMdns()
    }

    fun destroy() {
        stopDiscovery()
        scope.cancel()
        (allTransports.find { it is WifiDirectTransport } as? WifiDirectTransport)
            ?.unregisterReceiver()
    }

    // ── Transport evaluation ──────────────────────────────────────────────

    /**
     * Probe all available transports against [host]:[port].
     * Returns the transport with the highest score that can actually
     * reach the Hub endpoint, or null if none succeed.
     *
     * [excludeName]: skip the named transport (used during failover to
     *               avoid retrying the transport that just failed).
     */
    private suspend fun selectBestTransportForEndpoint(
        host: String,
        port: Int,
        excludeName: String? = null
    ): Transport? = withContext(Dispatchers.IO) {
        val candidates = allTransports
            .filter { it.name != excludeName && it.isAvailable }
            .sortedByDescending { it.score } // probe best candidates first

        if (candidates.isEmpty()) {
            Log.d(TAG, "No available transport candidates")
            return@withContext null
        }

        Log.d(TAG, "Evaluating ${candidates.size} transport(s): ${candidates.map { it.name }}")

        // For BT PAN, the host IP from discovery may not be the BT PAN gateway;
        // we substitute the BT PAN gateway IP for probing.
        val adjustedHost = { t: Transport ->
            if (t is BluetoothPanTransport) {
                // Use detected BT PAN gateway if available, else use the discovered host
                t.detectedGatewayIp ?: host
            } else {
                host
            }
        }

        val probeResults = candidates.map { transport ->
            val probeHost = adjustedHost(transport)
            val reachable = probePort(probeHost, port, PROBE_TIMEOUT_MS)
            Log.d(TAG, "  ${transport.name}: host=$probeHost reachable=$reachable score=${transport.score}")
            Pair(transport, reachable)
        }

        emitTransportStatus()

        val best = probeResults
            .filter { it.second } // only reachable ones
            .maxByOrNull { it.first.score }
            ?.first

        if (best == null) {
            Log.d(TAG, "No transport can reach $host:$port")
        } else {
            Log.i(TAG, "Selected: ${best.name} (score=${best.score})")
        }
        best
    }

    // ── Connection ─────────────────────────────────────────────────────────

    private suspend fun connectVia(transport: Transport, host: String, port: Int) {
        withContext(Dispatchers.Main) {
            // For BT PAN, use detected gateway instead of Wi-Fi host
            val effectiveHost = if (transport is BluetoothPanTransport) {
                transport.detectedGatewayIp ?: host
            } else {
                host
            }
            activeTransport = transport
            lastKnownHost = effectiveHost
            lastKnownPort = port
            emitTransportStatus()
            connectionManager.connect(effectiveHost, port, transport)
            startHealthMonitor()
        }
    }

    // ── Health monitor ────────────────────────────────────────────────────

    /**
     * Periodically re-evaluate transport health and available alternatives.
     * If a better transport becomes available, triggers a proactive switch.
     * If the active transport becomes unreachable, triggers failover.
     */
    private fun startHealthMonitor() {
        healthMonitorJob?.cancel()
        healthMonitorJob = scope.launch {
            while (isActive) {
                delay(HEALTH_CHECK_INTERVAL_MS)

                val host = lastKnownHost ?: continue
                val port = lastKnownPort.takeIf { it > 0 } ?: continue
                val current = activeTransport ?: continue

                if (!connectionManager.isConnected()) {
                    Log.d(TAG, "Health monitor: not connected, skipping re-evaluation")
                    emitTransportStatus()
                    continue
                }

                // Probe all transports to update scores and availability
                val allCandidates = allTransports.filter { it.isAvailable }
                val probeResults = allCandidates.map { t ->
                    val ph = if (t is BluetoothPanTransport) t.detectedGatewayIp ?: host else host
                    val reachable = probePort(ph, port, PROBE_TIMEOUT_MS)
                    Triple(t, ph, reachable)
                }

                emitTransportStatus()

                // Check if a better transport is available
                val best = probeResults
                    .filter { it.third } // reachable
                    .maxByOrNull { it.first.score }
                    ?.first

                if (best != null && best.name != current.name &&
                    best.score > current.score + SCORE_SWITCH_HYSTERESIS) {
                    Log.i(TAG, "Health monitor: ${best.name} (score=${best.score}) > " +
                               "${current.name} (score=${current.score}). Switching.")
                    val effectiveHost = if (best is BluetoothPanTransport) {
                        best.detectedGatewayIp ?: host
                    } else { host }
                    withContext(Dispatchers.Main) {
                        connectionManager.setTransportSwitching()
                        activeTransport = best
                        connectionManager.connect(effectiveHost, port, best)
                    }
                }
            }
        }
    }

    // ── Transport status emission ─────────────────────────────────────────

    private fun emitTransportStatus() {
        val activeName = activeTransport?.name
        val statuses = allTransports.map { t ->
            t.getStatus(isActive = t.name == activeName)
        }
        _availableTransports.value = statuses
    }

    // ── Discovery helpers ─────────────────────────────────────────────────

    private fun buildMdnsListener(onFound: (String, Int) -> Unit): NsdManager.DiscoveryListener {
        return object : NsdManager.DiscoveryListener {
            override fun onDiscoveryStarted(regType: String) {
                Log.d(TAG, "mDNS discovery started")
            }
            override fun onServiceFound(service: NsdServiceInfo) {
                if (service.serviceType.contains("_vivy._tcp")) {
                    nsdManager.resolveService(service, object : NsdManager.ResolveListener {
                        override fun onResolveFailed(si: NsdServiceInfo, errorCode: Int) {
                            Log.w(TAG, "mDNS resolve failed: $errorCode")
                        }
                        override fun onServiceResolved(si: NsdServiceInfo) {
                            val host = si.host?.hostAddress
                            val port = si.port
                            if (host != null) {
                                Log.i(TAG, "mDNS resolved: $host:$port")
                                onFound(host, port)
                            }
                        }
                    })
                }
            }
            override fun onServiceLost(service: NsdServiceInfo) {}
            override fun onDiscoveryStopped(serviceType: String) {}
            override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
                Log.w(TAG, "mDNS start discovery failed: $errorCode")
            }
            override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {
                try { nsdManager.stopServiceDiscovery(this) } catch (_: Exception) {}
            }
        }
    }

    private fun stopMdns() {
        currentDiscoveryListener?.let {
            try { nsdManager.stopServiceDiscovery(it) } catch (_: Exception) {}
            currentDiscoveryListener = null
        }
    }

    private suspend fun handleDiscoveryFailed() {
        withContext(Dispatchers.Main) {
            connectionManager.setDiscoveryFailed()
            emitTransportStatus()
        }
    }

    // ── TCP probe ─────────────────────────────────────────────────────────

    private fun probePort(host: String, port: Int, timeoutMs: Int): Boolean {
        return try {
            Socket().use { socket ->
                socket.connect(InetSocketAddress(host, port), timeoutMs)
            }
            true
        } catch (e: Exception) {
            false
        }
    }

    // ── Constants ─────────────────────────────────────────────────────────

    companion object {
        private const val TAG = "TransportManager"
        private const val DISCOVERY_TIMEOUT_MS = 30_000L
        private const val PROBE_TIMEOUT_MS = 2_500
        private const val HEALTH_CHECK_INTERVAL_MS = 30_000L
        /** Minimum score advantage for a proactive transport switch to occur. */
        private const val SCORE_SWITCH_HYSTERESIS = 0.15f
    }
}
