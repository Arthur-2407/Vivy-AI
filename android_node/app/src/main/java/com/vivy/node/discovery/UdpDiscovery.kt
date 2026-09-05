package com.vivy.node.discovery

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.GlobalScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.isActive
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.SocketTimeoutException

class UdpDiscovery(private val onDiscovered: (String, Int) -> Unit) {
    private var listenJob: Job? = null
    private var socket: DatagramSocket? = null
    private val PORT = 8766

    fun startListening() {
        if (listenJob != null) return
        
        Log.d("UdpDiscovery", "Starting UDP broadcast listener on port $PORT")
        
        listenJob = GlobalScope.launch(Dispatchers.IO) {
            try {
                socket = DatagramSocket(PORT).apply {
                    soTimeout = 2000
                }
                
                val buffer = ByteArray(1024)
                while (isActive) {
                    try {
                        val packet = DatagramPacket(buffer, buffer.size)
                        socket?.receive(packet)
                        
                        val message = String(packet.data, 0, packet.length).trim()
                        if (message.startsWith("VIVY_HUB:")) {
                            val parts = message.split(":")
                            if (parts.size >= 3) {
                                val ip = packet.address.hostAddress
                                val port = parts[2].toIntOrNull() ?: 8800
                                Log.d("UdpDiscovery", "Found Vivy Hub via UDP: $ip:$port")
                                
                                stopListening()
                                onDiscovered(ip, port)
                                break
                            }
                        }
                    } catch (e: SocketTimeoutException) {
                        // Just loop
                    } catch (e: Exception) {
                        Log.e("UdpDiscovery", "Error receiving packet", e)
                        break
                    }
                }
            } catch (e: Exception) {
                Log.e("UdpDiscovery", "Could not bind UDP socket", e)
            } finally {
                socket?.close()
            }
        }
    }

    fun stopListening() {
        listenJob?.cancel()
        listenJob = null
        socket?.close()
        socket = null
        Log.d("UdpDiscovery", "Stopped UDP listener")
    }
}
