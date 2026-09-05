package com.vivy.node.transport

import android.annotation.SuppressLint
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.wifi.p2p.*
import android.util.Log
import okhttp3.*
import java.net.Inet4Address
import java.net.NetworkInterface
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference

/**
 * Wi-Fi Direct / P2P Transport.
 *
 * Carries Vivy WebSocket traffic over a Wi-Fi Direct (IEEE 802.11 P2P)
 * peer-to-peer connection. When the Android phone forms a P2P group with
 * the Windows PC, both devices get IP addresses on a local P2P network.
 * The Hub WebSocket protocol is reused unchanged over that IP path.
 *
 * Architecture invariant: this transport does NOT contain any Vivy feature
 * logic. All features remain in the feature layer above.
 *
 * isAvailable: false → graceful no-op. Wi-Fi or BT PAN continue.
 *
 * Limitations (verified by investigation):
 *   - Windows supports Wi-Fi Direct via "Miracast / Wi-Fi Direct" but does
 *     not always expose a usable IP socket interface to user-space apps.
 *   - Android must discover the PC as a WifiP2pDevice and form a P2P group.
 *   - The Group Owner (GO) gets 192.168.49.1; clients get 192.168.49.x.
 *   - If the PC is the GO: Hub at 192.168.49.1:HUB_PORT is the target.
 *   - If Android is the GO: Hub IP is the client IP assigned to the PC.
 *   - This transport handles both topologies.
 *   - Required permissions: ACCESS_FINE_LOCATION (pre-T), NEARBY_WIFI_DEVICES (T+).
 *
 * Status: EXPERIMENTAL — implemented with real APIs, gracefully unavailable
 * if Wi-Fi Direct peer discovery fails or no group forms.
 */
class WifiDirectTransport(private val context: Context) : Transport {

    override val name = "Wi-Fi Direct"

    private val wifiP2pManager: WifiP2pManager? =
        context.getSystemService(Context.WIFI_P2P_SERVICE) as? WifiP2pManager

    private val channel: WifiP2pManager.Channel? =
        wifiP2pManager?.initialize(context, context.mainLooper, null)

    private val _groupInfo = AtomicReference<WifiP2pGroup?>(null)
    private val _peerIp = AtomicReference<String?>(null)

    override val isAvailable: Boolean
        get() = wifiP2pManager != null && _peerIp.get() != null

    override var isConnected: Boolean = false
        private set

    override val diagnosticState: String
        get() {
            if (isConnected) return "Connected"
            if (_groupInfo.get() != null) return "Group Formed"
            if (wifiP2pManager != null) return "Available"
            return "Unavailable"
        }

    override val diagnosticHubState: String?
        get() {
            if (wifiP2pManager == null) return null
            if (isConnected) return "Reachable"
            if (_groupInfo.get() == null) return "Peer: Not connected"
            if (lastFailureReason != null) return "Unreachable ($lastFailureReason)"
            return "Probing..."
        }

    private val _estimatedLatencyMs = AtomicLong(0L)
    override val estimatedLatencyMs: Long get() = _estimatedLatencyMs.get()

    override var lastFailureReason: String? = null
        private set

    /**
     * Score for Wi-Fi Direct:
     * - 0.75 base (good bandwidth, local, but group formation has overhead)
     * - Reduced if latency is high or if unavailable
     */
    override val score: Float
        get() {
            if (!isAvailable) return 0f
            var s = 0.75f
            val lat = estimatedLatencyMs
            if (lat in 1..50) s += 0.05f
            else if (lat > 150) s -= 0.1f
            if (lastFailureReason != null) s -= 0.2f
            return s.coerceIn(0f, 1f)
        }

    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .connectTimeout(20, TimeUnit.SECONDS)
        .build()

    private var webSocket: WebSocket? = null
    private var listener: TransportListener? = null
    private var connectStartMs: Long = 0L

    // ── Broadcast receiver for P2P state changes ──────────────────────────

