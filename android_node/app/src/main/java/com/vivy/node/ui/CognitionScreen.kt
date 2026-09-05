package com.vivy.node.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.vivy.node.connection.HubConnectionManager
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject

@Composable
fun CognitionScreen(connectionManager: HubConnectionManager) {
    var cognitiveState by remember { mutableStateOf<JSONObject?>(null) }
    var memoryState by remember { mutableStateOf<JSONObject?>(null) }

    // Poll for state
    LaunchedEffect(Unit) {
        while (true) {
            try {
                val cogResp = connectionManager.requestCapability("cognition.state", JSONObject())
                if (cogResp.optString("status") != "error") {
                    cognitiveState = cogResp.optJSONObject("payload")
                }
                
                val memResp = connectionManager.requestCapability("memory.read", JSONObject())
                if (memResp.optString("status") != "error") {
                    memoryState = memResp.optJSONObject("payload")
                }
            } catch (e: Exception) {
                // Ignore
            }
            delay(2000)
        }
    }

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text("Cognitive Architecture", style = MaterialTheme.typography.headlineMedium)
        Spacer(Modifier.height(16.dp))

        LazyColumn(modifier = Modifier.weight(1f)) {
            item {
                if (cognitiveState != null) {
                    val state = cognitiveState!!
                    val emotion = state.optJSONObject("emotion")
                    val affection = state.optJSONObject("affection")
                    val circadian = state.optJSONObject("circadian")
                    
                    Card(modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp)) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Text("Mode: ${state.optString("current_mode", "N/A")}", style = MaterialTheme.typography.titleMedium)
                            Text("Primary Emotion: ${emotion?.optString("primary", "N/A")}")
                            Text("Affection Level: ${affection?.optDouble("level", 0.0)} (${affection?.optString("stage_label", "N/A")})")
                            Text("Circadian Phase: ${circadian?.optString("phase", "N/A")} (Energy: ${circadian?.optDouble("energy", 0.0)})")
                        }
                    }
                }
            }
            item {
                if (memoryState != null) {
                    val mem = memoryState!!
                    val facts = mem.optJSONObject("facts") ?: JSONObject()
                    val episodes = mem.optJSONArray("recent_episodes") ?: org.json.JSONArray()
                    val symptoms = mem.optJSONArray("symptoms") ?: org.json.JSONArray()
                    
                    Card(modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Text("Memory Dashboard", style = MaterialTheme.typography.titleMedium)
                            Spacer(Modifier.height(8.dp))
                            Text("Topic: ${mem.optString("topic", "N/A")}")
                            Spacer(Modifier.height(8.dp))
                            Text("Facts Stored: ${facts.length()}")
                            Spacer(Modifier.height(8.dp))
                            Text("Recent Episodes: ${episodes.length()}")
                            Spacer(Modifier.height(8.dp))
                            Text("Active Symptoms: ${symptoms.length()}")
                        }
                    }
                }
            }
        }
    }
}
