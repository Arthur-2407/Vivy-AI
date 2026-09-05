package com.vivy.node.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vivy.node.connection.HubConnectionManager
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject

private val Purple = Color(0xFF7C3AED)
private val Pink = Color(0xFFEC4899)
private val Dark = Color(0xFF0D0D1A)
private val Card = Color(0xFF13132A)
private val Border = Color(0xFF2A2A4A)

@Composable
fun VoiceCloningScreen(connectionManager: HubConnectionManager) {
    var trainingStatus by remember { mutableStateOf<JSONObject?>(null) }
    var error by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    // Poll training status
    LaunchedEffect(Unit) {
        while (true) {
            try {
                val response = connectionManager.requestCapability("voice.training_status", JSONObject())
                if (response.optString("status") != "error") {
                    trainingStatus = response.optJSONObject("payload")
                } else {
                    error = response.optJSONObject("payload")?.optString("error") ?: "Could not fetch status"
                }
            } catch (e: Exception) { 
                error = e.message ?: "Could not fetch status"
            }
            delay(3000)
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().background(Dark).padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            "Voice Cloning",
            fontSize = 22.sp, fontWeight = FontWeight.Bold, color = Pink,
            modifier = Modifier.align(Alignment.Start)
        )
        Text(
            "Train RVC voice models on the primary host",
            fontSize = 12.sp, color = Color(0xFF64748B),
            modifier = Modifier.align(Alignment.Start).padding(bottom = 32.dp)
        )

        Card(
            colors = CardDefaults.cardColors(containerColor = Card),
            modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp)
        ) {
            Column(
                modifier = Modifier.padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Icon(Icons.Filled.Build, contentDescription = null, tint = Purple, modifier = Modifier.size(48.dp))
                Spacer(Modifier.height(16.dp))
                
                trainingStatus?.let { ts ->
                    val status = ts.optString("status", "idle")
                    if (status != "idle") {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Filled.Settings, contentDescription = null,
                                tint = Purple, modifier = Modifier.size(18.dp))
                            Spacer(Modifier.width(8.dp))
                            Text("Training Active", color = Purple, fontWeight = FontWeight.SemiBold)
                        }
                        Spacer(Modifier.height(8.dp))
                        Text("Status: $status", color = Color.White, fontSize = 13.sp)
                        if (ts.has("progress")) {
                            val prog = ts.optDouble("progress", 0.0)
                            Spacer(Modifier.height(6.dp))
                            LinearProgressIndicator(
                                progress = (prog / 100.0).toFloat(),
                                modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(4.dp)),
                                color = Purple, trackColor = Border
                            )
                            val epoch = ts.optInt("epoch", 0)
                            val totalEpochs = ts.optInt("total_epochs", 150)
                            Text("$epoch/$totalEpochs epochs • ${prog.toInt()}%",
                                color = Color(0xFF94A3B8), fontSize = 11.sp, modifier = Modifier.padding(top = 4.dp))
                        }
                    } else {
                        Text("Host GPU is idle. Ready to train.", color = Color.White, fontSize = 14.sp, textAlign = TextAlign.Center)
                    }
                } ?: run {
                    if (error.isNotEmpty()) {
                        Text("Hub Unreachable / Capability Unavailable:\n$error", color = Color(0xFFEF4444), fontSize = 13.sp, textAlign = TextAlign.Center)
                    } else {
                        CircularProgressIndicator(color = Purple, modifier = Modifier.size(24.dp))
                    }
                }
                
                Spacer(Modifier.height(24.dp))
                
                Button(
                    onClick = {
                        scope.launch {
                            try {
                                val req = JSONObject().apply {
                                    put("identity_name", "New Voice Model")
                                    put("audio_path", "placeholder")
                                    put("epochs", 150)
                                }
                                val response = connectionManager.requestCapability("voice.train", req)
                                val status = response.optString("status")
                                if (status == "error") {
                                    val payload = response.optJSONObject("payload")
                                    error = payload?.optString("error") ?: "Provider unavailable."
                                }
                            } catch (e: Exception) {
                                error = e.message ?: "Failed to dispatch training request."
                            }
                        }
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = Purple),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text("Start Training (Placeholder)", color = Color.White)
                }
            }
        }
    }
}