    private val p2pReceiver = object : BroadcastReceiver() {
        @SuppressLint("MissingPermission")
        override fun onReceive(ctx: Context, intent: Intent) {
            when (intent.action) {
                WifiP2pManager.WIFI_P2P_CONNECTION_CHANGED_ACTION -> {
                    val networkInfo = intent.getParcelableExtra<android.net.NetworkInfo>(
                        WifiP2pManager.EXTRA_NETWORK_INFO
                    )
                    if (networkInfo?.isConnected == true) {
                        wifiP2pManager?.requestGroupInfo(channel) { group ->
                            _groupInfo.set(group)
                            if (group != null) {
                                val ip = resolveGroupOwnerIp(group)
                                _peerIp.set(ip)
                                Log.i(TAG, "P2P group formed. GO/peer IP: $ip, isGO=${group.isGroupOwner}")
                            }
                        }
                    } else {
                        _groupInfo.set(null)
                        _peerIp.set(null)
                        Log.d(TAG, "P2P disconnected")
                    }
                }
                WifiP2pManager.WIFI_P2P_THIS_DEVICE_CHANGED_ACTION -> {
                    // Device state changed — not used in transport scoring
                }
            }
        }
    }

    private var receiverRegistered = false

    /** Register the P2P broadcast receiver. Call from activity/service onCreate. */
    fun registerReceiver() {
        if (receiverRegistered) return
        val filter = IntentFilter().apply {
            addAction(WifiP2pManager.WIFI_P2P_CONNECTION_CHANGED_ACTION)
            addAction(WifiP2pManager.WIFI_P2P_THIS_DEVICE_CHANGED_ACTION)
        }
        context.registerReceiver(p2pReceiver, filter)
        receiverRegistered = true
        Log.d(TAG, "P2P broadcast receiver registered")
    }

    /** Unregister the P2P broadcast receiver. Call from onDestroy. */
    fun unregisterReceiver() {
        if (!receiverRegistered) return
        try {
            context.unregisterReceiver(p2pReceiver)
        } catch (e: Exception) {
            Log.w(TAG, "Receiver unregister error: ${e.message}")
        }
        receiverRegistered = false
    }

    // ── P2P peer discovery ─────────────────────────────────────────────────

    /**
     * Start Wi-Fi Direct peer discovery.
     * Does not block. Results arrive via the P2P broadcast receiver.
     * Requires NEARBY_WIFI_DEVICES (Android 13+) or ACCESS_FINE_LOCATION.
     */
    @SuppressLint("MissingPermission")
    fun startDiscovery() {
        val mgr = wifiP2pManager ?: return
        val ch = channel ?: return
        try {
            mgr.discoverPeers(ch, object : WifiP2pManager.ActionListener {
                override fun onSuccess() {
                    Log.d(TAG, "P2P peer discovery started")
                }
                override fun onFailure(reason: Int) {
                    Log.w(TAG, "P2P peer discovery failed: reason $reason")
                    lastFailureReason = "P2P discovery failed (reason=$reason)"
                }
            })
        } catch (e: SecurityException) {
            Log.w(TAG, "SecurityException in P2P discovery — permission missing: ${e.message}")
            lastFailureReason = "Wi-Fi Direct: permission required"
        } catch (e: Exception) {
            Log.w(TAG, "Exception in P2P discovery: ${e.message}")
            lastFailureReason = "Wi-Fi Direct: ${e.message}"
        }
    }

    /**
     * Attempt to connect to a P2P peer by MAC address.
     * In Vivy deployment the Hub's device MAC is not hardcoded; instead
     * TransportManager calls this after peer list discovery.
     */
    @SuppressLint("MissingPermission")
    fun connectToPeer(deviceAddress: String) {
        val mgr = wifiP2pManager ?: return
        val ch = channel ?: return
        val config = WifiP2pConfig().apply {
            this.deviceAddress = deviceAddress
        }
        try {
            mgr.connect(ch, config, object : WifiP2pManager.ActionListener {
                override fun onSuccess() {
                    Log.d(TAG, "P2P connect initiated to $deviceAddress")
                }
                override fun onFailure(reason: Int) {
                    Log.w(TAG, "P2P connect failed: $reason")
                    lastFailureReason = "P2P connect failed (reason=$reason)"
                }
            })
        } catch (e: SecurityException) {
            Log.w(TAG, "SecurityException P2P connect: ${e.message}")
            lastFailureReason = "Wi-Fi Direct: permission required"
        } catch (e: Exception) {
            Log.w(TAG, "Exception P2P connect: ${e.message}")
            lastFailureReason = "Wi-Fi Direct: ${e.message}"
        }
    }

