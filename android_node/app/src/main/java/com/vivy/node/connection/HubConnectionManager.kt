package com.vivy.node.connection

import android.util.Log
import com.vivy.node.security.CredentialManager
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.CancellableContinuation
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import com.vivy.node.transport.Transport
import com.vivy.node.transport.TransportListener
import com.vivy.node.transport.TransportStatus

enum class ConnectionState {
    DISCONNECTED, DISCOVERING, DISCOVERY_FAILED, TRANSPORT_SWITCHING, CONNECTING, CONNECTION_FAILED, AUTHENTICATING, PAIRING_REQUIRED, AUTH_FAILED, CONNECTED
}

class HubConnectionManager(private val credentialManager: CredentialManager) : TransportListener {
    /**
     * Called when the active transport disconnects or fails.
     * Set by TransportManager after construction to avoid circular dependency.
     * The lambda should trigger transport failover logic.
     */
    var onTransportLost: (() -> Unit)? = null

    /** Expose available transports from TransportManager for UI consumption. */
    private val _availableTransports = MutableStateFlow<List<TransportStatus>>(emptyList())
    val availableTransports: StateFlow<List<TransportStatus>> = _availableTransports

    fun updateAvailableTransports(statuses: List<TransportStatus>) {
        _availableTransports.value = statuses
    }

    private var currentTransport: Transport? = null
    
    private val _activeTransportName = MutableStateFlow<String?>(null)
    val activeTransportName: StateFlow<String?> = _activeTransportName


    private val pendingRequests = ConcurrentHashMap<String, CancellableContinuation<JSONObject>>()

    private val _state = MutableStateFlow(ConnectionState.DISCONNECTED)
    val state: StateFlow<ConnectionState> = _state

    /** True when the connection is in CONNECTED state. Used by health monitor. */
    fun isConnected(): Boolean = _state.value == ConnectionState.CONNECTED

    private val _pairingCode = MutableStateFlow<String?>(null)
    val pairingCode: StateFlow<String?> = _pairingCode

    private val _hubAddress = MutableStateFlow<String?>(null)
    val hubAddress: StateFlow<String?> = _hubAddress

    private val _latency = MutableStateFlow(0L)
    val latency: StateFlow<Long> = _latency

    private val _perceptionResult = MutableStateFlow<String?>(null)
    val perceptionResult: StateFlow<String?> = _perceptionResult

    private var requestTimes = mutableMapOf<String, Long>()

    private var currentHost: String? = null

    fun connect(host: String, port: Int, transport: Transport) {
        if (_state.value == ConnectionState.CONNECTED && currentTransport?.name == transport.name) return

        currentTransport?.disconnect()
        currentTransport = transport

        currentHost = host
        _hubAddress.value = "${transport.name}://$host:$port"
        _state.value = ConnectionState.CONNECTING

        transport.connect(host, port, this)
    }

    fun setDiscovering() {
        _state.value = ConnectionState.DISCOVERING
    }

    fun setDiscoveryFailed() {
        _state.value = ConnectionState.DISCOVERY_FAILED
    }
    
    fun setTransportSwitching() {
        _state.value = ConnectionState.TRANSPORT_SWITCHING
    }

    fun disconnect() {
        currentTransport?.disconnect()
        currentTransport = null
        _state.value = ConnectionState.DISCONNECTED
    }

    override fun onConnected(transportName: String) {
        Log.d("Connection", "$transportName Transport Connected")
        _activeTransportName.value = transportName
        _state.value = ConnectionState.AUTHENTICATING
        val sessionKey = credentialManager.getSessionKey()
        if (sessionKey != null) {
            sendAuthenticateRequest(sessionKey)
        } else {
            sendIdentityRequest()
        }
    }

