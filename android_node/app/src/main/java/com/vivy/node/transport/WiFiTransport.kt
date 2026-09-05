package com.vivy.node.transport

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.util.Log
import okhttp3.*
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong

/**
 * Wi-Fi / LAN Transport.
 *
 * Carries Vivy WebSocket traffic over the active Wi-Fi or Ethernet interface.
 * Dynamically checks for an active Wi-Fi-capable network rather than assuming
 * it is always available.
 *
 * This transport does NOT contain any Vivy feature logic.
 * Feature code is fully independent of which transport is active.
 */
class WiFiTransport(private val context: Context? = null) : Transport {

    override val name = "Wi-Fi"

    /**
     * True if the system currently has an active network with Wi-Fi or
     * Wi-Fi-aware capabilities. Falls back to true if context is not
     * provided (preserves backward compatibility with older callers).
     */
    override val isAvailable: Boolean
        get() {
            try {
                val ifaces = java.net.NetworkInterface.getNetworkInterfaces()?.toList() ?: return false
                for (iface in ifaces) {
                    val name = iface.name?.lowercase() ?: continue
                    // Match Wi-Fi, Ethernet, and Hotspot AP interfaces
                    if (name.startsWith("wlan") || name.startsWith("eth") || 
                        name.startsWith("swlan") || name.startsWith("ap") || name.startsWith("rndis")) {
                        if (iface.isUp && !iface.isLoopback) {
                            for (addr in iface.inetAddresses.toList()) {
                                if (addr is java.net.Inet4Address) {
                                    return true
                                }
                            }
                        }
                    }
                }
            } catch (e: Exception) {
                // Ignore
            }
            return false
        }

    override val diagnosticState: String
        get() {
            if (isConnected) return "Connected"
            if (isAvailable) return "Active / Ready"
            return "Disabled or No IP"
        }

    override val diagnosticHubState: String?
        get() {
            if (!isAvailable) return null
            if (isConnected) return "Reachable"
            if (lastFailureReason != null) return "Unreachable ($lastFailureReason)"
            return "Probing..."
        }

    override var isConnected: Boolean = false
        private set

    private val _estimatedLatencyMs = AtomicLong(0L)
    override val estimatedLatencyMs: Long get() = _estimatedLatencyMs.get()

    override var lastFailureReason: String? = null
        private set

    /**
     * Score for this transport:
     * - 0.9 base (Wi-Fi is high-bandwidth and low-latency)
     * - Reduced if latency is high (> 100 ms) or transport is unavailable
     * - Reduced after recent failures (tracked via lastFailureReason)
     */
    override val score: Float
        get() {
            if (!isAvailable) return 0f
            var s = 0.9f
            val lat = estimatedLatencyMs
            if (lat in 1..100) s += 0.05f         // bonus for measured low latency
            else if (lat > 200) s -= 0.1f           // penalty for high latency
            if (lastFailureReason != null) s -= 0.2f // recent failure penalty
            return s.coerceIn(0f, 1f)
        }

    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .connectTimeout(10, TimeUnit.SECONDS)
        .build()

    private var webSocket: WebSocket? = null
    private var listener: TransportListener? = null
    private var connectStartMs: Long = 0L

    override fun connect(host: String, port: Int, listener: TransportListener) {
        this.listener = listener
        if (isConnected) return

        val url = "ws://$host:$port"
        Log.d(TAG, "Connecting to $url")
        val request = Request.Builder().url(url).build()
        connectStartMs = System.currentTimeMillis()

        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                isConnected = true
                lastFailureReason = null
                _estimatedLatencyMs.set(System.currentTimeMillis() - connectStartMs)
                Log.i(TAG, "Connected to $url in ${_estimatedLatencyMs.get()} ms")
                listener.onConnected(name)
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                listener.onMessageReceived(name, text)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                isConnected = false
                Log.d(TAG, "Closed: $reason")
                listener.onDisconnected(name)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                isConnected = false
                lastFailureReason = t.message ?: "Unknown error"
                Log.e(TAG, "Failure: ${t.message}")
                listener.onConnectionFailed(name, t)
            }
        })
    }

    override fun disconnect() {
        webSocket?.close(1000, "Normal closure")
        isConnected = false
    }

    override fun send(message: String) {
        webSocket?.send(message)
    }

    companion object {
        private const val TAG = "WiFiTransport"
    }
}
