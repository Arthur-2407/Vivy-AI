package com.vivy.node.transport

import android.content.Context
import android.net.ConnectivityManager
import android.net.LinkProperties
import android.net.NetworkCapabilities
import android.util.Log
import okhttp3.*
import java.net.Inet4Address
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong

/**
 * Bluetooth PAN / IP Transport.
 *
 * Carries Vivy WebSocket traffic over a Bluetooth Personal Area Network
 * (PAN) IP interface. When the Android device has a BT PAN connection to
 * the Windows PC, the OS creates a dedicated network interface (e.g.
 * `bt-pan`) with an IP address. The existing Hub WebSocket protocol is
 * reused unchanged over this IP path.
 *
 * Architecture invariant: this transport does NOT contain any Vivy feature
 * logic. All features (Chat, Voice, Camera, Screen, Avatar, RVC, etc.)
 * are completely transport-independent and remain in the feature layer above.
 *
 * isAvailable: false → graceful no-op. Wi-Fi or other transports continue.
 * isAvailable: true  → a BT PAN IP interface is present; the gateway/peer
 *                       IP of that interface is used as the Hub candidate.
 *
 * How BT PAN works in this deployment:
 *   1. Android phone and Windows PC are paired via Bluetooth.
 *   2. Windows PC has "Bluetooth Personal Area Network" adapter enabled.
 *   3. The phone connects to the PC's BT PAN, creating a local IP interface.
 *   4. The Hub (running on the Windows PC) is reachable at the PC's BT
 *      adapter IP on the Hub port.
 *   5. This transport detects that interface, extracts the gateway IP,
 *      and connects via OkHttp WebSocket — the same as WiFiTransport.
 *
 * Security: OS-level BT pairing is NOT Vivy authentication.
 * The normal PIN/session-key auth flow runs over this transport exactly
 * as it does over Wi-Fi.
 */
class BluetoothPanTransport(private val context: Context) : Transport {

    override val name = "Bluetooth PAN"

    /**
     * Detected BT PAN gateway IP (the PC's BT adapter IP).
     * Null if no BT PAN interface is currently active.
     */
    var detectedGatewayIp: String? = null
        private set