    override fun onMessageReceived(transportName: String, text: String) {
        Log.d("Connection", "Received via $transportName: $text")
        try {
            val json = JSONObject(text)
            val type = json.optString("type")

            when (type) {
                "pairing.challenge" -> {
                    _state.value = ConnectionState.PAIRING_REQUIRED
                    val payload = json.optJSONObject("payload")
                    _pairingCode.value = payload?.optString("pairing_code")
                }
                "identity.accept" -> {
                    val session = json.optString("session_id")
                    credentialManager.saveSessionKey(session)
                    
                    _state.value = ConnectionState.CONNECTED
                    _pairingCode.value = null
                }
                "device.authenticate_ack" -> {
                    _state.value = ConnectionState.CONNECTED
                }
                "pairing.failed" -> {
                    credentialManager.clearSession()
                    _state.value = ConnectionState.AUTH_FAILED
                }
                "capability.result" -> {
                    val reqId = json.optString("request_id")
                    val payload = json.optJSONObject("payload") ?: JSONObject()
                    
                    requestTimes.remove(reqId)?.let { t0 ->
                        _latency.value = System.currentTimeMillis() - t0
                    }
                    
                    val error = payload.optString("error", null)
                    val cont = pendingRequests.remove(reqId)
                    if (cont != null) {
                        if (!error.isNullOrEmpty()) {
                            cont.resumeWithException(Exception(error))
                        } else {
                            cont.resume(payload)
                        }
                    } else {
                        // Fire-and-forget capability responses like vision.all
                        _perceptionResult.value = payload.toString(2)
                    }
                }
                "capability.error" -> {
                    val reqId = json.optString("request_id")
                    val payload = json.optJSONObject("payload") ?: JSONObject()
                    val error = payload.optString("error", "Unknown capability error")
                    pendingRequests.remove(reqId)?.let { cont ->
                        cont.resumeWithException(Exception(error))
                    }
                }
            }
        } catch (e: Exception) {
            Log.e("Connection", "Message parse error", e)
        }
    }

    override fun onDisconnected(transportName: String) {
        Log.d("Connection", "Closed: $transportName")

        // Fail any pending requests immediately so feature callers get an error
        pendingRequests.values.forEach { it.resumeWithException(Exception("$transportName closed")) }
        pendingRequests.clear()

        if (currentTransport?.name == transportName) {
            _activeTransportName.value = null
        }

        // Trigger transport failover rather than just going to DISCONNECTED.
        // TransportManager will set TRANSPORT_SWITCHING and try alternate paths.
        // If no alternate is available it will call setDiscoveryFailed / discoverAndConnect.
        val failoverHandler = onTransportLost
        if (failoverHandler != null) {
            Log.i("Connection", "Transport lost — attempting failover")
            failoverHandler()
        } else {
            _state.value = ConnectionState.DISCONNECTED
        }
    }

    override fun onConnectionFailed(transportName: String, error: Throwable) {
        Log.e("Connection", "Error on $transportName: ${error.message}")

        pendingRequests.values.forEach {
            it.resumeWithException(Exception("$transportName failure: ${error.message}"))
        }
        pendingRequests.clear()

        if (currentTransport?.name == transportName) {
            _activeTransportName.value = null
        }

        // Attempt failover on connection failure, same as on disconnect
        val failoverHandler = onTransportLost
        if (failoverHandler != null) {
            Log.i("Connection", "Connection failed — attempting failover")
            failoverHandler()
        } else {
            _state.value = ConnectionState.CONNECTION_FAILED
        }
    }

    private fun sendIdentityRequest() {
        val transport = currentTransport ?: return
        val req = JSONObject().apply {
            put("protocol", "vivy")
            put("version", "1")
            put("message_id", UUID.randomUUID().toString())
            put("type", "identity.request")
            put("device_id", credentialManager.getDeviceId())
            put("payload", JSONObject().apply {
                put("device_type", "android")
                put("hardware", org.json.JSONArray().apply {
                    put("camera")
                    put("mic")
                })
            })
        }
        transport.send(req.toString())
    }

