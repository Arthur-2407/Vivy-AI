package com.vivy.node.security

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.util.UUID

class CredentialManager(context: Context) {
    private val prefs: SharedPreferences

    init {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()

        prefs = EncryptedSharedPreferences.create(
            context,
            "vivy_node_prefs",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }

    fun getDeviceId(): String {
        var id = prefs.getString("device_id", null)
        if (id == null) {
            id = "vivy-android-" + UUID.randomUUID().toString().substring(0, 8)
            prefs.edit().putString("device_id", id).apply()
        }
        return id
    }

    fun saveSessionKey(key: String) {
        prefs.edit().putString("session_key", key).apply()
    }

    fun getSessionKey(): String? {
        return prefs.getString("session_key", null)
    }

    fun clearSession() {
        prefs.edit().remove("session_key").apply()
    }

    fun saveLastEndpoint(host: String, port: Int) {
        prefs.edit()
            .putString("last_host", host)
            .putInt("last_port", port)
            .apply()
    }

    fun getLastEndpoint(): Pair<String, Int>? {
        val host = prefs.getString("last_host", null)
        val port = prefs.getInt("last_port", -1)
        if (host != null && port != -1) {
            return Pair(host, port)
        }
        return null
    }
}