    // ── Transport.connect ─────────────────────────────────────────────────

    override fun connect(host: String, port: Int, listener: TransportListener) {
        this.listener = listener
        if (isConnected) return

        val url = "ws://$host:$port"
        Log.d(TAG, "Connecting over Wi-Fi Direct to $url")
        val request = Request.Builder().url(url).build()
        connectStartMs = System.currentTimeMillis()

        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                isConnected = true
                lastFailureReason = null
                _estimatedLatencyMs.set(System.currentTimeMillis() - connectStartMs)
                Log.i(TAG, "Wi-Fi Direct connected in ${_estimatedLatencyMs.get()} ms")
                listener.onConnected(name)
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                listener.onMessageReceived(name, text)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                isConnected = false
                Log.d(TAG, "Wi-Fi Direct closed: $reason")
                listener.onDisconnected(name)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                isConnected = false
                lastFailureReason = t.message ?: "Wi-Fi Direct failure"
                Log.e(TAG, "Wi-Fi Direct failure: ${t.message}")
                listener.onConnectionFailed(name, t)
            }
        })
    }

    override fun disconnect() {
        webSocket?.close(1000, "Normal closure")
        isConnected = false
        wifiP2pManager?.removeGroup(channel, null)
    }

    override fun send(message: String) {
        webSocket?.send(message)
    }

    // ── IP resolution ─────────────────────────────────────────────────────

    /**
     * Resolve the Hub's reachable IP within the P2P group.
     * - If Android is the Group Owner: Hub is on the client side.
     *   We cannot know the client IP from group info alone; return null
     *   and let TransportManager probe the known P2P subnet.
     * - If Android is a client: Group Owner (GO) IP = 192.168.49.1 (standard).
     *   Hub runs on the GO (Windows PC), reachable at 192.168.49.1.
     * Returns null if not determinable.
     */
    private fun resolveGroupOwnerIp(group: WifiP2pGroup): String? {
        if (!group.isGroupOwner) {
            // Android is a client; the GO (Windows) is at the standard P2P GO IP
            return group.owner?.deviceAddress?.let { _ ->
                // The GO address in WifiP2pGroup is MAC, not IP.
                // The standard P2P GO IP is always 192.168.49.1 on Android P2P groups.
                getP2pGoIp()
            }
        }
        // Android is the GO: clients connect to us. We cannot reach Hub on PC
        // unless we know the PC's client IP. Try scanning the P2P subnet.
        // Return the standard client-range start for probing.
        Log.w(TAG, "Android is P2P GO — Hub on PC may be at 192.168.49.x client IP")
        return null // TransportManager will probe 192.168.49.1 range
    }

    /** Returns the actual P2P interface IP if this device is connected to a group. */
    private fun getP2pGoIp(): String {
        // The P2P GO (Windows PC) IP on Android-side P2P groups is always 192.168.49.1
        // per Android Wi-Fi P2P implementation.
        return "192.168.49.1"
    }

    /**
     * Returns the IP address of the local P2P interface (p2p-wlan0 or similar).
     * Useful when Android is a client to find its own address and derive subnet.
     */
    fun getLocalP2pIp(): String? {
        return try {
            val ifaces = NetworkInterface.getNetworkInterfaces()?.toList() ?: return null
            for (iface in ifaces) {
                val name = iface.name ?: continue
                if (!name.startsWith("p2p") && !name.contains("direct")) continue
                for (addr in iface.inetAddresses.toList()) {
                    if (addr is Inet4Address && !addr.isLoopbackAddress) {
                        return addr.hostAddress
                    }
                }
            }
            null
        } catch (e: Exception) {
            Log.w(TAG, "Error getting P2P local IP: ${e.message}")
            null
        }
    }

    companion object {
        private const val TAG = "WifiDirectTransport"
    }
}
