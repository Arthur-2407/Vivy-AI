package com.vivy.node.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.vivy.node.connection.HubConnectionManager
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject
import org.json.JSONArray

data class ChatHistoryItem(val sender: String, val text: String, val timestamp: Long? = null)

@Composable
fun ChatScreen(connectionManager: HubConnectionManager) {
    val coroutineScope = rememberCoroutineScope()
    var messages by remember { mutableStateOf<List<ChatHistoryItem>>(emptyList()) }
    var inputText by remember { mutableStateOf("") }

    // Poll for history
    LaunchedEffect(Unit) {
        while (true) {
            try {
                val response = connectionManager.requestCapability("conversation.history", JSONObject())
                if (response.optString("status") != "error") {
                    // Handle array wrapping
                    val arr = response.optJSONArray("history") ?: response.optJSONArray("data")
                    if (arr != null) {
                        val parsed = mutableListOf<ChatHistoryItem>()
                        for (i in 0 until arr.length()) {
                            val obj = arr.optJSONObject(i) ?: continue
                            parsed.add(ChatHistoryItem(
                                sender = obj.optString("sender", "unknown"),
                                text = obj.optString("text", ""),
                                timestamp = if (obj.has("timestamp")) obj.optLong("timestamp") else null
                            ))
                        }
                        messages = parsed
                    }
                }
            } catch (e: Exception) {
                // Ignore for now
            }
            delay(2000)
        }
    }

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text("Conversational Link", style = MaterialTheme.typography.headlineMedium)
        Spacer(Modifier.height(8.dp))

        LazyColumn(modifier = Modifier.weight(1f)) {
            items(messages) { msg ->
                val alignment = if (msg.sender == "user") Alignment.End else Alignment.Start
                val color = if (msg.sender == "user") MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.secondaryContainer
                Column(
                    modifier = Modifier.fillMaxWidth().padding(4.dp),
                    horizontalAlignment = alignment
                ) {
                    Surface(
                        color = color,
                        shape = MaterialTheme.shapes.medium
                    ) {
                        Text(
                            text = msg.text,
                            modifier = Modifier.padding(12.dp)
                        )
                    }
                }
            }
        }

        Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(
                value = inputText,
                onValueChange = { inputText = it },
                modifier = Modifier.weight(1f),
                label = { Text("Message") }
            )
            Spacer(Modifier.width(8.dp))
            Button(onClick = {
                val text = inputText
                if (text.isNotBlank()) {
                    inputText = ""
                    val msgObj = ChatHistoryItem("user", text, System.currentTimeMillis())
                    messages = messages + msgObj
                    coroutineScope.launch {
                        try {
                            val req = JSONObject().apply {
                                put("message", text)
                            }
                            connectionManager.requestCapability("conversation.chat", req)
                        } catch (e: Exception) {
                            messages = messages + ChatHistoryItem("system", "Error: ${e.message}", System.currentTimeMillis())
                        }
                    }
                }
            }) {
                Text("Send")
            }
        }
    }
}
