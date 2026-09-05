package com.vivy.node.transport

import android.util.Log
import okhttp3.*
import java.util.concurrent.TimeUnit

class WiFiTransport : Transport {
    override val name = "WiFi"
    override val isAvailable: Boolean = true // Always attemptable if network interface exists
    override var isConnected: Boolean = false
        private set

    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()

    private var webSocket: WebSocket? = null
    private var listener: TransportListener? = null

    override fun connect(host: String, port: Int, listener: TransportListener) {
        this.listener = listener
        if (isConnected) return

        val url = "ws://$host:$port"
        Log.d("WiFiTransport", "Connecting to $url")
        val request = Request.Builder().url(url).build()

        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                isConnected = true
                listener.onConnected(name)
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                listener.onMessageReceived(name, text)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                isConnected = false
                listener.onDisconnected(name)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                isConnected = false
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
}
