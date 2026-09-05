package com.vivy.node.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vivy.node.connection.HubConnectionManager
import org.json.JSONObject

private val Purple = Color(0xFF7C3AED)
private val Dark = Color(0xFF0D0D1A)
private val Card = Color(0xFF13132A)

@Composable
fun EvolutionScreen(connectionManager: HubConnectionManager) {
    var status by remember { mutableStateOf<Map<String, Any>?>(null) }
    var error by remember { mutableStateOf("") }

    LaunchedEffect(Unit) {
        try {
            val resp = connectionManager.requestCapability("evolution.status", JSONObject())
            if (resp.optString("status") != "error") {
                val payload = resp.optJSONObject("payload") ?: JSONObject()
                status = mapOf(
                    "status" to payload.optString("status", "unknown"),
                    "enabled" to payload.optBoolean("enabled", false).toString(),
                    "last_evolution" to payload.optString("last_evolution", "never"),
                    "pending_proposals" to payload.optInt("pending_proposals", 0).toString()
                )
            } else {
                error = resp.optJSONObject("payload")?.optString("error") ?: "Failed to load evolution status"
            }
        } catch (e: Exception) {
            error = e.message ?: "Failed to load evolution status"
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().background(Dark).padding(16.dp)
    ) {
        Text("Self-Evolution", fontSize = 22.sp, fontWeight = FontWeight.Bold, color = Purple)
        Text("Vivy's governed self-improvement engine",
            fontSize = 12.sp, color = Color(0xFF64748B), modifier = Modifier.padding(bottom = 16.dp))

        if (error.isNotEmpty()) {
            Text(error, color = Color(0xFFEF4444), fontSize = 13.sp)
        } else if (status == null) {
            CircularProgressIndicator(color = Purple, modifier = Modifier.align(Alignment.CenterHorizontally))
        } else {
            Card(colors = CardDefaults.cardColors(containerColor = Card), modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp)) {
                    status?.forEach { (key, value) ->
                        Row(
                            modifier = Modifier.padding(vertical = 5.dp).fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(key.replace("_", " ").replaceFirstChar { it.uppercase() },
                                color = Color(0xFF94A3B8), fontSize = 13.sp)
                            Text(value.toString(), color = Color.White, fontSize = 13.sp,
                                fontWeight = FontWeight.Medium)
                        }
                        Divider(color = Color(0xFF2A2A4A), thickness = 0.5.dp)
                    }
                }
            }
            Spacer(Modifier.height(16.dp))
            Card(colors = CardDefaults.cardColors(containerColor = Card), modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("Governance Policy", color = Color(0xFF94A3B8), fontSize = 11.sp,
                        modifier = Modifier.padding(bottom = 8.dp))
                    Text("Parameter learning: Auto-approved",
                        color = Color(0xFF22C55E), fontSize = 13.sp)
                    Text("Strategy learning: Review required",
                        color = Color(0xFFF59E0B), fontSize = 13.sp)
                    Text("Code evolution: Explicit approval required",
                        color = Color(0xFFEF4444), fontSize = 13.sp)
                }
            }
        }
    }
}

@Composable
fun SettingsScreen(connectionManager: HubConnectionManager) {
    var config by remember { mutableStateOf<JSONObject?>(null) }
    var error by remember { mutableStateOf("") }

    LaunchedEffect(Unit) {
        try {
            val resp = connectionManager.requestCapability("config.read", JSONObject())
            if (resp.optString("status") != "error") {
                config = resp.optJSONObject("payload")
            } else {
                error = resp.optJSONObject("payload")?.optString("error") ?: "Config unavailable"
            }
        } catch (e: Exception) {
            error = "Config unavailable: ${e.message}"
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().background(Dark).padding(16.dp)
    ) {
        Text("Settings", fontSize = 22.sp, fontWeight = FontWeight.Bold, color = Purple)
        Text("Primary host configuration (read-only view)",
            fontSize = 12.sp, color = Color(0xFF64748B), modifier = Modifier.padding(bottom = 16.dp))

        if (error.isNotEmpty()) {
            Text(error, color = Color(0xFFEF4444), fontSize = 13.sp)
        }

        val sections = listOf("models", "pipeline", "hub", "voice", "perception", "resources")
        sections.forEach { section ->
            if (config != null && config!!.has(section)) {
                val sectionData = config!!.optJSONObject(section)
                if (sectionData != null) {
                    Text(section.uppercase(), color = Color(0xFF64748B), fontSize = 10.sp,
                        fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 12.dp, bottom = 4.dp))
                    Card(colors = CardDefaults.cardColors(containerColor = Card), modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.padding(12.dp)) {
                            val keys = sectionData.keys()
                            var count = 0
                            while (keys.hasNext() && count < 6) {
                                val k = keys.next()
                                val v = sectionData.opt(k)
                                Row(
                                    modifier = Modifier.padding(vertical = 3.dp).fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Text(k.toString(), color = Color(0xFF94A3B8), fontSize = 12.sp)
                                    Text(v.toString().take(30), color = Color.White, fontSize = 12.sp)
                                }
                                count++
                            }
                        }
                    }
                }
            }
        }
    }
}