    /**
     * True if a Bluetooth PAN IP interface is currently active on this device.
     * This is checked fresh each time to handle dynamic interface changes.
     */
    private fun hasBluetoothConnectPermission(): Boolean {
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
            return androidx.core.content.ContextCompat.checkSelfPermission(
                context, android.Manifest.permission.BLUETOOTH_CONNECT
            ) == android.content.pm.PackageManager.PERMISSION_GRANTED
        }
        return true
    }

    override val isAvailable: Boolean
        get() {
            detectedGatewayIp = detectBluetoothPanGateway()
            if (detectedGatewayIp != null) return true
            
            if (!hasBluetoothConnectPermission()) return false
            
            val adapter = (context.getSystemService(Context.BLUETOOTH_SERVICE) as? android.bluetooth.BluetoothManager)?.adapter
            return try {
                adapter?.isEnabled == true && adapter.bondedDevices?.isNotEmpty() == true
            } catch (e: SecurityException) {
                Log.w(TAG, "SecurityException checking bonded devices: ${e.message}")
                false
            } catch (e: Exception) {
                Log.w(TAG, "Error checking bonded devices: ${e.message}")
                false
            }
        }

    override val diagnosticState: String
        get() {
            if (isConnected) return "Connected"
            if (detectedGatewayIp != null) return "PAN Active"
            if (!hasBluetoothConnectPermission()) return "Permission Required"
            if (isAvailable) return "Paired / PAN not established"
            return "Disabled"
        }

    override val diagnosticHubState: String?
        get() {
            if (!isAvailable || detectedGatewayIp == null) return null
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
     * Score for Bluetooth PAN:
     * - 0.6 base (lower bandwidth than Wi-Fi but reliable locally)
     * - Reduced for high latency or recent failures
     * - Only applicable when isAvailable (BT PAN interface exists)
     */
    override val score: Float
        get() {
            if (!isAvailable) return 0f
            var s = 0.6f
            val lat = estimatedLatencyMs
            if (lat in 1..80) s += 0.05f
            else if (lat > 150) s -= 0.1f
            if (lastFailureReason != null) s -= 0.2f
            return s.coerceIn(0f, 1f)
        }

    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .connectTimeout(15, TimeUnit.SECONDS) // BT connections can be slightly slower
        .build()

    private var webSocket: WebSocket? = null
    private var listener: TransportListener? = null
    private var connectStartMs: Long = 0L

    override fun connect(host: String, port: Int, listener: TransportListener) {
        this.listener = listener
        if (isConnected) return

        // Use the detected BT PAN gateway if the caller passes the BT PAN IP,
        // otherwise use the host as provided (TransportManager passes the correct IP).
        val url = "ws://$host:$port"
        Log.d(TAG, "Connecting over BT PAN to $url")
        val request = Request.Builder().url(url).build()
        connectStartMs = System.currentTimeMillis()

        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                isConnected = true
                lastFailureReason = null
                _estimatedLatencyMs.set(System.currentTimeMillis() - connectStartMs)
                Log.i(TAG, "BT PAN connected in ${_estimatedLatencyMs.get()} ms")
                listener.onConnected(name)
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                listener.onMessageReceived(name, text)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                isConnected = false
                Log.d(TAG, "BT PAN closed: $reason")
                listener.onDisconnected(name)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                isConnected = false
                lastFailureReason = t.message ?: "BT PAN failure"
                Log.e(TAG, "BT PAN failure: ${t.message}")
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

    /**
     * Inspect all active networks and look for a Bluetooth transport.
     * If found, extract the gateway (default route first hop) IPv4 address
     * — this is the Windows PC's BT PAN adapter IP, where the Hub listens.
     *
     * Returns null if no BT PAN interface is active or detectable.
     * Never throws. Never crashes.
     */
    private fun detectBluetoothPanGateway(): String? {
        return try {
            val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE)
                as? ConnectivityManager ?: return null

            @Suppress("DEPRECATION")
            for (network in cm.allNetworks) {
                val caps = cm.getNetworkCapabilities(network) ?: continue
                if (!caps.hasTransport(NetworkCapabilities.TRANSPORT_BLUETOOTH)) continue

                val lp: LinkProperties = cm.getLinkProperties(network) ?: continue

                // Try routes first: find the default route gateway
                for (routeInfo in lp.routes) {
                    if (routeInfo.isDefaultRoute) {
                        val gw = routeInfo.gateway
                        if (gw is Inet4Address && !gw.isLoopbackAddress) {
                            val ip = gw.hostAddress
                            if (ip != null) {
                                Log.i(TAG, "BT PAN gateway detected: $ip (via route)")
                                return ip
                            }
                        }
                    }
                }

                // Fallback: use the interface's own IPv4 address as approximation
                // (useful if gateway is not exposed but IP is in the same subnet)
                for (linkAddr in lp.linkAddresses) {
                    val addr = linkAddr.address
                    if (addr is Inet4Address && !addr.isLoopbackAddress) {
                        val ip = addr.hostAddress
                        if (ip != null) {
                            Log.i(TAG, "BT PAN interface IP (no gateway route): $ip")
                            // Do not return this as the Hub IP directly;
                            // the caller must still probe the known Hub port.
                            // Return it so TransportManager can derive the peer.
                            return ip
                        }
                    }
                }
            }
            null
        } catch (e: SecurityException) {
            Log.w(TAG, "SecurityException detecting BT PAN: ${e.message}")
            null
        } catch (e: Exception) {
            Log.w(TAG, "Error detecting BT PAN gateway: ${e.message}")
            null
        }
    }

    companion object {
        private const val TAG = "BluetoothPanTransport"
    }
}
