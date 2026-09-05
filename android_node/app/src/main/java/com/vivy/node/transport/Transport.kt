package com.vivy.node.transport

/**
 * Transport status snapshot used by the UI and TransportManager scoring.
 */
data class TransportStatus(
    val name: String,
    val isAvailable: Boolean,
    val isActive: Boolean,
    val isConnected: Boolean,
    val score: Float,          // 0.0 (worst) to 1.0 (best)
    val estimatedLatencyMs: Long,
    val lastFailureReason: String?,
    val displayState: String,
    val displayHubState: String? = null
)

interface TransportListener {
    fun onConnected(transportName: String)
    fun onDisconnected(transportName: String)
    fun onMessageReceived(transportName: String, text: String)
    fun onConnectionFailed(transportName: String, error: Throwable)
}

interface Transport {
    val name: String

    /** True if this transport's underlying path is currently detectable on this device. */
    val isAvailable: Boolean

    val isConnected: Boolean

    /** Estimated round-trip latency in ms. Updated after each probe/connection. */
    val estimatedLatencyMs: Long

    /**
     * Last failure reason, if any. Cleared on successful connection.
     * Never contains credentials or session material.
     */
    val lastFailureReason: String?

    /**
     * Score from 0.0 to 1.0 reflecting current suitability.
     * Higher = better. Computed by the transport itself based on
     * availability, latency, bandwidth class, and recent failures.
     */
    val score: Float
    
    /** Specific state describing the local adapter (e.g. "Connected", "Paired / PAN inactive"). */
    val diagnosticState: String
    
    /** Specific state describing the Hub on this transport (e.g. "Reachable", "Unreachable"). */
    val diagnosticHubState: String?

    fun connect(host: String, port: Int, listener: TransportListener)
    fun disconnect()
    fun send(message: String)

    /** Return a snapshot of this transport's current status for UI/observability. */
    fun getStatus(isActive: Boolean): TransportStatus = TransportStatus(
        name = name,
        isAvailable = isAvailable,
        isActive = isActive,
        isConnected = isConnected,
        score = score,
        estimatedLatencyMs = estimatedLatencyMs,
        lastFailureReason = lastFailureReason,
        displayState = diagnosticState,
        displayHubState = diagnosticHubState
    )
}
