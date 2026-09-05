package com.vivy.node.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vivy.node.connection.HubConnectionManager
import kotlinx.coroutines.delay
import org.json.JSONObject

private val Purple = Color(0xFF7C3AED)
private val Dark = Color(0xFF0D0D1A)
private val Card = Color(0xFF13132A)

data class HubNode(
    val device_id: String, val platform: String?, val trust_level: String?,
    val camera: Boolean?, val mic: Boolean?, val gps: Boolean?,
    val battery_pct: Double?, val latency_ms: Double?, val app_version: String?
)

@Composable
fun DevicesScreen(connectionManager: HubConnectionManager) {
    var nodes by remember { mutableStateOf<List<HubNode>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf("") }

    LaunchedEffect(Unit) {
        while (true) {
            try {
                val resp = connectionManager.requestCapability("hub.devices", JSONObject())
                if (resp.optString("status") != "error") {
                    val payload = resp.optJSONObject("payload")
                    val arr = payload?.optJSONArray("nodes") ?: org.json.JSONArray()
                    val parsed = mutableListOf<HubNode>()
                    for (i in 0 until arr.length()) {
                        val obj = arr.optJSONObject(i) ?: continue
                        parsed.add(HubNode(
                            device_id = obj.optString("device_id", "unknown"),
                            platform = obj.optString("platform"),
                            trust_level = obj.optString("trust_level"),
                            camera = if (obj.has("camera")) obj.optBoolean("camera") else null,
                            mic = if (obj.has("mic")) obj.optBoolean("mic") else null,
                            gps = if (obj.has("gps")) obj.optBoolean("gps") else null,
                            battery_pct = if (obj.has("battery_pct")) obj.optDouble("battery_pct") else null,
                            latency_ms = if (obj.has("latency_ms")) obj.optDouble("latency_ms") else null,
                            app_version = obj.optString("app_version")
                        ))
                    }
                    nodes = parsed
                    error = ""
                } else {
                    error = resp.optJSONObject("payload")?.optString("error") ?: "Failed to load nodes"
                }
            } catch (e: Exception) {
                error = e.message ?: "Failed to load nodes"
            } finally {
                isLoading = false
            }
            delay(5000)
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().background(Dark).padding(16.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Ecosystem Nodes", fontSize = 22.sp, fontWeight = FontWeight.Bold, color = Purple)
            Spacer(Modifier.weight(1f))
            Text("${nodes.size}", color = Color(0xFF64748B), fontSize = 13.sp)
        }
        Text("All devices connected to this Vivy Hub",
            fontSize = 12.sp, color = Color(0xFF64748B), modifier = Modifier.padding(bottom = 16.dp))

        if (error.isNotEmpty()) {
            Text(error, color = Color(0xFFEF4444), fontSize = 13.sp)
        }

        if (isLoading) {
            CircularProgressIndicator(color = Purple, modifier = Modifier.align(Alignment.CenterHorizontally))
        } else if (nodes.isEmpty()) {
            Text("No other nodes connected.", color = Color(0xFF64748B), fontSize = 13.sp)
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(nodes) { node ->
                    NodeCard(node)
                }
            }
        }
    }
}

@Composable
private fun NodeCard(node: HubNode) {
    val platformIcon = when (node.platform?.lowercase()) {
        "android", "ios" -> Icons.Filled.Phone
        "windows", "linux" -> Icons.Filled.Home
        else -> Icons.Filled.Build
    }
    val trustColor = when (node.trust_level) {
        "FULLY_AUTHORIZED", "AUTHENTICATED" -> Color(0xFF22C55E)
        "PAIRED" -> Color(0xFFF59E0B)
        else -> Color(0xFF64748B)
    }

    Card(colors = CardDefaults.cardColors(containerColor = Card), modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier.size(36.dp).clip(CircleShape)
                        .background(Purple.copy(alpha = 0.15f)),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(platformIcon, contentDescription = null, tint = Purple, modifier = Modifier.size(20.dp))
                }
                Spacer(Modifier.width(10.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(node.device_id, color = Color.White, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                    Text(node.platform ?: "unknown", color = Color(0xFF64748B), fontSize = 11.sp)
                }
                Box(
                    modifier = Modifier.size(8.dp).clip(CircleShape).background(trustColor)
                )
            }
            Spacer(Modifier.height(10.dp))
            // Sensor matrix
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                SensorBadge("CAM", node.camera == true)
                SensorBadge("MIC", node.mic == true)
                SensorBadge("GPS", node.gps == true)
                node.battery_pct?.let { batt ->
                    SensorBadge("${batt.toInt()}%", batt > 20)
                }
                node.app_version?.let {
                    if (it != "unknown") SensorBadge("v$it", true)
                }
            }
        }
    }
}

@Composable
private fun SensorBadge(label: String, active: Boolean) {
    Surface(
        color = if (active) Purple.copy(alpha = 0.15f) else Color(0xFF1E1E3A),
        shape = MaterialTheme.shapes.small
    ) {
        Text(
            label, color = if (active) Purple else Color(0xFF4A4A6A),
            fontSize = 10.sp, fontWeight = FontWeight.Medium,
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 3.dp)
        )
    }
}
