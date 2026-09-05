package com.vivy.node.camera

import android.annotation.SuppressLint
import android.content.Context
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import com.vivy.node.connection.HubConnectionManager
import org.json.JSONObject

class GpsCapabilityProvider(
    private val context: Context,
    private val connectionManager: HubConnectionManager
) {
    private var locationManager: LocationManager? = null
    private var isTracking = false

    private val locationListener = object : LocationListener {
        override fun onLocationChanged(location: Location) {
            val payload = JSONObject().apply {
                put("latitude", location.latitude)
                put("longitude", location.longitude)
                put("accuracy", location.accuracy)
                put("altitude", location.altitude)
                put("speed", location.speed)
                put("timestamp", location.time)
            }
            connectionManager.sendMessage("gps.update", payload)
        }
        override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) {}
        override fun onProviderEnabled(provider: String) {}
        override fun onProviderDisabled(provider: String) {}
    }

    @SuppressLint("MissingPermission")
    fun startTracking() {
        if (isTracking) return
        locationManager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        
        val providers = locationManager?.getProviders(true) ?: emptyList()
        if (providers.contains(LocationManager.GPS_PROVIDER)) {
            locationManager?.requestLocationUpdates(
                LocationManager.GPS_PROVIDER,
                10000L, // 10 seconds
                10f,    // 10 meters
                locationListener
            )
            isTracking = true
        } else if (providers.contains(LocationManager.NETWORK_PROVIDER)) {
            locationManager?.requestLocationUpdates(
                LocationManager.NETWORK_PROVIDER,
                10000L,
                10f,
                locationListener
            )
            isTracking = true
        }
    }

    fun stopTracking() {
        if (!isTracking) return
        locationManager?.removeUpdates(locationListener)
        isTracking = false
    }
}
