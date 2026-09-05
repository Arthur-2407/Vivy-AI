package com.vivy.node.discovery

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothManager
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Log

class BleDiscovery(private val context: Context, private val onDiscovered: (String, Int) -> Unit) {
    private val bluetoothManager = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
    private val adapter: BluetoothAdapter? = bluetoothManager.adapter
    private var isScanning = false

    private val scanCallback = object : ScanCallback() {
        @SuppressLint("MissingPermission")
        override fun onScanResult(callbackType: Int, result: ScanResult?) {
            result?.let {
                val record = it.scanRecord
                val name = record?.deviceName ?: it.device.name
                if (name != null && name.startsWith("VivyHub")) {
                    Log.d("BleDiscovery", "Found VivyHub via BLE: $name")
                    // Expected format: VivyHub_192.168.43.5_8800
                    val parts = name.split("_")
                    if (parts.size >= 3) {
                        val ip = parts[1]
                        val port = parts[2].toIntOrNull() ?: 8800
                        stopScan()
                        onDiscovered(ip, port)
                    }
                }
            }
        }

        override fun onScanFailed(errorCode: Int) {
            Log.e("BleDiscovery", "BLE Scan failed: $errorCode")
        }
    }

    fun startScan() {
        if (adapter == null || !adapter.isEnabled) {
            Log.e("BleDiscovery", "Bluetooth is disabled or not supported")
            return
        }
        if (isScanning) return
        
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
            if (androidx.core.content.ContextCompat.checkSelfPermission(context, android.Manifest.permission.BLUETOOTH_SCAN) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
                Log.w("BleDiscovery", "Missing BLUETOOTH_SCAN permission. Skipping BLE discovery.")
                return
            }
        }
        
        Log.d("BleDiscovery", "Starting BLE scan for Hub")
        isScanning = true
        val scanner = adapter.bluetoothLeScanner
        
        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build()
            
        try {
            scanner?.startScan(null, settings, scanCallback)
            // Stop scan after 10 seconds
            Handler(Looper.getMainLooper()).postDelayed({
                stopScan()
            }, 10000)
        } catch (e: SecurityException) {
            Log.e("BleDiscovery", "SecurityException during BLE scan: ${e.message}")
            isScanning = false
        } catch (e: Exception) {
            Log.e("BleDiscovery", "Exception during BLE scan: ${e.message}")
            isScanning = false
        }
    }

    fun stopScan() {
        if (!isScanning) return
        isScanning = false
        try {
            adapter?.bluetoothLeScanner?.stopScan(scanCallback)
            Log.d("BleDiscovery", "Stopped BLE scan")
        } catch (e: SecurityException) {
            Log.e("BleDiscovery", "SecurityException during BLE stop: ${e.message}")
        } catch (e: Exception) {
            Log.e("BleDiscovery", "Exception during BLE stop: ${e.message}")
        }
    }
}
