package com.vivy.node.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.vivy.node.connection.HubConnectionManager
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject

data class ActionItem(val action_id: String, val intent: String, val risk_level: String, val state: String)

@Composable
fun ActionsScreen(connectionManager: HubConnectionManager) {
    val coroutineScope = rememberCoroutineScope()
    var actions by remember { mutableStateOf<List<ActionItem>>(emptyList()) }

    // Poll for pending actions
    LaunchedEffect(Unit) {
        while (true) {
            try {
                val resp = connectionManager.requestCapability("action.request", JSONObject())
                if (resp.optString("status") != "error") {
                    val payload = resp.optJSONObject("payload")
                    val actionsArr = payload?.optJSONArray("actions") ?: org.json.JSONArray()
                    val parsed = mutableListOf<ActionItem>()
                    for (i in 0 until actionsArr.length()) {
                        val obj = actionsArr.optJSONObject(i) ?: continue
                        if (obj.optString("state") == "pending_approval") {
                            parsed.add(ActionItem(
                                action_id = obj.optString("action_id"),
                                intent = obj.optString("intent"),
                                risk_level = obj.optString("risk_level"),
                                state = obj.optString("state")
                            ))
                        }
                    }
                    actions = parsed
                }
            } catch (e: Exception) {
                // Ignore
            }
            delay(2000)
        }
    }

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text("Pending Actions", style = MaterialTheme.typography.headlineMedium)
        Spacer(Modifier.height(16.dp))

        if (actions.isEmpty()) {
            Text("No pending actions requiring approval.")
        } else {
            LazyColumn(modifier = Modifier.weight(1f)) {
                items(actions) { action ->
                    Card(modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp)) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Text("Intent: ${action.intent}", style = MaterialTheme.typography.titleMedium)
                            Text("Risk Level: ${action.risk_level}")
                            Spacer(Modifier.height(8.dp))
                            Row(horizontalArrangement = Arrangement.End, modifier = Modifier.fillMaxWidth()) {
                                OutlinedButton(onClick = {
                                    coroutineScope.launch {
                                        try {
                                            val req = JSONObject().apply { put("action_id", action.action_id) }
                                            connectionManager.requestCapability("action.cancel", req)
                                        } catch (e: Exception) {}
                                    }
                                }) {
                                    Text("Deny")
                                }
                                Spacer(Modifier.width(8.dp))
                                Button(onClick = {
                                    coroutineScope.launch {
                                        try {
                                            val req = JSONObject().apply { put("action_id", action.action_id) }
                                            connectionManager.requestCapability("action.confirm", req)
                                        } catch (e: Exception) {}
                                    }
                                }) {
                                    Text("Approve")
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
