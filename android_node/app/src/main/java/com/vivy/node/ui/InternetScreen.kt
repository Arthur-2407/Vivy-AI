package com.vivy.node.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vivy.node.connection.HubConnectionManager
import kotlinx.coroutines.launch
import org.json.JSONObject

private val Purple = Color(0xFF7C3AED)
private val Dark = Color(0xFF0D0D1A)
private val Card = Color(0xFF13132A)

data class SearchResult(val title: String?, val url: String?, val snippet: String?)

@OptIn(androidx.compose.ui.ExperimentalComposeUiApi::class)
@Composable
fun InternetScreen(connectionManager: HubConnectionManager) {
    val scope = rememberCoroutineScope()
    var query by remember { mutableStateOf("") }
    var results by remember { mutableStateOf<List<SearchResult>>(emptyList()) }
    var isSearching by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var netStatus by remember { mutableStateOf<JSONObject?>(null) }
    val keyboardController = LocalSoftwareKeyboardController.current

    LaunchedEffect(Unit) {
        try {
            val resp = connectionManager.requestCapability("internet.status", JSONObject())
            if (resp.optString("status") != "error") {
                netStatus = resp.optJSONObject("payload")
            }
        } catch (e: Exception) { /* non-fatal */ }
    }

    fun doSearch() {
        if (query.isBlank()) return
        scope.launch {
            isSearching = true
            error = ""
            results = emptyList()
            keyboardController?.hide()
            try {
                val req = JSONObject().apply { put("query", query) }
                val resp = connectionManager.requestCapability("internet.search", req)
                if (resp.optString("status") != "error") {
                    val payload = resp.optJSONObject("payload")
                    val arr = payload?.optJSONArray("results") ?: org.json.JSONArray()
                    val parsed = mutableListOf<SearchResult>()
                    for (i in 0 until arr.length()) {
                        val obj = arr.optJSONObject(i) ?: continue
                        parsed.add(SearchResult(
                            title = obj.optString("title"),
                            url = obj.optString("url"),
                            snippet = obj.optString("snippet")
                        ))
                    }
                    results = parsed
                    if (results.isEmpty()) error = "No results found."
                } else {
                    error = resp.optJSONObject("payload")?.optString("error") ?: "Search failed."
                }
            } catch (e: Exception) {
                error = "Search failed: ${e.message}"
            } finally {
                isSearching = false
            }
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().background(Dark).padding(16.dp)
    ) {
        Text("Internet Search", fontSize = 22.sp, fontWeight = FontWeight.Bold, color = Purple)
        Text(
            "Privacy-first • DuckDuckGo + Wikipedia",
            fontSize = 12.sp, color = Color(0xFF64748B), modifier = Modifier.padding(bottom = 16.dp)
        )

        // Net status
        val online = netStatus?.optString("status") == "online" ||
                netStatus?.optString("network_state")?.contains("online", ignoreCase = true) == true
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(bottom = 12.dp)) {
            Icon(
                if (online) Icons.Filled.CheckCircle else Icons.Filled.Warning,
                contentDescription = null,
                tint = if (online) Color(0xFF22C55E) else Color(0xFFF59E0B),
                modifier = Modifier.size(16.dp)
            )
            Spacer(Modifier.width(6.dp))
            Text(if (online) "Online" else "Offline", color = Color(0xFF94A3B8), fontSize = 12.sp)
        }

        // Search bar
        OutlinedTextField(
            value = query,
            onValueChange = { query = it },
            placeholder = { Text("Ask Vivy anything...", color = Color(0xFF64748B)) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { doSearch() }),
            trailingIcon = {
                if (isSearching) {
                    CircularProgressIndicator(modifier = Modifier.size(20.dp), color = Purple, strokeWidth = 2.dp)
                } else {
                    IconButton(onClick = { doSearch() }) {
                        Icon(Icons.Filled.Search, contentDescription = "Search", tint = Purple)
                    }
                }
            },
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = Purple, unfocusedBorderColor = Color(0xFF2A2A4A),
                focusedTextColor = Color.White, unfocusedTextColor = Color.White,
                cursorColor = Purple
            ),
            modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp)
        )

        if (error.isNotEmpty()) {
            Text(error, color = Color(0xFFEF4444), fontSize = 13.sp, modifier = Modifier.padding(bottom = 8.dp))
        }

        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(results) { result ->
                SearchResultCard(result)
            }
        }
    }
}

@Composable
private fun SearchResultCard(result: SearchResult) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Card),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            result.title?.let {
                Text(it, color = Color.White, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                Spacer(Modifier.height(4.dp))
            }
            result.snippet?.let {
                Text(it, color = Color(0xFF94A3B8), fontSize = 12.sp, lineHeight = 18.sp)
                Spacer(Modifier.height(4.dp))
            }
            result.url?.let {
                Text(it, color = Purple, fontSize = 11.sp, maxLines = 1)
            }
        }
    }
}