    private fun sendAuthenticateRequest(sessionKey: String) {
        val transport = currentTransport ?: return
        val req = JSONObject().apply {
            put("protocol", "vivy")
            put("version", "1")
            put("message_id", UUID.randomUUID().toString())
            put("type", "device.authenticate")
            put("device_id", credentialManager.getDeviceId())
            put("security", JSONObject().apply {
                put("session_key", sessionKey)
            })
        }
        transport.send(req.toString())
    }

    fun sendPairingResponse(pin: String) {
        val transport = currentTransport ?: return
        val req = JSONObject().apply {
            put("protocol", "vivy")
            put("version", "1")
            put("message_id", UUID.randomUUID().toString())
            put("type", "pairing.response")
            put("device_id", credentialManager.getDeviceId())
            put("payload", JSONObject().apply {
                put("pin", pin)
            })
        }
        transport.send(req.toString())
    }

    fun sendFrame(base64Image: String) {
        if (_state.value != ConnectionState.CONNECTED) return
        val sessionKey = credentialManager.getSessionKey() ?: return
        val transport = currentTransport ?: return

        val reqId = UUID.randomUUID().toString()
        requestTimes[reqId] = System.currentTimeMillis()

        val req = JSONObject().apply {
            put("protocol", "vivy")
            put("version", "1")
            put("message_id", reqId)
            put("type", "capability.request")
            put("device_id", credentialManager.getDeviceId())
            put("session_id", sessionKey)
            put("capability", "vision.all")
            put("payload", JSONObject().apply {
                put("image", base64Image)
            })
        }
        transport.send(req.toString())
    }
    
    fun sendMessage(type: String, payload: JSONObject) {
        if (_state.value != ConnectionState.CONNECTED) return
        val sessionKey = credentialManager.getSessionKey() ?: return
        val transport = currentTransport ?: return

        val reqId = UUID.randomUUID().toString()
        val req = JSONObject().apply {
            put("protocol", "vivy")
            put("version", "1")
            put("message_id", reqId)
            put("type", type)
            put("device_id", credentialManager.getDeviceId())
            put("session_id", sessionKey)
            put("payload", payload)
        }
        transport.send(req.toString())
    }

    fun sendCapabilityRequest(capability: String, payload: JSONObject) {
        if (_state.value != ConnectionState.CONNECTED) return
        val sessionKey = credentialManager.getSessionKey() ?: return
        val transport = currentTransport ?: return

        val reqId = UUID.randomUUID().toString()
        val req = JSONObject().apply {
            put("protocol", "vivy")
            put("version", "1")
            put("message_id", reqId)
            put("type", "capability.request")
            put("device_id", credentialManager.getDeviceId())
            put("session_id", sessionKey)
            put("capability", capability)
            put("payload", payload)
        }
        transport.send(req.toString())
    }

    suspend fun requestCapability(capability: String, payload: JSONObject): JSONObject = suspendCancellableCoroutine { cont ->
        if (_state.value != ConnectionState.CONNECTED) {
            cont.resumeWithException(IllegalStateException("Not connected to Hub"))
            return@suspendCancellableCoroutine
        }
        val sessionKey = credentialManager.getSessionKey()
        if (sessionKey == null) {
            cont.resumeWithException(IllegalStateException("No session key"))
            return@suspendCancellableCoroutine
        }
        val transport = currentTransport
        if (transport == null) {
            cont.resumeWithException(IllegalStateException("Transport is null"))
            return@suspendCancellableCoroutine
        }

        val reqId = UUID.randomUUID().toString()
        requestTimes[reqId] = System.currentTimeMillis()
        pendingRequests[reqId] = cont

        val req = JSONObject().apply {
            put("protocol", "vivy")
            put("version", "1")
            put("message_id", reqId)
            put("type", "capability.request")
            put("device_id", credentialManager.getDeviceId())
            put("session_id", sessionKey)
            put("capability", capability)
            put("payload", payload)
        }
        transport.send(req.toString())

        cont.invokeOnCancellation {
            pendingRequests.remove(reqId)
        }
    }
}
