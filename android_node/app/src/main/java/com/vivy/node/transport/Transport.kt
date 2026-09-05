package com.vivy.node.transport

import org.json.JSONObject

interface TransportListener {
    fun onConnected(transportName: String)
    fun onDisconnected(transportName: String)
    fun onMessageReceived(transportName: String, text: String)
    fun onConnectionFailed(transportName: String, error: Throwable)
}

interface Transport {
    val name: String
    val isAvailable: Boolean
    val isConnected: Boolean

    fun connect(host: String, port: Int, listener: TransportListener)
    fun disconnect()
    fun send(message: String)
}
